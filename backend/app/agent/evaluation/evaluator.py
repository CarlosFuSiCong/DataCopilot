"""Deterministic Agent evaluator boundary."""
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.loop.agent_models import AgentValidationSummary
from app.agent.observation.models import ObservationSummary
from app.agent.policy.models import ActionPolicyResult


EvaluationNextAction = Literal[
    "finalize",
    "ask_user",
    "retry",
    "replan",
    "select_new_tool",
    "fail",
]

EvaluationResultStatus = Literal[
    "verified_result",
    "warning_result",
    "blocked_result",
    "failed_result",
    "incomplete_result",
]


class EvaluationDecision(BaseModel):
    """Formal evaluator output contract for one Agent decision point."""

    result_status: EvaluationResultStatus
    step_status: Literal["complete", "incomplete", "failed", "blocked"]
    task_status: Literal["continue", "complete", "needs_replan", "needs_user", "failed"]
    next_action: EvaluationNextAction
    reason: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    signals: list[str] = Field(default_factory=list)


class EvaluationInput(BaseModel):
    """Formal evaluator input contract.

    The evaluator reads validation, policy, and observation outputs. It does
    not validate workflow structure or replace deterministic validators.
    """

    task: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    current_step: dict[str, Any] | None = None
    observation: ObservationSummary = Field(default_factory=ObservationSummary)
    policy: ActionPolicyResult | None = None
    validation: AgentValidationSummary = Field(default_factory=AgentValidationSummary)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=1, ge=0)


def evaluate(input: EvaluationInput) -> EvaluationDecision:
    """Evaluate one bounded Agent decision point using deterministic signals."""
    if input.policy and input.policy.decision == "blocked":
        return EvaluationDecision(
            result_status="blocked_result",
            step_status="blocked",
            task_status="failed",
            next_action="fail",
            reason=input.policy.reason,
            confidence=0.95,
            signals=_policy_signals(input),
        )

    if input.validation.status == "blocked":
        return EvaluationDecision(
            result_status="blocked_result",
            step_status="blocked",
            task_status="failed",
            next_action="fail",
            reason=input.validation.error or "Validation blocked the workflow.",
            confidence=0.95,
            signals=_signals(input),
        )

    if input.policy and input.policy.decision == "requires_confirmation":
        return EvaluationDecision(
            result_status="blocked_result",
            step_status="blocked",
            task_status="needs_user",
            next_action="ask_user",
            reason=input.policy.reason,
            confidence=0.9,
            signals=_policy_signals(input),
        )

    if input.validation.status == "failed":
        if input.observation.recommended_next_action == "clarify":
            return EvaluationDecision(
                result_status="failed_result",
                step_status="failed",
                task_status="needs_user",
                next_action="ask_user",
                reason=input.validation.error or input.observation.message or "Validation failed and needs clarification.",
                confidence=0.9,
                signals=_signals(input),
            )
        return EvaluationDecision(
            result_status="failed_result",
            step_status="failed",
            task_status="needs_replan",
            next_action="replan",
            reason=input.validation.error or "Validation failed; create a corrected workflow plan.",
            confidence=0.85,
            signals=_signals(input),
        )

    if input.observation.status == "not_observed" or input.validation.status == "not_run":
        return EvaluationDecision(
            result_status="incomplete_result",
            step_status="incomplete",
            task_status="continue",
            next_action="retry",
            reason="Required validation or observation evidence is not available yet.",
            confidence=0.75,
            signals=_signals(input),
        )

    if input.observation.status == "error":
        if _has_tool_alternatives(input):
            return EvaluationDecision(
                result_status="failed_result",
                step_status="failed",
                task_status="continue",
                next_action="select_new_tool",
                reason=input.observation.message or "The current tool failed and alternatives are available.",
                confidence=0.8,
                signals=_signals(input),
            )
        if input.retry_count < input.max_retries:
            return EvaluationDecision(
                result_status="failed_result",
                step_status="failed",
                task_status="continue",
                next_action="retry",
                reason=input.observation.message or "The workflow step failed and can be retried.",
                confidence=0.75,
                signals=_signals(input),
            )
        if "execution_error" in input.observation.signals:
            return EvaluationDecision(
                result_status="failed_result",
                step_status="failed",
                task_status="needs_replan",
                next_action="replan",
                reason=input.observation.message or "Execution failed after retry budget was exhausted.",
                confidence=0.8,
                signals=_signals(input),
            )
        return EvaluationDecision(
            result_status="failed_result",
            step_status="failed",
            task_status="failed",
            next_action="fail",
            reason=input.observation.message or "Observation reported a non-recoverable error.",
            confidence=0.85,
            signals=_signals(input),
        )

    if input.observation.status == "warning":
        if _has_tool_alternatives(input) and "high_warning_rate" in input.observation.signals:
            return EvaluationDecision(
                result_status="warning_result",
                step_status="complete",
                task_status="continue",
                next_action="select_new_tool",
                reason=input.observation.message or "Warnings suggest trying a safer available tool.",
                confidence=0.7,
                signals=_signals(input),
            )
        return EvaluationDecision(
            result_status="warning_result",
            step_status="complete",
            task_status="needs_user",
            next_action="ask_user",
            reason=input.observation.message or "Workflow completed with warnings that need user review.",
            confidence=0.85,
            signals=_signals(input),
        )

    return EvaluationDecision(
        result_status="verified_result",
        step_status="complete",
        task_status="complete",
        next_action="finalize",
        reason=input.observation.message or "Workflow result is verified.",
        confidence=0.9,
        signals=_signals(input),
    )


def evaluate_observation(status: str, *, reason: str = "") -> EvaluationDecision:
    """Backward-compatible helper for simple observation status mapping."""
    observation = ObservationSummary(status=status if status in {"not_observed", "ok", "warning", "error"} else "error")
    if status == "blocked":
        return EvaluationDecision(
            result_status="blocked_result",
            step_status="blocked",
            task_status="needs_user",
            next_action="ask_user",
            reason=reason or "Observation is blocked and needs user input.",
        )
    decision = evaluate(EvaluationInput(task="", observation=observation, validation=AgentValidationSummary(status="passed")))
    if reason:
        decision.reason = reason
    return decision


def _signals(input: EvaluationInput) -> list[str]:
    signals = list(input.observation.signals)
    if input.policy:
        signals.extend(input.policy.issue_codes)
    return _dedupe(signals)


def _policy_signals(input: EvaluationInput) -> list[str]:
    if input.policy and input.policy.issue_codes:
        return input.policy.issue_codes
    return _signals(input)


def _has_tool_alternatives(input: EvaluationInput) -> bool:
    if not input.current_step:
        return False
    alternatives = input.current_step.get("alternative_tools") or input.current_step.get("alternative_tool_types")
    return isinstance(alternatives, list) and bool(alternatives)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value and value not in deduped:
            deduped.append(value)
    return deduped
