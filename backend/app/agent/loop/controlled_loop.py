"""Deterministic controls for the bounded Agent loop.

This module keeps the loop rules separate from the chat/workflow API
orchestration. It turns evaluator decisions into explicit Agent actions and
checks the guardrails that every iteration must obey.
"""
import time
from typing import Any

from pydantic import BaseModel, Field

from app.agent.evaluation.evaluator import EvaluationDecision, EvaluationInput, evaluate
from app.agent.loop.agent_models import (
    DEFAULT_MAX_AGENT_ITERATIONS,
    DEFAULT_MAX_AGENT_RETRIES,
    DEFAULT_MAX_AGENT_RUNTIME_SECONDS,
    AgentAction,
    AgentActionType,
    AgentDecision,
    AgentIteration,
    AgentTrace,
    AgentTraceSummary,
    AgentValidationSummary,
)
from app.agent.observation.models import ObservationSummary
from app.agent.policy import action_policy
from app.agent.policy.models import ActionPolicyResult
from app.agent.validation import workflow_validator
from app.core.exceptions import PolicyError, WorkflowValidationError
from app.models.workflow_steps import WorkflowStep
from app.models.workflow_transport import PreviewResponse, WorkflowRequest


class AgentLoopConfig(BaseModel):
    """Execution limits for one controlled Agent loop."""

    max_iterations: int = Field(default=DEFAULT_MAX_AGENT_ITERATIONS, ge=1)
    max_retries: int = Field(default=DEFAULT_MAX_AGENT_RETRIES, ge=0)
    max_runtime_seconds: float = Field(default=DEFAULT_MAX_AGENT_RUNTIME_SECONDS, gt=0)


class AgentLoopState(BaseModel):
    """Mutable counters used to enforce bounded loop execution."""

    iteration_count: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    started_at: float = Field(default_factory=time.monotonic)


class AgentLoopContext(BaseModel):
    """Compact input for deciding and recording a single Agent iteration."""

    task: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    current_step: dict[str, Any] | None = None
    observation: ObservationSummary = Field(default_factory=ObservationSummary)
    validation: AgentValidationSummary = Field(default_factory=AgentValidationSummary)
    policy: ActionPolicyResult | None = None


def decide_next_action(
    context: AgentLoopContext,
    *,
    config: AgentLoopConfig | None = None,
    state: AgentLoopState | None = None,
) -> tuple[AgentDecision, AgentAction, EvaluationDecision]:
    """Evaluate the current evidence and return exactly one explicit action."""
    config = config or AgentLoopConfig()
    state = state or AgentLoopState()
    limit_action = _limit_action(config=config, state=state)
    if limit_action:
        return limit_action

    if not context.plan:
        decision = AgentDecision(
            decision="plan_workflow",
            rationale="No workflow plan exists yet; create one before validation or preview.",
            confidence=0.9,
        )
        action = AgentAction(type="plan_workflow")
        evaluation = _synthetic_evaluation("Plan a workflow before continuing.", next_action="retry")
        return decision, action, evaluation

    evaluation = evaluate(
        EvaluationInput(
            task=context.task,
            plan=context.plan,
            current_step=context.current_step,
            observation=context.observation,
            policy=context.policy,
            validation=context.validation,
            retry_count=state.retry_count,
            max_retries=config.max_retries,
        )
    )
    action_type = map_evaluation_to_action(evaluation, context)
    decision = AgentDecision(
        decision=action_type,
        rationale=evaluation.reason,
        confidence=evaluation.confidence,
        requires_user_input=action_type in {"clarify", "confirm_required"},
    )
    action = AgentAction(
        type=action_type,
        workflow_steps=context.plan if action_type in _WORKFLOW_STEP_ACTIONS else [],
    )
    return decision, action, evaluation


def build_iteration(
    *,
    context: AgentLoopContext,
    config: AgentLoopConfig | None = None,
    state: AgentLoopState | None = None,
) -> AgentIteration:
    """Create one traceable Agent iteration after applying loop guardrails."""
    config = config or AgentLoopConfig()
    state = state or AgentLoopState()
    decision, action, evaluation = decide_next_action(context, config=config, state=state)
    return AgentIteration(
        iteration_index=state.iteration_count,
        input={
            "task": context.task,
            "plan": context.plan,
            "current_step": context.current_step,
            "observation": context.observation.model_dump(),
            "validation": context.validation.model_dump(),
            "policy": context.policy.model_dump() if context.policy else None,
            "retry_count": state.retry_count,
            "max_retries": config.max_retries,
        },
        decision=decision,
        action=action,
        validation=context.validation,
        observation=context.observation,
        stop_reason=_stop_reason(action.type, evaluation.reason),
    )


def make_trace(
    iterations: list[AgentIteration],
    *,
    config: AgentLoopConfig | None = None,
) -> AgentTrace:
    """Build an AgentTrace summary from completed iterations."""
    config = config or AgentLoopConfig()
    state = _trace_state(iterations, config)
    last_iteration = iterations[-1] if iterations else None
    return AgentTrace(
        state=state,
        max_iterations=config.max_iterations,
        summary=AgentTraceSummary(
            state=state,
            iteration_count=len(iterations),
            max_iterations=config.max_iterations,
            stop_reason=last_iteration.stop_reason if last_iteration else None,
            last_action=last_iteration.action.type if last_iteration else None,
            last_observation=last_iteration.observation if last_iteration else None,
            workflow_context_summary=(
                last_iteration.workflow_trace.context_summary
                if last_iteration and last_iteration.workflow_trace
                else None
            ),
            full_trace_available=True,
        ),
        iterations=iterations,
    )


def enforce_action_guardrails(
    action: AgentAction,
    *,
    column_names: list[str],
    config: AgentLoopConfig | None = None,
    state: AgentLoopState | None = None,
    preview_result: PreviewResponse | None = None,
    confirmed: bool = False,
) -> ActionPolicyResult | None:
    """Check policy, validation, and bounded retry rules before an action runs."""
    config = config or AgentLoopConfig()
    state = state or AgentLoopState()
    if state.iteration_count >= config.max_iterations:
        raise PolicyError(
            "Agent loop cannot continue because max_iterations was reached.",
            error_code=action_policy.POLICY_BLOCKED,
        )
    if _runtime_exhausted(config=config, state=state):
        raise PolicyError(
            "Agent loop cannot continue because max_runtime was reached.",
            error_code=action_policy.POLICY_BLOCKED,
        )
    if action.type == "retry_preview" and state.retry_count >= config.max_retries:
        raise PolicyError(
            "Agent loop cannot retry preview because max_retries was reached.",
            error_code=action_policy.POLICY_BLOCKED,
        )

    policy = _policy_for_action(action.type, preview_result=preview_result, confirmed=confirmed)
    if policy and action.type != "confirm_required":
        action_policy.enforce_policy(policy)

    if action.type in _WORKFLOW_STEP_VALIDATE_ACTIONS:
        steps = _parse_steps(action.workflow_steps)
        workflow_validator.validate(steps, column_names)

    if action.type == "stop_with_result" and _requires_confirmation(preview_result, confirmed):
        raise PolicyError(
            "Agent loop cannot stop with a result before preview warnings are confirmed.",
            error_code=action_policy.POLICY_BLOCKED,
            context={"preview_confirm_boundary": True},
        )

    return policy


def map_evaluation_to_action(
    evaluation: EvaluationDecision,
    context: AgentLoopContext,
) -> AgentActionType:
    """Map evaluator decisions to the explicit action taxonomy from Task 5."""
    if evaluation.next_action == "finalize":
        return "stop_with_result"
    if evaluation.next_action == "ask_user":
        if context.policy and context.policy.decision == "requires_confirmation":
            return "confirm_required"
        if context.observation.recommended_next_action == "confirm_required":
            return "confirm_required"
        return "clarify"
    if evaluation.next_action == "retry":
        return "retry_preview"
    if evaluation.next_action == "replan":
        return "replan_workflow"
    if evaluation.next_action == "select_new_tool":
        return "select_new_tool"
    return "stop_with_error"


# Actions that attach the current plan to workflow_steps so downstream handlers
# have plan context.  select_new_tool is included because the tool selector
# needs the failing plan to choose an alternative.
_WORKFLOW_STEP_ACTIONS = {
    "plan_workflow",
    "preview_workflow",
    "retry_preview",
    "replan_workflow",
    "select_new_tool",
}

# Actions that also require deterministic step-level validation before
# execution.  select_new_tool is excluded: it carries the *failing* plan as
# reference context only — validating those steps would always raise an error
# since they are the steps being replaced.
_WORKFLOW_STEP_VALIDATE_ACTIONS = _WORKFLOW_STEP_ACTIONS - {"select_new_tool"}


def _limit_action(
    *,
    config: AgentLoopConfig,
    state: AgentLoopState,
) -> tuple[AgentDecision, AgentAction, EvaluationDecision] | None:
    if state.iteration_count >= config.max_iterations:
        reason = "Agent loop stopped because max_iterations was reached."
        decision = AgentDecision(decision="stop_with_error", rationale=reason, confidence=0.95)
        return decision, AgentAction(type="stop_with_error"), _synthetic_evaluation(reason, next_action="fail")
    if _runtime_exhausted(config=config, state=state):
        reason = "Agent loop stopped because max_runtime was reached."
        decision = AgentDecision(decision="stop_with_error", rationale=reason, confidence=0.95)
        return decision, AgentAction(type="stop_with_error"), _synthetic_evaluation(reason, next_action="fail")
    return None


def _policy_for_action(
    action_type: AgentActionType,
    *,
    preview_result: PreviewResponse | None,
    confirmed: bool,
) -> ActionPolicyResult | None:
    if action_type in {"plan_workflow", "replan_workflow", "select_new_tool"}:
        return action_policy.evaluate_workflow_action("plan_workflow")
    if action_type in {"preview_workflow", "retry_preview"}:
        return action_policy.evaluate_workflow_action("preview_workflow")
    if action_type == "confirm_required":
        return action_policy.evaluate_workflow_action(
            "execute_workflow",
            preview_result=preview_result,
            confirmed=confirmed,
        )
    if action_type == "stop_with_result":
        return action_policy.evaluate_workflow_action(
            "execute_workflow",
            preview_result=preview_result,
            confirmed=confirmed,
        )
    return None


def _parse_steps(raw_steps: list[dict[str, Any]]) -> list[WorkflowStep]:
    return WorkflowRequest(dataset_id="__agent_loop__", steps=raw_steps).steps


def _requires_confirmation(preview_result: PreviewResponse | None, confirmed: bool) -> bool:
    if not preview_result or confirmed:
        return False
    policy = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=preview_result,
        confirmed=False,
    )
    return policy.decision == "requires_confirmation"


def _runtime_exhausted(*, config: AgentLoopConfig, state: AgentLoopState) -> bool:
    return time.monotonic() - state.started_at >= config.max_runtime_seconds


def _trace_state(iterations: list[AgentIteration], config: AgentLoopConfig):
    if not iterations:
        return "created"
    last_action = iterations[-1].action.type
    if last_action == "clarify":
        return "needs_clarification"
    if last_action == "confirm_required":
        return "waiting_confirmation"
    if last_action == "stop_with_result":
        return "completed"
    if last_action == "stop_with_error":
        if len(iterations) == config.max_iterations and iterations[-1].stop_reason:
            return "max_iterations_reached"
        return "failed"
    return "running"


def _stop_reason(action_type: AgentActionType, reason: str) -> str | None:
    if action_type in {"clarify", "confirm_required", "stop_with_result", "stop_with_error"}:
        return reason
    return None


def _synthetic_evaluation(reason: str, *, next_action) -> EvaluationDecision:
    return EvaluationDecision(
        result_status="incomplete_result" if next_action != "fail" else "failed_result",
        step_status="incomplete" if next_action != "fail" else "failed",
        task_status="continue" if next_action != "fail" else "failed",
        next_action=next_action,
        reason=reason,
        confidence=0.9,
    )
