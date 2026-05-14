"""Pydantic contracts for the controlled Agent runtime."""
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.agent.observation.models import ObservationSignal as ObservationSignal, ObservationSummary as ObservationSummary
from app.agent.loop.runtime_models import WorkflowContextSummary, WorkflowTrace


DEFAULT_MAX_AGENT_ITERATIONS = 3


AgentRunState = Literal[
    "created",
    "running",
    "needs_clarification",
    "waiting_confirmation",
    "completed",
    "failed",
    "cancelled",
    "max_iterations_reached",
]

AgentActionType = Literal[
    "clarify",
    "plan_workflow",
    "preview_workflow",
    "confirm_required",
    "stop_with_result",
    "stop_with_error",
]

class AgentDecision(BaseModel):
    decision: AgentActionType
    rationale: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    requires_user_input: bool = False


class AgentAction(BaseModel):
    type: AgentActionType
    parameters: dict[str, Any] = Field(default_factory=dict)
    workflow_steps: list[dict[str, Any]] = Field(default_factory=list)


class AgentValidationSummary(BaseModel):
    status: Literal["not_run", "passed", "failed", "blocked"] = "not_run"
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AgentIteration(BaseModel):
    iteration_index: int = Field(ge=0)
    input: dict[str, Any]
    decision: AgentDecision
    action: AgentAction
    validation: AgentValidationSummary
    observation: ObservationSummary
    stop_reason: str | None = None
    workflow_trace: WorkflowTrace | None = Field(
        default=None,
        description="Full workflow trace produced by a workflow action in this Agent iteration.",
    )


class AgentTraceSummary(BaseModel):
    state: AgentRunState
    iteration_count: int = Field(ge=0)
    max_iterations: int = DEFAULT_MAX_AGENT_ITERATIONS
    stop_reason: str | None = None
    last_action: AgentActionType | None = None
    last_observation: ObservationSummary | None = None
    workflow_context_summary: WorkflowContextSummary | None = None
    full_trace_available: bool = True


class AgentTrace(BaseModel):
    state: AgentRunState
    max_iterations: int = Field(default=DEFAULT_MAX_AGENT_ITERATIONS, ge=1)
    summary: AgentTraceSummary
    iterations: list[AgentIteration] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_trace_contract(self) -> "AgentTrace":
        if len(self.iterations) > self.max_iterations:
            raise ValueError("AgentTrace iterations must not exceed max_iterations.")

        if self.summary.state != self.state:
            raise ValueError("AgentTrace summary state must match trace state.")

        if self.summary.iteration_count != len(self.iterations):
            raise ValueError("AgentTrace summary iteration_count must match iterations.")

        if self.summary.max_iterations != self.max_iterations:
            raise ValueError("AgentTrace summary max_iterations must match trace max_iterations.")

        if self.state == "max_iterations_reached":
            if len(self.iterations) != self.max_iterations:
                raise ValueError(
                    "AgentTrace with max_iterations_reached must contain exactly max_iterations iterations."
                )
            if not self.summary.stop_reason:
                raise ValueError("AgentTrace must explain why max_iterations was reached.")

        return self
