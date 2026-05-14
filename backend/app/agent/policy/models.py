"""Pydantic contracts for deterministic action policy decisions."""
from typing import Literal

from pydantic import BaseModel, Field


PolicyDecision = Literal[
    "auto_executable",
    "preview_only",
    "requires_confirmation",
    "blocked",
]

WorkflowAction = Literal[
    "plan_workflow",
    "preview_workflow",
    "execute_workflow",
    "confirm_workflow",
]


class ActionPolicyResult(BaseModel):
    action: WorkflowAction
    decision: PolicyDecision
    reason: str
    can_execute: bool = False
    requires_confirmation: bool = False
    error_code: str | None = None
    issue_codes: list[str] = Field(default_factory=list)
