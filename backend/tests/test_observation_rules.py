"""Unit tests for deterministic observation signal rules."""

from app.agent.loop import workflow_runtime
from app.agent.loop.runtime_models import WorkflowContextSummary
from app.agent.observation import signal_rules
from app.agent.observation.models import ObservationSummary
from app.agent.observation.risk_rules import AFFECTS_MOST_ROWS, EMPTY_OUTPUT, NO_ROWS_MATCHED
from app.models.workflow import PreviewResponse, StepIssue, StepResult


def _step_result(
    *,
    step_index: int = 0,
    step_type: str = "filter_rows",
    status: str = "success",
    issues: list[StepIssue] | None = None,
    input_rows: int = 10,
    output_rows: int = 10,
    input_columns: int = 2,
    output_columns: int = 2,
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
        message="test step",
    )


def _preview(step_results: list[StepResult], planned_steps: list[dict] | None = None) -> PreviewResponse:
    return PreviewResponse(
        planned_steps=planned_steps or [{"type": result.step_type} for result in step_results],
        step_results=step_results,
        has_warnings=any(result.status == "warning" for result in step_results),
        has_errors=any(result.status == "error" for result in step_results),
    )


def test_empty_numeric_filter_reports_strict_filter_and_valid_no_match_causes():
    result = _step_result(
        status="warning",
        issues=[
            StepIssue(severity="warning", code=EMPTY_OUTPUT, message="empty"),
            StepIssue(severity="warning", code=NO_ROWS_MATCHED, message="none matched"),
        ],
        output_rows=0,
        match_rate=0.0,
    )

    observation = signal_rules.from_preview(
        _preview([result]),
        planned_steps=[{"type": "filter_rows", "column": "sales", "operator": ">", "value": 9999}],
    )

    assert observation.status == "warning"
    assert "empty_result" in observation.signals
    assert "filter_too_strict" in observation.possible_causes
    assert "valid_no_match" in observation.possible_causes
    assert observation.recommended_next_action == "confirm_required"


def test_empty_equality_filter_reports_wrong_value_cause():
    result = _step_result(
        status="warning",
        issues=[StepIssue(severity="warning", code=EMPTY_OUTPUT, message="empty")],
        output_rows=0,
        match_rate=0.0,
    )

    observation = signal_rules.from_preview(
        _preview([result]),
        planned_steps=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "closed"}],
    )

    assert "wrong_value" in observation.possible_causes


def test_high_warning_rate_signal_requires_multiple_warning_steps():
    result_a = _step_result(
        step_index=0,
        status="warning",
        issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="many")],
    )
    result_b = _step_result(
        step_index=1,
        status="warning",
        issues=[StepIssue(severity="warning", code=AFFECTS_MOST_ROWS, message="many")],
    )

    observation = signal_rules.from_preview(_preview([result_a, result_b]))

    assert "high_warning_rate" in observation.signals
    assert "multiple workflow steps produced warnings" in observation.possible_causes


def test_validation_failure_signal_recommends_clarification():
    observation = signal_rules.from_validation_failure("Column 'sales' does not exist.")

    assert observation.status == "error"
    assert observation.signals == ["validation_failed"]
    assert observation.recommended_next_action == "clarify"


def test_execution_error_signal_recommends_stopping_with_error():
    result = _step_result(
        status="error",
        issues=[StepIssue(severity="error", code="execution_error", message="boom")],
        output_rows=0,
    )

    observation = signal_rules.from_preview(_preview([result]))

    assert observation.status == "error"
    assert "execution_error" in observation.signals
    assert observation.recommended_next_action == "stop_with_error"


def test_schema_changed_signal_uses_step_metrics_and_structural_steps():
    result = _step_result(
        step_type="select_columns",
        input_columns=4,
        output_columns=2,
    )

    observation = signal_rules.from_preview(
        _preview([result]),
        planned_steps=[{"type": "select_columns", "columns": ["region", "sales"]}],
    )

    assert "schema_changed" in observation.signals
    assert "the workflow changed the available columns" in observation.possible_causes


def test_observation_enters_agent_next_decision_input():
    summary = WorkflowContextSummary(
        query="filter rows",
        dataset_hash="hash-1",
        schema_columns=["status"],
        row_count=2,
        planned_step_types=["filter_rows"],
        status="preview_ready",
        boundary="preview",
    )
    observation = ObservationSummary(
        status="ok",
        message="Observation did not find workflow warnings or errors.",
        recommended_next_action="stop_with_result",
    )

    decision_input = workflow_runtime.make_next_decision_input(
        context_summary=summary,
        observation=observation,
    )

    assert decision_input["observation"]["status"] == "ok"
    assert decision_input["workflow_context_summary"]["planned_step_types"] == ["filter_rows"]
