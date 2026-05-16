"""Pydantic contracts for slot extraction results.

Slot extraction converts a raw user query into structured named parameters
(slots) before workflow planning. It does NOT generate workflow JSON directly.

Supported intents: filter, sort, group_aggregate, limit, inspect, clean.
Supported slot keys: column, operator, value, target_column, aggregation,
sort_direction, limit.
"""
from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #

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
    "eq",   # equal / 等于
    "ne",   # not equal / 不等于
    "gt",   # greater than / 大于 / 高于
    "gte",  # greater than or equal / 大于等于
    "lt",   # less than / 小于 / 低于
    "lte",  # less than or equal / 小于等于
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


# --------------------------------------------------------------------------- #
# Slot value container
# --------------------------------------------------------------------------- #

class ExtractedSlots(BaseModel):
    """Named parameters extracted from the user query.

    All fields are optional; missing slots are reported in
    SlotExtractionResult.missing_slots.
    """

    column: str | None = None
    operator: SlotOperator | None = None
    value: str | None = None
    target_column: str | None = None
    aggregation: AggregationFunction | None = None
    sort_direction: SortDirection | None = None
    limit: int | None = Field(default=None, ge=1)


# --------------------------------------------------------------------------- #
# Top-level result contract
# --------------------------------------------------------------------------- #

class SlotExtractionResult(BaseModel):
    """Result of slot extraction from a raw user query.

    This contract sits between raw chat input and the workflow planner.
    Slot extraction only fills named parameters; it does not produce
    workflow JSON.

    Fields:
        raw_query:      Original user input, preserved without modification.
        intent:         Primary operation the user wants to perform.
        slots:          Named parameter values extracted from the query.
        confidence:     0.0–1.0 estimate of extraction reliability.
        missing_slots:  Slot names that are required for the intent but absent.
        ambiguities:    Free-text descriptions of ambiguous parts of the query.
        query_locale:   Detected language of the query (en / zh / mixed).
    """

    raw_query: str
    intent: SlotIntent = "unknown"
    slots: ExtractedSlots = Field(default_factory=ExtractedSlots)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    missing_slots: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    query_locale: QueryLocale = "en"
