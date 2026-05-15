"""Controlled Agent API boundary.

The legacy /chat endpoint remains the single-turn compatibility path. This
router adds Agent run/session semantics around the same deterministic pipeline.
"""
from fastapi import APIRouter

from app.agent.loop import orchestrator
from app.agent.loop.agent_models import AgentActionType, AgentRunState
from app.core.exceptions import DataCopilotError
from app.models.agent_api import (
    AgentCancelRequest,
    AgentContinueRequest,
    AgentIterationSummary,
    AgentRunRequest,
    AgentRunResponse,
    NextRequiredUserAction,
)
from app.models.chat import ChatRequest, ChatResponse
from app.services import agent_run_store
from app.services.agent_run_store import AgentRunRecord

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/runs", response_model=AgentRunResponse)
async def start_agent_run(request: AgentRunRequest) -> AgentRunResponse:
    record = agent_run_store.create_run(dataset_id=request.dataset_id, query=request.query)
    response = await orchestrator.run_chat(
        ChatRequest(
            dataset_id=request.dataset_id,
            query=request.query,
            rag_top_k=request.rag_top_k,
            auto_confirm=request.auto_confirm,
            previous_steps=request.previous_steps,
        )
    )
    agent_run_store.update_run(record, response)
    return _build_response(record)


@router.post("/runs/{agent_run_id}/continue", response_model=AgentRunResponse)
async def continue_agent_run(
    agent_run_id: str,
    request: AgentContinueRequest,
) -> AgentRunResponse:
    record = _require_run(agent_run_id)
    if record.cancelled:
        raise DataCopilotError(
            "Agent run has already been cancelled.",
            error_code="agent_run_cancelled",
            context={"agent_run_id": agent_run_id},
        )
    if not record.clarification_context or record.clarification_context.status != "pending":
        raise DataCopilotError(
            "Agent run is not waiting for a clarification answer.",
            error_code="agent_run_not_waiting_clarification",
            context={"agent_run_id": agent_run_id},
        )

    answer = request.answer.strip()
    if not answer:
        raise DataCopilotError(
            "Clarification answer cannot be empty.",
            error_code="clarification_answer_empty",
            context={"agent_run_id": agent_run_id},
        )

    clarification = record.clarification_context.model_copy(update={"user_answer": answer})
    response = await orchestrator.run_chat(
        ChatRequest(
            dataset_id=record.dataset_id,
            query=record.query,
            auto_confirm=request.auto_confirm,
            previous_steps=request.previous_steps,
            clarification_context=clarification,
        )
    )
    agent_run_store.update_run(record, response)
    return _build_response(record)


@router.post("/runs/{agent_run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(
    agent_run_id: str,
    request: AgentCancelRequest | None = None,
) -> AgentRunResponse:
    record = _require_run(agent_run_id)
    agent_run_store.cancel_run(record, reason=request.reason if request else None)
    return _build_response(record)


def _require_run(agent_run_id: str) -> AgentRunRecord:
    record = agent_run_store.get_run(agent_run_id)
    if not record:
        raise DataCopilotError(
            "Agent run was not found.",
            error_code="agent_run_not_found",
            context={"agent_run_id": agent_run_id},
        )
    return record


def _build_response(record: AgentRunRecord) -> AgentRunResponse:
    workflow_response = record.workflow_response
    if record.cancelled:
        workflow_state = workflow_response.state if workflow_response else None
        return AgentRunResponse(
            agent_run_id=record.agent_run_id,
            agent_state="cancelled",
            iteration_summary=_iteration_summaries(record) + [
                AgentIterationSummary(
                    iteration_index=record.iteration_count,
                    action="stop_with_error",
                    agent_state="cancelled",
                    workflow_state=workflow_state,
                    stop_reason=record.cancel_reason or "Agent run was cancelled by request.",
                )
            ],
            workflow_state=workflow_state,
            workflow_response=workflow_response,
        )

    if workflow_response is None:
        return AgentRunResponse(
            agent_run_id=record.agent_run_id,
            agent_state="created",
            iteration_summary=[],
        )

    return AgentRunResponse(
        agent_run_id=record.agent_run_id,
        agent_state=_agent_state(workflow_response),
        iteration_summary=_iteration_summaries(record),
        workflow_state=workflow_response.state,
        next_required_user_action=_next_user_action(record, workflow_response),
        workflow_response=workflow_response,
    )


def _iteration_summaries(record: AgentRunRecord) -> list[AgentIterationSummary]:
    return [
        AgentIterationSummary(
            iteration_index=index,
            action=_action_for_response(response),
            agent_state=_agent_state(response),
            workflow_state=response.state,
            stop_reason=_stop_reason(response),
            observation_status=_observation_status(response),
        )
        for index, response in enumerate(record.events)
    ]


def _agent_state(response: ChatResponse) -> AgentRunState:
    if response.needs_clarification:
        return "needs_clarification"
    if response.state in {"preview_ready", "warning_review"} and response.execution_result is None:
        return "waiting_confirmation"
    if response.state == "executed":
        return "completed"
    if response.has_errors or response.state == "failed":
        return "failed"
    return "running"


def _action_for_response(response: ChatResponse) -> AgentActionType:
    state = _agent_state(response)
    if state == "needs_clarification":
        return "clarify"
    if state == "waiting_confirmation":
        return "confirm_required"
    if state == "completed":
        return "stop_with_result"
    if state == "failed":
        return "stop_with_error"
    return "preview_workflow"


def _stop_reason(response: ChatResponse) -> str | None:
    state = _agent_state(response)
    if state == "needs_clarification":
        return "User clarification is required before the Agent can continue."
    if state == "waiting_confirmation":
        return "Workflow preview is ready and requires explicit user confirmation."
    if state == "completed":
        return "Workflow completed successfully."
    if state == "failed":
        return "Workflow failed before completion."
    return None


def _observation_status(response: ChatResponse) -> str | None:
    observation = response.context_summary.last_observation if response.context_summary else None
    return observation.status if observation else None


def _next_user_action(
    record: AgentRunRecord,
    response: ChatResponse,
) -> NextRequiredUserAction | None:
    state = _agent_state(response)
    if state == "needs_clarification":
        return NextRequiredUserAction(
            type="answer_clarification",
            message=response.clarification_question or "Please answer the clarification question.",
            endpoint=f"/api/agent/runs/{record.agent_run_id}/continue",
            payload={"answer": "<user answer>"},
        )
    if state == "waiting_confirmation":
        return NextRequiredUserAction(
            type="confirm_workflow",
            message="Review the preview, then confirm the workflow if the result is acceptable.",
            endpoint="/api/workflows/confirm",
            payload={
                "dataset_id": record.dataset_id,
                "query": record.query,
                "steps": response.planned_steps,
            },
        )
    return None
