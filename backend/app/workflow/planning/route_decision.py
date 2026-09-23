"""RouteDecision contract: output of query classifier for each incoming query."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

QueryType = Literal[
    "ask",
    "cleaning",
    "filtering",
    "sorting",
    "aggregation",
    "comparison",
    "profiling",
    "diagnosis",
    "visual_analysis",
    "broad_analysis_request",
    "ambiguous_request",
    "unsupported_request",
]

Route = Literal[
    "ask_mode",
    "deterministic_tool",
    "llm_planner",
    "clarification",
    "unsupported",
]


class RouteDecision(BaseModel):
    """Classifier output for a single query.

    Consumers use `route` to decide the next processing path.
    `evidence` lists the signals that drove the decision.
    """

    route: Route
    query_type: QueryType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    evidence: list[str] = Field(default_factory=list)
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    selected_tool: str | None = None
    fallback_route: Route | None = None
