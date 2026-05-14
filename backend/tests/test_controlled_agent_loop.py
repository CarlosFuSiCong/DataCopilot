"""Focused tests for the Task 5 controlled Agent loop service."""

import time

import pytest

from app.agent.loop.controlled_loop import (
    AgentLoopConfig,
    AgentLoopContext,
    AgentLoopState,
    build_iteration,
    decide_next_action,
    enforce_action_guardrails,
    make_trace,
    _trace_state,
)
from app.agent.loop.agent_models import AgentAction, AgentValidationSummary
from app.agent.observation.models import ObservationSummary
from app.agent.policy.models import ActionPolicyResult
from app.core.exceptions import PolicyError, WorkflowValidationError
from app.models.workflow import PreviewResponse, StepIssue, StepResult


def _plan() -> list[dict]:
    return [
        {
            "type": "filter_rows",
            "column": "status",
            "operator": "=",
            "value": "completed",
        }
    ]


def _context(
    *,
    observation: ObservationSummary | None = None,
    validation: AgentValidationSummary | None = None,
    policy: ActionPolicyResult | None = None,
    plan: list[dict] | None = None,
    current_step: dict | None = None,
) -> AgentLoopContext:
    return AgentLoopContext(
        task="filter completed orders",
        plan=_plan() if plan is None else plan,
        current_step=current_step,
        observation=observation or ObservationSummary(status="ok", message="Preview passed."),
        validation=validation or AgentValidationSummary(status="passed"),
        policy=policy,
    )


def _preview(*, warning: bool = False, error: bool = False) -> PreviewResponse:
    status = "success"
    issues: list[StepIssue] = []
    if warning:
        status = "warning"
        issues = [StepIssue(severity="warning", code="empty_output", message="empty")]
    if error:
        status = "error"
        issues = [StepIssue(severity="error", code="execution_error", message="boom")]
    return PreviewResponse(
        planned_steps=_plan(),
        step_results=[
            StepResult(
                step_index=0,
                step_type="filter_rows",
                status=status,
                issues=issues,
                input_row_count=2,
                output_row_count=0 if warning or error else 1,
                input_column_count=2,
                output_column_count=2,
                affected_rows=1,
                match_rate=0.5,
                affected_rate=0.5,
                preview=[],
                message="preview",
            )
        ],
        has_warnings=warning,
        has_errors=error,
        blocked_at_step=0 if error else None,
    )


def test_missing_plan_starts_with_plan_workflow_action():
    decision, action, _ = decide_next_action(_context(plan=[]))

    assert decision.decision == "plan_workflow"
    assert action.type == "plan_workflow"


def test_verified_result_stops_with_result():
    decision, action, _ = decide_next_action(_context())

    assert decision.decision == "stop_with_result"
    assert action.type == "stop_with_result"


def test_requires_confirmation_maps_to_confirm_required():
    policy = ActionPolicyResult(
        action="execute_workflow",
        decision="requires_confirmation",
        reason="Preview has warnings.",
        requires_confirmation=True,
    )

    decision, action, _ = decide_next_action(_context(policy=policy))

    assert decision.decision == "confirm_required"
    assert decision.requires_user_input is True
    assert action.type == "confirm_required"


def test_validation_clarification_maps_to_clarify():
    decision, action, _ = decide_next_action(
        _context(
            observation=ObservationSummary(
                status="error",
                signals=["validation_failed"],
                message="Column missing.",
                recommended_next_action="clarify",
            ),
            validation=AgentValidationSummary(status="failed", error="Column missing."),
        )
    )

    assert decision.decision == "clarify"
    assert action.type == "clarify"


def test_execution_error_retry_maps_to_retry_preview():
    decision, action, _ = decide_next_action(
        _context(
            observation=ObservationSummary(
                status="error",
                signals=["execution_error"],
                message="Temporary failure.",
            ),
        )
    )

    assert decision.decision == "retry_preview"
    assert action.type == "retry_preview"


def test_retry_budget_exhaustion_replans_instead_of_retrying():
    decision, action, _ = decide_next_action(
        _context(
            observation=ObservationSummary(
                status="error",
                signals=["execution_error"],
                message="Still failing.",
            ),
        ),
        state=AgentLoopState(retry_count=1),
        config=AgentLoopConfig(max_retries=1),
    )

    assert decision.decision == "replan_workflow"
    assert action.type == "replan_workflow"


def test_tool_alternatives_map_to_select_new_tool():
    decision, action, _ = decide_next_action(
        _context(
            observation=ObservationSummary(
                status="error",
                signals=["execution_error"],
                message="Current tool failed.",
            ),
            current_step={"type": "filter_rows", "alternative_tools": ["select_columns"]},
        )
    )

    assert decision.decision == "select_new_tool"
    assert action.type == "select_new_tool"


def test_iteration_records_exactly_one_action():
    iteration = build_iteration(context=_context())

    assert iteration.action.type == "stop_with_result"
    assert iteration.decision.decision == iteration.action.type
    assert iteration.input["max_retries"] == 1


def test_guardrails_validate_workflow_steps_before_preview_actions():
    with pytest.raises(WorkflowValidationError):
        enforce_action_guardrails(
            AgentAction(
                type="preview_workflow",
                workflow_steps=[
                    {
                        "type": "filter_rows",
                        "column": "missing",
                        "operator": "=",
                        "value": "completed",
                    }
                ],
            ),
            column_names=["status"],
        )


def test_guardrails_allow_valid_preview_action_after_policy_and_validation():
    policy = enforce_action_guardrails(
        AgentAction(type="preview_workflow", workflow_steps=_plan()),
        column_names=["status", "amount"],
    )

    assert policy is not None
    assert policy.decision == "preview_only"


def test_agent_loop_cannot_stop_with_result_without_preview_boundary():
    with pytest.raises(PolicyError, match="bypasses preview"):
        enforce_action_guardrails(
            AgentAction(type="stop_with_result"),
            column_names=["status"],
        )


def test_agent_loop_cannot_stop_with_warning_result_before_confirmation():
    with pytest.raises(PolicyError, match="requires explicit confirmation"):
        enforce_action_guardrails(
            AgentAction(type="stop_with_result"),
            column_names=["status"],
            preview_result=_preview(warning=True),
            confirmed=False,
        )


def test_agent_loop_can_stop_with_warning_result_after_confirmation():
    policy = enforce_action_guardrails(
        AgentAction(type="stop_with_result"),
        column_names=["status"],
        preview_result=_preview(warning=True),
        confirmed=True,
    )

    assert policy is not None
    assert policy.decision == "auto_executable"


def test_retry_preview_is_blocked_after_max_retries():
    with pytest.raises(PolicyError, match="max_retries"):
        enforce_action_guardrails(
            AgentAction(type="retry_preview", workflow_steps=_plan()),
            column_names=["status"],
            state=AgentLoopState(retry_count=1),
            config=AgentLoopConfig(max_retries=1),
        )


def test_loop_stops_when_max_iterations_reached():
    decision, action, _ = decide_next_action(
        _context(),
        state=AgentLoopState(iteration_count=3),
        config=AgentLoopConfig(max_iterations=3),
    )

    assert decision.decision == "stop_with_error"
    assert action.type == "stop_with_error"


def test_guardrails_block_after_max_runtime():
    with pytest.raises(PolicyError, match="max_runtime"):
        enforce_action_guardrails(
            AgentAction(type="plan_workflow", workflow_steps=_plan()),
            column_names=["status"],
            state=AgentLoopState(started_at=time.monotonic() - 2),
            config=AgentLoopConfig(max_runtime_seconds=1),
        )


def test_trace_summary_reflects_last_action_and_state():
    iteration = build_iteration(
        context=_context(
            policy=ActionPolicyResult(
                action="execute_workflow",
                decision="requires_confirmation",
                reason="Preview has warnings.",
                requires_confirmation=True,
            )
        )
    )
    trace = make_trace([iteration])

    assert trace.state == "waiting_confirmation"
    assert trace.summary.last_action == "confirm_required"
    assert trace.summary.iteration_count == 1


def test_trace_state_marks_max_iterations_only_at_exact_limit():
    config = AgentLoopConfig(max_iterations=3)
    iterations = [
        build_iteration(
            context=_context(),
            state=AgentLoopState(iteration_count=config.max_iterations),
            config=config,
        )
        for index in range(4)
    ]

    assert _trace_state(iterations[:3], config) == "max_iterations_reached"
    assert _trace_state(iterations, config) == "failed"
