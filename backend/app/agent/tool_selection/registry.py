"""Central registry for deterministic workflow tools.

The registry is the single dispatch table for transformation validation,
execution, planner metadata, RAG metadata, and editor metadata. Workflow JSON
remains the contract; each tool spec defines how one workflow step is checked
and applied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from app.core.exceptions import ExecutionError, WorkflowValidationError
from app.models.workflow_steps import (
    BinColumnStep,
    CastColumnStep,
    CompareGroupsStep,
    ConditionalColumnStep,
    CorrelationSummaryStep,
    DateDiffStep,
    DateExtractStep,
    DeduplicateRowsStep,
    DeriveColumnStep,
    DistributionSummaryStep,
    DropColumnsStep,
    ExtractTextStep,
    FillMissingValuesStep,
    FilterRowsStep,
    GenerateSummaryStep,
    GroupByStep,
    InspectUniqueValuesStep,
    LimitRowsStep,
    NormalizeTextStep,
    PivotTableStep,
    ProfileColumnStep,
    ReplaceValuesStep,
    RemoveMissingValuesStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
    SuggestAnalysisStepsStep,
    SummarizeNumericColumnStep,
    TrimTextStep,
    WorkflowStep,
)


@dataclass(frozen=True)
class StepMetrics:
    match_rate: float | None = None
    affected_rate: float | None = None


ValidateFn = Callable[[WorkflowStep, set[str], str], None]
ExecuteFn = Callable[[WorkflowStep, pd.DataFrame], tuple[pd.DataFrame, str, StepMetrics]]
AdvanceColumnsFn = Callable[[WorkflowStep, set[str]], set[str]]


@dataclass(frozen=True)
class ToolSpec:
    type: str
    description: str
    input_schema: dict[str, Any]
    validate: ValidateFn
    execute: ExecuteFn
    examples: list[dict[str, Any]] = field(default_factory=list)
    risk_profile: dict[str, Any] = field(default_factory=dict)
    advance_columns: AdvanceColumnsFn | None = None


def all_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def get_tool(step_type: str) -> ToolSpec:
    try:
        return _REGISTRY[step_type]
    except KeyError as exc:
        raise WorkflowValidationError(f"Unknown workflow step type '{step_type}'.") from exc


def step_types() -> set[str]:
    return set(_REGISTRY)


def supported_tools_prompt() -> str:
    """Return compact planner-facing metadata for supported tools."""
    return "\n".join(
        f"- {spec.type}: {spec.description}; params: {', '.join(_schema_fields(spec.input_schema)) or 'none'}"
        for spec in all_tools()
    )


def rag_metadata() -> list[dict[str, Any]]:
    """Return inspectable metadata suitable for RAG indexing or consistency checks."""
    return [
        {
            "type": spec.type,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "examples": spec.examples,
            "risk_profile": spec.risk_profile,
        }
        for spec in all_tools()
    ]


def workflow_editor_metadata() -> list[dict[str, Any]]:
    """Return frontend-friendly tool metadata for workflow editors."""
    return [
        {
            "type": spec.type,
            "description": spec.description,
            "fields": _schema_fields(spec.input_schema),
            "examples": spec.examples,
            "risk_profile": spec.risk_profile,
        }
        for spec in all_tools()
    ]


def validate_step(step: WorkflowStep, col_set: set[str], idx: int) -> None:
    label = f"Step {idx} ({step.type})"
    get_tool(step.type).validate(step, col_set, label)


def advance_columns(step: WorkflowStep, col_set: set[str]) -> set[str]:
    spec = get_tool(step.type)
    if spec.advance_columns is None:
        return set(col_set)
    return spec.advance_columns(step, col_set)


def execute_step(step: WorkflowStep, df: pd.DataFrame, idx: int) -> tuple[pd.DataFrame, str, StepMetrics]:
    try:
        return get_tool(step.type).execute(step, df)
    except ExecutionError:
        raise
    except Exception as exc:
        raise ExecutionError(f"Step {idx} ({step.type}) failed: {exc}") from exc


def _schema(model: type) -> dict[str, Any]:
    return model.model_json_schema()


def _schema_fields(schema: dict[str, Any]) -> list[str]:
    return [
        name for name in schema.get("properties", {})
        if name != "type"
    ]


def _require_columns(cols: list[str], col_set: set[str], label: str) -> None:
    for col in cols:
        if col not in col_set:
            available = sorted(col_set)
            raise WorkflowValidationError(
                f"{label}: column '{col}' does not exist in the dataset. "
                f"Available columns: {available}"
            )


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _available(df: pd.DataFrame) -> list[str]:
    return sorted(df.columns.tolist())


def _validate_noop(step: WorkflowStep, col_set: set[str], label: str) -> None:
    return None


def _validate_select_columns(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, SelectColumnsStep)
    _require_columns(step.columns, col_set, label)


def _validate_filter_rows(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, FilterRowsStep)
    _require_columns([step.column], col_set, label)


def _validate_group_by(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, GroupByStep)
    group_cols = step.columns if step.columns else [step.column]
    _require_columns(group_cols + [step.target], col_set, label)


def _validate_sort_values(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, SortValuesStep)
    _require_columns([step.column], col_set, label)


def _validate_rename_columns(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, RenameColumnsStep)
    _require_columns(list(step.mapping.keys()), col_set, label)


def _validate_limit_rows(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, LimitRowsStep)
    if step.n <= 0:
        raise WorkflowValidationError(f"{label}: n must be a positive integer, got {step.n}.")


def _validate_derive_column(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, DeriveColumnStep)
    _require_columns([step.column], col_set, label)
    if step.other_column:
        _require_columns([step.other_column], col_set, label)
    if step.value is not None and step.other_column:
        raise WorkflowValidationError(
            f"{label}: derive_column requires exactly one of 'value' or 'other_column', not both."
        )
    if step.value is None and not step.other_column:
        raise WorkflowValidationError(
            f"{label}: derive_column requires either 'value' or 'other_column'."
        )


def _validate_date_extract(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, DateExtractStep)
    _require_columns([step.column], col_set, label)


def _validate_drop_columns(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, DropColumnsStep)
    if not step.columns:
        raise WorkflowValidationError(f"{label}: columns list must not be empty.")
    _require_columns(step.columns, col_set, label)


def _validate_fill_missing_values(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, FillMissingValuesStep)
    _require_columns([step.column], col_set, label)
    if step.strategy == "constant" and step.value is None:
        raise WorkflowValidationError(
            f"{label}: fill_missing_values with strategy 'constant' requires a 'value'."
        )


def _validate_deduplicate_rows(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, DeduplicateRowsStep)
    if step.columns:
        _require_columns(step.columns, col_set, label)


def _validate_replace_values(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, ReplaceValuesStep)
    _require_columns([step.column], col_set, label)
    if not step.mapping:
        raise WorkflowValidationError(f"{label}: mapping must not be empty.")


def _validate_cast_column(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, CastColumnStep)
    _require_columns([step.column], col_set, label)


def _validate_conditional_column(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, ConditionalColumnStep)
    _require_columns([step.condition_column], col_set, label)


def _validate_bin_column(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, BinColumnStep)
    _require_columns([step.column], col_set, label)
    if len(step.bins) < 2:
        raise WorkflowValidationError(f"{label}: bins must contain at least two boundaries.")
    if any(left >= right for left, right in zip(step.bins, step.bins[1:])):
        raise WorkflowValidationError(f"{label}: bins must be strictly increasing.")
    if step.labels and len(step.labels) != len(step.bins) - 1:
        raise WorkflowValidationError(
            f"{label}: labels length must be exactly len(bins) - 1."
        )


def _validate_pivot_table(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, PivotTableStep)
    if not step.index:
        raise WorkflowValidationError(f"{label}: index list must not be empty.")
    cols = list(step.index) + [step.values]
    if step.columns:
        cols.append(step.columns)
    _require_columns(cols, col_set, label)


def _validate_trim_text(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, TrimTextStep)
    _require_columns([step.column], col_set, label)


def _validate_normalize_text(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, NormalizeTextStep)
    _require_columns([step.column], col_set, label)


def _validate_extract_text(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, ExtractTextStep)
    _require_columns([step.column], col_set, label)
    if step.group < 0:
        raise WorkflowValidationError(f"{label}: group must be zero or a positive integer.")
    try:
        compiled = re.compile(step.pattern)
    except re.error as exc:
        raise WorkflowValidationError(f"{label}: invalid regex pattern: {exc}") from exc
    if step.group > compiled.groups:
        raise WorkflowValidationError(
            f"{label}: group {step.group} does not exist in pattern with {compiled.groups} capture group(s)."
        )


def _validate_date_diff(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, DateDiffStep)
    _require_columns([step.start_column, step.end_column], col_set, label)


def _advance_select_columns(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, SelectColumnsStep)
    return set(step.columns)


def _advance_drop_columns(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, DropColumnsStep)
    return set(col_set) - set(step.columns)


def _advance_rename_columns(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, RenameColumnsStep)
    return {step.mapping.get(c, c) for c in col_set}


def _advance_derive_column(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, DeriveColumnStep)
    return set(col_set) | {step.new_column}


def _advance_date_extract(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, DateExtractStep)
    return set(col_set) | {step.new_column}


def _advance_group_by(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, GroupByStep)
    group_cols = set(step.columns) if step.columns else {step.column}
    return group_cols | {step.target}


def _advance_add_new_column(step: WorkflowStep, col_set: set[str]) -> set[str]:
    new_column = getattr(step, "new_column")
    return set(col_set) | {new_column}


def _advance_pivot_table(step: WorkflowStep, col_set: set[str]) -> set[str]:
    assert isinstance(step, PivotTableStep)
    # Pivoted value columns are data-dependent and the original values column
    # is aggregated away, so only stable index columns remain in static state.
    return set(step.index)


def _execute_remove_missing_values(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    before = len(df)
    result = df.dropna()
    removed = before - len(result)
    return (
        result.reset_index(drop=True),
        f"Removed {removed} rows with missing values.",
        StepMetrics(affected_rate=_safe_rate(removed, before)),
    )


def _execute_select_columns(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, SelectColumnsStep)
    missing = [c for c in step.columns if c not in df.columns]
    if missing:
        raise ExecutionError(
            f"select_columns: column(s) {missing} not found. "
            f"Available columns: {_available(df)}"
        )
    return df[step.columns].copy(), f"Selected columns: {step.columns}.", StepMetrics()


_FILTER_OPS = {
    "=": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
    ">": lambda s, v: s > v,
    ">=": lambda s, v: s >= v,
    "<": lambda s, v: s < v,
    "<=": lambda s, v: s <= v,
}


def _execute_filter_rows(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, FilterRowsStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"filter_rows: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    mask = _FILTER_OPS[step.operator](df[step.column], step.value)
    result = df[mask].reset_index(drop=True)
    return (
        result,
        f"Filtered '{step.column}' {step.operator} {step.value!r}: {len(result)} rows kept.",
        StepMetrics(match_rate=_safe_rate(len(result), len(df))),
    )


def _execute_group_by(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, GroupByStep)
    group_cols = step.columns if step.columns else [step.column]
    for col in group_cols + [step.target]:
        if col not in df.columns:
            raise ExecutionError(
                f"group_by: column '{col}' not found. "
                f"Available columns: {_available(df)}"
            )
    result = (
        df.groupby(group_cols, as_index=False)[step.target]
        .agg(step.agg)
        .reset_index(drop=True)
    )
    affected_rows = len(df) - len(result)
    by_label = ", ".join(f"'{c}'" for c in group_cols)
    return (
        result,
        f"Grouped by {by_label}, aggregated '{step.target}' with {step.agg}.",
        StepMetrics(affected_rate=_safe_rate(affected_rows, len(df))),
    )


def _execute_sort_values(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, SortValuesStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"sort_values: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.sort_values(by=step.column, ascending=step.ascending).reset_index(drop=True)
    direction = "ascending" if step.ascending else "descending"
    return result, f"Sorted by '{step.column}' {direction}.", StepMetrics()


def _execute_rename_columns(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, RenameColumnsStep)
    missing = [c for c in step.mapping if c not in df.columns]
    if missing:
        raise ExecutionError(
            f"rename_columns: column(s) {missing} not found. "
            f"Available columns: {_available(df)}"
        )
    return df.rename(columns=step.mapping), f"Renamed columns: {step.mapping}.", StepMetrics()


def _execute_generate_summary(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    return df, "Summary requested — will be generated by the explainer.", StepMetrics(affected_rate=0.0)


def _execute_limit_rows(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, LimitRowsStep)
    result = df.head(step.n).reset_index(drop=True)
    return (
        result,
        f"Limited to first {step.n} rows.",
        StepMetrics(affected_rate=_safe_rate(len(df) - len(result), len(df))),
    )


_DERIVE_OPS = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
}


def _execute_derive_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DeriveColumnStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"derive_column: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    op_fn = _DERIVE_OPS[step.operator]
    if step.other_column:
        if step.other_column not in df.columns:
            raise ExecutionError(
                f"derive_column: other_column '{step.other_column}' not found. "
                f"Available columns: {_available(df)}"
            )
        operand = df[step.other_column]
        operand_label = f"'{step.other_column}'"
    else:
        operand = step.value
        operand_label = str(step.value)
    result = df.copy()
    result[step.new_column] = op_fn(df[step.column], operand)
    return (
        result,
        f"Derived '{step.new_column}' = '{step.column}' {step.operator} {operand_label}.",
        StepMetrics(),
    )


_DATE_PARTS = {
    "year": lambda s: s.dt.year,
    "month": lambda s: s.dt.month,
    "quarter": lambda s: s.dt.quarter,
    "day": lambda s: s.dt.day,
    "weekday": lambda s: s.dt.dayofweek,
}


def _execute_date_extract(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DateExtractStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"date_extract: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    try:
        parsed = pd.to_datetime(df[step.column])
    except Exception as exc:
        raise ExecutionError(
            f"date_extract: could not parse '{step.column}' as dates: {exc}"
        ) from exc
    result = df.copy()
    result[step.new_column] = _DATE_PARTS[step.part](parsed)
    return result, f"Extracted {step.part} from '{step.column}' into '{step.new_column}'.", StepMetrics()


def _execute_drop_columns(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DropColumnsStep)
    missing = [c for c in step.columns if c not in df.columns]
    if missing:
        raise ExecutionError(
            f"drop_columns: column(s) {missing} not found. "
            f"Available columns: {_available(df)}"
        )
    return df.drop(columns=step.columns), f"Dropped columns: {step.columns}.", StepMetrics()


def _execute_fill_missing_values(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, FillMissingValuesStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"fill_missing_values: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    before_missing = int(result[step.column].isna().sum())
    if before_missing == 0:
        return result, f"No missing values in '{step.column}'; nothing to fill.", StepMetrics(affected_rate=0.0)
    if step.strategy == "constant":
        if step.value is None:
            raise ExecutionError("fill_missing_values: strategy 'constant' requires a 'value'.")
        result[step.column] = result[step.column].fillna(step.value)
    elif step.strategy == "mean":
        result[step.column] = result[step.column].fillna(result[step.column].mean())
    elif step.strategy == "median":
        result[step.column] = result[step.column].fillna(result[step.column].median())
    elif step.strategy == "mode":
        mode_series = result[step.column].mode()
        if mode_series.empty:
            raise ExecutionError(
                f"fill_missing_values: could not compute mode for '{step.column}'."
            )
        result[step.column] = result[step.column].fillna(mode_series.iloc[0])
    elif step.strategy == "ffill":
        result[step.column] = result[step.column].ffill()
    elif step.strategy == "bfill":
        result[step.column] = result[step.column].bfill()
    else:
        raise ExecutionError(f"fill_missing_values: unknown strategy '{step.strategy}'.")
    after_missing = int(result[step.column].isna().sum())
    filled = before_missing - after_missing
    return (
        result,
        f"Filled {filled} missing value(s) in '{step.column}' using strategy '{step.strategy}'.",
        StepMetrics(affected_rate=_safe_rate(filled, len(df))),
    )


def _execute_deduplicate_rows(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DeduplicateRowsStep)
    subset = step.columns or None
    if subset:
        missing = [c for c in subset if c not in df.columns]
        if missing:
            raise ExecutionError(
                f"deduplicate_rows: column(s) {missing} not found. "
                f"Available columns: {_available(df)}"
            )
    before = len(df)
    result = df.drop_duplicates(subset=subset, keep=step.keep).reset_index(drop=True)
    removed = before - len(result)
    scope = f"columns {step.columns}" if step.columns else "all columns"
    return (
        result,
        f"Removed {removed} duplicate row(s) using {scope}, keeping {step.keep}.",
        StepMetrics(affected_rate=_safe_rate(removed, before)),
    )


def _coerce_mapping_key(raw: object, series: pd.Series) -> object:
    if pd.api.types.is_bool_dtype(series):
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
        return raw
    if pd.api.types.is_integer_dtype(series):
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    if pd.api.types.is_float_dtype(series):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return raw
    return raw


def _execute_replace_values(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, ReplaceValuesStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"replace_values: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    mapping = {
        _coerce_mapping_key(k, result[step.column]): v
        for k, v in step.mapping.items()
    }
    before = result[step.column].copy()
    result[step.column] = result[step.column].replace(mapping)
    both_missing = before.isna() & result[step.column].isna()
    changed = int(((before != result[step.column]) & ~both_missing).sum())
    return (
        result,
        f"Replaced {changed} value(s) in '{step.column}'.",
        StepMetrics(),
    )


def _execute_cast_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, CastColumnStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"cast_column: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    errors = step.errors
    try:
        if step.target_type == "string":
            result[step.column] = result[step.column].astype("string")
        elif step.target_type == "int":
            converted = pd.to_numeric(result[step.column], errors=errors)
            result[step.column] = converted.astype("Int64" if errors == "coerce" else "int64")
        elif step.target_type == "float":
            result[step.column] = pd.to_numeric(result[step.column], errors=errors).astype("float64")
        elif step.target_type == "boolean":
            result[step.column] = _to_boolean_series(result[step.column], errors)
        elif step.target_type == "datetime":
            result[step.column] = pd.to_datetime(result[step.column], errors=errors)
        else:
            raise ExecutionError(f"cast_column: unknown target_type '{step.target_type}'.")
    except Exception as exc:
        raise ExecutionError(
            f"cast_column: could not cast '{step.column}' to {step.target_type}: {exc}"
        ) from exc
    return result, f"Cast '{step.column}' to {step.target_type}.", StepMetrics()


def _to_boolean_series(series: pd.Series, errors: str) -> pd.Series:
    mapping = {
        "true": True, "1": True, "yes": True, "y": True,
        "false": False, "0": False, "no": False, "n": False,
    }
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")
    normalized = series.astype("string").str.strip().str.lower()
    converted = normalized.map(mapping)
    invalid = converted.isna() & normalized.notna()
    if invalid.any() and errors == "raise":
        bad = sorted(normalized[invalid].dropna().unique().tolist())
        raise ExecutionError(f"boolean cast found unsupported value(s): {bad}")
    return converted.astype("boolean")


def _execute_conditional_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, ConditionalColumnStep)
    if step.condition_column not in df.columns:
        raise ExecutionError(
            f"conditional_column: column '{step.condition_column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    mask = _FILTER_OPS[step.operator](result[step.condition_column], step.value)
    result[step.new_column] = mask.map({True: step.true_value, False: step.false_value})
    matched = int(mask.sum())
    return (
        result,
        f"Created '{step.new_column}' from condition '{step.condition_column}' {step.operator} {step.value!r}.",
        StepMetrics(match_rate=_safe_rate(matched, len(df))),
    )


def _execute_bin_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, BinColumnStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"bin_column: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    try:
        result[step.new_column] = pd.cut(
            result[step.column],
            bins=step.bins,
            labels=step.labels or None,
            include_lowest=step.include_lowest,
        )
    except Exception as exc:
        raise ExecutionError(f"bin_column: could not bin '{step.column}': {exc}") from exc
    return result, f"Binned '{step.column}' into '{step.new_column}'.", StepMetrics()


def _execute_pivot_table(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, PivotTableStep)
    required = list(step.index) + [step.values]
    if step.columns:
        required.append(step.columns)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ExecutionError(
            f"pivot_table: column(s) {missing} not found. "
            f"Available columns: {_available(df)}"
        )
    try:
        result = pd.pivot_table(
            df,
            index=step.index,
            columns=step.columns,
            values=step.values,
            aggfunc=step.agg,
            fill_value=0,
        ).reset_index()
    except Exception as exc:
        raise ExecutionError(f"pivot_table: could not build pivot table: {exc}") from exc
    result.columns = [
        "_".join(str(part) for part in col if str(part))
        if isinstance(col, tuple)
        else str(col)
        for col in result.columns
    ]
    affected_rows = len(df) - len(result)
    return (
        result,
        f"Pivoted values '{step.values}' by index {step.index} and columns '{step.columns}'.",
        StepMetrics(affected_rate=_safe_rate(affected_rows, len(df))),
    )


def _execute_trim_text(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, TrimTextStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"trim_text: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    before = result[step.column].copy()
    text = result[step.column].astype("string").str.strip()
    if step.collapse_whitespace:
        text = text.str.replace(r"\s+", " ", regex=True)
    result[step.column] = text
    both_missing = before.isna() & result[step.column].isna()
    changed = int(((before != result[step.column]) & ~both_missing).sum())
    return result, f"Trimmed text in '{step.column}' for {changed} row(s).", StepMetrics()


def _execute_normalize_text(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, NormalizeTextStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"normalize_text: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    before = result[step.column].copy()
    text = result[step.column].astype("string")
    if step.case == "lower":
        result[step.column] = text.str.lower()
    elif step.case == "upper":
        result[step.column] = text.str.upper()
    elif step.case == "title":
        result[step.column] = text.str.title()
    else:
        raise ExecutionError(f"normalize_text: unknown case '{step.case}'.")
    both_missing = before.isna() & result[step.column].isna()
    changed = int(((before != result[step.column]) & ~both_missing).sum())
    return result, f"Normalized text in '{step.column}' to {step.case} for {changed} row(s).", StepMetrics()


def _execute_extract_text(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, ExtractTextStep)
    if step.column not in df.columns:
        raise ExecutionError(
            f"extract_text: column '{step.column}' not found. "
            f"Available columns: {_available(df)}"
        )
    try:
        compiled = re.compile(step.pattern)
    except re.error as exc:
        raise ExecutionError(f"extract_text: invalid regex pattern: {exc}") from exc
    result = df.copy()
    series = result[step.column].astype("string").map(
        lambda value: (
            match.group(step.group)
            if not pd.isna(value) and (match := compiled.search(str(value))) is not None
            else None
        ),
        na_action=None,
    )
    result[step.new_column] = series.where(series.notna(), step.no_match)
    matched = int(series.notna().sum())
    return (
        result,
        f"Extracted text from '{step.column}' into '{step.new_column}' for {matched} row(s).",
        StepMetrics(match_rate=_safe_rate(matched, len(df))),
    )


def _execute_date_diff(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DateDiffStep)
    missing = [c for c in [step.start_column, step.end_column] if c not in df.columns]
    if missing:
        raise ExecutionError(
            f"date_diff: column(s) {missing} not found. "
            f"Available columns: {_available(df)}"
        )
    result = df.copy()
    try:
        start = pd.to_datetime(result[step.start_column], errors=step.errors)
        end = pd.to_datetime(result[step.end_column], errors=step.errors)
    except Exception as exc:
        raise ExecutionError(
            f"date_diff: could not parse date columns '{step.start_column}' and '{step.end_column}': {exc}"
        ) from exc
    diff = end - start
    if step.unit == "days":
        result[step.new_column] = diff.dt.days
    else:
        raise ExecutionError(f"date_diff: unknown unit '{step.unit}'.")
    computed = int(result[step.new_column].notna().sum())
    return (
        result,
        f"Computed date difference from '{step.start_column}' to '{step.end_column}' in {step.unit}.",
        StepMetrics(match_rate=_safe_rate(computed, len(df))),
    )


# --------------------------------------------------------------------------- #
# Analytical / diagnostic tool helpers (Task 7)
# --------------------------------------------------------------------------- #

def _validate_single_analytic_column(step_type: str):
    """Factory: return a validator that checks a single `column` field exists."""
    def _validate(step: WorkflowStep, col_set: set[str], label: str) -> None:
        col = getattr(step, "column", None)
        if col:
            _require_columns([col], col_set, label)
    return _validate


def _validate_profile_column(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, ProfileColumnStep)
    _require_columns([step.column], col_set, label)


def _execute_profile_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, ProfileColumnStep)
    col = step.column
    if col not in df.columns:
        raise ExecutionError(f"profile_column: column '{col}' not found. Available: {_available(df)}")
    series = df[col]
    total = len(series)
    non_null = int(series.notna().sum())
    missing_pct = round(100.0 * (total - non_null) / total, 1) if total else 0.0
    unique_count = int(series.nunique(dropna=True))
    top_vals = series.value_counts(dropna=True).head(5)
    top_str = ", ".join(f"{v}({c})" for v, c in top_vals.items())
    rows: list[tuple] = [
        ("column", col),
        ("dtype", str(series.dtype)),
        ("total_rows", total),
        ("non_null_count", non_null),
        ("missing_pct", f"{missing_pct}%"),
        ("unique_count", unique_count),
        ("top_values", top_str),
    ]
    if pd.api.types.is_numeric_dtype(series):
        rows.append(("min", series.min()))
        rows.append(("max", series.max()))
        rows.append(("mean", round(float(series.mean()), 4) if non_null > 0 else None))
    result = pd.DataFrame(rows, columns=["stat", "value"])
    msg = f"Profile of '{col}': {series.dtype}, {missing_pct}% missing, {unique_count} unique values."
    return result, msg, StepMetrics(affected_rate=0.0)


def _validate_inspect_unique_values(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, InspectUniqueValuesStep)
    _require_columns([step.column], col_set, label)


def _execute_inspect_unique_values(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, InspectUniqueValuesStep)
    col = step.column
    if col not in df.columns:
        raise ExecutionError(f"inspect_unique_values: column '{col}' not found. Available: {_available(df)}")
    counts = df[col].value_counts(dropna=False).head(step.max_values).reset_index()
    counts.columns = ["value", "count"]
    if len(df) > 0:
        counts["pct"] = (counts["count"] / len(df) * 100).round(1)
    else:
        counts["pct"] = 0.0
    msg = f"Top {len(counts)} unique values in '{col}' (of {df[col].nunique(dropna=False)} total)."
    return counts, msg, StepMetrics(affected_rate=0.0)


def _execute_summarize_numeric_column(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, SummarizeNumericColumnStep)
    col = step.column
    if col not in df.columns:
        raise ExecutionError(f"summarize_numeric_column: column '{col}' not found. Available: {_available(df)}")
    if not pd.api.types.is_numeric_dtype(df[col]):
        raise ExecutionError(f"summarize_numeric_column: column '{col}' is not numeric (dtype={df[col].dtype}).")
    series = df[col].dropna()
    if series.empty:
        raise ExecutionError(f"summarize_numeric_column: column '{col}' has no non-null values.")
    q25 = float(series.quantile(0.25))
    q75 = float(series.quantile(0.75))
    iqr = q75 - q25
    lower = q25 - 1.5 * iqr
    upper = q75 + 1.5 * iqr
    outlier_count = int(((series < lower) | (series > upper)).sum())
    rows: list[tuple] = [
        ("count", int(series.count())),
        ("mean", round(float(series.mean()), 4)),
        ("median", round(float(series.median()), 4)),
        ("std", round(float(series.std()), 4)),
        ("min", float(series.min())),
        ("q25", q25),
        ("q75", q75),
        ("max", float(series.max())),
        ("outlier_count_iqr", outlier_count),
    ]
    result = pd.DataFrame(rows, columns=["stat", "value"])
    msg = (
        f"Numeric summary of '{col}': "
        f"mean={rows[1][1]}, median={rows[2][1]}, "
        f"{outlier_count} IQR outliers."
    )
    return result, msg, StepMetrics(affected_rate=0.0)


def _validate_compare_groups(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, CompareGroupsStep)
    _require_columns([step.group_column, step.value_column], col_set, label)


def _execute_compare_groups(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, CompareGroupsStep)
    for col in (step.group_column, step.value_column):
        if col not in df.columns:
            raise ExecutionError(f"compare_groups: column '{col}' not found. Available: {_available(df)}")
    if not pd.api.types.is_numeric_dtype(df[step.value_column]):
        raise ExecutionError(
            f"compare_groups: value_column '{step.value_column}' is not numeric "
            f"(dtype={df[step.value_column].dtype})."
        )
    grouped = (
        df.groupby(step.group_column)[step.value_column]
        .agg([step.agg, "count"])
        .reset_index()
    )
    grouped.columns = [step.group_column, step.agg, "count"]
    grouped = grouped.sort_values(step.agg, ascending=False).reset_index(drop=True)
    msg = (
        f"Compared '{step.value_column}' by '{step.group_column}' "
        f"({step.agg}): {len(grouped)} groups."
    )
    return grouped, msg, StepMetrics(affected_rate=0.0)


def _validate_correlation_summary(step: WorkflowStep, col_set: set[str], label: str) -> None:
    assert isinstance(step, CorrelationSummaryStep)
    if step.columns:
        _require_columns(step.columns, col_set, label)


def _execute_correlation_summary(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, CorrelationSummaryStep)
    if step.columns:
        for col in step.columns:
            if col not in df.columns:
                raise ExecutionError(f"correlation_summary: column '{col}' not found. Available: {_available(df)}")
        num_df = df[step.columns].select_dtypes(include="number")
    else:
        num_df = df.select_dtypes(include="number")
    if num_df.shape[1] < 2:
        raise ExecutionError(
            "correlation_summary: at least 2 numeric columns are required. "
            f"Found: {list(num_df.columns)}"
        )
    corr = num_df.corr(numeric_only=True).round(4)
    stacked = corr.stack().reset_index()
    stacked.columns = ["col_a", "col_b", "correlation"]
    pairs = stacked[stacked["col_a"] < stacked["col_b"]].copy()
    pairs = pairs.sort_values("correlation", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)
    msg = f"Correlations between {list(num_df.columns)}: {len(pairs)} pairs computed."
    return pairs, msg, StepMetrics(affected_rate=0.0)


def _execute_distribution_summary(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    assert isinstance(step, DistributionSummaryStep)
    col = step.column
    if col not in df.columns:
        raise ExecutionError(f"distribution_summary: column '{col}' not found. Available: {_available(df)}")
    if not pd.api.types.is_numeric_dtype(df[col]):
        raise ExecutionError(f"distribution_summary: column '{col}' is not numeric (dtype={df[col].dtype}).")
    series = df[col].dropna()
    if series.empty:
        raise ExecutionError(f"distribution_summary: column '{col}' has no non-null values.")
    q25 = float(series.quantile(0.25))
    q75 = float(series.quantile(0.75))
    iqr = q75 - q25
    lower = q25 - 1.5 * iqr
    upper = q75 + 1.5 * iqr
    outlier_count = int(((series < lower) | (series > upper)).sum())
    skewness = round(float(series.skew()), 4)
    if abs(skewness) < 0.5:
        skew_label = "symmetric"
    elif skewness > 0:
        skew_label = "right-skewed"
    else:
        skew_label = "left-skewed"
    rows: list[tuple] = [
        ("count", int(series.count())),
        ("min", float(series.min())),
        ("q25", q25),
        ("median", round(float(series.median()), 4)),
        ("q75", q75),
        ("max", float(series.max())),
        ("std", round(float(series.std()), 4)),
        ("skewness", skewness),
        ("skew_label", skew_label),
        ("outlier_count_iqr", outlier_count),
    ]
    result = pd.DataFrame(rows, columns=["stat", "value"])
    msg = (
        f"Distribution of '{col}': {skew_label} "
        f"(skew={skewness}), {outlier_count} IQR outliers."
    )
    return result, msg, StepMetrics(affected_rate=0.0)


def _execute_suggest_analysis_steps(step: WorkflowStep, df: pd.DataFrame) -> tuple[pd.DataFrame, str, StepMetrics]:
    suggestions: list[str] = []
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = [
        c for c in df.columns
        if c not in numeric_cols and df[c].nunique(dropna=True) <= 30
    ]
    missing_cols = [c for c in df.columns if df[c].isnull().any()]
    if numeric_cols:
        suggestions.append(
            f"Use summarize_numeric_column on '{numeric_cols[0]}' to inspect its distribution."
        )
    if cat_cols and numeric_cols:
        suggestions.append(
            f"Use compare_groups with group_column='{cat_cols[0]}' and "
            f"value_column='{numeric_cols[0]}' to compare groups."
        )
    if len(numeric_cols) >= 2:
        suggestions.append(
            "Use correlation_summary to explore numeric column relationships."
        )
    if missing_cols:
        suggestions.append(
            f"Columns with missing values: {missing_cols}. "
            "Consider remove_missing_values or fill_missing_values."
        )
    if cat_cols:
        suggestions.append(
            f"Use inspect_unique_values on '{cat_cols[0]}' to see actual category values."
        )
    if not suggestions:
        msg = "No specific analysis suggestions for this dataset."
    else:
        msg = "Suggested next steps:\n" + "\n".join(f"- {s}" for s in suggestions)
    return df, msg, StepMetrics(affected_rate=0.0)


_REGISTRY: dict[str, ToolSpec] = {
    "remove_missing_values": ToolSpec(
        type="remove_missing_values",
        description="Remove rows containing missing values.",
        input_schema=_schema(RemoveMissingValuesStep),
        validate=_validate_noop,
        execute=_execute_remove_missing_values,
        examples=[{"type": "remove_missing_values"}],
        risk_profile={"can_reduce_rows": True, "warning_codes": ["empty_output", "affects_most_rows"]},
    ),
    "select_columns": ToolSpec(
        type="select_columns",
        description="Keep only selected columns.",
        input_schema=_schema(SelectColumnsStep),
        validate=_validate_select_columns,
        execute=_execute_select_columns,
        advance_columns=_advance_select_columns,
        examples=[{"type": "select_columns", "columns": ["region", "amount"]}],
        risk_profile={"can_change_columns": True},
    ),
    "filter_rows": ToolSpec(
        type="filter_rows",
        description="Keep rows where a column satisfies a comparison.",
        input_schema=_schema(FilterRowsStep),
        validate=_validate_filter_rows,
        execute=_execute_filter_rows,
        examples=[{"type": "filter_rows", "column": "amount", "operator": ">", "value": 1000}],
        risk_profile={"can_reduce_rows": True, "warning_codes": ["empty_output", "no_rows_matched", "affects_most_rows"]},
    ),
    "group_by": ToolSpec(
        type="group_by",
        description="Group rows by one or more columns and aggregate a target column.",
        input_schema=_schema(GroupByStep),
        validate=_validate_group_by,
        execute=_execute_group_by,
        advance_columns=_advance_group_by,
        examples=[{"type": "group_by", "column": "region", "target": "amount", "agg": "sum"}],
        risk_profile={"can_reduce_rows": True, "can_change_columns": True},
    ),
    "sort_values": ToolSpec(
        type="sort_values",
        description="Sort rows by a column.",
        input_schema=_schema(SortValuesStep),
        validate=_validate_sort_values,
        execute=_execute_sort_values,
        examples=[{"type": "sort_values", "column": "amount", "ascending": False}],
        risk_profile={},
    ),
    "rename_columns": ToolSpec(
        type="rename_columns",
        description="Rename columns using a source-to-target mapping.",
        input_schema=_schema(RenameColumnsStep),
        validate=_validate_rename_columns,
        execute=_execute_rename_columns,
        advance_columns=_advance_rename_columns,
        examples=[{"type": "rename_columns", "mapping": {"amount": "total_amount"}}],
        risk_profile={"can_change_columns": True},
    ),
    "generate_summary": ToolSpec(
        type="generate_summary",
        description="Request a grounded natural-language summary after execution.",
        input_schema=_schema(GenerateSummaryStep),
        validate=_validate_noop,
        execute=_execute_generate_summary,
        examples=[{"type": "generate_summary"}],
        risk_profile={},
    ),
    "limit_rows": ToolSpec(
        type="limit_rows",
        description="Keep the first n rows.",
        input_schema=_schema(LimitRowsStep),
        validate=_validate_limit_rows,
        execute=_execute_limit_rows,
        examples=[{"type": "limit_rows", "n": 10}],
        risk_profile={"can_reduce_rows": True, "warning_codes": ["empty_output", "affects_most_rows"]},
    ),
    "derive_column": ToolSpec(
        type="derive_column",
        description="Create a new column from arithmetic on a source column.",
        input_schema=_schema(DeriveColumnStep),
        validate=_validate_derive_column,
        execute=_execute_derive_column,
        advance_columns=_advance_derive_column,
        examples=[{"type": "derive_column", "new_column": "total", "column": "amount", "operator": "*", "other_column": "quantity"}],
        risk_profile={"can_change_columns": True},
    ),
    "date_extract": ToolSpec(
        type="date_extract",
        description="Extract a date part into a new column.",
        input_schema=_schema(DateExtractStep),
        validate=_validate_date_extract,
        execute=_execute_date_extract,
        advance_columns=_advance_date_extract,
        examples=[{"type": "date_extract", "column": "order_date", "part": "month", "new_column": "order_month"}],
        risk_profile={"can_change_columns": True},
    ),
    "drop_columns": ToolSpec(
        type="drop_columns",
        description="Remove selected columns.",
        input_schema=_schema(DropColumnsStep),
        validate=_validate_drop_columns,
        execute=_execute_drop_columns,
        advance_columns=_advance_drop_columns,
        examples=[{"type": "drop_columns", "columns": ["notes"]}],
        risk_profile={"can_change_columns": True},
    ),
    "fill_missing_values": ToolSpec(
        type="fill_missing_values",
        description="Fill missing values in one column with a strategy.",
        input_schema=_schema(FillMissingValuesStep),
        validate=_validate_fill_missing_values,
        execute=_execute_fill_missing_values,
        examples=[{"type": "fill_missing_values", "column": "amount", "strategy": "mean"}],
        risk_profile={"can_modify_values": True},
    ),
    "deduplicate_rows": ToolSpec(
        type="deduplicate_rows",
        description="Remove duplicate rows using all columns or a subset of columns.",
        input_schema=_schema(DeduplicateRowsStep),
        validate=_validate_deduplicate_rows,
        execute=_execute_deduplicate_rows,
        examples=[{"type": "deduplicate_rows", "columns": ["customer_id"], "keep": "first"}],
        risk_profile={"can_reduce_rows": True, "warning_codes": ["empty_output", "affects_most_rows"]},
    ),
    "replace_values": ToolSpec(
        type="replace_values",
        description="Replace values in one column using an explicit mapping.",
        input_schema=_schema(ReplaceValuesStep),
        validate=_validate_replace_values,
        execute=_execute_replace_values,
        examples=[{"type": "replace_values", "column": "status", "mapping": {"N/A": "unknown"}}],
        risk_profile={"can_modify_values": True},
    ),
    "cast_column": ToolSpec(
        type="cast_column",
        description="Cast one column to string, int, float, boolean, or datetime.",
        input_schema=_schema(CastColumnStep),
        validate=_validate_cast_column,
        execute=_execute_cast_column,
        examples=[{"type": "cast_column", "column": "amount", "target_type": "float", "errors": "raise"}],
        risk_profile={"can_modify_values": True},
    ),
    "conditional_column": ToolSpec(
        type="conditional_column",
        description="Create a new column using true/false values from a condition.",
        input_schema=_schema(ConditionalColumnStep),
        validate=_validate_conditional_column,
        execute=_execute_conditional_column,
        advance_columns=_advance_add_new_column,
        examples=[{
            "type": "conditional_column",
            "new_column": "is_large",
            "condition_column": "amount",
            "operator": ">",
            "value": 1000,
            "true_value": True,
            "false_value": False,
        }],
        risk_profile={"can_change_columns": True, "can_modify_values": True},
    ),
    "bin_column": ToolSpec(
        type="bin_column",
        description="Bucket a numeric column into intervals and store labels in a new column.",
        input_schema=_schema(BinColumnStep),
        validate=_validate_bin_column,
        execute=_execute_bin_column,
        advance_columns=_advance_add_new_column,
        examples=[{
            "type": "bin_column",
            "column": "amount",
            "new_column": "amount_band",
            "bins": [0, 100, 1000, 10000],
            "labels": ["low", "medium", "high"],
        }],
        risk_profile={"can_change_columns": True},
    ),
    "pivot_table": ToolSpec(
        type="pivot_table",
        description="Create a pivot table from index, optional columns, values, and aggregation.",
        input_schema=_schema(PivotTableStep),
        validate=_validate_pivot_table,
        execute=_execute_pivot_table,
        advance_columns=_advance_pivot_table,
        examples=[{"type": "pivot_table", "index": ["region"], "columns": "category", "values": "amount", "agg": "sum"}],
        risk_profile={"can_reduce_rows": True, "can_change_columns": True},
    ),
    "trim_text": ToolSpec(
        type="trim_text",
        description="Trim leading/trailing whitespace in one text column, optionally collapsing repeated whitespace.",
        input_schema=_schema(TrimTextStep),
        validate=_validate_trim_text,
        execute=_execute_trim_text,
        examples=[{"type": "trim_text", "column": "customer_name", "collapse_whitespace": True}],
        risk_profile={"can_modify_values": True},
    ),
    "normalize_text": ToolSpec(
        type="normalize_text",
        description="Normalize text case in one column using lower, upper, or title case.",
        input_schema=_schema(NormalizeTextStep),
        validate=_validate_normalize_text,
        execute=_execute_normalize_text,
        examples=[{"type": "normalize_text", "column": "status", "case": "lower"}],
        risk_profile={"can_modify_values": True},
    ),
    "extract_text": ToolSpec(
        type="extract_text",
        description="Extract text from one column into a new column using a validated regex group.",
        input_schema=_schema(ExtractTextStep),
        validate=_validate_extract_text,
        execute=_execute_extract_text,
        advance_columns=_advance_add_new_column,
        examples=[{"type": "extract_text", "column": "order_code", "pattern": "([A-Z]+)-\\d+", "new_column": "order_prefix", "group": 1}],
        risk_profile={"can_change_columns": True},
    ),
    "date_diff": ToolSpec(
        type="date_diff",
        description="Compute the day difference between two date columns into a new column.",
        input_schema=_schema(DateDiffStep),
        validate=_validate_date_diff,
        execute=_execute_date_diff,
        advance_columns=_advance_add_new_column,
        examples=[{"type": "date_diff", "start_column": "order_date", "end_column": "ship_date", "new_column": "ship_days", "unit": "days"}],
        risk_profile={"can_change_columns": True},
    ),
    # ------------------------------------------------------------------ #
    # Analytical / diagnostic tools (Task 7)
    # ------------------------------------------------------------------ #
    "profile_column": ToolSpec(
        type="profile_column",
        description="Return a stat/value profile of a single column: dtype, missing%, unique count, top values, min/max.",
        input_schema=_schema(ProfileColumnStep),
        validate=_validate_profile_column,
        execute=_execute_profile_column,
        examples=[{"type": "profile_column", "column": "amount"}],
        risk_profile={},
    ),
    "inspect_unique_values": ToolSpec(
        type="inspect_unique_values",
        description="Return the top unique values and their counts for a column.",
        input_schema=_schema(InspectUniqueValuesStep),
        validate=_validate_inspect_unique_values,
        execute=_execute_inspect_unique_values,
        examples=[{"type": "inspect_unique_values", "column": "region", "max_values": 20}],
        risk_profile={},
    ),
    "summarize_numeric_column": ToolSpec(
        type="summarize_numeric_column",
        description="Return count, mean, median, std, min/max, quartiles, and IQR outlier count for a numeric column.",
        input_schema=_schema(SummarizeNumericColumnStep),
        validate=_validate_single_analytic_column("summarize_numeric_column"),
        execute=_execute_summarize_numeric_column,
        examples=[{"type": "summarize_numeric_column", "column": "sales"}],
        risk_profile={},
    ),
    "compare_groups": ToolSpec(
        type="compare_groups",
        description="Compare a numeric column across groups of a categorical column using an aggregation function.",
        input_schema=_schema(CompareGroupsStep),
        validate=_validate_compare_groups,
        execute=_execute_compare_groups,
        examples=[{"type": "compare_groups", "group_column": "region", "value_column": "sales", "agg": "mean"}],
        risk_profile={},
    ),
    "correlation_summary": ToolSpec(
        type="correlation_summary",
        description="Return pairwise Pearson correlations between numeric columns, sorted by absolute value.",
        input_schema=_schema(CorrelationSummaryStep),
        validate=_validate_correlation_summary,
        execute=_execute_correlation_summary,
        examples=[{"type": "correlation_summary", "columns": []}],
        risk_profile={},
    ),
    "distribution_summary": ToolSpec(
        type="distribution_summary",
        description="Return quartiles, skewness, and IQR-based outlier count for a numeric column.",
        input_schema=_schema(DistributionSummaryStep),
        validate=_validate_single_analytic_column("distribution_summary"),
        execute=_execute_distribution_summary,
        examples=[{"type": "distribution_summary", "column": "price"}],
        risk_profile={},
    ),
    "suggest_analysis_steps": ToolSpec(
        type="suggest_analysis_steps",
        description="Inspect the dataset schema and emit next-step suggestions as a message. Does not modify data.",
        input_schema=_schema(SuggestAnalysisStepsStep),
        validate=_validate_noop,
        execute=_execute_suggest_analysis_steps,
        examples=[{"type": "suggest_analysis_steps"}],
        risk_profile={},
    ),
}
