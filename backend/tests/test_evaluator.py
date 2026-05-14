"""Focused tests for the deterministic Agent evaluator."""

from app.agent.evaluation.evaluator import EvaluationInput, evaluate, evaluate_observation
from app.agent.loop.agent_models import AgentValidationSummary
from app.agent.observation.models import ObservationSummary
from app.agent.policy.models import ActionPolicyResult


def _input(
    *,
    observation: ObservationSummary | None = None,
    validation: AgentValidationSummary | None = None,
    policy: ActionPolicyResult | None = None,
    current_step: dict | None = None,
    retry_count: int = 0,
    max_retries: int = 1,
) -> EvaluationInput:
    return EvaluationInput(
        task="filter completed orders",
        plan=[{"type": "filter_rows", "column": "status", "operator": "=", "value": "completed"}],
        current_step=current_step,
        observation=observation or ObservationSummary(status="ok", message="Preview passed."),
        policy=policy,
        validation=validation or AgentValidationSummary(status="passed"),
        retry_count=retry_count,
        max_retries=max_retries,
    )


def test_verified_result_finalizes():
    decision = evaluate(_input())

    assert decision.result_status == "verified_result"
    assert decision.step_status == "complete"
    assert decision.task_status == "complete"
    assert decision.next_action == "finalize"


def test_warning_result_asks_user_for_review():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="warning",
            signals=["empty_result"],
            message="Workflow can produce an empty result.",
            recommended_next_action="confirm_required",
        ),
    ))

    assert decision.result_status == "warning_result"
    assert decision.next_action == "ask_user"
    assert decision.task_status == "needs_user"


def test_requires_confirmation_policy_is_blocked_result_for_user_input():
    decision = evaluate(_input(
        policy=ActionPolicyResult(
            action="execute_workflow",
            decision="requires_confirmation",
            reason="Preview has warnings.",
            requires_confirmation=True,
            issue_codes=["empty_output"],
        ),
    ))

    assert decision.result_status == "blocked_result"
    assert decision.step_status == "blocked"
    assert decision.next_action == "ask_user"
    assert decision.signals == ["empty_output"]


def test_blocked_policy_fails_without_replacing_policy():
    decision = evaluate(_input(
        policy=ActionPolicyResult(
            action="execute_workflow",
            decision="blocked",
            reason="Policy blocked execution.",
            error_code="policy_blocked",
            issue_codes=["execution_error"],
        ),
    ))

    assert decision.result_status == "blocked_result"
    assert decision.task_status == "failed"
    assert decision.next_action == "fail"
    assert decision.reason == "Policy blocked execution."


def test_blocked_policy_falls_back_to_observation_signals_when_issue_codes_empty():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="warning",
            signals=["empty_result"],
            message="Workflow can produce an empty result.",
        ),
        policy=ActionPolicyResult(
            action="execute_workflow",
            decision="blocked",
            reason="Policy blocked execution.",
        ),
    ))

    assert decision.next_action == "fail"
    assert decision.signals == ["empty_result"]


def test_requires_confirmation_policy_uses_same_signal_fallback_as_blocked_policy():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="warning",
            signals=["empty_result"],
            message="Workflow can produce an empty result.",
        ),
        policy=ActionPolicyResult(
            action="execute_workflow",
            decision="requires_confirmation",
            reason="Preview has warnings.",
            requires_confirmation=True,
        ),
    ))

    assert decision.next_action == "ask_user"
    assert decision.signals == ["empty_result"]


def test_execution_error_retries_within_retry_budget():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="error",
            signals=["execution_error"],
            message="Temporary execution failure.",
        ),
        retry_count=0,
        max_retries=1,
    ))

    assert decision.result_status == "failed_result"
    assert decision.next_action == "retry"
    assert decision.task_status == "continue"


def test_execution_error_replans_after_retry_budget():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="error",
            signals=["execution_error"],
            message="Execution still fails.",
        ),
        retry_count=1,
        max_retries=1,
    ))

    assert decision.result_status == "failed_result"
    assert decision.next_action == "replan"
    assert decision.task_status == "needs_replan"


def test_failed_step_selects_new_tool_when_alternatives_exist():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="error",
            signals=["execution_error"],
            message="Current tool failed.",
        ),
        current_step={"type": "filter_rows", "alternative_tools": ["select_columns"]},
    ))

    assert decision.result_status == "failed_result"
    assert decision.next_action == "select_new_tool"


def test_validation_failure_asks_user_when_observation_recommends_clarification():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="error",
            signals=["validation_failed"],
            message="Column 'sales' does not exist.",
            recommended_next_action="clarify",
        ),
        validation=AgentValidationSummary(
            status="failed",
            error="Column 'sales' does not exist.",
        ),
    ))

    assert decision.result_status == "failed_result"
    assert decision.next_action == "ask_user"
    assert decision.task_status == "needs_user"


def test_validation_failure_replans_without_clarification_signal():
    decision = evaluate(_input(
        observation=ObservationSummary(
            status="error",
            signals=["validation_failed"],
            message="Workflow shape is invalid.",
        ),
        validation=AgentValidationSummary(
            status="failed",
            error="Workflow shape is invalid.",
        ),
    ))

    assert decision.result_status == "failed_result"
    assert decision.next_action == "replan"


def test_not_observed_result_is_incomplete_and_retries():
    decision = evaluate(_input(
        observation=ObservationSummary(status="not_observed"),
        validation=AgentValidationSummary(status="not_run"),
    ))

    assert decision.result_status == "incomplete_result"
    assert decision.step_status == "incomplete"
    assert decision.next_action == "retry"


def test_legacy_evaluate_observation_still_maps_error_to_decision():
    decision = evaluate_observation("error", reason="legacy error")

    assert decision.result_status == "failed_result"
    assert decision.next_action == "retry"
    assert decision.reason == "legacy error"


def test_legacy_evaluate_observation_preserves_reason_for_non_error_status():
    decision = evaluate_observation("ok", reason="legacy ok")

    assert decision.result_status == "verified_result"
    assert decision.next_action == "finalize"
    assert decision.reason == "legacy ok"
