"""Pandas executor.

Runs a validated list of WorkflowStep against a DataFrame in order.
Returns an ExecutionResult with a preview, column list, and per-step logs.
"""
import io
import logging
import math
from dataclasses import dataclass

import pandas as pd

from app.core.exceptions import ExecutionError
from app.models.workflow import (
    ExecutionResult,
    FilterRowsStep,
    GenerateSummaryStep,
    GroupByStep,
    PreviewResponse,
    RemoveMissingValuesStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
    StepIssue,
    StepLog,
    StepResult,
    WorkflowStep,
)
from app.services import risk_rules

logger = logging.getLogger(__name__)

_PREVIEW_ROWS = 5
_FILTER_OPS = {
    "=": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
    ">": lambda s, v: s > v,
    ">=": lambda s, v: s >= v,
    "<": lambda s, v: s < v,
    "<=": lambda s, v: s <= v,
}
# Issue code used when a step raises ExecutionError at runtime (after validation).
_EXECUTION_ERROR_CODE = "execution_error"


@dataclass(frozen=True)
class _StepMetrics:
    match_rate: float | None = None
    affected_rate: float | None = None


def execute(steps: list[WorkflowStep], content: bytes) -> ExecutionResult:
    """Execute all steps sequentially and return the result."""
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ExecutionError(f"Failed to load dataset: {exc}") from exc

    logs: list[StepLog] = []
    step_results: list[StepResult] = []
    has_summary = False

    for idx, step in enumerate(steps):
        input_row_count = len(df)
        input_column_count = len(df.columns)
        df, message, metrics = _apply_step(step, df, idx)
        output_row_count = len(df)
        output_column_count = len(df.columns)
        issues = risk_rules.check(
            step_type=step.type,
            output_row_count=output_row_count,
            match_rate=metrics.match_rate,
            affected_rate=metrics.affected_rate,
        )
        status = risk_rules.worst_status(issues)
        step_results.append(
            StepResult(
                step_index=idx,
                step_type=step.type,
                status=status,
                issues=issues,
                input_row_count=input_row_count,
                output_row_count=output_row_count,
                input_column_count=input_column_count,
                output_column_count=output_column_count,
                match_rate=metrics.match_rate,
                affected_rate=metrics.affected_rate,
                preview=_to_preview(df),
                message=message,
            )
        )
        if status == "error":
            raise ExecutionError(
                f"Step {idx} ({step.type}) has a blocking error: "
                + "; ".join(i.message for i in issues if i.severity == "error")
            )
        logs.append(
            StepLog(
                step_index=idx,
                step_type=step.type,
                rows_before=input_row_count,
                rows_after=output_row_count,
                message=message,
            )
        )
        if isinstance(step, GenerateSummaryStep):
            has_summary = True

    preview = _to_preview(df)
    logger.info("Execution complete: %d rows, %d columns", len(df), len(df.columns))

    return ExecutionResult(
        row_count=len(df),
        column_count=len(df.columns),
        columns=list(df.columns),
        preview=preview,
        step_results=step_results,
        logs=logs,
        has_summary=has_summary,
    )


def preview(steps: list[WorkflowStep], content: bytes) -> PreviewResponse:
    """Run all steps for preview.

    Identical execution path to execute() — same validator, same risk rules —
    but errors are captured into StepResult instead of raised.  The result
    explainer is never called.  Execution stops at the first error step and
    reports blocked_at_step.
    """
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise ExecutionError(f"Failed to load dataset: {exc}") from exc

    step_results: list[StepResult] = []
    blocked_at_step: int | None = None

    for idx, step in enumerate(steps):
        input_row_count = len(df)
        input_column_count = len(df.columns)

        try:
            df, message, metrics = _apply_step(step, df, idx)
        except ExecutionError as exc:
            step_results.append(
                StepResult(
                    step_index=idx,
                    step_type=step.type,
                    status="error",
                    issues=[
                        StepIssue(
                            severity="error",
                            code=_EXECUTION_ERROR_CODE,
                            message=str(exc),
                        )
                    ],
                    input_row_count=input_row_count,
                    output_row_count=0,
                    input_column_count=input_column_count,
                    output_column_count=0,
                    preview=[],
                    message=str(exc),
                )
            )
            blocked_at_step = idx
            break

        output_row_count = len(df)
        output_column_count = len(df.columns)
        issues = risk_rules.check(
            step_type=step.type,
            output_row_count=output_row_count,
            match_rate=metrics.match_rate,
            affected_rate=metrics.affected_rate,
        )
        status = risk_rules.worst_status(issues)
        step_results.append(
            StepResult(
                step_index=idx,
                step_type=step.type,
                status=status,
                issues=issues,
                input_row_count=input_row_count,
                output_row_count=output_row_count,
                input_column_count=input_column_count,
                output_column_count=output_column_count,
                match_rate=metrics.match_rate,
                affected_rate=metrics.affected_rate,
                preview=_to_preview(df),
                message=message,
            )
        )
        if status == "error":
            blocked_at_step = idx
            break

    has_warnings = any(sr.status == "warning" for sr in step_results)
    has_errors = any(sr.status == "error" for sr in step_results)

    logger.info(
        "Preview complete: %d/%d steps, has_warnings=%s has_errors=%s",
        len(step_results),
        len(steps),
        has_warnings,
        has_errors,
    )

    return PreviewResponse(
        planned_steps=[s.model_dump() for s in steps],
        step_results=step_results,
        has_warnings=has_warnings,
        has_errors=has_errors,
        blocked_at_step=blocked_at_step,
    )


# ---------------------------------------------------------------------------
# Step handlers
# ---------------------------------------------------------------------------

def _apply_step(
    step: WorkflowStep, df: pd.DataFrame, idx: int
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    try:
        if isinstance(step, RemoveMissingValuesStep):
            return _remove_missing(df)
        if isinstance(step, SelectColumnsStep):
            return _select_columns(step, df)
        if isinstance(step, FilterRowsStep):
            return _filter_rows(step, df)
        if isinstance(step, GroupByStep):
            return _group_by(step, df)
        if isinstance(step, SortValuesStep):
            return _sort_values(step, df)
        if isinstance(step, RenameColumnsStep):
            return _rename_columns(step, df)
        if isinstance(step, GenerateSummaryStep):
            return (
                df,
                "Summary requested — will be generated by the explainer.",
                _StepMetrics(affected_rate=0.0),
            )
    except ExecutionError:
        raise
    except Exception as exc:
        raise ExecutionError(f"Step {idx} ({step.type}) failed: {exc}") from exc

    raise ExecutionError(f"Step {idx}: unknown step type '{step.type}'.")


def _remove_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, str, _StepMetrics]:
    before = len(df)
    result = df.dropna()
    removed = before - len(result)
    return (
        result.reset_index(drop=True),
        f"Removed {removed} rows with missing values.",
        _StepMetrics(affected_rate=_safe_rate(removed, before)),
    )


def _select_columns(
    step: SelectColumnsStep, df: pd.DataFrame
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    missing = [c for c in step.columns if c not in df.columns]
    if missing:
        raise ExecutionError(f"select_columns: columns not found: {missing}")
    return (
        df[step.columns].copy(),
        f"Selected columns: {step.columns}.",
        _StepMetrics(),
    )


def _filter_rows(
    step: FilterRowsStep, df: pd.DataFrame
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    if step.column not in df.columns:
        raise ExecutionError(f"filter_rows: column '{step.column}' not found.")
    op_fn = _FILTER_OPS[step.operator]
    mask = op_fn(df[step.column], step.value)
    result = df[mask].reset_index(drop=True)
    return (
        result,
        (
            f"Filtered '{step.column}' {step.operator} {step.value!r}: "
            f"{len(result)} rows kept."
        ),
        _StepMetrics(match_rate=_safe_rate(len(result), len(df))),
    )


def _group_by(
    step: GroupByStep, df: pd.DataFrame
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    for col in (step.column, step.target):
        if col not in df.columns:
            raise ExecutionError(f"group_by: column '{col}' not found.")
    result = (
        df.groupby(step.column, as_index=False)[step.target]
        .agg(step.agg)
        .reset_index(drop=True)
    )
    affected_rows = len(df) - len(result)
    return (
        result,
        f"Grouped by '{step.column}', aggregated '{step.target}' with {step.agg}.",
        _StepMetrics(affected_rate=_safe_rate(affected_rows, len(df))),
    )


def _sort_values(
    step: SortValuesStep, df: pd.DataFrame
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    if step.column not in df.columns:
        raise ExecutionError(f"sort_values: column '{step.column}' not found.")
    result = df.sort_values(by=step.column, ascending=step.ascending).reset_index(drop=True)
    direction = "ascending" if step.ascending else "descending"
    return result, f"Sorted by '{step.column}' {direction}.", _StepMetrics()


def _rename_columns(
    step: RenameColumnsStep, df: pd.DataFrame
) -> tuple[pd.DataFrame, str, _StepMetrics]:
    missing = [c for c in step.mapping if c not in df.columns]
    if missing:
        raise ExecutionError(f"rename_columns: columns not found: {missing}")
    result = df.rename(columns=step.mapping)
    return (
        result,
        f"Renamed columns: {step.mapping}.",
        _StepMetrics(),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_preview(df: pd.DataFrame) -> list[dict]:
    raw = df.head(_PREVIEW_ROWS).to_dict(orient="records")
    return [
        {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        for row in raw
    ]


def _safe_rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator
