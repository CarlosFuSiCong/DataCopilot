"""Pydantic contracts for slot extraction results."""
from typing import Literal

from pydantic import BaseModel, Field

SlotIntent = Literal[
    "filter",
    "sort",
    "group_aggregate",
    "limit",
    "inspect",
    "clean",
    "unknown",
]

SlotOperator = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "is_null",
    "is_not_null",
]

SortDirection = Literal["asc", "desc"]
AggregationFunction = Literal["sum", "mean", "count", "min", "max", "median"]
QueryLocale = Literal["en", "zh", "mixed"]


class ExtractedSlots(BaseModel):
    """Named parameters extracted from the user query."""

    column: str | None = None
    operator: SlotOperator | None = None
    value: str | None = None
    target_column: str | None = None
    aggregation: AggregationFunction | None = None
    sort_direction: SortDirection | None = None
    limit: int | None = Field(default=None, ge=1)


class SlotExtractionResult(BaseModel):
    """Structured slot extraction contract between raw input and planning."""

    raw_query: str
    intent: SlotIntent = "unknown"
    slots: ExtractedSlots = Field(default_factory=ExtractedSlots)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_slots: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    query_locale: QueryLocale = "en"
