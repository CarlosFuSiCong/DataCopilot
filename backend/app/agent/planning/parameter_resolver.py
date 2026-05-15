"""Parameter resolver — deterministic column/value resolution for workflow steps.

Checks column existence, applies case-insensitive fixes, fills known defaults,
and reports missing required fields. No LLM calls.
"""
from typing import Any

from app.agent.planning.pipeline_models import ParameterResolutionResult

_COLUMN_FIELDS = {"column", "target", "other_column", "condition_column", "start_column", "end_column"}
_LIST_COLUMN_FIELDS = {"columns", "values", "index"}

# Step-type level safe defaults for optional fields.
_STEP_DEFAULTS: dict[str, dict[str, Any]] = {
    "limit_rows": {"n": 10},
    "sort_values": {"ascending": True},
    "fill_missing_values": {"strategy": "mean"},
    "remove_missing_values": {},
    "generate_summary": {},
    "deduplicate_rows": {},
    "normalize_text": {"case": "lower"},
    "trim_text": {},
}


def resolve_parameters(
    step: dict[str, Any],
    column_names: list[str],
) -> ParameterResolutionResult:
    """Check column existence, apply defaults, report missing required fields.

    Returns both the original raw step and the resolved step so the caller
    can compare and inspect what changed.
    """
    column_set = set(column_names)
    column_lower = {c.lower(): c for c in column_names}
    resolved: dict[str, Any] = dict(step)

    defaulted_fields: list[str] = []
    missing_required_fields: list[str] = []
    column_errors: list[str] = []

    step_type = resolved.get("type", "")

    for field, default in _STEP_DEFAULTS.get(step_type, {}).items():
        if field not in resolved:
            resolved[field] = default
            defaulted_fields.append(field)

    for field in _COLUMN_FIELDS:
        if field not in resolved:
            continue
        value = resolved[field]
        if not isinstance(value, str):
            continue
        if value not in column_set:
            fixed = column_lower.get(value.lower())
            if fixed:
                resolved[field] = fixed
                defaulted_fields.append(f"{field}(case_fixed:{value}→{fixed})")
            else:
                column_errors.append(
                    f"Column '{value}' not found in dataset for field '{field}'."
                )

    for field in _LIST_COLUMN_FIELDS:
        if field not in resolved:
            continue
        values = resolved[field]
        if not isinstance(values, list):
            continue
        fixed_list = []
        for col in values:
            if not isinstance(col, str) or col in column_set:
                fixed_list.append(col)
                continue
            fixed = column_lower.get(col.lower())
            if fixed:
                fixed_list.append(fixed)
                defaulted_fields.append(f"{field}[{col}](case_fixed:{col}→{fixed})")
            else:
                column_errors.append(
                    f"Column '{col}' not found in dataset for field '{field}'."
                )
                fixed_list.append(col)
        resolved[field] = fixed_list

    return ParameterResolutionResult(
        raw_step=step,
        resolved_step=resolved,
        missing_required_fields=missing_required_fields,
        defaulted_fields=defaulted_fields,
        column_errors=column_errors,
    )
