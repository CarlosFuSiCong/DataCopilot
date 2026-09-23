"""Tool policy matrix — classifies each workflow tool as read_only or mutating.

Read-only tools produce analytical results without changing the dataset state.
They can run in Ask Mode directly, require no preview/confirm step, and are
not saved to the transformation run history.

Mutating tools change or filter the dataset. They always go through
validate → preview → confirm → execute and produce a persisted run artifact.
"""
from __future__ import annotations

from typing import Literal

ToolKind = Literal["read_only", "mutating"]

# ---------------------------------------------------------------------------
# Policy matrix
# ---------------------------------------------------------------------------
# Maps every supported tool type to its kind.
# "view" tools (like filter_rows, select_columns) are classified as mutating
# because they produce a new dataset state that needs to be confirmed.

_POLICY: dict[str, ToolKind] = {
    # --- Read-only analytical tools ---
    "profile_column":             "read_only",
    "distribution_summary":       "read_only",
    "compare_groups":             "read_only",
    "detect_missing_values":      "read_only",
    "detect_duplicates":          "read_only",
    "correlation_summary":        "read_only",
    "inspect_unique_values":      "read_only",
    "summarize_numeric_column":   "read_only",
    "suggest_analysis_steps":     "read_only",
    # --- Mutating / view tools ---
    "filter_rows":                "mutating",
    "select_columns":             "mutating",
    "group_by":                   "mutating",
    "sort_values":                "mutating",
    "rename_columns":             "mutating",
    "remove_missing_values":      "mutating",
    "fill_missing_values":        "mutating",
    "drop_columns":               "mutating",
    "derive_column":              "mutating",
    "date_extract":               "mutating",
    "limit_rows":                 "mutating",
    "generate_summary":           "mutating",
    "pivot_table":                "mutating",
    "trim_text":                  "mutating",
    "extract_text":               "mutating",
    "date_diff":                  "mutating",
    "cast_column":                "mutating",
    "replace_values":             "mutating",
    "remove_duplicates":          "mutating",
}


def get_tool_kind(tool_type: str) -> ToolKind:
    """Return the policy kind for a tool type. Unknown tools are treated as mutating."""
    return _POLICY.get(tool_type, "mutating")


def is_read_only(tool_type: str) -> bool:
    """Return True when the tool produces analytical output without mutating the dataset."""
    return get_tool_kind(tool_type) == "read_only"


def can_run_in_ask_mode(tool_type: str) -> bool:
    """Return True when the tool is safe to run in Ask Mode (no confirm required)."""
    return is_read_only(tool_type)


def requires_confirm(tool_type: str) -> bool:
    """Return True when the tool must go through the preview / confirm flow."""
    return get_tool_kind(tool_type) == "mutating"


def all_read_only(tool_types: list[str]) -> bool:
    """Return True when every tool in a workflow step list is read-only."""
    return bool(tool_types) and all(is_read_only(t) for t in tool_types)
