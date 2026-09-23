"""Structured clarification context scoped to one dataset and query."""
import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel

ClarificationStatus = Literal["pending", "resolved"]

ClarificationType = Literal[
    # Structural / parameter gaps
    "missing_column",
    "missing_value",
    "ambiguous_metric",
    "ambiguous_group",
    # Routing decisions
    "broad_analysis_request",
    "unsupported_operation",
    "high_risk_operation",
    # Pipeline-internal
    "planning",
    "slot_validation",
    "deterministic_tool",
]


class ClarificationChoice(BaseModel):
    """One suggested analysis direction presented to the user as a button/card."""
    id: str
    label: str
    description: str
    query: str
    tool: str | None = None


class ClarificationContext(BaseModel):
    dataset_id: str
    original_query: str
    question: str | None = None
    user_answer: str | None = None
    resolved_parameter: str | None = None
    affected_step: dict[str, Any] | None = None
    status: ClarificationStatus = "pending"
    scope_key: str
    clarification_type: ClarificationType | str | None = None
    choices: list[dict[str, Any]] | None = None


def make_scope_key(*, dataset_id: str, original_query: str) -> str:
    digest = hashlib.sha256(f"{dataset_id}:{original_query}".encode("utf-8")).hexdigest()
    return digest[:16]


def new_pending_context(
    *,
    dataset_id: str,
    original_query: str,
    question: str,
    affected_step: dict[str, Any] | None = None,
    clarification_type: str | None = None,
    choices: list[dict[str, Any]] | None = None,
) -> ClarificationContext:
    return ClarificationContext(
        dataset_id=dataset_id,
        original_query=original_query,
        question=question,
        affected_step=affected_step,
        status="pending",
        scope_key=make_scope_key(dataset_id=dataset_id, original_query=original_query),
        clarification_type=clarification_type,
        choices=choices,
    )


def resolve_context(
    clarification_context: str | ClarificationContext | None,
    *,
    dataset_id: str,
    original_query: str,
) -> ClarificationContext | None:
    """Return a resolved context after normalizing legacy string answers."""
    if clarification_context is None:
        return None

    if isinstance(clarification_context, str):
        answer = clarification_context.strip()
        if not answer:
            return None
        return ClarificationContext(
            dataset_id=dataset_id,
            original_query=original_query,
            user_answer=answer,
            resolved_parameter=answer,
            status="resolved",
            scope_key=make_scope_key(dataset_id=dataset_id, original_query=original_query),
        )

    answer = (clarification_context.user_answer or clarification_context.resolved_parameter or "").strip()
    return clarification_context.model_copy(
        update={
            "user_answer": answer or None,
            "resolved_parameter": answer or None,
            "status": "resolved" if answer else clarification_context.status,
        }
    )


def validate_scope(
    context: ClarificationContext,
    *,
    dataset_id: str,
    original_query: str,
) -> bool:
    return (
        context.dataset_id == dataset_id
        and context.original_query == original_query
        and context.scope_key == make_scope_key(dataset_id=dataset_id, original_query=original_query)
    )


def planner_query_with_context(query: str, context: ClarificationContext | None) -> str:
    """Append or deterministically apply the resolved clarification answer."""
    if not context or not context.user_answer:
        return query
    rewritten = _query_with_resolved_parameter(query, context)
    if rewritten != query:
        return rewritten
    return f"{query}\nUser clarification: {context.user_answer}"


def _query_with_resolved_parameter(query: str, context: ClarificationContext) -> str:
    affected_column = (context.affected_step or {}).get("column")
    resolved = context.resolved_parameter or context.user_answer
    if not isinstance(affected_column, str) or not resolved:
        return query

    pattern = re.compile(rf"\b{re.escape(affected_column)}\b", flags=re.IGNORECASE)
    rewritten, count = pattern.subn(str(resolved), query)
    if count > 0:
        return rewritten

    return query


def next_iteration_input(context: ClarificationContext) -> dict[str, Any]:
    return {
        "dataset_id": context.dataset_id,
        "original_query": context.original_query,
        "question": context.question,
        "user_answer": context.user_answer,
        "resolved_parameter": context.resolved_parameter,
        "affected_step": context.affected_step,
        "scope_key": context.scope_key,
    }


# ---------------------------------------------------------------------------
# Broad-analysis choice generators
# ---------------------------------------------------------------------------

_NUMERIC_DTYPES = frozenset({
    "int64", "float64", "int32", "float32",
    "uint64", "uint32", "Int64", "Float64",
})


def broad_analysis_choices(column_names: list[str], dataset_profile) -> list[dict]:
    """Generate 3-5 schema-aware analysis direction choices for broad analysis requests.

    Each choice has: id, label, description, query, tool.
    Choices are ordered from cheapest / most diagnostic to more exploratory.
    """
    choices: list[dict] = []

    numeric_cols = [c.name for c in dataset_profile.columns if c.dtype in _NUMERIC_DTYPES]
    categorical_cols = [c.name for c in dataset_profile.columns if c.dtype == "object"]
    missing_count = sum(1 for c in dataset_profile.columns if c.missing_count > 0)

    # 1. Missing values — always useful
    missing_hint = f" ({missing_count} columns affected)" if missing_count else ""
    choices.append({
        "id": "missing_values",
        "label": f"Check for missing values{missing_hint}",
        "description": "Find columns with missing data and the percentage missing.",
        "query": "Check for missing values in the dataset",
        "tool": "detect_missing_values",
    })

    # 2. Duplicate rows — always useful
    choices.append({
        "id": "duplicate_rows",
        "label": "Check for duplicate rows",
        "description": "Identify records that appear more than once.",
        "query": "Check for duplicate rows",
        "tool": "deduplicate_rows",
    })

    # 3. Profile first numeric column
    if numeric_cols:
        col = numeric_cols[0]
        choices.append({
            "id": "profile_numeric",
            "label": f"Profile the '{col}' column",
            "description": f"Get statistics for {col}: min, max, mean, quartiles, missing count.",
            "query": f"Profile the {col} column",
            "tool": "profile_column",
        })

    # 4. Compare groups (categorical × numeric)
    if categorical_cols and numeric_cols:
        cat_col, num_col = categorical_cols[0], numeric_cols[0]
        choices.append({
            "id": "compare_groups",
            "label": f"Compare '{num_col}' by '{cat_col}'",
            "description": f"See how {num_col} varies across different {cat_col} values.",
            "query": f"Compare average {num_col} by {cat_col}",
            "tool": "compare_groups",
        })

    # 5. Correlation (only if 2+ numeric columns remain)
    if len(numeric_cols) >= 2:
        choices.append({
            "id": "correlation",
            "label": "Find correlations between numeric columns",
            "description": "Identify which numeric columns move together.",
            "query": "Show correlation between numeric columns",
            "tool": "correlation_summary",
        })

    return choices[:5]


def ambiguous_request_question(column_names: list[str]) -> str:
    """Return a clarification question for genuinely ambiguous requests."""
    available = ", ".join(column_names[:6])
    suffix = " ..." if len(column_names) > 6 else ""
    return (
        "I'm not sure what kind of analysis you'd like. Could you be more specific?\n"
        "For example: 'Filter rows', 'Group by region', 'Profile the amount column', "
        "'Check for missing values'.\n"
        f"Available columns: {available}{suffix}"
    )

