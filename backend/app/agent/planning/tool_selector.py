"""Tool selector — deterministic layer that ranks candidate tools from retrieved docs.

Derives intent from the composition of retrieved doc types, then uses that
derived intent to apply a scoring bonus. No LLM calls, no separate keyword list.
"""
from app.agent.planning.pipeline_models import ToolSelectionResult
from app.agent.task_intake.intent import ParsedTaskIntent, TaskIntentType
from app.models.rag import RetrievedDoc

_INSPECT_TOOLS = {"generate_summary", "select_columns", "limit_rows"}
_TRANSFORM_TOOLS = {
    "filter_rows", "group_by", "sort_values", "rename_columns",
    "remove_missing_values", "fill_missing_values", "drop_columns",
    "derive_column", "date_extract", "date_diff", "bin_column",
    "cast_column", "deduplicate_rows", "replace_values", "pivot_table",
    "normalize_text", "trim_text", "extract_text", "conditional_column",
}

_INTENT_BONUS = 0.5


def select_tools(
    intent: ParsedTaskIntent,
    retrieved_docs: list[RetrievedDoc],
) -> ToolSelectionResult:
    """Derive intent from retrieved doc types, then rank candidate tools.

    Intent is determined by which category (transform vs inspect) appears more
    frequently in the top-k docs. The derived intent is used to apply a scoring
    bonus to matching tools. Raw scores are preserved for downstream inspection.

    The ParsedTaskIntent argument carries candidate_columns and constraints from
    the query; its intent field is intentionally ignored here.
    """
    derived_intent = _derive_intent_from_docs(retrieved_docs)
    scores = _score_tools(derived_intent, retrieved_docs)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    candidate_tools = [tool for tool, _ in ordered]

    return ToolSelectionResult(
        intent=derived_intent,
        candidate_tools=candidate_tools,
        selected_tool=candidate_tools[0] if candidate_tools else None,
        scores={tool: round(score, 4) for tool, score in scores.items()},
    )


def _derive_intent_from_docs(docs: list[RetrievedDoc]) -> TaskIntentType:
    """Count transform vs inspect tools in retrieved docs to vote on intent.

    On a tie, transform_dataset wins because most user queries are data
    transformation requests. Returns 'unknown' only when no relevant docs exist.
    """
    transform_count = 0
    inspect_count = 0
    for doc in docs:
        if doc.doc_type != "transformation" or not doc.type:
            continue
        if doc.type in _TRANSFORM_TOOLS:
            transform_count += 1
        elif doc.type in _INSPECT_TOOLS:
            inspect_count += 1

    if transform_count == 0 and inspect_count == 0:
        return "unknown"
    if inspect_count > transform_count:
        return "inspect_dataset"
    return "transform_dataset"


def _score_tools(
    derived_intent: TaskIntentType,
    retrieved_docs: list[RetrievedDoc],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for doc in retrieved_docs:
        if doc.doc_type != "transformation" or not doc.type:
            continue
        tool_type = doc.type
        candidate = float(doc.score) + _intent_bonus(derived_intent, tool_type)
        # Keep the highest score when multiple docs reference the same tool type.
        if candidate > scores.get(tool_type, 0.0):
            scores[tool_type] = candidate
    return scores


def _intent_bonus(derived_intent: TaskIntentType, tool_type: str) -> float:
    if derived_intent == "inspect_dataset" and tool_type in _INSPECT_TOOLS:
        return _INTENT_BONUS
    if derived_intent == "transform_dataset" and tool_type in _TRANSFORM_TOOLS:
        return _INTENT_BONUS
    return 0.0
