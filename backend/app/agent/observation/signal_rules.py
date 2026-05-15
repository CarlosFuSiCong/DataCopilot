"""Deterministic rules that turn runtime evidence into Agent observations."""
from __future__ import annotations

from collections.abc import Iterable

from app.agent.observation import risk_rules
from app.agent.observation.models import ObservationSummary
from app.models.workflow_execution import StepResult
from app.models.workflow_transport import PreviewResponse

_HIGH_WARNING_RATE = 0.5
_MIN_WARNINGS_FOR_HIGH_RATE = 2
_STRUCTURAL_STEP_TYPES = {
    "select_columns",
    "drop_columns",
    "rename_columns",
    "derive_column",
    "date_extract",
    "group_by",
    "pivot_table",
}


def from_preview(
    preview_result: PreviewResponse,
    *,
    planned_steps: list[dict] | None = None,
    workflow_state: str | None = None,
) -> ObservationSummary:
    """Build an observation from preview execution evidence."""
    planned_steps = planned_steps or preview_result.planned_steps
    signals: list[str] = []
    possible_causes: list[str] = []

    if _has_empty_result(preview_result.step_results):
        signals.append("empty_result")
        possible_causes.extend(_empty_result_causes(preview_result.step_results, planned_steps))

    if _has_large_row_removal(preview_result.step_results):
        signals.append("large_row_removal")
        possible_causes.append("a filter step removed a large fraction of input rows")

    if _has_high_warning_rate(preview_result.step_results):
        signals.append("high_warning_rate")
        possible_causes.append("multiple workflow steps produced warnings")

    if _has_execution_error(preview_result.step_results):
        signals.append("execution_error")
        possible_causes.append("a workflow step failed during deterministic execution")

    if _schema_changed(preview_result.step_results, planned_steps):
        signals.append("schema_changed")
        possible_causes.append("the workflow changed the available columns")

    if preview_result.has_errors:
        status = "error"
        recommended_next_action = "stop_with_error"
    elif signals:
        status = "warning"
        recommended_next_action = "confirm_required"
    else:
        status = "ok"
        recommended_next_action = "stop_with_result"

    return ObservationSummary(
        status=status,
        signals=_dedupe(signals),
        message=_message(signals, preview_result),
        possible_causes=_dedupe(possible_causes),
        recommended_next_action=recommended_next_action,
        workflow_state=workflow_state,
    )


def from_validation_failure(
    message: str,
    *,
    workflow_state: str | None = "validation_failed",
) -> ObservationSummary:
    return ObservationSummary(
        status="error",
        signals=["validation_failed"],
        message=message,
        possible_causes=[
            "the workflow references a column or parameter that validation rejected",
            "the user request may need clarification against the active dataset schema",
        ],
        recommended_next_action="clarify",
        workflow_state=workflow_state,
    )


def from_execution_error(
    message: str,
    *,
    workflow_state: str | None = "failed",
) -> ObservationSummary:
    return ObservationSummary(
        status="error",
        signals=["execution_error"],
        message=message,
        possible_causes=[
            "a workflow step could not be executed with the current dataset values",
            "the workflow may need replanning or corrected parameters",
        ],
        recommended_next_action="stop_with_error",
        workflow_state=workflow_state,
    )


def _has_empty_result(step_results: Iterable[StepResult]) -> bool:
    return any(
        result.output_row_count == 0
        or any(issue.code == risk_rules.EMPTY_OUTPUT for issue in result.issues)
        for result in step_results
    )


def _has_large_row_removal(step_results: Iterable[StepResult]) -> bool:
    return any(
        any(issue.code == risk_rules.LARGE_ROW_REMOVAL for issue in result.issues)
        for result in step_results
    )


def _has_high_warning_rate(step_results: list[StepResult]) -> bool:
    if not step_results:
        return False
    warning_steps = sum(1 for result in step_results if result.status == "warning")
    return warning_steps >= _MIN_WARNINGS_FOR_HIGH_RATE and (warning_steps / len(step_results)) >= _HIGH_WARNING_RATE


def _has_execution_error(step_results: Iterable[StepResult]) -> bool:
    return any(
        result.status == "error"
        or any(issue.code == "execution_error" for issue in result.issues)
        for result in step_results
    )


def _schema_changed(step_results: Iterable[StepResult], planned_steps: list[dict]) -> bool:
    if any(result.input_column_count != result.output_column_count for result in step_results):
        return True
    return any(str(step.get("type")) in _STRUCTURAL_STEP_TYPES for step in planned_steps)


def _empty_result_causes(step_results: list[StepResult], planned_steps: list[dict]) -> list[str]:
    causes: list[str] = []
    for result in step_results:
        if result.output_row_count != 0:
            continue
        step = _planned_step(planned_steps, result.step_index)
        if result.step_type == "filter_rows" or step.get("type") == "filter_rows":
            operator = str(step.get("operator", ""))
            if operator in {">", ">=", "<", "<="}:
                causes.append("filter_too_strict")
            if operator in {"=", "!="}:
                causes.append("wrong_value")
            if result.match_rate == 0 or any(issue.code == risk_rules.NO_ROWS_MATCHED for issue in result.issues):
                causes.append("valid_no_match")
        else:
            causes.append("upstream_step_removed_all_rows")
    return causes or ["result contains no rows after workflow execution"]


def _planned_step(planned_steps: list[dict], step_index: int) -> dict:
    if 0 <= step_index < len(planned_steps):
        return planned_steps[step_index]
    return {}


def _message(signals: list[str], preview_result: PreviewResponse) -> str:
    if preview_result.has_errors:
        return "Observation found a blocking execution error."
    if "empty_result" in signals:
        return "Observation found that the workflow can produce an empty result."
    if "large_row_removal" in signals:
        return "Observation found that the filter removes a large fraction of input rows."
    if signals:
        return "Observation found workflow warnings that should be reviewed."
    return "Observation did not find workflow warnings or errors."


def _dedupe(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
