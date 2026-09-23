"""Deterministic intent parser layer for candidate columns and constraints."""
import re

from app.workflow.intake.intent import ParsedTaskIntent
from app.workflow.planning.pipeline_models import IntentParseResult

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
    """Extract candidate columns and constraints from the query.

    Intent classification remains intentionally conservative. Candidate column
    matching uses word boundaries so short columns do not match inside unrelated
    words such as "age" inside "message".
    """
    cols = column_names or []
    candidate_columns = _find_candidate_columns(query, cols)
    constraints = _extract_constraints(query)
    match_ratio = len(candidate_columns) / max(len(cols), 1) if cols else 0.0

    return IntentParseResult(
        raw_query=query,
        parsed=ParsedTaskIntent(
            intent="unknown",
            goal=query,
            constraints=constraints,
            candidate_columns=candidate_columns,
            missing_information=[],
        ),
        candidate_column_match_ratio=round(match_ratio, 4),
    )


def _find_candidate_columns(query: str, column_names: list[str]) -> list[str]:
    lowered_query = query.lower()
    matched = []
    for col in column_names:
        pattern = r"\b" + re.escape(col.lower()) + r"\b"
        if re.search(pattern, lowered_query):
            matched.append(col)
    return matched


def _extract_constraints(query: str) -> list[str]:
    constraints = []
    for pattern in _CONSTRAINT_PATTERNS:
        matches = re.findall(pattern, query, re.IGNORECASE)
        constraints.extend(matches)
    return constraints
