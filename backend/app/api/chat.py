"""Chat endpoint — RAG + Planner + Preview/Confirm pipeline.

POST /api/chat runs:
  RAG retrieval → LLM planner → validator → executor.preview() → risk check

If auto_confirm=True (default) and no warnings or errors are detected, the
endpoint also runs the full executor and result explainer, returning a
complete result in one round-trip.

If auto_confirm=False, or if the preview detects warnings/errors, only the
preview result is returned so the frontend can surface issues and ask the
user to confirm before calling POST /api/workflows/confirm.

Error states returned as 400 with error_code + context:
  - rag_no_hits: RAG retrieved no matching docs for the query
  - empty_workflow: planner returned no steps (query out of scope)
  - missing_column: workflow references a column not in the dataset
  - execution_error: a step failed at pandas runtime
"""
import logging
import re

from fastapi import APIRouter

from app.core.exceptions import ClarificationNeeded, ExecutionError, PlannerError, WorkflowValidationError
from app.models.chat import ChatRequest, ChatResponse
from app.models.workflow import ExecutionResult
from app.services import dataset_store, executor as executor_service
from app.services import rag_service, result_explainer, run_store, validator as validator_service
from app.services import workflow_planner
from app.services.profiler import profile
from app.services.validator import simulate_columns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Shown when the planner returns no steps for the query.
_SUPPORTED_STEPS = [
    "filter_rows", "select_columns", "group_by", "sort_values",
    "rename_columns", "remove_missing_values", "fill_missing_values",
    "drop_columns", "derive_column", "date_extract", "limit_rows",
    "generate_summary",
]
_EXAMPLE_QUERIES = [
    "Filter rows where amount > 1000",
    "Group by region and sum the amount",
    "Show the top 10 rows sorted by quantity descending",
    "Remove rows with missing values",
    "Extract the month from the order_date column",
    "Add a new column total = amount * quantity",
]


def _explicit_missing_column(query: str, column_names: list[str]) -> str | None:
    """Return an explicitly referenced missing column, if the query has one.

    This catches product-facing cases like "where sales > 1000" before the LLM
    can reinterpret "sales" as a semantically similar existing column.
    """
    available = set(column_names)
    patterns = [
        r"\bwhere\s+([A-Za-z_][A-Za-z0-9_]*)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            col = match.group(1)
            if col not in available:
                return col
    return None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    content = await dataset_store.load(request.dataset_id)
    dataset_profile = profile(content, filename="<cached>")
    column_names = [col.name for col in dataset_profile.columns]

    missing_col = _explicit_missing_column(request.query, column_names)
    if missing_col:
        raise WorkflowValidationError(
            f"Column '{missing_col}' does not exist in the dataset.",
            error_code="missing_column",
            context={"available_columns": column_names},
        )

    # When the user answers a clarification question, merge the answer into the
    # query so the planner has full context.
    planner_query = request.query
    if request.clarification_context:
        planner_query = (
            f"{request.query}\nUser clarification: {request.clarification_context}"
        )

    rag_ctx = await rag_service.build_context(
        query=planner_query,
        dataset_profile=dataset_profile,
        top_k=request.rag_top_k,
    )

    # RAG no hits: surface retrieval info so the user can rephrase.
    if not rag_ctx.retrieved_docs:
        raise WorkflowValidationError(
            "No matching workflow documentation found for your query. "
            "Try rephrasing using keywords like 'filter', 'group by', 'sort', or 'select'.",
            error_code="rag_no_hits",
            context={
                "retrieval_method": rag_ctx.debug.method,
                "query": request.query,
                "suggestion": (
                    "Try describing the operation more explicitly, e.g. "
                    "'filter rows where status = completed'."
                ),
            },
        )

    try:
        new_steps = workflow_planner.plan(query=planner_query, ctx=rag_ctx)
    except ClarificationNeeded as exc:
        # Planner decided it needs more information — return 200 with a
        # clarification question; the frontend will ask the user and resend.
        logger.info("Clarification needed for query=%r: %s", request.query, exc.question)
        return ChatResponse(
            query=request.query,
            planned_steps=[],
            step_results=[],
            has_warnings=False,
            has_errors=False,
            rag_context=rag_ctx,
            needs_clarification=True,
            clarification_question=exc.question,
        )
    except PlannerError as exc:
        # Build context from what RAG actually retrieved — only show the
        # operations that were relevant to this query, not the full list.
        relevant = [
            {"step_type": doc.type, "description": doc.description, "example": doc.example}
            for doc in rag_ctx.retrieved_docs
            if doc.doc_type == "transformation" and doc.type
        ]
        planner_hint = str(exc) if str(exc) != "The request cannot be handled with the supported transformations." else None
        raise WorkflowValidationError(
            "The planner could not build a workflow for this query. "
            "The request may be outside the supported transformation scope.",
            error_code="empty_workflow",
            context={
                "planner_hint": planner_hint,
                "relevant_steps": relevant or None,
                # Fall back to generic list only when RAG returned nothing useful.
                "supported_steps": _SUPPORTED_STEPS if not relevant else None,
                "example_queries": _EXAMPLE_QUERIES if not relevant else None,
            },
        ) from exc

    # Chain: prepend steps from the previous confirmed workflow so the new
    # query operates on the result of prior transformations, not the raw CSV.
    steps = list(request.previous_steps) + new_steps
    planned_steps = [step.model_dump() for step in steps]

    try:
        validator_service.validate(steps, column_names)
    except WorkflowValidationError as exc:
        msg = str(exc)
        # Empty workflow: planner produced no steps.
        if "at least one step" in msg:
            relevant = [
                {"step_type": doc.type, "description": doc.description, "example": doc.example}
                for doc in rag_ctx.retrieved_docs
                if doc.doc_type == "transformation" and doc.type
            ]
            raise WorkflowValidationError(
                "The planner could not build a workflow for this query. "
                "The request may be outside the supported transformation scope.",
                error_code="empty_workflow",
                context={
                    "relevant_steps": relevant or None,
                    "supported_steps": _SUPPORTED_STEPS if not relevant else None,
                    "example_queries": _EXAMPLE_QUERIES if not relevant else None,
                },
            ) from exc
        # Missing column: planner referenced a column that doesn't exist.
        # For chained workflows, show the columns available *after* previous
        # steps ran, not the original dataset columns.
        if "does not exist in the dataset" in msg or "not found" in msg.lower():
            intermediate_cols = simulate_columns(request.previous_steps, column_names)
            raise WorkflowValidationError(
                msg,
                error_code="missing_column",
                context={"available_columns": intermediate_cols},
            ) from exc
        raise

    preview_result = executor_service.preview(steps, content)

    # If preview captured a step-level execution error, surface it with context.
    if preview_result.blocked_at_step is not None and preview_result.has_errors:
        blocked = preview_result.step_results[preview_result.blocked_at_step]
        issue_msg = blocked.issues[0].message if blocked.issues else blocked.message
        # Columns available just before the failing step — accounts for any
        # structural changes made by preceding steps (select, drop, rename, etc.).
        cols_at_failure = simulate_columns(steps[:preview_result.blocked_at_step], column_names)
        if "not found" in issue_msg.lower():
            raise ExecutionError(
                issue_msg,
                error_code="missing_column",
                context={"available_columns": cols_at_failure},
            )
        raise ExecutionError(
            issue_msg,
            error_code="execution_error",
            context={
                "failed_step_index": preview_result.blocked_at_step,
                "failed_step_type": blocked.step_type,
                "available_columns": cols_at_failure,
                "suggestion": (
                    "Check that the column names and parameter values match your dataset. "
                    "Use 'select columns' or 'show schema' to inspect available columns."
                ),
            },
        )

    explanation: str | None = None
    execution_result: ExecutionResult | None = None
    run_id: str | None = None

    if (
        request.auto_confirm
        and not preview_result.has_warnings
        and not preview_result.has_errors
    ):
        execution_result = executor_service.execute(steps, content)
        explanation = result_explainer.explain(
            query=request.query,
            planned_steps=planned_steps,
            execution_result=execution_result,
            dataset_summary=rag_ctx.dataset_summary.model_dump(),
        )
        # Persist result CSV so the frontend can offer a download link.
        try:
            result_df = executor_service.execute_to_df(steps, content)
            result_name = request.query[:40].strip().replace(" ", "_") + "_result.csv"
            csv_bytes = result_df.to_csv(index=False).encode("utf-8")
            run_id = await run_store.save(
                dataset_id=request.dataset_id,
                csv_bytes=csv_bytes,
                filename=result_name,
                planned_steps=planned_steps,
                row_count=execution_result.row_count,
                query=request.query,
                status="success",
                explanation=explanation,
            )
        except Exception:
            logger.warning("Failed to persist run artifact for dataset %s", request.dataset_id, exc_info=True)

        logger.info(
            "Chat auto-confirm complete: query=%r steps=%d rows=%d run_id=%s",
            request.query,
            len(steps),
            execution_result.row_count,
            run_id,
        )
    else:
        logger.info(
            "Chat preview-only: query=%r auto_confirm=%s has_warnings=%s has_errors=%s",
            request.query,
            request.auto_confirm,
            preview_result.has_warnings,
            preview_result.has_errors,
        )

    return ChatResponse(
        query=request.query,
        planned_steps=planned_steps,
        step_results=preview_result.step_results,
        has_warnings=preview_result.has_warnings,
        has_errors=preview_result.has_errors,
        rag_context=rag_ctx,
        explanation=explanation,
        execution_result=execution_result,
        run_id=run_id,
        needs_clarification=False,
    )
