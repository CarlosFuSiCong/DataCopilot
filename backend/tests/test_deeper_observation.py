"""Task 6 – Deeper Observation: unit tests for new signals, diagnostic_explanation,
and candidate_fixes introduced in signal_rules.py and models.py.
"""
import pytest

from app.agent.observation import signal_rules
from app.agent.observation.models import CandidateFix, ObservationSummary
from app.agent.observation.risk_rules import (
    AFFECTS_MOST_ROWS,
    EMPTY_OUTPUT,
    LARGE_ROW_REMOVAL,
    MISSING_COLUMN,
    NO_ROWS_MATCHED,
)
from app.models.workflow_execution import StepIssue, StepResult
from app.models.workflow_transport import PreviewResponse


# --------------------------------------------------------------------------- #
# Helpers (mirrors test_observation_rules.py so both suites stay independent)
# --------------------------------------------------------------------------- #

def _step_result(
    *,
    step_index: int = 0,
    step_type: str = "filter_rows",
    status: str = "success",
    issues: list[StepIssue] | None = None,
    input_rows: int = 100,
    output_rows: int = 100,
    input_columns: int = 3,
    output_columns: int = 3,
    match_rate: float | None = None,
) -> StepResult:
    return StepResult(
        step_index=step_index,
        step_type=step_type,
        status=status,
        issues=issues or [],
        input_row_count=input_rows,
        output_row_count=output_rows,
        input_column_count=input_columns,
        output_column_count=output_columns,
        affected_rows=abs(input_rows - output_rows),
        match_rate=match_rate,
        affected_rate=None,
        preview=[],
        message="test",
    )


def _preview(
    step_results: list[StepResult],
    planned_steps: list[dict] | None = None,
    has_errors: bool = False,
) -> PreviewResponse:
    return PreviewResponse(
        planned_steps=planned_steps or [{"type": r.step_type} for r in step_results],
        step_results=step_results,
        has_warnings=any(r.status == "warning" for r in step_results),
        has_errors=has_errors or any(r.status == "error" for r in step_results),
    )


# --------------------------------------------------------------------------- #
# New ObservationSummary fields exist (model-level)
# --------------------------------------------------------------------------- #

class TestObservationSummaryNewFields:
    def test_diagnostic_explanation_defaults_to_none(self):
        obs = ObservationSummary()
        assert obs.diagnostic_explanation is None

    def test_candidate_fixes_defaults_to_empty_list(self):
        obs = ObservationSummary()
        assert obs.candidate_fixes == []

    def test_candidate_fix_has_action_and_rationale(self):
        fix = CandidateFix(action="inspect_unique_values", rationale="Check values")
        assert fix.action == "inspect_unique_values"
        assert fix.rationale == "Check values"

    def test_candidate_fix_evidence_is_optional(self):
        fix = CandidateFix(action="check_column_name", rationale="Verify column")
        assert fix.evidence is None

    def test_candidate_fix_evidence_can_be_set(self):
        fix = CandidateFix(action="check_column_name", rationale="Verify", evidence="Column: amount")
        assert fix.evidence == "Column: amount"


# --------------------------------------------------------------------------- #
# New ObservationSignal literals are accepted by the model
# --------------------------------------------------------------------------- #

class TestNewObservationSignals:
    def test_suspected_wrong_column_is_valid_signal(self):
        obs = ObservationSummary(signals=["suspected_wrong_column"])
        assert "suspected_wrong_column" in obs.signals

    def test_suspected_wrong_value_is_valid_signal(self):
        obs = ObservationSummary(signals=["suspected_wrong_value"])
        assert "suspected_wrong_value" in obs.signals

    def test_data_quality_issue_is_valid_signal(self):
        obs = ObservationSummary(signals=["data_quality_issue"])
        assert "data_quality_issue" in obs.signals

    def test_needs_inspection_is_valid_signal(self):
        obs = ObservationSummary(signals=["needs_inspection"])
        assert "needs_inspection" in obs.signals


# --------------------------------------------------------------------------- #
# suspected_wrong_column signal
# --------------------------------------------------------------------------- #

class TestSuspectedWrongColumnSignal:
    def test_emitted_when_missing_column_issue_present(self):
        result = _step_result(
            output_rows=0,
            issues=[StepIssue(severity="error", code=MISSING_COLUMN, message="Column 'rev' not found")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert "suspected_wrong_column" in obs.signals

    def test_not_emitted_without_missing_column_issue(self):
        result = _step_result(output_rows=5)
        obs = signal_rules.from_preview(_preview([result]))
        assert "suspected_wrong_column" not in obs.signals

    def test_candidate_fix_included(self):
        result = _step_result(
            output_rows=0,
            issues=[StepIssue(severity="error", code=MISSING_COLUMN, message="not found")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        actions = [f.action for f in obs.candidate_fixes]
        assert "check_column_name" in actions

    def test_message_references_column(self):
        result = _step_result(
            output_rows=0,
            issues=[StepIssue(severity="error", code=MISSING_COLUMN, message="not found")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.message is not None
        assert "column" in obs.message.lower()

    def test_diagnostic_explanation_not_none(self):
        result = _step_result(
            output_rows=0,
            issues=[StepIssue(severity="error", code=MISSING_COLUMN, message="not found")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.diagnostic_explanation is not None


# --------------------------------------------------------------------------- #
# suspected_wrong_value signal
# --------------------------------------------------------------------------- #

class TestSuspectedWrongValueSignal:
    def test_emitted_for_eq_filter_with_zero_rows(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "active"}])
        )
        assert "suspected_wrong_value" in obs.signals

    def test_emitted_for_ne_filter_with_zero_rows(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "!=", "value": "X"}])
        )
        assert "suspected_wrong_value" in obs.signals

    def test_not_emitted_for_gt_filter_with_zero_rows(self):
        """gt/lt operators suggest filter_too_strict, not wrong value."""
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "amount", "operator": ">", "value": "9999"}])
        )
        assert "suspected_wrong_value" not in obs.signals

    def test_not_emitted_when_rows_exist(self):
        result = _step_result(output_rows=5, match_rate=0.5, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "active"}])
        )
        assert "suspected_wrong_value" not in obs.signals

    def test_candidate_fix_inspect_unique_values(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "active"}])
        )
        actions = [f.action for f in obs.candidate_fixes]
        assert "inspect_unique_values" in actions

    def test_candidate_fix_evidence_includes_column_name(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "X"}])
        )
        fix = next(f for f in obs.candidate_fixes if f.action == "inspect_unique_values")
        assert fix.evidence is not None
        assert "status" in fix.evidence

    def test_diagnostic_explanation_mentions_value(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "active"}])
        )
        assert obs.diagnostic_explanation is not None
        assert "value" in obs.diagnostic_explanation.lower()


# --------------------------------------------------------------------------- #
# data_quality_issue signal
# --------------------------------------------------------------------------- #

class TestDataQualityIssueSignal:
    def test_emitted_for_non_filter_affects_most_rows(self):
        result = _step_result(
            step_type="remove_missing_values",
            output_rows=5,
            input_rows=100,
            issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="95% affected")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert "data_quality_issue" in obs.signals

    def test_not_emitted_for_filter_rows_affects_most_rows(self):
        """Filter steps with affects_most_rows are expected; not a quality issue."""
        result = _step_result(
            step_type="filter_rows",
            output_rows=95,
            match_rate=0.95,
            issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="filter matches 95%")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert "data_quality_issue" not in obs.signals

    def test_candidate_fix_inspect_missing_values(self):
        result = _step_result(
            step_type="fill_missing_values",
            output_rows=5,
            input_rows=100,
            issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="affected")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        actions = [f.action for f in obs.candidate_fixes]
        assert "inspect_missing_values" in actions

    def test_diagnostic_explanation_mentions_data_quality(self):
        result = _step_result(
            step_type="remove_missing_values",
            output_rows=5,
            input_rows=100,
            issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="affected")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.diagnostic_explanation is not None
        assert "quality" in obs.diagnostic_explanation.lower() or "missing" in obs.diagnostic_explanation.lower()


# --------------------------------------------------------------------------- #
# needs_inspection signal
# --------------------------------------------------------------------------- #

class TestNeedsInspectionSignal:
    def test_emitted_when_empty_result(self):
        result = _step_result(output_rows=0, match_rate=0.0)
        obs = signal_rules.from_preview(_preview([result]))
        assert "needs_inspection" in obs.signals

    def test_emitted_when_suspected_wrong_value(self):
        result = _step_result(output_rows=0, match_rate=0.0, step_type="filter_rows")
        obs = signal_rules.from_preview(
            _preview([result], planned_steps=[{"type": "filter_rows", "column": "s", "operator": "=", "value": "X"}])
        )
        assert "needs_inspection" in obs.signals

    def test_not_emitted_for_normal_result(self):
        result = _step_result(output_rows=80, match_rate=0.8)
        obs = signal_rules.from_preview(_preview([result]))
        assert "needs_inspection" not in obs.signals

    def test_candidate_fix_profile_column_included(self):
        result = _step_result(output_rows=0, match_rate=0.0)
        obs = signal_rules.from_preview(_preview([result]))
        actions = [f.action for f in obs.candidate_fixes]
        assert "profile_column" in actions


# --------------------------------------------------------------------------- #
# diagnostic_explanation
# --------------------------------------------------------------------------- #

class TestDiagnosticExplanation:
    def test_none_when_no_signals(self):
        result = _step_result(output_rows=50, match_rate=0.5)
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.diagnostic_explanation is None

    def test_present_for_large_row_removal(self):
        result = _step_result(
            output_rows=20, input_rows=100, match_rate=0.2,
            issues=[StepIssue(severity="warning", code=LARGE_ROW_REMOVAL, message="removes 80%")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.diagnostic_explanation is not None
        assert "filter" in obs.diagnostic_explanation.lower() or "removed" in obs.diagnostic_explanation.lower()

    def test_present_for_empty_result(self):
        result = _step_result(output_rows=0, match_rate=0.0)
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.diagnostic_explanation is not None

    def test_from_validation_failure_has_explanation(self):
        obs = signal_rules.from_validation_failure("Column 'rev' not found")
        assert obs.diagnostic_explanation is not None
        assert "validation" in obs.diagnostic_explanation.lower() or "schema" in obs.diagnostic_explanation.lower()

    def test_from_execution_error_has_explanation(self):
        obs = signal_rules.from_execution_error("Step raised TypeError")
        assert obs.diagnostic_explanation is not None


# --------------------------------------------------------------------------- #
# candidate_fixes on validation failure and execution error
# --------------------------------------------------------------------------- #

class TestBuiltInCandidateFixes:
    def test_validation_failure_includes_check_column_name(self):
        obs = signal_rules.from_validation_failure("Column not found")
        actions = [f.action for f in obs.candidate_fixes]
        assert "check_column_name" in actions

    def test_validation_failure_includes_clarify_request(self):
        obs = signal_rules.from_validation_failure("Column not found")
        actions = [f.action for f in obs.candidate_fixes]
        assert "clarify_request" in actions

    def test_execution_error_includes_replan(self):
        obs = signal_rules.from_execution_error("TypeError")
        actions = [f.action for f in obs.candidate_fixes]
        assert "replan_workflow" in actions


# --------------------------------------------------------------------------- #
# No regression: existing signals still work
# --------------------------------------------------------------------------- #

class TestExistingSignalsUnchanged:
    def test_empty_result_signal_still_present(self):
        result = _step_result(output_rows=0, match_rate=0.0)
        obs = signal_rules.from_preview(_preview([result]))
        assert "empty_result" in obs.signals

    def test_large_row_removal_signal_still_present(self):
        result = _step_result(
            output_rows=20, input_rows=100, match_rate=0.2,
            issues=[StepIssue(severity="warning", code=LARGE_ROW_REMOVAL, message="removes 80%")],
        )
        obs = signal_rules.from_preview(_preview([result]))
        assert "large_row_removal" in obs.signals

    def test_validation_failed_signal_present(self):
        obs = signal_rules.from_validation_failure("test")
        assert "validation_failed" in obs.signals

    def test_execution_error_signal_present(self):
        obs = signal_rules.from_execution_error("test")
        assert "execution_error" in obs.signals

    def test_ok_status_for_normal_execution(self):
        result = _step_result(output_rows=50, match_rate=0.5)
        obs = signal_rules.from_preview(_preview([result]))
        assert obs.status == "ok"
        assert obs.signals == []
