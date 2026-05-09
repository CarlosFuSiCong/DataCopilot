"""Central registry for deterministic workflow tools.

The registry is the single dispatch table for transformation validation,
execution, planner metadata, RAG metadata, and editor metadata. Workflow JSON
remains the contract; each tool spec defines how one workflow step is checked
and applied.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from app.core.exceptions import ExecutionError, WorkflowValidationError
from app.models.workflow import (
    DateExtractStep,
    DeriveColumnStep,
    DropColumnsStep,
    FillMissingValuesStep,
    FilterRowsStep,
    GenerateSummaryStep,
    GroupByStep,
    LimitRowsStep,
    RemoveMissingValuesStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
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
}
