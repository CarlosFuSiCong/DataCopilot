"""Deterministic policy layer for workflow actions."""
from app.core.exceptions import PolicyError
from app.agent.policy.models import ActionPolicyResult, WorkflowAction
from app.models.workflow import PreviewResponse


POLICY_BLOCKED = "policy_blocked"


def evaluate_workflow_action(
    action: WorkflowAction,
    *,
    preview_result: PreviewResponse | None = None,
    confirmed: bool = False,
) -> ActionPolicyResult:
    """Return the policy decision for a workflow action.

    Policy is deterministic and independent from the LLM planner. It only uses
    the requested action, explicit confirmation state, and preview issues.
    """
    if action == "plan_workflow":
        return ActionPolicyResult(
            action=action,
            decision="auto_executable",
            reason="Planning is allowed because it does not execute data changes.",
        )

    if action == "preview_workflow":
        return ActionPolicyResult(
            action=action,
            decision="preview_only",
            reason="Preview may run deterministic validation and dry-run execution only.",
        )

    if action == "execute_workflow" and preview_result is None:
        return ActionPolicyResult(
            action=action,
            decision="blocked",
            reason="Direct workflow execution is blocked because it bypasses preview and confirmation.",
            error_code=POLICY_BLOCKED,
        )

    return _evaluate_execution_action(
        action=action,
        preview_result=preview_result,
        confirmed=confirmed,
    )


def enforce_policy(result: ActionPolicyResult) -> None:
    """Raise a structured error when policy does not allow execution."""
    if result.decision not in ("blocked", "requires_confirmation"):
        return
    raise PolicyError(
        result.reason,
        error_code=result.error_code or POLICY_BLOCKED,
        context={"policy": result.model_dump()},
    )


def _evaluate_execution_action(
    *,
    action: WorkflowAction,
    preview_result: PreviewResponse | None,
    confirmed: bool,
) -> ActionPolicyResult:
    issue_codes = _issue_codes(preview_result)

    if preview_result and preview_result.has_errors:
        return ActionPolicyResult(
            action=action,
            decision="blocked",
            reason="Workflow execution is blocked because preview found errors.",
            error_code=POLICY_BLOCKED,
            issue_codes=issue_codes,
        )

    if preview_result and preview_result.has_warnings and not confirmed:
        return ActionPolicyResult(
            action=action,
            decision="requires_confirmation",
            reason="Workflow preview has warnings and requires explicit confirmation before execution.",
            requires_confirmation=True,
            issue_codes=issue_codes,
        )

    return ActionPolicyResult(
        action=action,
        decision="auto_executable",
        reason="Workflow execution is allowed by policy.",
        can_execute=True,
        issue_codes=issue_codes,
    )


def _issue_codes(preview_result: PreviewResponse | None) -> list[str]:
    if preview_result is None:
        return []

    codes: list[str] = []
    for step_result in preview_result.step_results:
        for issue in step_result.issues:
            codes.append(issue.code)
    return codes
