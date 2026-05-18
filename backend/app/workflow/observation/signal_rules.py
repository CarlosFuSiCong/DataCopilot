"""Deterministic rules that turn runtime evidence into Agent observations."""
from __future__ import annotations

from collections.abc import Iterable

from app.workflow.observation import risk_rules
from app.workflow.observation.models import CandidateFix, ObservationSummary
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
        diagnostic_explanation=_diagnostic_explanation(signals, possible_causes),
        possible_causes=_dedupe(possible_causes),
        candidate_fixes=_candidate_fixes(signals, possible_causes, preview_result.step_results, planned_steps),
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
        diagnostic_explanation=(
            "Validation rejected the workflow because a referenced column or parameter "
            "does not match the active dataset schema. The workflow cannot run until "
            "the column name or parameter is corrected."
        ),
        possible_causes=[
            "the workflow references a column or parameter that validation rejected",
            "the user request may need clarification against the active dataset schema",
        ],
        candidate_fixes=[
            CandidateFix(
                id="choose_column",
                label="Choose another column",
                description="Pick one of the available columns from your dataset.",
                action_type="suggest_query",
                query=None,
            ),
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
        diagnostic_explanation=(
            "A workflow step raised a runtime error during deterministic execution. "
            "This usually means the column type or value format is incompatible with "
            "the requested operation, or the step received unexpected input data."
        ),
        possible_causes=[
            "a workflow step could not be executed with the current dataset values",
            "the workflow may need corrected parameters",
        ],
        candidate_fixes=[
            CandidateFix(
                id="inspect_unique",
                label="Inspect unique values",
                description="Check what values are actually in the affected column.",
                action_type="inspect_column",
                query=None,
            ),
            CandidateFix(
                id="back_to_preview",
                label="Back to preview",
                description="Discard and try a different query.",
                action_type="back_to_preview",
                query=None,
            ),
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
    if signals:
        return "Observation found workflow warnings that should be reviewed."
    return "Observation did not find workflow warnings or errors."


def _dedupe(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped


# ---------------------------------------------------------------------------
# Diagnostic explanation
# ---------------------------------------------------------------------------

_SIGNAL_EXPLANATION: dict[str, str] = {
    "empty_result": (
        "The workflow produced zero rows after applying the requested operations. "
        "This is not an error, but the result is empty and may not be what was intended."
    ),
    "large_row_removal": (
        "A filter step removed a large portion of the dataset rows. "
        "This can be intentional but may also indicate that the filter condition is stricter than expected."
    ),
    "no_rows_matched": (
        "The filter condition matched no rows in the dataset. "
        "The filtered value may not exist, or the column name may be incorrect."
    ),
    "high_warning_rate": (
        "Multiple steps in the workflow produced warnings. "
        "Review each warning step to confirm the result is correct before executing."
    ),
    "execution_error": (
        "A step in the workflow failed during execution. "
        "The workflow cannot complete until the failing step is corrected."
    ),
    "validation_failed": (
        "The workflow references a column or parameter that is not valid for this dataset. "
        "Check that all column names and parameter values match the actual dataset."
    ),
    "schema_changed": (
        "The workflow modifies which columns are available in the output. "
        "Subsequent steps may operate on a reduced or restructured column set."
    ),
    "missing_column": (
        "A column referenced in the workflow does not exist in the current dataset. "
        "Use 'show schema' or 'inspect unique values' to explore available columns."
    ),
}


def _diagnostic_explanation(signals: list[str], possible_causes: list[str]) -> str | None:
    """Return the most specific explanation for the primary signal, or None if no signals."""
    for signal in signals:
        explanation = _SIGNAL_EXPLANATION.get(signal)
        if explanation:
            return explanation
    return None


# ---------------------------------------------------------------------------
# Candidate fixes
# ---------------------------------------------------------------------------

def _candidate_fixes(
    signals: list[str],
    possible_causes: list[str],
    step_results: list[StepResult],
    planned_steps: list[dict],
) -> list[CandidateFix]:
    """Return actionable fix suggestions based on observed signals and causes."""
    fixes: list[CandidateFix] = []

    if "empty_result" in signals or "no_rows_matched" in signals:
        # Find the filter step's column for inspect suggestion
        filter_col = _filter_column(step_results, planned_steps)
        if filter_col:
            fixes.append(CandidateFix(
                id="inspect_unique",
                label="Inspect unique values",
                description=f"See what values are in column '{filter_col}' to find a valid filter value.",
                action_type="inspect_column",
                query=f"inspect unique values of {filter_col}",
            ))
        fixes.append(CandidateFix(
            id="relax_filter",
            label="Relax filter",
            description="Try a less restrictive filter condition.",
            action_type="relax_filter",
            query=None,
        ))
        if filter_col:
            fixes.append(CandidateFix(
                id="choose_column",
                label="Choose another column",
                description="Filter on a different column instead.",
                action_type="suggest_query",
                query=None,
            ))

    if "large_row_removal" in signals:
        filter_col = _filter_column(step_results, planned_steps)
        if filter_col:
            fixes.append(CandidateFix(
                id="inspect_distribution",
                label="Check distribution",
                description=f"Profile column '{filter_col}' to understand its value range.",
                action_type="inspect_column",
                query=f"profile column {filter_col}",
            ))
        if not any(f.id == "relax_filter" for f in fixes):
            fixes.append(CandidateFix(
                id="relax_filter",
                label="Relax filter",
                description="Try a less strict filter threshold.",
                action_type="relax_filter",
                query=None,
            ))

    if "execution_error" in signals:
        fixes.append(CandidateFix(
            id="back_to_preview",
            label="Back to preview",
            description="Discard this workflow and start with a revised query.",
            action_type="back_to_preview",
            query=None,
        ))

    if "validation_failed" in signals or "missing_column" in signals:
        fixes.append(CandidateFix(
            id="choose_column",
            label="Choose another column",
            description="Pick from the columns that exist in your dataset.",
            action_type="suggest_query",
            query=None,
        ))

    return fixes


def _filter_column(step_results: list[StepResult], planned_steps: list[dict]) -> str | None:
    """Return the column referenced in the first filter step, if available."""
    for result in step_results:
        if result.step_type == "filter_rows":
            step = _planned_step(planned_steps, result.step_index)
            col = step.get("column")
            if col:
                return str(col)
    # fall back to planned steps
    for step in planned_steps:
        if step.get("type") == "filter_rows" and step.get("column"):
            return str(step["column"])
    return None
