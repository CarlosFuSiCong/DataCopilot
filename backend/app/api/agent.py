"""Controlled Agent API boundary.

The legacy /chat endpoint remains the single-turn compatibility path. This
router adds Agent run/session semantics around the same deterministic pipeline.
"""
from fastapi import APIRouter, Query

from app.agent.loop import orchestrator
from app.agent.loop.agent_trace_runtime import make_agent_trace
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
async def start_agent_run(
    request: AgentRunRequest,
    include_trace: bool = Query(False, description="Include full AgentTrace iterations."),
) -> AgentRunResponse:
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
    return _build_response(record, include_trace=include_trace)


@router.post("/runs/{agent_run_id}/continue", response_model=AgentRunResponse)
async def continue_agent_run(
    agent_run_id: str,
    request: AgentContinueRequest,
    include_trace: bool = Query(False, description="Include full AgentTrace iterations."),
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
    return _build_response(record, include_trace=include_trace)


@router.post("/runs/{agent_run_id}/cancel", response_model=AgentRunResponse)
async def cancel_agent_run(
    agent_run_id: str,
    request: AgentCancelRequest | None = None,
    include_trace: bool = Query(False, description="Include full AgentTrace iterations."),
) -> AgentRunResponse:
    record = _require_run(agent_run_id)
    agent_run_store.cancel_run(record, reason=request.reason if request else None)
    return _build_response(record, include_trace=include_trace)


def _require_run(agent_run_id: str) -> AgentRunRecord:
    record = agent_run_store.get_run(agent_run_id)
    if not record:
        raise DataCopilotError(
            "Agent run was not found.",
            error_code="agent_run_not_found",
            context={"agent_run_id": agent_run_id},
        )
    return record


def _build_response(record: AgentRunRecord, *, include_trace: bool = False) -> AgentRunResponse:
    workflow_response = record.workflow_response
    agent_state = "cancelled" if record.cancelled else _record_state(record)
    agent_trace = make_agent_trace(
        state=agent_state,
        events=record.events,
        action_for_event=_action_for_response,
        stop_reason_for_event=_stop_reason,
        cancelled_reason=record.cancel_reason,
    )
    if record.cancelled:
        workflow_state = workflow_response.state if workflow_response else None
        return AgentRunResponse(
            agent_run_id=record.agent_run_id,
            agent_state="cancelled",
            iteration_summary=_iteration_summaries(record, agent_trace=agent_trace),
            agent_trace_summary=agent_trace.summary,
            agent_trace=agent_trace if include_trace else None,
            workflow_state=workflow_state,
            workflow_response=workflow_response,
        )

    if workflow_response is None:
        return AgentRunResponse(
            agent_run_id=record.agent_run_id,
            agent_state="created",
            iteration_summary=[],
            agent_trace_summary=agent_trace.summary,
            agent_trace=agent_trace if include_trace else None,
        )

    return AgentRunResponse(
        agent_run_id=record.agent_run_id,
        agent_state=agent_state,
        iteration_summary=_iteration_summaries(record, agent_trace=agent_trace),
        agent_trace_summary=agent_trace.summary,
        agent_trace=agent_trace if include_trace else None,
        workflow_state=workflow_response.state,
        next_required_user_action=_next_user_action(record, workflow_response),
        workflow_response=workflow_response,
    )


def _iteration_summaries(record: AgentRunRecord, *, agent_trace=None) -> list[AgentIterationSummary]:
    if agent_trace:
        return [
            AgentIterationSummary(
                iteration_index=iteration.iteration_index,
                action=iteration.action.type,
                agent_state=agent_trace.state if iteration == agent_trace.iterations[-1] else _agent_state(record.events[index]),
                workflow_state=record.events[index].state if index < len(record.events) else None,
                stop_reason=iteration.stop_reason,
                observation_status=iteration.observation.status,
            )
            for index, iteration in enumerate(agent_trace.iterations)
        ]
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


def _record_state(record: AgentRunRecord) -> AgentRunState:
    if not record.workflow_response:
        return "created"
    return _agent_state(record.workflow_response)


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
