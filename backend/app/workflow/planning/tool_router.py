"""Level 1 deterministic tool router.

Selects a specific tool and drafts workflow steps without calling the LLM.
Invoked only when the classifier returns route="deterministic_tool".

Supported tools
---------------
Column-free (no required params):
  detect_missing_values, detect_duplicates, correlation_summary,
  suggest_analysis_steps

Single-column (requires: column):
  profile_column, inspect_unique_values

Single-column, numeric constraint (requires: numeric column):
  distribution_summary, summarize_numeric_column

Two-column (requires: group_column + value_column):
  compare_groups

If required parameters cannot be resolved from query / classifier evidence /
schema, the router returns a targeted clarification question instead of
guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models.dataset import DatasetProfile
from app.workflow.planning.route_decision import RouteDecision

_NUMERIC_DTYPES = frozenset({
    "int64", "float64", "int32", "float32",
    "uint64", "uint32", "Int64", "Float64",
})

_COLUMN_FREE_TOOLS = frozenset({
    "detect_missing_values",
    "detect_duplicates",
    "correlation_summary",
    "suggest_analysis_steps",
})

_SINGLE_COLUMN_TOOLS = frozenset({
    "profile_column",
    "inspect_unique_values",
})

_NUMERIC_COLUMN_TOOLS = frozenset({
    "distribution_summary",
    "summarize_numeric_column",
})


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------

@dataclass
class ToolRouterResult:
    """Output of the tool router.

    Either raw_steps is populated (ready for parameter_resolver + workflow_builder)
    or clarification_question is populated. Never both, never neither.
    """

    selected_tool: str
    raw_steps: list[dict] = field(default_factory=list)
    clarification_question: str | None = None
    evidence: list[str] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _col_dtypes(profile: DatasetProfile) -> dict[str, str]:
    return {col.name: col.dtype for col in profile.columns}


def _is_numeric(dtype: str) -> bool:
    return dtype in _NUMERIC_DTYPES


def _is_categorical(dtype: str) -> bool:
    return not _is_numeric(dtype)


def _numeric_columns(column_names: list[str], dtypes: dict[str, str]) -> list[str]:
    return [c for c in column_names if _is_numeric(dtypes.get(c, ""))]


def _categorical_columns(column_names: list[str], dtypes: dict[str, str]) -> list[str]:
    return [c for c in column_names if _is_categorical(dtypes.get(c, ""))]


# ---------------------------------------------------------------------------
# Aggregation extraction
# ---------------------------------------------------------------------------

_AGG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(sum|total|合计|求和)\b", re.IGNORECASE), "sum"),
    (re.compile(r"\b(mean|average|avg|均值|平均)\b", re.IGNORECASE), "mean"),
    (re.compile(r"\b(count|计数|数量)\b", re.IGNORECASE), "count"),
    (re.compile(r"\b(min|minimum|最小|最低)\b", re.IGNORECASE), "min"),
    (re.compile(r"\b(max|maximum|最大|最高)\b", re.IGNORECASE), "max"),
]


def _extract_agg(query_lower: str) -> str:
    for pattern, agg in _AGG_PATTERNS:
        if pattern.search(query_lower):
            return agg
    return "mean"


# ---------------------------------------------------------------------------
# Per-tool step builders
# ---------------------------------------------------------------------------

def _single_column_step(
    tool: str,
    candidates: list[str],
    column_names: list[str],
    query_lower: str,
) -> ToolRouterResult:
    if not candidates:
        available = ", ".join(column_names[:10])
        return ToolRouterResult(
            selected_tool=tool,
            clarification_question=(
                f"Which column would you like to {tool.replace('_', ' ')}? "
                f"Available columns: {available}."
            ),
        )
    if len(candidates) == 1:
        col = candidates[0]
        step: dict = {"type": tool, "column": col}
        if tool == "inspect_unique_values":
            m = re.search(r"\b(top|first|show)\s+(\d+)\b", query_lower)
            if m:
                step["max_values"] = int(m.group(2))
        return ToolRouterResult(
            selected_tool=tool,
            raw_steps=[step],
            evidence=candidates,
            reason=f"Resolved column '{col}' for {tool}.",
        )
    opts = ", ".join(f"'{c}'" for c in candidates[:5])
    return ToolRouterResult(
        selected_tool=tool,
        clarification_question=(
            f"Multiple columns could match: {opts}. "
            f"Which column would you like to {tool.replace('_', ' ')}?"
        ),
        evidence=candidates,
    )


def _numeric_column_step(
    tool: str,
    candidates: list[str],
    column_names: list[str],
    dtypes: dict[str, str],
    query_lower: str,
) -> ToolRouterResult:
    """Like _single_column_step but restricts to numeric columns."""
    num_cands = [c for c in candidates if _is_numeric(dtypes.get(c, ""))]
    if not num_cands:
        num_cands = _numeric_columns(column_names, dtypes)

    if not num_cands:
        return ToolRouterResult(
            selected_tool=tool,
            clarification_question=(
                f"{tool.replace('_', ' ')} requires a numeric column, "
                "but no numeric columns were found in this dataset."
            ),
        )
    if candidates and not [c for c in candidates if _is_numeric(dtypes.get(c, ""))]:
        non_num = candidates[0]
        num_available = ", ".join(num_cands[:5])
        return ToolRouterResult(
            selected_tool=tool,
            clarification_question=(
                f"Column '{non_num}' is not numeric. "
                f"{tool.replace('_', ' ')} requires a numeric column. "
                f"Available numeric columns: {num_available}."
            ),
            evidence=candidates,
        )
    return _single_column_step(tool, num_cands, column_names, query_lower)


def _compare_groups_step(
    candidates: list[str],
    column_names: list[str],
    dtypes: dict[str, str],
    query_lower: str,
) -> ToolRouterResult:
    cat_cands = [c for c in candidates if _is_categorical(dtypes.get(c, ""))]
    num_cands = [c for c in candidates if _is_numeric(dtypes.get(c, ""))]

    if not cat_cands:
        cat_cands = _categorical_columns(column_names, dtypes)
    if not num_cands:
        num_cands = _numeric_columns(column_names, dtypes)

    available = ", ".join(column_names[:10])
    if not cat_cands:
        return ToolRouterResult(
            selected_tool="compare_groups",
            clarification_question=(
                "To compare groups I need a categorical column for grouping. "
                f"Available columns: {available}. Which column contains the groups?"
            ),
        )
    if not num_cands:
        return ToolRouterResult(
            selected_tool="compare_groups",
            clarification_question=(
                "To compare groups I need a numeric column for values. "
                f"Available columns: {available}. Which numeric column should be compared?"
            ),
        )
    if len(cat_cands) == 1 and len(num_cands) == 1:
        agg = _extract_agg(query_lower)
        return ToolRouterResult(
            selected_tool="compare_groups",
            raw_steps=[{
                "type": "compare_groups",
                "group_column": cat_cands[0],
                "value_column": num_cands[0],
                "agg": agg,
            }],
            evidence=cat_cands + num_cands,
            reason=f"group by '{cat_cands[0]}', values '{num_cands[0]}', agg={agg}.",
        )
    cat_opts = ", ".join(f"'{c}'" for c in cat_cands[:3])
    num_opts = ", ".join(f"'{c}'" for c in num_cands[:3])
    if len(cat_cands) > 1 and len(num_cands) > 1:
        return ToolRouterResult(
            selected_tool="compare_groups",
            clarification_question=(
                "To compare groups I need: "
                f"(1) a grouping column — options: {cat_opts}; "
                f"(2) a numeric values column — options: {num_opts}. "
                "Which would you like to use?"
            ),
            evidence=cat_cands + num_cands,
        )
    if len(cat_cands) > 1:
        return ToolRouterResult(
            selected_tool="compare_groups",
            clarification_question=f"Which column contains the groups to compare? Options: {cat_opts}.",
            evidence=cat_cands,
        )
    return ToolRouterResult(
        selected_tool="compare_groups",
        clarification_question=f"Which numeric column should be compared? Options: {num_opts}.",
        evidence=num_cands,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def route(
    query: str,
    column_names: list[str],
    dataset_profile: DatasetProfile,
    route_decision: RouteDecision,
) -> ToolRouterResult:
    """Route a deterministic_tool request to a concrete workflow step.

    Called only when route_decision.route == "deterministic_tool".
    Returns ToolRouterResult with either raw_steps or clarification_question.
    """
    tool = route_decision.selected_tool or ""
    candidates: list[str] = list(route_decision.extracted_slots.get("candidate_columns", []))
    query_lower = query.lower()
    dtypes = _col_dtypes(dataset_profile)

    if tool in _COLUMN_FREE_TOOLS:
        step: dict = {"type": tool}
        if tool == "correlation_summary":
            num_cands = [c for c in candidates if _is_numeric(dtypes.get(c, ""))]
            step["columns"] = num_cands
        return ToolRouterResult(
            selected_tool=tool,
            raw_steps=[step],
            evidence=candidates,
            reason=f"{tool} requires no column selection.",
        )

    if tool in _SINGLE_COLUMN_TOOLS:
        return _single_column_step(tool, candidates, column_names, query_lower)

    if tool in _NUMERIC_COLUMN_TOOLS:
        return _numeric_column_step(tool, candidates, column_names, dtypes, query_lower)

    if tool == "compare_groups":
        return _compare_groups_step(candidates, column_names, dtypes, query_lower)

    return ToolRouterResult(
        selected_tool=tool or "unknown",
        clarification_question=(
            "I could not determine the right tool for this request. "
            "Could you describe the operation in more detail?"
        ),
        reason=f"No handler for tool '{tool}' in deterministic router.",
    )
