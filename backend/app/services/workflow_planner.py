"""Workflow planner service.

Assembles a prompt from RAG context, calls the LLM with JSON-mode output,
and parses the response into a list of WorkflowStep.

The LLM is constrained to:
- Output only a JSON array of steps.
- Use only supported step types.
- Use only columns that exist in the dataset profile.

The planner never executes or validates — it only plans.
Validation is always performed by the validator before execution.
"""
import json
import logging

from openai import OpenAI

from app.core.config import settings
from app.core.exceptions import PlannerError
from app.models.rag import RAGContext
from app.models.workflow import WorkflowRequest, WorkflowStep

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the Workflow Planner for DataCopilot.

Your job is to convert the user's data-processing request into a JSON workflow.

Rules:
- Output only valid JSON.
- Output a JSON object with a single key "steps" whose value is an array of workflow steps.
- Use only the supported step types listed below.
- Do not invent column names. Use only columns from the dataset profile.
- Do not include explanations or comments in the JSON.
- If the request cannot be represented with the supported steps, return {{"steps": []}}.

Supported step types:
{supported_transformations}

Dataset profile:
{dataset_profile}

Relevant transformation docs:
{retrieved_docs}
"""

_USER_PROMPT = """\
User request: {user_request}

Generate the workflow JSON.
"""


_SUPPORTED_STEP_TYPES = (
    "remove_missing_values, select_columns, filter_rows, "
    "group_by, sort_values, rename_columns, generate_summary"
)


def _format_supported_transformations() -> str:
    return _SUPPORTED_STEP_TYPES


def _format_dataset_profile(ctx: RAGContext) -> str:
    ds = ctx.dataset_summary
    cols = ", ".join(
        f"{c['name']} ({c['dtype']}, {c['missing_count']} missing)"
        for c in ds.columns
    )
    return (
        f"filename: {ds.filename}, "
        f"rows: {ds.row_count}, "
        f"columns: [{cols}]"
    )


def _format_retrieved_docs(ctx: RAGContext) -> str:
    parts = []
    for doc in ctx.retrieved_docs:
        params = ", ".join(
            f"{p['name']} ({'required' if p.get('required') else 'optional'})"
            for p in doc.parameters
        )
        example = json.dumps(doc.example, ensure_ascii=False)
        parts.append(
            f"- {doc.type}: {doc.description}"
            + (f" | params: {params}" if params else "")
            + f" | example: {example}"
        )
    return "\n".join(parts) if parts else "none"


def _build_messages(query: str, ctx: RAGContext) -> list[dict]:
    system = _SYSTEM_PROMPT.format(
        supported_transformations=_format_supported_transformations(),
        dataset_profile=_format_dataset_profile(ctx),
        retrieved_docs=_format_retrieved_docs(ctx),
    )
    user = _USER_PROMPT.format(user_request=query)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_steps(raw_json: str) -> list[WorkflowStep]:
    """Parse LLM output into a list of WorkflowStep, raising PlannerError on failure."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise PlannerError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict) or "steps" not in data:
        raise PlannerError(
            "LLM response must be a JSON object with a 'steps' key."
        )

    steps_raw = data["steps"]
    if not isinstance(steps_raw, list):
        raise PlannerError("'steps' must be a JSON array.")

    if len(steps_raw) == 0:
        raise PlannerError(
            "The request cannot be handled with the supported transformations."
        )

    try:
        request = WorkflowRequest(dataset_id="__parse_only__", steps=steps_raw)
    except Exception as exc:
        raise PlannerError(f"LLM workflow contains invalid step structure: {exc}") from exc

    return request.steps


def plan(query: str, ctx: RAGContext, client: OpenAI | None = None) -> list[WorkflowStep]:
    """Call the LLM to produce a workflow for the given query and RAG context.

    Pass `client` explicitly in tests to inject a mock.
    Raises PlannerError when the LLM output cannot be parsed or is empty.
    """
    if not settings.llm_api_key:
        raise PlannerError(
            "LLM API key is not configured. Set LLM_API_KEY in your .env file."
        )

    if client is None:
        client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )

    messages = _build_messages(query, ctx)
    logger.info("Calling LLM planner model=%s query=%r", settings.llm_model, query)

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            max_completion_tokens=settings.llm_max_tokens,
            temperature=0,
        )
    except Exception as exc:
        raise PlannerError(f"LLM API call failed: {exc}") from exc

    try:
        raw = response.choices[0].message.content or ""
    except (IndexError, AttributeError) as exc:
        raise PlannerError(f"Planner received unexpected response structure: {exc}") from exc

    logger.info("LLM planner raw response: %s", raw)

    steps = _parse_steps(raw)
    logger.info("Planner produced %d steps", len(steps))
    return steps
