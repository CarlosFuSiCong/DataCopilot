"""In-memory Agent run state for the MVP Agent API surface."""
from dataclasses import dataclass, field
from uuid import uuid4

from app.models.chat import ChatResponse
from app.models.clarification_context import ClarificationContext


@dataclass
class AgentRunRecord:
    agent_run_id: str
    dataset_id: str
    query: str
    workflow_response: ChatResponse | None = None
    clarification_context: ClarificationContext | None = None
    cancelled: bool = False
    cancel_reason: str | None = None
    iteration_count: int = 0
    events: list[ChatResponse] = field(default_factory=list)


_RUNS: dict[str, AgentRunRecord] = {}


def create_run(*, dataset_id: str, query: str) -> AgentRunRecord:
    agent_run_id = str(uuid4())
    record = AgentRunRecord(agent_run_id=agent_run_id, dataset_id=dataset_id, query=query)
    _RUNS[agent_run_id] = record
    return record


def get_run(agent_run_id: str) -> AgentRunRecord | None:
    return _RUNS.get(agent_run_id)


def update_run(record: AgentRunRecord, response: ChatResponse) -> AgentRunRecord:
    record.workflow_response = response
    record.clarification_context = response.clarification_context
    record.iteration_count += 1
    record.events.append(response)
    return record


def cancel_run(record: AgentRunRecord, reason: str | None = None) -> AgentRunRecord:
    record.cancelled = True
    record.cancel_reason = reason
    return record
