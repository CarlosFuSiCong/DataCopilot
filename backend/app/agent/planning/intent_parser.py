"""Intent parser — deterministic layer that classifies query intent and extracts candidates.

Uses keyword matching and regex only. No LLM calls.
The old workflow_planner.plan() remains the fallback for full LLM-driven planning.
"""
import re

from app.agent.planning.pipeline_models import IntentParseResult
from app.agent.task_intake.intent import ParsedTaskIntent, TaskIntentType

_TRANSFORM_KEYWORDS = {
    # English
    "filter", "group", "sort", "select", "rename", "remove", "fill", "drop",
    "derive", "extract", "limit", "bin", "pivot", "deduplicate", "replace",
    "aggregate", "sum", "count", "mean", "average", "min", "max",
    # Chinese
    "过滤", "筛选", "分组", "排序", "选择", "统计", "汇总", "去重",
    "提取", "重命名", "删除", "填充", "限制",
}

_INSPECT_KEYWORDS = {
    # English
    "show", "describe", "preview", "display", "list", "what", "which", "how many",
    "summarize", "summary", "overview",
    # Chinese
    "显示", "展示", "描述", "有多少", "是什么", "概览", "摘要",
}

_CONSTRAINT_PATTERNS = [
    r"\bwhere\s+\S+\s*[><=!]+\s*\S+",
    r"\bif\s+\S+\s*[><=!]+\s*\S+",
    r"\bgreater\s+than\b",
    r"\bless\s+than\b",
    r"\bequal\s+to\b",
]


def parse_intent(
    query: str,
    column_names: list[str] | None = None,
) -> IntentParseResult:
    """Classify query intent and extract candidate columns and constraints.

    Accepts an optional column_names list so column matching can be done
    without a full dataset profile.
    """
    cols = column_names or []
    intent_type = _classify_intent(query)
    candidate_columns = _find_candidate_columns(query, cols)
    constraints = _extract_constraints(query)
    missing_information = _detect_missing(query, intent_type)

    match_ratio = len(candidate_columns) / max(len(cols), 1) if cols else 0.0

    return IntentParseResult(
        raw_query=query,
        parsed=ParsedTaskIntent(
            intent=intent_type,
            goal=query,
            constraints=constraints,
            candidate_columns=candidate_columns,
            missing_information=missing_information,
        ),
        candidate_column_match_ratio=round(match_ratio, 4),
    )


def _classify_intent(query: str) -> TaskIntentType:
    lowered = query.lower()
    for kw in _TRANSFORM_KEYWORDS:
        if _kw_matches(kw, lowered):
            return "transform_dataset"
    for kw in _INSPECT_KEYWORDS:
        if _kw_matches(kw, lowered):
            return "inspect_dataset"
    return "unknown"


def _kw_matches(kw: str, lowered_query: str) -> bool:
    """Whole-word match for ASCII keywords; substring match for CJK."""
    if kw.isascii():
        return bool(re.search(r"\b" + re.escape(kw) + r"\b", lowered_query))
    return kw in lowered_query


def _find_candidate_columns(query: str, column_names: list[str]) -> list[str]:
    lowered_query = query.lower()
    return [col for col in column_names if col.lower() in lowered_query]


def _extract_constraints(query: str) -> list[str]:
    constraints = []
    for pattern in _CONSTRAINT_PATTERNS:
        matches = re.findall(pattern, query, re.IGNORECASE)
        constraints.extend(matches)
    return constraints


def _detect_missing(query: str, intent_type: TaskIntentType) -> list[str]:
    if intent_type == "unknown":
        return [
            "Intent is unclear. Supported operations: filter, group by, sort, select columns, "
            "rename, remove or fill missing values, derive column, extract date parts."
        ]
    return []
