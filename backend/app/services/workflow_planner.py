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
from app.core.exceptions import ClarificationNeeded, PlannerError
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

STRICT FIELD CONSTRAINTS (must be followed exactly, no synonyms or alternatives):
- filter_rows "operator": MUST be one of exactly: "=", "!=", ">", ">=", "<", "<="
  Do NOT use: "equals", "eq", "greater_than", "gt", "lt", "gte", "lte", or any word form.
- group_by "agg": MUST be one of: "sum", "mean", "count", "min", "max"
- sort_values "ascending": MUST be a boolean — true (ascending) or false (descending). Do NOT use "order", "asc", "desc", or any string.

CLARIFICATION (use sparingly — only when genuinely required):
- If a critical parameter is missing AND cannot be reasonably inferred, you may request clarification instead of generating steps.
- To request clarification output EXACTLY: {{"needs_clarification": true, "question": "Your concise question here"}}
- Only request clarification when ALL of these are true:
  1. A specific column, numeric threshold, or operation target is required but not mentioned.
  2. It cannot be inferred from the request or dataset profile.
  3. Different answers would lead to materially different workflows.
- Do NOT request clarification for minor phrasing ambiguities or when a reasonable default exists.
- When asking, reference only column names from the dataset profile. Be concise and specific.
- Examples that warrant clarification: "group the data" (missing: group-by column and aggregation target), "filter the big orders" (missing: threshold value and column).
- Examples that do NOT warrant clarification: "show top rows" (use limit_rows with default 10), "remove bad data" (use remove_missing_values).

Supported step types:
{supported_transformations}

Dataset profile:
{dataset_profile}

Relevant docs (transformations, failure cases, correction guidance, workflow examples):
{retrieved_docs}
"""

_USER_PROMPT = """\
User request: {user_request}

Generate the workflow JSON.
"""


_SUPPORTED_STEP_TYPES = (
    "remove_missing_values, select_columns, filter_rows, "
    "group_by, sort_values, rename_columns, generate_summary, "
    "limit_rows, derive_column, date_extract, "
    "drop_columns, fill_missing_values"
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
        doc_type = doc.doc_type

        if doc_type == "transformation":
            label = doc.type or doc.title
            params = ", ".join(
                f"{p['name']} ({'required' if p.get('required') else 'optional'})"
                for p in doc.parameters
            )
            example = json.dumps(doc.example, ensure_ascii=False) if doc.example else ""
            line = f"[STEP] {label}: {doc.description}"
            if params:
                line += f" | params: {params}"
            if example:
                line += f" | example: {example}"

        elif doc_type == "failure_case":
            line = f"[WARNING] {doc.title}: {doc.description}"
            if doc.planner_guidance:
                line += f" | guidance: {doc.planner_guidance}"

        elif doc_type == "correction_case":
            line = f"[CORRECTION] {doc.title}: {doc.description}"
            if doc.planner_guidance:
                line += f" | guidance: {doc.planner_guidance}"

        elif doc_type == "workflow_example":
            steps_preview = ""
            if isinstance(doc.example.get("steps"), list):
                step_types = [s.get("type", "?") for s in doc.example["steps"]]
                steps_preview = " → ".join(step_types)
            line = f"[EXAMPLE] {doc.title}: {doc.description}"
            if steps_preview:
                line += f" | steps: {steps_preview}"

        else:
            line = f"- {doc.title}: {doc.description}"

        parts.append(line)
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
    """Parse LLM output into a list of WorkflowStep.

    Raises ClarificationNeeded when the LLM requests more information.
    Raises PlannerError when the output is invalid or empty.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise PlannerError(f"LLM returned invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise PlannerError("LLM response must be a JSON object.")

    # Clarification path: LLM decided it needs more information.
    if data.get("needs_clarification"):
        question = data.get("question", "Could you provide more details about your request?")
        raise ClarificationNeeded(question)

    if "steps" not in data:
        raise PlannerError("LLM response must be a JSON object with a 'steps' key.")

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
