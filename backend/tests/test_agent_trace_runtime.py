"""Tests for agent_trace_runtime helpers."""
import pytest

from app.agent.loop.agent_trace_runtime import _iteration_input
from app.models.chat import ChatResponse
from app.models.clarification_context import ClarificationContext, make_scope_key


# --------------------------------------------------------------------------- #
# Minimal ChatResponse builder
# _iteration_input only reads .query, .context_summary, .clarification_context,
# so we use model_construct to skip full validation.
# --------------------------------------------------------------------------- #

def _response(
    *,
    query: str = "test query",
    clarification_context: ClarificationContext | None = None,
    context_summary=None,
) -> ChatResponse:
    return ChatResponse.model_construct(
        query=query,
        planned_steps=[],
        step_results=[],
        has_warnings=False,
        has_errors=False,
        rag_context=None,
        clarification_context=clarification_context,
        context_summary=context_summary,
    )


def _clarification(
    *,
    dataset_id: str = "ds-1",
    original_query: str = "filter revenue > 1000",
    question: str = "Which column?",
    user_answer: str | None = None,
    resolved_parameter: str | None = None,
    affected_step: dict | None = None,
    status: str = "pending",
) -> ClarificationContext:
    return ClarificationContext(
        dataset_id=dataset_id,
        original_query=original_query,
        question=question,
        user_answer=user_answer,
        resolved_parameter=resolved_parameter,
        affected_step=affected_step,
        status=status,
        scope_key=make_scope_key(dataset_id=dataset_id, original_query=original_query),
    )


# --------------------------------------------------------------------------- #
# _iteration_input — clarification_context fields
# --------------------------------------------------------------------------- #

class TestIterationInputClarificationContext:
    def test_clarification_context_none_when_absent(self):
        result = _iteration_input(_response())
        assert result["clarification_context"] is None

    def test_includes_dataset_id(self):
        # Bug regression: dataset_id was previously omitted from the serialized dict.
        ctx = _clarification(dataset_id="ds-42")
        result = _iteration_input(_response(clarification_context=ctx))
        assert result["clarification_context"]["dataset_id"] == "ds-42"

    def test_includes_original_query(self):
        # Bug regression: original_query was previously omitted from the serialized dict.
        ctx = _clarification(original_query="filter amount > 500")
        result = _iteration_input(_response(clarification_context=ctx))
        assert result["clarification_context"]["original_query"] == "filter amount > 500"

    def test_includes_all_clarification_context_fields(self):
        ctx = _clarification(
            dataset_id="ds-1",
            original_query="filter revenue > 1000",
            question="Which column?",
            user_answer="amount",
            resolved_parameter="amount",
            affected_step={"type": "filter_rows", "column": "revenue"},
            status="resolved",
        )
        result = _iteration_input(_response(clarification_context=ctx))
        cc = result["clarification_context"]

        assert cc["dataset_id"] == "ds-1"
        assert cc["original_query"] == "filter revenue > 1000"
        assert cc["question"] == "Which column?"
        assert cc["user_answer"] == "amount"
        assert cc["resolved_parameter"] == "amount"
        assert cc["affected_step"] == {"type": "filter_rows", "column": "revenue"}
        assert cc["status"] == "resolved"
        assert "scope_key" in cc

    def test_clarification_context_is_serializable_dict(self):
        ctx = _clarification()
        result = _iteration_input(_response(clarification_context=ctx))
        # Must be a plain dict, not a Pydantic model, so it can be stored in trace.input.
        assert isinstance(result["clarification_context"], dict)

    def test_scope_key_matches_expected_value(self):
        ctx = _clarification(dataset_id="ds-1", original_query="filter revenue > 1000")
        result = _iteration_input(_response(clarification_context=ctx))
        expected_key = make_scope_key(dataset_id="ds-1", original_query="filter revenue > 1000")
        assert result["clarification_context"]["scope_key"] == expected_key


# --------------------------------------------------------------------------- #
# _iteration_input — other fields
# --------------------------------------------------------------------------- #

class TestIterationInputOtherFields:
    def test_query_is_preserved(self):
        result = _iteration_input(_response(query="my query"))
        assert result["query"] == "my query"

    def test_workflow_context_summary_none_when_absent(self):
        result = _iteration_input(_response(context_summary=None))
        assert result["workflow_context_summary"] is None


# --------------------------------------------------------------------------- #
# make_agent_trace — max_iterations contract
# Bug regression: max_iterations was previously computed as
# max(DEFAULT_MAX_AGENT_ITERATIONS, len(iterations) or 1), which grows with
# the actual iteration count and breaks the max_iterations_reached contract.
# --------------------------------------------------------------------------- #


from app.agent.loop.agent_trace_runtime import make_agent_trace
from app.agent.loop.agent_models import DEFAULT_MAX_AGENT_ITERATIONS


class TestMakeAgentTraceMaxIterations:
    def _no_events_trace(self, **kwargs):
        return make_agent_trace(
            state="completed",
            events=[],
            action_for_event=lambda r: "stop_with_result",
            stop_reason_for_event=lambda r: None,
            **kwargs,
        )

    def test_default_max_iterations_is_constant(self):
        trace = self._no_events_trace()
        assert trace.max_iterations == DEFAULT_MAX_AGENT_ITERATIONS

    def test_summary_max_iterations_matches_trace(self):
        trace = self._no_events_trace()
        assert trace.summary.max_iterations == trace.max_iterations

    def test_explicit_max_iterations_is_respected(self):
        trace = self._no_events_trace(max_iterations=5)
        assert trace.max_iterations == 5
        assert trace.summary.max_iterations == 5

    def test_max_iterations_does_not_shrink_to_default_when_configured_higher(self):
        # Bug regression: old code used max(DEFAULT_MAX_AGENT_ITERATIONS, len(iterations) or 1).
        # If configured max is 5 but only 1 event ran, old code would report DEFAULT (3),
        # not the configured 5 — making the trace lie about the actual configured limit.
        events = [_response(query="q0")]
        trace = make_agent_trace(
            state="completed",
            events=events,
            action_for_event=lambda r: "stop_with_result",
            stop_reason_for_event=lambda r: "done",
            max_iterations=5,
        )
        assert trace.max_iterations == 5
        assert trace.summary.max_iterations == 5

    def test_trace_and_summary_max_iterations_always_consistent(self):
        for configured in (1, 3, 5, 10):
            trace = self._no_events_trace(max_iterations=configured)
            assert trace.max_iterations == trace.summary.max_iterations == configured
