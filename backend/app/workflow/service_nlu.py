"""Query analysis helpers for the chat service pipeline.

These functions inspect query text and dataset schema to produce planning
signals (slot extraction, missing-column detection, complex-tool hints) that
inform whether the workflow should go through the deterministic router,
the LLM planner, or return a clarification request.
"""
from __future__ import annotations

import logging
import re

from app.models.clarification_context import ClarificationContext
from app.models.dataset import DatasetProfile
from app.workflow.nlu.slot_extractor import extract_slots
from app.workflow.nlu.slot_validator import validate_slots
from app.workflow.observation import signal_rules
from app.workflow.observation.models import ObservationSummary

logger = logging.getLogger(__name__)

_SLOT_MIN_CONFIDENCE = 0.7

_INTENT_TO_STEP_TYPE: dict[str, str] = {
    "filter": "filter_rows",
    "sort": "sort_values",
    "group_aggregate": "group_by",
}


# ---------------------------------------------------------------------------
# Slot extraction
# ---------------------------------------------------------------------------

class _SlotClarificationSignal:
    """Sentinel returned by _run_slot_extraction when schema validation needs
    user input before the planner can run."""

    __slots__ = ("question", "affected_step", "observation")

    def __init__(
        self,
        *,
        question: str,
        affected_step: dict | None,
        observation: ObservationSummary,
    ):
        self.question = question
        self.affected_step = affected_step
        self.observation = observation


def _run_slot_extraction(
    query: str,
    dataset_profile: DatasetProfile,
    clarification: ClarificationContext | None,
) -> object:
    """Run slot extraction and schema validation before workflow planning.

    Returns:
      - None              — skip slot path, proceed to planner as-is.
      - SlotExtractionResult — valid slots to pass to the planner.
      - _SlotClarificationSignal — user must clarify before planning.
    """
    if clarification and clarification.user_answer:
        return None

    try:
        slot_output = extract_slots(query)
    except Exception:
        logger.debug("Slot extraction raised; falling back to planner-only path.", exc_info=True)
        return None

    if slot_output.parse_error or slot_output.result.intent == "unknown":
        return None
    if slot_output.result.confidence < _SLOT_MIN_CONFIDENCE:
        return None

    validation = validate_slots(slot_output.result, dataset_profile)

    if validation.blocked:
        return None

    if validation.needs_clarification:
        question = validation.clarification_question or "Please clarify your request."
        slots = slot_output.result.slots
        step_type = _INTENT_TO_STEP_TYPE.get(slot_output.result.intent)
        affected_step = {"type": step_type, "column": slots.column} if step_type and slots.column else None
        observation = signal_rules.from_validation_failure(
            question,
            workflow_state="needs_clarification",
        )
        return _SlotClarificationSignal(
            question=question,
            affected_step=affected_step,
            observation=observation,
        )

    if validation.is_valid:
        return slot_output.result

    return None


# ---------------------------------------------------------------------------
# Column detection helpers
# ---------------------------------------------------------------------------

def _explicit_missing_column(query: str, column_names: list[str]) -> str | None:
    """Return a column name that appears in the query but is not in the dataset."""
    available = set(column_names)
    available_lower = {c.lower() for c in column_names}
    identifier = r"([\w]+)"
    patterns = [
        r"\bwhere\s+" + identifier + r"\b",
        r"(?:sort(?:ed)?\s+by|order\s+by)\s+" + identifier + r"\b",
        identifier + r"\s*(?:大于等于|小于等于|不等于|大于|小于|等于|高于|低于)",
        r"(?:按|根据)\s*" + identifier + r"\s*(?:排序|降序|升序|排列)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            col = match.group(1)
            if col not in available and col.lower() not in available_lower:
                return col
    return None


def _extract_column_from_error(msg: str) -> str | None:
    """Extract a column name from a planner/validator error message."""
    match = re.search(r"[Cc]olumn ['\"]?([\w]+)['\"]?", msg)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Step-type detection
# ---------------------------------------------------------------------------

_SORT_PATTERN = re.compile(r"(?:sort(?:ed)?\s+by|order\s+by|按|根据).*", re.IGNORECASE)
_GROUP_PATTERN = re.compile(
    r"(?:group\s+by|grouped\s+by|\b(?:total|sum|average|avg|mean|count|min|max)\b.*\bby\b|汇总|分组)",
    re.IGNORECASE,
)
_FILTER_PATTERN = re.compile(r"(?:\bwhere\b|filter|过滤|删除|移除|保留)", re.IGNORECASE)


def _detect_step_type_from_query(query: str) -> str | None:
    """Return a workflow step type hint based on query keywords."""
    if _SORT_PATTERN.search(query):
        return "sort_values"
    if _GROUP_PATTERN.search(query):
        return "group_by"
    if _FILTER_PATTERN.search(query):
        return "filter_rows"
    return None


# ---------------------------------------------------------------------------
# Complex tool hints
# ---------------------------------------------------------------------------

_COMPLEX_TOOL_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (
        re.compile(r"\bpivot\b|pivot\s*table|crosstab|透视|交叉表", re.IGNORECASE),
        "pivot_table",
        (
            "To create a pivot table I need a few details: "
            "(1) Which column(s) should form the row index? "
            "(2) Which column should become the new column headers (optional)? "
            "(3) Which numeric column should be aggregated as values? "
            "(4) What aggregation function: sum, mean, count, min, or max?"
        ),
    ),
    (
        re.compile(r"\btrim\b|\bstrip\s+(whitespace|spaces?)\b|去除空格|修剪", re.IGNORECASE),
        "trim_text",
        "To trim text, which column should I apply the trim to?",
    ),
    (
        re.compile(
            r"\bextract\b.*\b(pattern|regex|text|part)\b"
            r"|\b(parse|pull\s+out|extract)\b.*\bcolumn\b"
            r"|提取.*列|正则提取",
            re.IGNORECASE,
        ),
        "extract_text",
        (
            "To extract text using a pattern I need: "
            "(1) the source column, "
            "(2) a regex pattern (e.g. r'(\\d+)'), and "
            "(3) a name for the new column that will hold the extracted value."
        ),
    ),
    (
        re.compile(
            r"\bdate\s*(diff|difference|gap|between|delta)\b"
            r"|\bdays?\s+between\b"
            r"|\bhow\s+many\s+days\b"
            r"|日期差|相差天数",
            re.IGNORECASE,
        ),
        "date_diff",
        (
            "To calculate the date difference I need: "
            "(1) the start date column, "
            "(2) the end date column, and "
            "(3) a name for the new column that will hold the result (in days)."
        ),
    ),
]


def _detect_complex_tool_hint(query: str, column_names: list[str]) -> str | None:
    """Return a targeted clarification message when the query likely intends a
    complex tool (pivot_table, trim_text, extract_text, date_diff) but the
    planner could not build a complete workflow.

    Returns None when no complex tool pattern matches.
    """
    available = ", ".join(column_names)
    for pattern, tool_type, base_question in _COMPLEX_TOOL_PATTERNS:
        if pattern.search(query):
            suffix = f" Available columns: {available}." if available else ""
            logger.info("Complex tool hint triggered: tool=%s query=%r", tool_type, query)
            return base_question + suffix
    return None
