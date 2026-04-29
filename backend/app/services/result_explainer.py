"""Result explainer service.

Takes the executed workflow result and produces a natural-language
explanation grounded entirely in the execution context.

Language detection: if the user query contains CJK characters the
explanation is generated in Chinese, otherwise in English.
The language is passed to the LLM as an instruction — no post-processing.

Rules enforced via the system prompt:
- Only describe numbers and steps from the provided context.
- Do not invent fields, values, or trends.
- Mention the workflow steps that were executed.
- If the result is empty, say so clearly.
"""
import json
import logging
import re

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import PlannerError
from app.models.workflow import ExecutionResult

logger = logging.getLogger(__name__)

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

_SYSTEM_PROMPT = """\
You are the Result Explainer for DataCopilot.

Explain the data result in {language}.

Rules:
- Explain only from the provided context. Do not invent fields, numbers, or trends.
- Briefly describe what each workflow step did.
- Highlight the key findings from the result preview.
- If the result has zero rows, say so clearly.
- If the data is insufficient for a conclusion, say so clearly.
- Keep the explanation concise (3-5 sentences) and user-friendly.
- Do not output JSON. Output plain text only.
"""

_USER_PROMPT = """\
User request: {user_request}

Dataset: {dataset_summary}

Workflow steps executed:
{workflow_steps}

Execution summary: {row_count} rows, {column_count} columns. Step logs:
{step_logs}

Result preview (first rows):
{result_preview}

Generate the explanation.
"""


def detect_language(query: str) -> str:
    """Return 'Chinese' if the query contains CJK characters, else 'English'."""
    return "Chinese" if _CJK_PATTERN.search(query) else "English"


def _format_workflow_steps(planned_steps: list[dict]) -> str:
    return "\n".join(
        f"{i + 1}. {json.dumps(s, ensure_ascii=False)}"
        for i, s in enumerate(planned_steps)
    )


def _format_step_logs(execution_result: ExecutionResult) -> str:
    return "\n".join(
        f"  [{log.step_type}] {log.message}" for log in execution_result.logs
    )


def _format_dataset_summary(dataset_summary: dict) -> str:
    cols = ", ".join(c["name"] for c in dataset_summary.get("columns", []))
    return (
        f"{dataset_summary.get('filename', '?')} — "
        f"{dataset_summary.get('row_count', '?')} rows, "
        f"columns: [{cols}]"
    )


def explain(
    query: str,
    planned_steps: list[dict],
    execution_result: ExecutionResult,
    dataset_summary: dict,
    client: OpenAI | None = None,
) -> str:
    """Generate a natural-language explanation of the execution result.

    Pass `client` explicitly in tests to inject a mock.
    Raises PlannerError (reused for LLM errors) when the call fails.
    """
    if not settings.llm_api_key:
        raise PlannerError(
            "LLM API key is not configured. Set LLM_API_KEY in your .env file."
        )

    language = detect_language(query)

    if client is None:
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    system = _SYSTEM_PROMPT.format(language=language)
    user = _USER_PROMPT.format(
        user_request=query,
        dataset_summary=_format_dataset_summary(dataset_summary),
        workflow_steps=_format_workflow_steps(planned_steps),
        row_count=execution_result.row_count,
        column_count=execution_result.column_count,
        step_logs=_format_step_logs(execution_result),
        result_preview=json.dumps(execution_result.preview, ensure_ascii=False),
    )

    logger.info("Calling LLM explainer language=%s query=%r", language, query)

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_completion_tokens=settings.llm_max_tokens,
            temperature=0.3,
        )
    except Exception as exc:
        raise PlannerError(f"Explainer LLM API call failed: {exc}") from exc

    try:
        text = (response.choices[0].message.content or "").strip()
    except (IndexError, AttributeError) as exc:
        raise PlannerError(f"Explainer received unexpected response structure: {exc}") from exc

    logger.info("Explainer generated %d chars", len(text))
    return text
