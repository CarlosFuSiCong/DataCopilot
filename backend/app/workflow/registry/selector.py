"""Future step-level tool selector.

Current tool selection is still mostly handled by the planner and registry
metadata. This module provides a deterministic boundary for MVP5 expansion.
"""
from pydantic import BaseModel, Field


class ToolSelection(BaseModel):
    selected_tool: str | None = None
    candidate_tools: list[str] = Field(default_factory=list)
    reason: str = ""


def select_tool(action_type: str, available_tools: set[str]) -> ToolSelection:
    """Select a matching tool by exact action type when available."""
    if action_type in available_tools:
        return ToolSelection(
            selected_tool=action_type,
            candidate_tools=[action_type],
            reason="Exact action type matched an available tool.",
        )
    return ToolSelection(
        selected_tool=None,
        candidate_tools=sorted(available_tools),
        reason="No exact tool match found.",
    )
