"""Unit tests for deterministic workflow action policy."""
import pytest

from app.core.exceptions import PolicyError
from app.models.workflow import PreviewResponse, StepIssue, StepResult
from app.services import action_policy


def _step_result(
    *,
    status: str = "success",
    issues: list[StepIssue] | None = None,
) -> StepResult:
    return StepResult(
        step_index=0,
        step_type="filter_rows",
        status=status,
        issues=issues or [],
        input_row_count=2,
        output_row_count=1,
        input_column_count=2,
        output_column_count=2,
        message="ok",
    )


def _preview(*, warnings: bool = False, errors: bool = False) -> PreviewResponse:
    issues: list[StepIssue] = []
    status = "success"
    if warnings:
        status = "warning"
        issues.append(
            StepIssue(
                severity="warning",
                code="empty_output",
                message="This step produced no output rows.",
            )
        )
    if errors:
        status = "error"
        issues.append(
            StepIssue(
                severity="error",
                code="execution_error",
                message="The workflow failed during preview.",
            )
        )
    return PreviewResponse(
        planned_steps=[{"type": "filter_rows"}],
        step_results=[_step_result(status=status, issues=issues)],
        has_warnings=warnings,
        has_errors=errors,
        blocked_at_step=0 if errors else None,
    )


def test_plan_workflow_is_auto_executable():
    result = action_policy.evaluate_workflow_action("plan_workflow")

    assert result.decision == "auto_executable"


def test_preview_workflow_is_preview_only():
    result = action_policy.evaluate_workflow_action("preview_workflow")

    assert result.decision == "preview_only"
    assert result.can_execute is False


def test_clean_workflow_execution_is_auto_executable():
    result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=_preview(),
        confirmed=False,
    )

    assert result.decision == "auto_executable"
    assert result.can_execute is True


def test_warning_workflow_requires_confirmation_before_execution():
    result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=_preview(warnings=True),
        confirmed=False,
    )

    assert result.decision == "requires_confirmation"
    assert result.requires_confirmation is True
    assert result.issue_codes == ["empty_output"]


def test_confirmed_warning_workflow_is_auto_executable():
    result = action_policy.evaluate_workflow_action(
        "confirm_workflow",
        preview_result=_preview(warnings=True),
        confirmed=True,
    )

    assert result.decision == "auto_executable"
    assert result.can_execute is True


def test_error_preview_blocks_execution_with_structured_code():
    result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=_preview(errors=True),
        confirmed=True,
    )

    assert result.decision == "blocked"
    assert result.error_code == action_policy.POLICY_BLOCKED
    assert result.issue_codes == ["execution_error"]


def test_enforce_policy_raises_structured_error_for_blocked_action():
    result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=_preview(errors=True),
        confirmed=True,
    )

    with pytest.raises(PolicyError) as exc_info:
        action_policy.enforce_policy(result)

    assert exc_info.value.error_code == action_policy.POLICY_BLOCKED
    assert exc_info.value.context["policy"]["decision"] == "blocked"


def test_enforce_policy_raises_structured_error_when_confirmation_required():
    result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=_preview(warnings=True),
        confirmed=False,
    )

    with pytest.raises(PolicyError) as exc_info:
        action_policy.enforce_policy(result)

    assert exc_info.value.error_code == action_policy.POLICY_BLOCKED
    assert exc_info.value.context["policy"]["decision"] == "requires_confirmation"
