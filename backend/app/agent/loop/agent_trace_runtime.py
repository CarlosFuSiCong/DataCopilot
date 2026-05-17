"""Runtime helpers for building public Agent traces from API run events."""
from app.agent.loop.agent_models import (
    DEFAULT_MAX_AGENT_ITERATIONS,
    AgentAction,
    AgentActionType,
    AgentDecision,
    AgentIteration,
    AgentRunState,
    AgentTrace,
    AgentTraceSummary,
    AgentValidationSummary,
)
from app.agent.observation.models import ObservationSummary
from app.models.chat import ChatResponse


def make_agent_trace(
    *,
    state: AgentRunState,
    events: list[ChatResponse],
    action_for_event,
    stop_reason_for_event,
    cancelled_reason: str | None = None,
    max_iterations: int = DEFAULT_MAX_AGENT_ITERATIONS,
) -> AgentTrace:
    """Build an AgentTrace without copying raw dataset preview rows."""
    iterations = [
        _iteration_from_response(
            index=index,
            response=response,
            action_type=action_for_event(response),
            stop_reason=stop_reason_for_event(response),
        )
        for index, response in enumerate(events)
    ]
    if state == "cancelled":
        iterations.append(_cancel_iteration(len(iterations), events[-1] if events else None, cancelled_reason))

    last_iteration = iterations[-1] if iterations else None
    workflow_summary = None
    if events and events[-1].context_summary:
        workflow_summary = events[-1].context_summary

    return AgentTrace(
        state=state,
        max_iterations=max_iterations,
        summary=AgentTraceSummary(
            state=state,
            iteration_count=len(iterations),
            max_iterations=max_iterations,
            stop_reason=last_iteration.stop_reason if last_iteration else None,
            last_action=last_iteration.action.type if last_iteration else None,
            last_observation=last_iteration.observation if last_iteration else None,
            workflow_context_summary=workflow_summary,
            full_trace_available=True,
        ),
        iterations=iterations,
    )


def _iteration_from_response(
    *,
    index: int,
    response: ChatResponse,
    action_type: AgentActionType,
    stop_reason: str | None,
) -> AgentIteration:
    observation = _observation(response)
    return AgentIteration(
        iteration_index=index,
        input=_iteration_input(response),
        decision=AgentDecision(
            decision=action_type,
            rationale=stop_reason or "Agent selected the next workflow action from the current runtime state.",
            requires_user_input=action_type in {"clarify", "confirm_required"},
        ),
        action=AgentAction(
            type=action_type,
            parameters=_action_parameters(response),
            workflow_steps=response.planned_steps if action_type != "clarify" else [],
        ),
        validation=_validation_summary(response),
        observation=observation,
        stop_reason=stop_reason,
    )


def _cancel_iteration(
    index: int,
    response: ChatResponse | None,
    reason: str | None,
) -> AgentIteration:
    observation = ObservationSummary(
        status="warning",
        message=reason or "Agent run was cancelled by request.",
        recommended_next_action="stop_with_error",
    )
    return AgentIteration(
        iteration_index=index,
        input={
            "workflow_context_summary": (
                response.context_summary.model_dump() if response and response.context_summary else None
            )
        },
        decision=AgentDecision(
            decision="stop_with_error",
            rationale=observation.message,
            requires_user_input=False,
        ),
        action=AgentAction(type="stop_with_error", parameters={"cancelled": True}),
        validation=AgentValidationSummary(status="not_run"),
        observation=observation,
        stop_reason=observation.message,
    )


def _iteration_input(response: ChatResponse) -> dict:
    return {
        "query": response.query,
        "workflow_context_summary": response.context_summary.model_dump() if response.context_summary else None,
        "clarification_context": (
            response.clarification_context.model_dump()
            if response.clarification_context
            else None
        ),
    }


def _action_parameters(response: ChatResponse) -> dict:
    if response.needs_clarification:
        return {"question": response.clarification_question}
    if response.execution_result is None:
        return {
            "requires_confirmation": response.state in {"preview_ready", "warning_review"},
            "has_warnings": response.has_warnings,
            "has_errors": response.has_errors,
        }
    return {"run_id": response.run_id, "row_count": response.execution_result.row_count}


def _validation_summary(response: ChatResponse) -> AgentValidationSummary:
    validation_status = response.context_summary.validation_status if response.context_summary else None
    if validation_status in {"passed", "repaired"}:
        return AgentValidationSummary(status="passed", details={"validation_status": validation_status})
    if validation_status == "failed":
        return AgentValidationSummary(status="failed", details={"validation_status": validation_status})
    if response.has_errors:
        return AgentValidationSummary(status="failed", details={"workflow_state": response.state})
    return AgentValidationSummary(status="not_run", details={"workflow_state": response.state})


def _observation(response: ChatResponse) -> ObservationSummary:
    if response.context_summary and response.context_summary.last_observation:
        return response.context_summary.last_observation
    if response.needs_clarification:
        return ObservationSummary(
            status="warning",
            message=response.clarification_question or "Clarification is required.",
            recommended_next_action="clarify",
        )
    return ObservationSummary(
        status="ok",
        message=f"Workflow state is {response.state}.",
    )
