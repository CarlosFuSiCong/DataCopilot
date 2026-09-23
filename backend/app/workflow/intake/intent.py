"""Contracts for parsed user intent.

These models are intentionally lightweight. They document the future boundary
between raw chat input and the planning pipeline without changing the current
chat route behavior.
"""
from typing import Literal

from pydantic import BaseModel, Field


TaskIntentType = Literal[
    "transform_dataset",
    "inspect_dataset",
    "explain_result",
    "unknown",
]


class ParsedTaskIntent(BaseModel):
    intent: TaskIntentType = "unknown"
    goal: str
    constraints: list[str] = Field(default_factory=list)
    candidate_columns: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
