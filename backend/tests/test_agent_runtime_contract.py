"""Tests for the MVP5 controlled Agent runtime contract."""
import pytest

from app.models.agent import (
    DEFAULT_MAX_AGENT_ITERATIONS,
    AgentAction,
    AgentDecision,
    AgentIteration,
    AgentTrace,
    AgentTraceSummary,
    AgentValidationSummary,
    ObservationSummary,
)
from app.models.runtime import WorkflowContext, WorkflowContextSummary, WorkflowTrace


def _iteration(index: int = 0, *, workflow_trace: WorkflowTrace | None = None) -> AgentIteration:
    return AgentIteration(
        iteration_index=index,
        input={"query": "filter completed orders"},
        decision=AgentDecision(
            decision="plan_workflow",
            rationale="The request can be represented as a validated workflow.",
        ),
        action=AgentAction(
            type="plan_workflow",
            workflow_steps=[
                {
                    "type": "filter_rows",
                    "column": "status",
                    "operator": "==",
                    "value": "completed",
                }
            ],
        ),
        validation=AgentValidationSummary(status="passed"),
        observation=ObservationSummary(
            status="ok",
            message="Workflow planning passed validation.",
            recommended_next_action="preview_workflow",
        ),
        workflow_trace=workflow_trace,
    )


def _workflow_trace() -> WorkflowTrace:
    context = WorkflowContext(
        dataset_id="dataset-1",
        dataset_hash="hash-1",
        query="filter completed orders",
        dataset_profile={"row_count": 2},
        current_schema=["status", "amount"],
        execution_boundary="preview",
    )
    summary = WorkflowContextSummary(
        query=context.query,
        dataset_hash=context.dataset_hash,
        schema_columns=context.current_schema,
        row_count=2,
        planned_step_types=["filter_rows"],
        status="planned",
        boundary="preview",
        validation_status="passed",
    )
    return WorkflowTrace(
        state="planned",
        context=context,
        context_summary=summary,
        attempts=[],
    )


def test_agent_trace_uses_three_iterations_by_default():
    iteration = _iteration()
    trace = AgentTrace(
        state="running",
        summary=AgentTraceSummary(
            state="running",
            iteration_count=1,
            last_action=iteration.action.type,
            last_observation=iteration.observation,
        ),
        iterations=[iteration],
    )

    assert trace.max_iterations == DEFAULT_MAX_AGENT_ITERATIONS
    assert trace.summary.max_iterations == DEFAULT_MAX_AGENT_ITERATIONS


def test_agent_iteration_records_required_loop_fields():
    data = _iteration().model_dump()

    for field in (
        "input",
        "decision",
        "action",
        "validation",
        "observation",
        "stop_reason",
    ):
        assert field in data


def test_agent_trace_wraps_workflow_trace_and_exposes_compressed_summary():
    workflow_trace = _workflow_trace()
    iteration = _iteration(workflow_trace=workflow_trace)
    trace = AgentTrace(
        state="running",
        summary=AgentTraceSummary(
            state="running",
            iteration_count=1,
            last_action=iteration.action.type,
            last_observation=iteration.observation,
            workflow_context_summary=workflow_trace.context_summary,
        ),
        iterations=[iteration],
    )

    compressed = trace.summary.model_dump()

    assert trace.iterations[0].workflow_trace == workflow_trace
    assert compressed["workflow_context_summary"]["planned_step_types"] == ["filter_rows"]
    assert "iterations" not in compressed


def test_agent_trace_rejects_more_than_max_iterations():
    iterations = [_iteration(index) for index in range(DEFAULT_MAX_AGENT_ITERATIONS + 1)]

    with pytest.raises(ValueError, match="max_iterations"):
        AgentTrace(
            state="running",
            summary=AgentTraceSummary(
                state="running",
                iteration_count=len(iterations),
            ),
            iterations=iterations,
        )


def test_max_iteration_stop_requires_explanation():
    iterations = [_iteration(index) for index in range(DEFAULT_MAX_AGENT_ITERATIONS)]

    with pytest.raises(ValueError, match="explain"):
        AgentTrace(
            state="max_iterations_reached",
            summary=AgentTraceSummary(
                state="max_iterations_reached",
                iteration_count=len(iterations),
            ),
            iterations=iterations,
        )


def test_max_iteration_stop_requires_full_iteration_count():
    iterations = [_iteration(index) for index in range(DEFAULT_MAX_AGENT_ITERATIONS - 1)]

    with pytest.raises(ValueError, match="exactly max_iterations"):
        AgentTrace(
            state="max_iterations_reached",
            summary=AgentTraceSummary(
                state="max_iterations_reached",
                iteration_count=len(iterations),
                stop_reason="Reached the configured iteration limit.",
            ),
            iterations=iterations,
        )
