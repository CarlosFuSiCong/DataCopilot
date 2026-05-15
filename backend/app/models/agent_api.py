"""HTTP contracts for the controlled Agent API surface."""
from typing import Literal

from pydantic import BaseModel, Field

from app.agent.loop.agent_models import AgentActionType, AgentRunState, AgentTrace, AgentTraceSummary
from app.models.chat import ChatResponse
from app.models.runtime_trace import WorkflowRunState
from app.models.workflow_steps import WorkflowStep


NextRequiredUserActionType = Literal["answer_clarification", "confirm_workflow"]


class AgentRunRequest(BaseModel):
    dataset_id: str
    query: str
    rag_top_k: int = 3
    auto_confirm: bool = True
    previous_steps: list[WorkflowStep] = Field(default_factory=list)


class AgentContinueRequest(BaseModel):
    answer: str
    auto_confirm: bool = True
    previous_steps: list[WorkflowStep] = Field(default_factory=list)


class AgentCancelRequest(BaseModel):
    reason: str | None = None


class AgentIterationSummary(BaseModel):
    iteration_index: int
    action: AgentActionType
    agent_state: AgentRunState
    workflow_state: WorkflowRunState | None = None
    stop_reason: str | None = None
    observation_status: str | None = None


class NextRequiredUserAction(BaseModel):
    type: NextRequiredUserActionType
    message: str
    endpoint: str
    payload: dict = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    agent_run_id: str
    agent_state: AgentRunState
    iteration_summary: list[AgentIterationSummary]
    agent_trace_summary: AgentTraceSummary
    agent_trace: AgentTrace | None = None
    workflow_state: WorkflowRunState | None = None
    next_required_user_action: NextRequiredUserAction | None = None
    workflow_response: ChatResponse | None = None
