"""Pydantic contracts for agent observation intelligence."""
from typing import Literal

from pydantic import BaseModel, Field


ObservationSignal = Literal[
    "empty_result",
    "high_warning_rate",
    "validation_failed",
    "execution_error",
    "schema_changed",
    "large_row_removal",
    "no_rows_matched",
    "missing_column",
]


ObservationRecommendedAction = Literal[
    "clarify",
    "plan_workflow",
    "preview_workflow",
    "confirm_required",
    "stop_with_result",
    "stop_with_error",
]

# Action types for candidate fixes — what the UI should do when the fix is chosen.
CandidateFixAction = Literal[
    "suggest_query",   # prefill the chat input with a suggested query
    "inspect_column",  # trigger an inspect_unique_values query for a column
    "back_to_preview", # discard and go back
    "relax_filter",    # trigger a relaxed filter query
]


class CandidateFix(BaseModel):
    """A single actionable fix suggestion surfaced in the Observation panel."""
    id: str
    label: str
    description: str
    action_type: CandidateFixAction
    # For suggest_query / relax_filter / inspect_column: the query or column name to use.
    query: str | None = None


class ObservationSummary(BaseModel):
    status: Literal["not_observed", "ok", "warning", "error"] = "not_observed"
    signals: list[ObservationSignal] = Field(default_factory=list)
    message: str | None = None
    # Human-readable explanation of what the observation means and why it matters.
    diagnostic_explanation: str | None = None
    possible_causes: list[str] = Field(default_factory=list)
    # Actionable fix suggestions surfaced to the user via the UI.
    candidate_fixes: list[CandidateFix] = Field(default_factory=list)
    recommended_next_action: ObservationRecommendedAction | None = None
    workflow_state: str | None = None
