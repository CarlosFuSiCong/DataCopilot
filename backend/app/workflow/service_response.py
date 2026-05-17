"""Response and trace builders for the chat service pipeline.

These functions construct ChatResponse, RAGContext, WorkflowTrace, and related
output objects. They are called from service.py but are kept separate so that
the orchestration logic in service.py stays focused on pipeline flow.
"""
from __future__ import annotations

import logging

from app.workflow import runtime as workflow_runtime
from app.workflow.execution import executor as executor_service
from app.workflow.response import result_explainer
from app.workflow.observation.models import ObservationSummary
from app.models.chat import ChatRequest, ChatResponse
from app.models.clarification_context import ClarificationContext, new_pending_context
from app.models.rag import DatasetSummary, RAGContext, RetrievalDebug
from app.models.workflow_execution import ExecutionResult
from app.services import run_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clarification helpers
# ---------------------------------------------------------------------------

def _clarification_answer(value: str | ClarificationContext | None) -> str | None:
    """Extract the resolved answer string from a clarification context or raw string."""
    if isinstance(value, ClarificationContext):
        return value.user_answer or value.resolved_parameter
    return value


# ---------------------------------------------------------------------------
# Minimal RAGContext
# ---------------------------------------------------------------------------

def _build_minimal_rag_ctx(
    query: str,
    dataset_profile,
    column_names: list[str],
    method: str = "deterministic_tool",
) -> RAGContext:
    """Build a minimal RAGContext for routes that skip RAG retrieval."""
    return RAGContext(
        query=query,
        retrieved_docs=[],
        dataset_summary=DatasetSummary(
            filename=f"<{method}>",
            row_count=dataset_profile.row_count,
            column_count=len(column_names),
            columns=[
                {
                    "name": c.name,
                    "dtype": c.dtype,
                    "missing_count": c.missing_count,
                    "missing_pct": c.missing_pct,
                }
                for c in dataset_profile.columns
            ],
        ),
        debug=RetrievalDebug(method=method, query_tokens=[], all_scores={}),
    )


# ---------------------------------------------------------------------------
# Ask mode
# ---------------------------------------------------------------------------

def _ask_mode_response(
    *,
    request: ChatRequest,
    dataset_profile,
    column_names: list[str],
    route_decision,
) -> ChatResponse:
    """Return a read-only answer about the dataset without invoking the planner."""
    col_lines = []
    for col in dataset_profile.columns:
        missing = f", missing={col.missing_count}" if col.missing_count else ""
        col_lines.append(f"  - {col.name} ({col.dtype}{missing})")
    cols_text = "\n".join(col_lines)

    answer = (
        f"Dataset has {dataset_profile.row_count} rows and {len(column_names)} columns:\n"
        f"{cols_text}"
    )

    minimal_rag = RAGContext(
        query=request.query,
        retrieved_docs=[],
        dataset_summary=DatasetSummary(
            filename="<ask_mode>",
            row_count=dataset_profile.row_count,
            column_count=len(column_names),
            columns=[
                {
                    "name": c.name,
                    "dtype": c.dtype,
                    "missing_count": c.missing_count,
                    "missing_pct": c.missing_pct,
                }
                for c in dataset_profile.columns
            ],
        ),
        debug=RetrievalDebug(method="ask_mode", query_tokens=[], all_scores={}),
    )

    return ChatResponse(
        query=request.query,
        planned_steps=[],
        step_results=[],
        has_warnings=False,
        has_errors=False,
        rag_context=minimal_rag,
        explanation=answer,
        state="executed",
        route_decision=route_decision.model_dump() if route_decision else None,
    )


# ---------------------------------------------------------------------------
# Clarification response
# ---------------------------------------------------------------------------

def _clarification_response(
    *,
    request: ChatRequest,
    content: bytes,
    dataset_profile,
    column_names: list[str],
    rag_ctx: RAGContext,
    question: str,
    current_steps: list = None,
    attempts: list = None,
    validation_status: str | None = None,
    observation: ObservationSummary | None = None,
    affected_step: dict | None = None,
    clarification_type: str = "planning",
) -> ChatResponse:
    steps = current_steps or []
    trace_attempts = attempts or []
    clarification = new_pending_context(
        dataset_id=request.dataset_id,
        original_query=request.query,
        question=question,
        affected_step=affected_step,
    )
    context = workflow_runtime.build_context(
        dataset_id=request.dataset_id,
        content=content,
        query=request.query,
        dataset_profile=dataset_profile,
        column_names=column_names,
        previous_steps=request.previous_steps,
        current_steps=steps,
        rag_ctx=rag_ctx,
        clarification_answer=_clarification_answer(request.clarification_context),
        execution_boundary="preview",
    )
    trace = workflow_runtime.make_trace(
        state="needs_clarification",
        context=context,
        attempts=trace_attempts,
        validation_status=validation_status,
        observation=observation,
    )
    return ChatResponse(
        query=request.query,
        planned_steps=[step.model_dump() for step in steps],
        step_results=[],
        has_warnings=False,
        has_errors=False,
        rag_context=rag_ctx,
        needs_clarification=True,
        clarification_question=question,
        clarification_type=clarification_type,
        clarification_context=clarification,
        state="needs_clarification",
        attempts=trace_attempts,
        context_summary=trace.context_summary,
    )


# ---------------------------------------------------------------------------
# Relevant steps helper
# ---------------------------------------------------------------------------

def _relevant_steps(rag_ctx: RAGContext) -> list[dict]:
    """Extract transformation step summaries from retrieved RAG docs."""
    return [
        {"step_type": doc.type, "description": doc.description, "example": doc.example}
        for doc in rag_ctx.retrieved_docs
        if doc.doc_type == "transformation" and doc.type
    ]


# ---------------------------------------------------------------------------
# Trace builder
# ---------------------------------------------------------------------------

def _build_trace_after_preview(
    *,
    request: ChatRequest,
    content: bytes,
    dataset_profile,
    column_names: list[str],
    steps: list,
    rag_ctx: RAGContext,
    execution_boundary: str,
    attempts: list,
    state: str,
    planner_raw_output: str | None,
    validation_status: str | None,
    preview_result,
    observation: ObservationSummary,
):
    context = workflow_runtime.build_context(
        dataset_id=request.dataset_id,
        content=content,
        query=request.query,
        dataset_profile=dataset_profile,
        column_names=column_names,
        previous_steps=request.previous_steps,
        current_steps=steps,
        rag_ctx=rag_ctx,
        clarification_answer=_clarification_answer(request.clarification_context),
        execution_boundary=execution_boundary,
    )
    final_attempt = workflow_runtime.make_attempt(
        attempt_index=attempts[-1].attempt_index if attempts else 0,
        query=request.query,
        steps=steps,
        final_status=state,
        rag_ctx=rag_ctx,
        planner_raw_output=planner_raw_output,
        validation_result={"ok": True},
        preview_result=preview_result,
        repair_reason=attempts[-1].repair_reason if attempts else None,
    )
    attempts = attempts[:-1] + [final_attempt] if attempts else [final_attempt]
    observation.workflow_state = state
    trace = workflow_runtime.make_trace(
        state=state,
        context=context,
        attempts=attempts,
        validation_status=validation_status,
        preview_result=preview_result,
        observation=observation,
    )
    return trace, attempts


# ---------------------------------------------------------------------------
# Run artifact persistence
# ---------------------------------------------------------------------------

async def _persist_run_artifact(
    *,
    dataset_id: str,
    content: bytes,
    query: str,
    steps: list,
    planned_steps: list[dict],
    row_count: int,
    status: str,
    explanation: str,
    trace,
    parent_run_id: str | None = None,
) -> str | None:
    try:
        result_df = executor_service.execute_to_df(steps, content)
        result_name = query[:40].strip().replace(" ", "_") + "_result.csv"
        csv_bytes = result_df.to_csv(index=False).encode("utf-8")
        return await run_store.save(
            dataset_id=dataset_id,
            csv_bytes=csv_bytes,
            filename=result_name,
            planned_steps=planned_steps,
            row_count=row_count,
            query=query,
            status=status,
            explanation=explanation,
            parent_run_id=parent_run_id,
            trace=trace.model_dump(),
            context_summary=trace.context_summary.model_dump(),
        )
    except Exception:
        logger.warning("Failed to persist run artifact for dataset %s", dataset_id, exc_info=True)
    return None
