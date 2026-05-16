"""Deterministic rules that turn runtime evidence into Agent observations."""
from __future__ import annotations

from collections.abc import Iterable

from app.agent.observation import risk_rules
from app.agent.observation.models import CandidateFix, ObservationSummary
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

    # Task 6 – deeper diagnostic signals
    if _suspected_wrong_column(preview_result.step_results):
        signals.append("suspected_wrong_column")
        possible_causes.append("a referenced column may not exist in the dataset schema")

    if _suspected_wrong_value(preview_result.step_results, planned_steps):
        signals.append("suspected_wrong_value")
        possible_causes.append("the filter value does not match any rows; the value may be incorrect")

    if _has_data_quality_issue(preview_result.step_results):
        signals.append("data_quality_issue")
        possible_causes.append("missing or inconsistent values may have affected the result")

    if _needs_inspection(signals):
        signals.append("needs_inspection")
        possible_causes.append("the result warrants manual inspection before drawing conclusions")

    if preview_result.has_errors:
        status = "error"
        recommended_next_action = "stop_with_error"
    elif signals:
        status = "warning"
        recommended_next_action = "confirm_required"
    else:
        status = "ok"
        recommended_next_action = "stop_with_result"

    deduped_signals = _dedupe(signals)
    deduped_causes = _dedupe(possible_causes)

    return ObservationSummary(
        status=status,
        signals=deduped_signals,
        message=_message(deduped_signals, preview_result),
        possible_causes=deduped_causes,
        recommended_next_action=recommended_next_action,
        workflow_state=workflow_state,
        diagnostic_explanation=_diagnostic_explanation(deduped_signals, preview_result),
        candidate_fixes=_candidate_fixes(deduped_signals, preview_result.step_results, planned_steps),
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
        diagnostic_explanation=(
            "Validation rejected the workflow before execution. "
            "The referenced column or parameter does not match the active dataset schema."
        ),
        candidate_fixes=[
            CandidateFix(
                action="check_column_name",
                rationale="Verify the column name against the dataset schema.",
            ),
            CandidateFix(
                action="clarify_request",
                rationale="Ask the user to confirm the intended column or parameter.",
            ),
        ],
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
        diagnostic_explanation=(
            "A workflow step raised an execution error. "
            "This often means the data does not match the expected format for the chosen operation."
        ),
        candidate_fixes=[
            CandidateFix(
                action="replan_workflow",
                rationale="Replan the workflow with corrected step parameters.",
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Existing detection helpers
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Task 6 – new detection helpers
# --------------------------------------------------------------------------- #

def _suspected_wrong_column(step_results: Iterable[StepResult]) -> bool:
    """True when any step has a missing_column issue from the validator."""
    return any(
        any(issue.code == risk_rules.MISSING_COLUMN for issue in result.issues)
        for result in step_results
    )


def _suspected_wrong_value(step_results: list[StepResult], planned_steps: list[dict]) -> bool:
    """True when a filter_rows step produces zero rows with an eq/ne operator.

    This is a stronger signal than the generic empty_result: the column likely
    exists but the provided value doesn't match any row in the dataset.
    """
    for result in step_results:
        if result.output_row_count != 0:
            continue
        step = _planned_step(planned_steps, result.step_index)
        step_type = result.step_type or step.get("type", "")
        if step_type != "filter_rows":
            continue
        operator = str(step.get("operator", ""))
        if operator in {"=", "eq", "!=", "ne"}:
            return True
    return False


def _has_data_quality_issue(step_results: Iterable[StepResult]) -> bool:
    """True when any step signals potential data quality problems.

    Currently triggered by the affects_most_rows risk code on non-filter steps
    (e.g., many missing values that caused rows to be dropped by clean steps).
    """
    return any(
        result.step_type not in {"filter_rows"}
        and any(issue.code == risk_rules.AFFECTS_MOST_ROWS for issue in result.issues)
        for result in step_results
    )


def _needs_inspection(signals: list[str]) -> bool:
    """True when the observation contains signals that warrant further data inspection."""
    inspection_triggers = {"suspected_wrong_value", "suspected_wrong_column", "data_quality_issue", "empty_result"}
    return bool(inspection_triggers.intersection(signals))


# --------------------------------------------------------------------------- #
# Task 6 – diagnostic text and candidate fix generation
# --------------------------------------------------------------------------- #

def _diagnostic_explanation(signals: list[str], preview_result: PreviewResponse) -> str | None:
    if not signals:
        return None

    parts: list[str] = []

    if "suspected_wrong_column" in signals:
        parts.append(
            "A referenced column was not found in the dataset schema. "
            "Check column names for typos or use the dataset profile to see available columns."
        )
    if "suspected_wrong_value" in signals:
        parts.append(
            "The filter matched zero rows using an equality/inequality condition. "
            "The value may not exist in the column; inspect unique values to find valid options."
        )
    if "empty_result" in signals and "suspected_wrong_value" not in signals:
        parts.append(
            "The workflow produced an empty result. "
            "The filter condition may be too strict or the upstream data may have been removed."
        )
    if "large_row_removal" in signals:
        removed_pct = _max_removal_rate(preview_result.step_results)
        pct_str = f"{removed_pct:.0%}" if removed_pct is not None else "a large fraction"
        parts.append(
            f"A filter step removed {pct_str} of input rows. "
            "This may significantly affect downstream aggregation or analysis results."
        )
    if "data_quality_issue" in signals:
        parts.append(
            "Data quality issues were detected: some steps processed or removed a high proportion "
            "of rows, which may indicate missing or inconsistent values in the dataset."
        )
    if "high_warning_rate" in signals:
        parts.append(
            "Multiple workflow steps produced warnings. "
            "Review each step result before accepting the final output."
        )

    return " ".join(parts) if parts else None


def _candidate_fixes(
    signals: list[str],
    step_results: list[StepResult],
    planned_steps: list[dict],
) -> list[CandidateFix]:
    fixes: list[CandidateFix] = []

    if "suspected_wrong_column" in signals:
        fixes.append(CandidateFix(
            action="check_column_name",
            rationale="Verify the column name against the dataset schema.",
            evidence="A missing_column issue was raised during workflow execution.",
        ))

    if "suspected_wrong_value" in signals:
        col = _first_empty_filter_column(step_results, planned_steps)
        fixes.append(CandidateFix(
            action="inspect_unique_values",
            rationale="The filter value matched zero rows; inspect actual column values.",
            evidence=f"Column: {col}" if col else None,
        ))

    if "empty_result" in signals and "suspected_wrong_value" not in signals:
        fixes.append(CandidateFix(
            action="adjust_filter_threshold",
            rationale="Loosen the filter condition to include more rows.",
        ))

    if "large_row_removal" in signals:
        fixes.append(CandidateFix(
            action="confirm_filter_intent",
            rationale="Confirm that removing this fraction of rows is intentional.",
        ))

    if "data_quality_issue" in signals:
        fixes.append(CandidateFix(
            action="inspect_missing_values",
            rationale="Check for missing or null values that may affect the result.",
        ))

    if "needs_inspection" in signals:
        fixes.append(CandidateFix(
            action="profile_column",
            rationale="Profile the relevant column to understand its value distribution.",
        ))

    return fixes


def _max_removal_rate(step_results: list[StepResult]) -> float | None:
    rates = [
        1.0 - result.match_rate
        for result in step_results
        if result.match_rate is not None
        and any(issue.code == risk_rules.LARGE_ROW_REMOVAL for issue in result.issues)
    ]
    return max(rates) if rates else None


def _first_empty_filter_column(step_results: list[StepResult], planned_steps: list[dict]) -> str | None:
    for result in step_results:
        if result.output_row_count != 0:
            continue
        step = _planned_step(planned_steps, result.step_index)
        if step.get("type") == "filter_rows" or result.step_type == "filter_rows":
            col = step.get("column")
            if col:
                return str(col)
    return None


# --------------------------------------------------------------------------- #
# Shared utilities
# --------------------------------------------------------------------------- #

def _planned_step(planned_steps: list[dict], step_index: int) -> dict:
    if 0 <= step_index < len(planned_steps):
        return planned_steps[step_index]
    return {}


def _message(signals: list[str], preview_result: PreviewResponse) -> str:
    if preview_result.has_errors:
        return "Observation found a blocking execution error."
    if "suspected_wrong_column" in signals:
        return "Observation suspects a referenced column does not exist in the dataset."
    if "suspected_wrong_value" in signals:
        return "Observation suspects the filter value does not match any rows in the dataset."
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
