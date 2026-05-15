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
import re
from dataclasses import dataclass

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.exceptions import ClarificationNeeded, PlannerError
from app.models.rag import RAGContext
from app.models.workflow_steps import WorkflowStep
from app.models.workflow_transport import WorkflowRequest
from app.agent.tool_selection import registry

logger = logging.getLogger(__name__)
last_raw_output: str | None = None


@dataclass(frozen=True)
class PlannerResult:
    steps: list[WorkflowStep]
    raw_output: str

_SYSTEM_PROMPT = """\
You are the Workflow Planner for DataCopilot.

Your job is to convert the user's data-processing request into a JSON workflow.

Rules:
- Output only valid JSON.
- Output a JSON object with a single key "steps" whose value is an array of workflow steps.
- Use only the supported step types listed below.
- Do not invent column names. Use only columns from the dataset profile.
- Do not include explanations or comments in the JSON.
- Do not add data-cleaning steps unless the user explicitly asks for cleaning,
  dropping, removing, or filling missing values. For example, "Group by region
  and sum amount" should be only a group_by step, even if amount has missing values.
- If the request cannot be represented with the supported steps, return {{"steps": []}}.
- If the request references a column that does NOT exist in the dataset profile, return:
  {{"steps": [], "error_hint": "Column '<name>' does not exist in the dataset. Available columns: <comma-separated list from profile>. Did you mean '<closest column>'?"}}
  Always include the full list of available columns so the user knows what to choose from.

STRICT FIELD CONSTRAINTS (must be followed exactly, no synonyms or alternatives):
- filter_rows REQUIRED FIELDS — ALL THREE must always be present, never omit any:
    "column": the column name from the dataset profile to filter on (e.g. "sales", "region")
    "operator": MUST be one of exactly: "=", "!=", ">", ">=", "<", "<="
      Do NOT use: "equals", "eq", "greater_than", "gt", "lt", "gte", "lte", or any word form.
    "value": the comparison value (number or string)
  Chinese filter verbs always map to filter_rows — identify the column from the comparison token:
    "删除所有 X 低于 Y 的行"  → keep rows: {{"type":"filter_rows","column":"X","operator":">=","value":Y}}
    "只保留 X 是 Y 的数据"    → keep rows: {{"type":"filter_rows","column":"X","operator":"=","value":"Y"}}
    "过滤出 X 大于 Y 的行"    → keep rows: {{"type":"filter_rows","column":"X","operator":">","value":Y}}
- group_by "agg": MUST be one of: "sum", "mean", "count", "min", "max"
- sort_values "ascending": MUST be a boolean — true (ascending) or false (descending). Do NOT use "order", "asc", "desc", or any string.

CLARIFICATION — apply a structural test, not a list of examples:

Before generating steps, ask yourself:
  "Can I map this request to ONE specific sequence of supported transformations,
   or could a reasonable person interpret it as two or more DIFFERENT structures?"

- If ONE clear structure → generate it (use sensible defaults for missing numeric params).
- If TWO OR MORE plausible structures → ask for clarification.

To request clarification output EXACTLY: {{"needs_clarification": true, "question": "Your concise question here"}}

SIGNALS that indicate structural ambiguity (ask):
1. The verb is analytical/vague with no clear transformation target:
   "summarize", "analyse", "explore", "understand", "what's interesting about"
   → could mean group_by, sort+limit, generate_summary, or filter — ask which.
2. "top / best / highest / lowest / most / least [noun]" without a sort column:
   → implies ranking but no column given — ask which column to rank by.
   Exception: "top [N] rows" or "first [N] rows" — literal row slice, use limit_rows.
3. The operation could mean filter OR group OR sort depending on intent:
   "show sales by region" — filter to one region? group by region? ask which.
4. The filter condition uses vague or relative threshold language with no explicit number:
   "abnormally low/high", "unusually small/large", "too low/high", "extreme values",
   "异常低", "异常高", "过低", "过高", "偏低", "偏高", "特别低", "特别高"
   → the threshold is a business judgment — ask for the specific numeric value.
   Exception: if the query already contains an explicit number, use it directly.

SIGNALS that indicate clear intent (act, use defaults for missing numeric values):
1. The transformation type is explicit: "sort", "filter … where", "rename", "remove nulls",
   "fill missing", "group by [column]", "select columns", "show the first N rows".
   Chinese equivalents: "删除所有 X 低于/高于 Y", "只保留 X 是/大于/小于 Y", "过滤出 X 大于/小于 Y",
   "按 X 排序", "按 X 分组求 Y", "选择 X 列".
2. Only a numeric threshold or count is unspecified and a default is safe:
   "show top rows / first few rows" → limit_rows n=10
   "filter large orders" with a numeric column → ask the threshold (one clear op, one missing param).
3. Column name, operator, and approximate value are all present in the query.

When asking: name the specific missing information, reference column names from the profile,
and offer 2-3 concrete example answers to make it easy for the user to reply.

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


def _format_supported_transformations() -> str:
    return registry.supported_tools_prompt()


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


def _explicit_missing_column(query: str, ctx: RAGContext) -> str | None:
    """Return an explicitly referenced missing column, if present.

    This deterministic guard prevents the LLM from mapping a named missing
    column to a semantically similar existing column. Covers both English
    `where <col>` syntax and Chinese comparison patterns.
    """
    available = {c["name"] for c in ctx.dataset_summary.columns}
    available_lower = {c["name"].lower() for c in ctx.dataset_summary.columns}
    patterns = [
        r"\bwhere\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        # Chinese: <col> 大于/小于/等于/高于/低于/不等于 ... (identifier before comparison keyword)
        r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:大于等于|小于等于|大于|小于|等于|高于|低于|不等于)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            col = match.group(1)
            if col not in available and col.lower() not in available_lower:
                return col
    return None


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
        hint = data.get("error_hint", "")
        msg = hint if hint else "The request cannot be handled with the supported transformations."
        raise PlannerError(msg)

    try:
        request = WorkflowRequest(dataset_id="__parse_only__", steps=steps_raw)
    except ValidationError as exc:
        question = _missing_required_field_question(exc, steps_raw)
        if question:
            raise ClarificationNeeded(question) from exc
        raise PlannerError(f"LLM workflow contains invalid step structure: {exc}") from exc
    except Exception as exc:
        raise PlannerError(f"LLM workflow contains invalid step structure: {exc}") from exc

    return request.steps


def _missing_required_field_question(
    exc: ValidationError,
    steps_raw: list,
) -> str | None:
    missing_errors = [err for err in exc.errors() if err.get("type") == "missing"]
    if not missing_errors:
        return None

    first = missing_errors[0]
    loc = first.get("loc", ())
    field_name = str(loc[-1]) if loc else "a required field"
    step_index = _extract_step_index(loc)
    step_type = _extract_step_type(steps_raw, step_index)
    if step_type:
        return (
            f"The planned '{step_type}' step is missing required field '{field_name}'. "
            f"What value should I use for '{field_name}'?"
        )
    return (
        f"The planned workflow is missing required field '{field_name}'. "
        f"What value should I use for '{field_name}'?"
    )


def _extract_step_index(loc: tuple) -> int | None:
    for part in loc:
        if isinstance(part, int):
            return part
    return None


def _extract_step_type(steps_raw: list, step_index: int | None) -> str | None:
    if step_index is None or step_index >= len(steps_raw):
        return None
    step_raw = steps_raw[step_index]
    if isinstance(step_raw, dict):
        step_type = step_raw.get("type")
        return str(step_type) if step_type else None
    return None


def plan_with_trace(query: str, ctx: RAGContext, client: OpenAI | None = None) -> PlannerResult:
    """Call the LLM to produce a workflow for the given query and RAG context.

    Pass `client` explicitly in tests to inject a mock.
    Raises PlannerError when the LLM output cannot be parsed or is empty.
    """
    missing_col = _explicit_missing_column(query, ctx)
    if missing_col:
        available = ", ".join(c["name"] for c in ctx.dataset_summary.columns)
        raise PlannerError(
            f"Column '{missing_col}' does not exist in the dataset. "
            f"Available columns: {available}."
        )

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
    global last_raw_output
    last_raw_output = raw

    steps = _parse_steps(raw)
    logger.info("Planner produced %d steps", len(steps))
    return PlannerResult(steps=steps, raw_output=raw)


def plan(query: str, ctx: RAGContext, client: OpenAI | None = None) -> list[WorkflowStep]:
    """Return only workflow steps for callers/tests that do not need trace data."""
    return plan_with_trace(query=query, ctx=ctx, client=client).steps
