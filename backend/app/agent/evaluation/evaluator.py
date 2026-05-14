"""Future Agent evaluator boundary."""
from typing import Literal

from pydantic import BaseModel


EvaluationNextAction = Literal[
    "continue_plan",
    "retry",
    "select_new_tool",
    "replan",
    "ask_user",
    "finalize",
    "fail",
]


class EvaluationDecision(BaseModel):
    step_status: Literal["complete", "incomplete", "failed", "blocked"]
    task_status: Literal["continue", "complete", "needs_replan", "needs_user", "failed"]
    next_action: EvaluationNextAction
    reason: str
    confidence: float | None = None


def evaluate_observation(status: str, *, reason: str = "") -> EvaluationDecision:
    """Map a simple observation status to an MVP5-style decision."""
    if status == "blocked":
        return EvaluationDecision(
            step_status="blocked",
            task_status="needs_user",
            next_action="ask_user",
            reason=reason or "Observation is blocked and needs user input.",
        )
    if status == "error":
        return EvaluationDecision(
            step_status="failed",
            task_status="needs_replan",
            next_action="replan",
            reason=reason or "Observation reported an error.",
        )
    return EvaluationDecision(
        step_status="complete",
        task_status="continue",
        next_action="continue_plan",
        reason=reason or "Observation is usable.",
    )
