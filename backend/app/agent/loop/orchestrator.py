"""Controlled Agent orchestration service."""
import logging
import re

from app.agent.context import rag_service
from app.agent.execution import executor as executor_service
from app.agent.final_response import result_explainer
from app.agent.loop.agent_models import DEFAULT_MAX_AGENT_ITERATIONS, AgentTrace, AgentTraceSummary
from app.agent.loop import workflow_runtime
from app.agent.nlu.slot_extractor import SlotExtractorOutput, extract_slots
from app.agent.nlu.slot_models import SlotExtractionResult
from app.agent.nlu.slot_validator import validate_slots
from app.agent.observation import signal_rules
from app.agent.observation.models import ObservationSummary
from app.agent.planning import workflow_planner
from app.agent.policy import action_policy
from app.agent.validation.workflow_validator import simulate_columns, validate as validate_workflow
from app.core.exceptions import ClarificationNeeded, ExecutionError, PlannerError, WorkflowValidationError
from app.models.chat import ChatRequest, ChatResponse
from app.models.clarification_context import (
    ClarificationContext,
    new_pending_context,
    planner_query_with_context,
    resolve_context,
    validate_scope,
)
from app.models.workflow_execution import ExecutionResult
from app.models.workflow_responses import ConfirmResponse
from app.models.workflow_transport import ConfirmRequest
from app.services import dataset_store, run_store
from app.services.profiler import get_column_names, profile

logger = logging.getLogger(__name__)

# Minimum slot extraction confidence required to use slot context in planning.
# Must stay in sync with workflow_planner._SLOT_HINT_MIN_CONFIDENCE (both = 0.7).
# A single threshold avoids the gap where slots are validated but then silently
# discarded by the planner's hint formatter (0.5 validation + 0.7 hint = broken).
_SLOT_MIN_CONFIDENCE = 0.7

# Maps slot extraction intent to the workflow step type it corresponds to.
# Used to build accurate affected_step context when slot validation needs clarification.
_INTENT_TO_STEP_TYPE: dict[str, str] = {
    "filter": "filter_rows",
    "sort": "sort_values",
    "group_aggregate": "group_by",
}

_SUPPORTED_STEPS = [
    "filter_rows", "select_columns", "group_by", "sort_values",
    "rename_columns", "remove_missing_values", "fill_missing_values",
    "drop_columns", "derive_column", "date_extract", "limit_rows",
    "generate_summary",
    "profile_column", "inspect_unique_values", "summarize_numeric_column",
    "compare_groups", "correlation_summary", "distribution_summary",
    "suggest_analysis_steps",
]
_EXAMPLE_QUERIES = [
    "Filter rows where amount > 1000",
    "Group by region and sum the amount",
    "Show the top 10 rows sorted by quantity descending",
    "Remove rows with missing values",
    "Extract the month from the order_date column",
    "Add a new column total = amount * quantity",
]


def empty_agent_trace() -> AgentTrace:
    """Return an empty created trace for future orchestration callers."""
    return AgentTrace(
        state="created",
        max_iterations=DEFAULT_MAX_AGENT_ITERATIONS,
        summary=AgentTraceSummary(
            state="created",
            iteration_count=0,
            max_iterations=DEFAULT_MAX_AGENT_ITERATIONS,
            full_trace_available=True,
        ),
        iterations=[],
    )


async def run_chat(request: ChatRequest) -> ChatResponse:
    """Run the full chat planning, preview, and optional execution pipeline."""
    content = await dataset_store.load(request.dataset_id)
    dataset_profile = profile(content, filename="<cached>")
    column_names = [col.name for col in dataset_profile.columns]
    clarification = _resolve_request_clarification(request)

    explicit_missing_col = (
        None
        if clarification and clarification.user_answer
        else _explicit_missing_column(request.query, column_names)
    )
    planner_query = planner_query_with_context(request.query, clarification)

    rag_ctx = await rag_service.build_context(
        query=planner_query,
        dataset_profile=dataset_profile,
        top_k=request.rag_top_k,
    )

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

    if explicit_missing_col:
        available = ", ".join(column_names)
        observation = signal_rules.from_validation_failure(
            f"Column '{explicit_missing_col}' is not in this dataset.",
            workflow_state="needs_clarification",
        )
        return _clarification_response(
            request=request,
            content=content,
            dataset_profile=dataset_profile,
            column_names=column_names,
            rag_ctx=rag_ctx,
            question=(
                f"Column '{explicit_missing_col}' is not in this dataset. "
                f"Which available column should I use instead? Available columns: {available}."
            ),
            validation_status="failed",
            observation=observation,
            affected_step={"type": "filter_rows", "column": explicit_missing_col},
        )

    # Slot extraction layer: run before planner to validate column/operator/value.
    # Skipped when the user is responding to a clarification (they already answered).
    slot_context = _run_slot_extraction(request.query, dataset_profile, clarification)
    if isinstance(slot_context, _SlotClarificationSignal):
        return _clarification_response(
            request=request,
            content=content,
            dataset_profile=dataset_profile,
            column_names=column_names,
            rag_ctx=rag_ctx,
            question=slot_context.question,
            validation_status="failed",
            observation=slot_context.observation,
            affected_step=slot_context.affected_step,
        )
    # slot_context is now SlotExtractionResult | None

    try:
        workflow_planner.last_raw_output = None
        new_steps = workflow_planner.plan(query=planner_query, ctx=rag_ctx, slot_context=slot_context)
        planner_raw_output = workflow_planner.last_raw_output
    except ClarificationNeeded as exc:
        logger.info("Clarification needed for query=%r: %s", request.query, exc.question)
        return _clarification_response(
            request=request,
            content=content,
            dataset_profile=dataset_profile,
            column_names=column_names,
            rag_ctx=rag_ctx,
            question=exc.question,
        )
    except PlannerError as exc:
        relevant = _relevant_steps(rag_ctx)
        planner_hint = str(exc) if str(exc) != "The request cannot be handled with the supported transformations." else None
        raise WorkflowValidationError(
            "The planner could not build a workflow for this query. "
            "The request may be outside the supported transformation scope.",
            error_code="empty_workflow",
            context={
                "planner_hint": planner_hint,
                "relevant_steps": relevant or None,
                "supported_steps": _SUPPORTED_STEPS if not relevant else None,
                "example_queries": _EXAMPLE_QUERIES if not relevant else None,
            },
        ) from exc

    steps = list(request.previous_steps) + new_steps
    planned_steps = [step.model_dump() for step in steps]

    try:
        steps, attempts, validation_status = workflow_runtime.validate_with_single_repair(
            steps,
            column_names,
            query=request.query,
            rag_ctx=rag_ctx,
            planner_raw_output=planner_raw_output,
        )
        planned_steps = [step.model_dump() for step in steps]
    except WorkflowValidationError as exc:
        msg = str(exc)
        if "at least one step" in msg:
            relevant = _relevant_steps(rag_ctx)
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
        if "does not exist in the dataset" in msg or "not found" in msg.lower():
            intermediate_cols = simulate_columns(request.previous_steps, column_names)
            observation = signal_rules.from_validation_failure(msg, workflow_state="needs_clarification")
            failed_attempt = workflow_runtime.make_attempt(
                attempt_index=0,
                query=request.query,
                steps=steps,
                final_status="needs_clarification",
                rag_ctx=rag_ctx,
                planner_raw_output=planner_raw_output,
                validation_result={"ok": False, "error": msg},
            )
            available = ", ".join(intermediate_cols)
            return _clarification_response(
                request=request,
                content=content,
                dataset_profile=dataset_profile,
                column_names=column_names,
                rag_ctx=rag_ctx,
                question=f"{msg} Which available column should I use instead? Available columns: {available}.",
                current_steps=steps,
                attempts=[failed_attempt],
                validation_status="failed",
                observation=observation,
                affected_step=_failed_new_step(
                    previous_steps=request.previous_steps,
                    new_steps=new_steps,
                    column_names=column_names,
                ),
            )
        raise

    preview_result = executor_service.preview(steps, content)
    observation = signal_rules.from_preview(
        preview_result,
        planned_steps=planned_steps,
        workflow_state="failed" if preview_result.has_errors else None,
    )
    if preview_result.blocked_at_step is not None and preview_result.has_errors:
        blocked = preview_result.step_results[preview_result.blocked_at_step]
        issue_msg = blocked.issues[0].message if blocked.issues else blocked.message
        cols_at_failure = simulate_columns(steps[:preview_result.blocked_at_step], column_names)
        if "not found" in issue_msg.lower():
            raise ExecutionError(
                issue_msg,
                error_code="missing_column",
                context={"available_columns": cols_at_failure, "observation": observation.model_dump()},
            )
        raise ExecutionError(
            issue_msg,
            error_code="execution_error",
            context={
                "failed_step_index": preview_result.blocked_at_step,
                "failed_step_type": blocked.step_type,
                "available_columns": cols_at_failure,
                "observation": observation.model_dump(),
                "suggestion": (
                    "Check that the column names and parameter values match your dataset. "
                    "Use 'select columns' or 'show schema' to inspect available columns."
                ),
            },
        )

    explanation: str | None = None
    execution_result: ExecutionResult | None = None
    run_id: str | None = None
    state = "preview_ready"
    execution_boundary = "preview"
    execution_policy = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=preview_result,
        confirmed=False,
    )

    if request.auto_confirm and execution_policy.decision == "auto_executable":
        state = "executed"
        execution_boundary = "executed"
        execution_result = executor_service.execute(steps, content)
        explanation = result_explainer.explain(
            query=request.query,
            planned_steps=planned_steps,
            execution_result=execution_result,
            dataset_summary=rag_ctx.dataset_summary.model_dump(),
        )
        trace, attempts = _build_trace_after_preview(
            request=request,
            content=content,
            dataset_profile=dataset_profile,
            column_names=column_names,
            steps=steps,
            rag_ctx=rag_ctx,
            execution_boundary=execution_boundary,
            attempts=attempts,
            state=state,
            planner_raw_output=planner_raw_output,
            validation_status=validation_status,
            preview_result=preview_result,
            observation=observation,
            clarification=clarification,
        )
        run_id = await _persist_run_artifact(
            dataset_id=request.dataset_id,
            content=content,
            query=request.query,
            steps=steps,
            planned_steps=planned_steps,
            row_count=execution_result.row_count,
            status=state,
            explanation=explanation,
            trace=trace,
        )
        logger.info(
            "Chat auto-confirm complete: query=%r steps=%d rows=%d run_id=%s",
            request.query,
            len(steps),
            execution_result.row_count,
            run_id,
        )
    else:
        state = "warning_review" if preview_result.has_warnings else "preview_ready"
        execution_boundary = "warning" if preview_result.has_warnings else "preview"
        logger.info(
            "Chat preview-only: query=%r auto_confirm=%s has_warnings=%s has_errors=%s",
            request.query,
            request.auto_confirm,
            preview_result.has_warnings,
            preview_result.has_errors,
        )
        trace, attempts = _build_trace_after_preview(
            request=request,
            content=content,
            dataset_profile=dataset_profile,
            column_names=column_names,
            steps=steps,
            rag_ctx=rag_ctx,
            execution_boundary=execution_boundary,
            attempts=attempts,
            state=state,
            planner_raw_output=planner_raw_output,
            validation_status=validation_status,
            preview_result=preview_result,
            observation=observation,
            clarification=clarification,
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
        state=state,
        attempts=attempts,
        context_summary=trace.context_summary,
        clarification_context=clarification,
    )


async def confirm_workflow(request: ConfirmRequest) -> ConfirmResponse:
    """Execute a pre-reviewed workflow and return the result with explanation."""
    content = await dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    steps, attempts, validation_status = workflow_runtime.validate_with_single_repair(
        request.steps,
        column_names,
        query=request.query,
    )

    planned_steps = [step.model_dump() for step in steps]
    preview_result = executor_service.preview(steps, content)
    observation = signal_rules.from_preview(
        preview_result,
        planned_steps=planned_steps,
        workflow_state="executed",
    )
    policy_result = action_policy.evaluate_workflow_action(
        "confirm_workflow",
        preview_result=preview_result,
        confirmed=True,
    )
    action_policy.enforce_policy(policy_result)
    execution_result = executor_service.execute(steps, content)

    dataset_profile = profile(content, filename="<dataset>")
    explanation = result_explainer.explain(
        query=request.query,
        planned_steps=planned_steps,
        execution_result=execution_result,
        dataset_summary=dataset_profile.model_dump(),
    )
    context = workflow_runtime.build_context(
        dataset_id=request.dataset_id,
        content=content,
        query=request.query,
        dataset_profile=dataset_profile,
        column_names=column_names,
        previous_steps=[],
        current_steps=steps,
        execution_boundary="executed",
    )
    final_attempt = workflow_runtime.make_attempt(
        attempt_index=attempts[-1].attempt_index if attempts else 0,
        query=request.query,
        steps=steps,
        final_status="executed",
        validation_result={"ok": True},
        preview_result=preview_result,
        repair_reason=attempts[-1].repair_reason if attempts else None,
    )
    attempts = attempts[:-1] + [final_attempt] if attempts else [final_attempt]
    trace = workflow_runtime.make_trace(
        state="executed",
        context=context,
        attempts=attempts,
        validation_status=validation_status,
        preview_result=preview_result,
        observation=observation,
    )
    run_id = await _persist_run_artifact(
        dataset_id=request.dataset_id,
        content=content,
        query=request.query,
        steps=steps,
        planned_steps=planned_steps,
        row_count=execution_result.row_count,
        status="executed",
        explanation=explanation,
        trace=trace,
        parent_run_id=request.parent_run_id,
    )

    logger.info(
        "Confirm complete: query=%r steps=%d rows=%d run_id=%s",
        request.query,
        len(request.steps),
        execution_result.row_count,
        run_id,
    )

    return ConfirmResponse(
        query=request.query,
        planned_steps=planned_steps,
        execution_result=execution_result,
        explanation=explanation,
        run_id=run_id,
        state="executed",
        attempts=attempts,
        context_summary=trace.context_summary,
    )


def _clarification_response(
    *,
    request: ChatRequest,
    content: bytes,
    dataset_profile,
    column_names: list[str],
    rag_ctx,
    question: str,
    current_steps: list = None,
    attempts: list = None,
    validation_status: str | None = None,
    observation: ObservationSummary | None = None,
    affected_step: dict | None = None,
) -> ChatResponse:
    steps = current_steps or []
    trace_attempts = attempts or []
    pending_clarification = new_pending_context(
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
        clarification_answer=pending_clarification.user_answer,
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
        state="needs_clarification",
        attempts=trace_attempts,
        context_summary=trace.context_summary,
        clarification_context=pending_clarification,
    )


def _explicit_missing_column(query: str, column_names: list[str]) -> str | None:
    available = set(column_names)
    available_lower = {c.lower() for c in column_names}
    patterns = [
        r"\bwhere\s+([A-Za-z_][A-Za-z0-9_]*)\b",
        # Chinese: <col> 大于/小于/等于/高于/低于/不等于 ... (identifier before comparison keyword)
        r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:大于等于|小于等于|大于|小于|等于|高于|低于|不等于)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            col = match.group(1)
            if col not in available and col.lower() not in available_lower:
                return col
    return None


def _resolve_request_clarification(request: ChatRequest) -> ClarificationContext | None:
    clarification = resolve_context(
        request.clarification_context,
        dataset_id=request.dataset_id,
        original_query=request.query,
    )
    if clarification and not validate_scope(
        clarification,
        dataset_id=request.dataset_id,
        original_query=request.query,
    ):
        raise WorkflowValidationError(
            "Clarification context does not belong to this dataset and query.",
            error_code="clarification_context_scope_mismatch",
            context={
                "dataset_id": request.dataset_id,
                "original_query": request.query,
                "clarification_dataset_id": clarification.dataset_id,
                "clarification_original_query": clarification.original_query,
            },
        )
    return clarification


def _run_slot_extraction(
    query: str,
    dataset_profile,
    clarification: ClarificationContext | None,
):
    """Run slot extraction and schema validation before planning.

    Returns:
      - SlotExtractionResult         when extraction succeeded and validation passed.
      - _SlotClarificationSignal     when slot validation requires user clarification.
      - None                         when the slot path should be bypassed (fallback to planner-only).

    Fallback conditions:
      - User is answering a clarification (skip to avoid double-processing).
      - LLM extraction fails, parse_error is set, or intent is unknown.
      - Extracted confidence is below the minimum threshold.
      - Slot validation is blocked (unsupported intent) — let planner decide.
    """
    if clarification and clarification.user_answer:
        return None

    try:
        slot_output = extract_slots(query)
    except Exception:
        logger.debug("Slot extraction raised an exception; falling back to planner-only path.")
        return None

    if slot_output.parse_error or slot_output.result.intent == "unknown":
        return None
    if slot_output.result.confidence < _SLOT_MIN_CONFIDENCE:
        return None

    validation = validate_slots(slot_output.result, dataset_profile)

    if validation.blocked:
        # Unsupported intent — let the planner handle or reject it.
        return None

    if validation.needs_clarification:
        question = validation.clarification_question or "Please clarify your request."
        slots = slot_output.result.slots
        intent = slot_output.result.intent
        affected_step: dict | None = None
        step_type = _INTENT_TO_STEP_TYPE.get(intent)
        if step_type and slots.column:
            affected_step = {"type": step_type, "column": slots.column}
        observation = signal_rules.from_validation_failure(
            question, workflow_state="needs_clarification"
        )
        return _SlotClarificationSignal(
            question=question,
            affected_step=affected_step,
            observation=observation,
        )

    if validation.is_valid:
        return slot_output.result

    # Partially valid or other status — bypass slot path, let planner handle.
    return None


class _SlotClarificationSignal:
    """Sentinel returned by _run_slot_extraction when slot validation needs user input."""

    __slots__ = ("question", "affected_step", "observation")

    def __init__(self, *, question: str, affected_step: dict | None, observation: ObservationSummary):
        self.question = question
        self.affected_step = affected_step
        self.observation = observation


def _failed_new_step(*, previous_steps: list, new_steps: list, column_names: list[str]) -> dict | None:
    if not new_steps:
        return None
    for idx, step in enumerate(new_steps):
        candidate_steps = list(previous_steps) + list(new_steps[: idx + 1])
        try:
            validate_workflow(candidate_steps, column_names)
        except WorkflowValidationError:
            return step.model_dump()
    # The incremental prefix search covers previous_steps + new_steps on the
    # final iteration, which is the same call that already failed.  Reaching
    # here means no prefix isolated the failure (e.g. non-deterministic
    # validator or unexpected state).  Returning None is the only honest
    # answer — there is no justification for blaming the last step.
    return None


def _relevant_steps(rag_ctx) -> list[dict]:
    return [
        {"step_type": doc.type, "description": doc.description, "example": doc.example}
        for doc in rag_ctx.retrieved_docs
        if doc.doc_type == "transformation" and doc.type
    ]


def _build_trace_after_preview(
    *,
    request: ChatRequest,
    content: bytes,
    dataset_profile,
    column_names: list[str],
    steps: list,
    rag_ctx,
    execution_boundary: str,
    attempts: list,
    state: str,
    planner_raw_output: str | None,
    validation_status: str | None,
    preview_result,
    observation: ObservationSummary,
    clarification: ClarificationContext | None = None,
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
        clarification_answer=clarification.user_answer if clarification else None,
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
