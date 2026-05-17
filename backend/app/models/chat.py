"""Pydantic models for the chat (full pipeline) endpoint."""
from typing import Any

from pydantic import BaseModel

from app.models.clarification_context import ClarificationContext
from app.models.runtime_trace import WorkflowAttempt, WorkflowContextSummary, WorkflowRunState
from app.models.rag import RAGContext
from app.models.workflow_execution import ExecutionResult, StepResult
from app.models.workflow_steps import WorkflowStep


class ChatRequest(BaseModel):
    dataset_id: str
    query: str
    rag_top_k: int = 3
    # When True (default) and no warnings/errors are detected, the backend
    # automatically runs execute() + explain() and returns the full result.
    # When False, always returns preview-only so the UI can show the Confirm button.
    auto_confirm: bool = True
    # Steps from the previous confirmed workflow. When non-empty, the planner's
    # new steps are appended after these so that the second query operates on the
    # result of the first, enabling multi-turn chaining within one dataset session.
    previous_steps: list[WorkflowStep] = []
    # User's answer to a clarification question. When present, the planner
    # receives the original query plus this context to resolve ambiguity.
    clarification_context: str | ClarificationContext | None = None


class ChatResponse(BaseModel):
    query: str
    # Raw step dicts as produced by the planner — inspectable before validation
    planned_steps: list[dict]
    # Per-step execution metrics and risk-rule issues from the preview pass
    step_results: list[StepResult]
    has_warnings: bool
    has_errors: bool
    rag_context: RAGContext
    # Populated only when auto_confirm triggered a full execute + explain pass.
    # None means the client should show a Confirm button and call /workflows/confirm.
    explanation: str | None = None
    execution_result: ExecutionResult | None = None
    # UUID of the persisted result run; populated alongside execution_result.
    run_id: str | None = None
    # Set to True when the planner needs more information before planning.
    # The frontend should show clarification_question and await the user's answer.
    needs_clarification: bool = False
    clarification_question: str | None = None
    clarification_type: str | None = None
    clarification_context: ClarificationContext | None = None
    state: WorkflowRunState = "draft"
    attempts: list[WorkflowAttempt] = []
    context_summary: WorkflowContextSummary | None = None
    # RouteDecision from the query classifier; included for traceability.
    route_decision: dict[str, Any] | None = None
    # Set to True for read-only analytical results (profile, distribution, etc.)
    # that do not mutate the dataset state and are not saved to the run history.
    is_read_only: bool = False
    # Sub-type of an Ask Mode response: "schema_overview", "column_detail",
    # "dataset_overview", "analytical", or None for mutating workflow responses.
    ask_mode_type: str | None = None
    # Where the answer was grounded: "schema", "analytical_execution",
    # "workflow_execution", or None.
    evidence_source: str | None = None
    # Suggested analysis directions for broad / ambiguous clarification requests.
    # Each dict has: id, label, description, query, tool.
    clarification_choices: list[dict[str, Any]] | None = None
