"""Tool selector — deterministic layer that ranks candidate tools from retrieved docs.

Uses doc retrieval scores plus an intent-type bonus. No LLM calls.
"""
from app.agent.planning.pipeline_models import ToolSelectionResult
from app.agent.task_intake.intent import ParsedTaskIntent
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
    """Rank and return candidate tools from retrieved docs based on intent.

    Tools are ordered by (base retrieval score + intent bonus), highest first.
    Preserves raw scores for downstream inspection.
    """
    scores = _score_tools(intent, retrieved_docs)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    candidate_tools = [tool for tool, _ in ordered]

    return ToolSelectionResult(
        intent=intent.intent,
        candidate_tools=candidate_tools,
        selected_tool=candidate_tools[0] if candidate_tools else None,
        scores={tool: round(score, 4) for tool, score in scores.items()},
    )


def _score_tools(
    intent: ParsedTaskIntent,
    retrieved_docs: list[RetrievedDoc],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for doc in retrieved_docs:
        if doc.doc_type != "transformation" or not doc.type:
            continue
        tool_type = doc.type
        base = float(doc.score)
        bonus = _intent_bonus(intent.intent, tool_type)
        scores[tool_type] = base + bonus
    return scores


def _intent_bonus(intent_type: str, tool_type: str) -> float:
    if intent_type == "inspect_dataset" and tool_type in _INSPECT_TOOLS:
        return _INTENT_BONUS
    if intent_type == "transform_dataset" and tool_type in _TRANSFORM_TOOLS:
        return _INTENT_BONUS
    return 0.0
