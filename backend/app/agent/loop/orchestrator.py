"""Future controlled Agent orchestration service.

This module intentionally does not drive runtime behavior yet. It documents
the entry point that will coordinate bounded observe-decide-act iterations in
MVP5.
"""
from app.agent.loop.agent_models import DEFAULT_MAX_AGENT_ITERATIONS, AgentTrace, AgentTraceSummary


def empty_agent_trace() -> AgentTrace:
    """Return an empty created trace for future orchestration callers."""
    return AgentTrace(
        state="created",
        max_iterations=DEFAULT_MAX_AGENT_ITERATIONS,
        summary=AgentTraceSummary(
            state="created",
            iteration_count=0,
            max_iterations=DEFAULT_MAX_AGENT_ITERATIONS,
            full_trace_available=True,
        ),
        iterations=[],
    )
