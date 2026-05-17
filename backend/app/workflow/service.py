"""Workflow assistant service for the one-pass preview/confirm pipeline."""
import logging
import re

from app.workflow.context import rag_service
from app.workflow.execution import executor as executor_service
from app.workflow.response import result_explainer
from app.workflow import runtime as workflow_runtime
from app.workflow.observation import signal_rules
from app.workflow.observation.models import ObservationSummary
from app.workflow.planning import workflow_planner
from app.workflow.policy import action_policy
from app.workflow.validation.workflow_validator import simulate_columns
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
from app.workflow.nlu.slot_extractor import extract_slots
from app.workflow.nlu.slot_validator import validate_slots

logger = logging.getLogger(__name__)

_SLOT_MIN_CONFIDENCE = 0.7

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
    "Profile the amount column",
    "Compare average amount by region",
]


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
        step_type = _detect_step_type_from_query(request.query)
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
            affected_step={"type": step_type, "column": explicit_missing_col} if step_type else None,
        )

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
            clarification_type="slot_validation",
        )

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
            clarification_type="planning",
        )
    except PlannerError as exc:
        msg = str(exc)
        if "does not exist in the dataset" in msg or "not found" in msg.lower():
            missing_col = _extract_column_from_error(msg) or _explicit_missing_column(request.query, column_names)
            available = ", ".join(column_names)
            observation = signal_rules.from_validation_failure(
                msg,
                workflow_state="needs_clarification",
            )
            step_type = _detect_step_type_from_query(request.query)
            question = (
                f"Column '{missing_col}' is not in this dataset. "
                f"Which available column should I use instead? Available columns: {available}."
                if missing_col
                else f"{msg} Which available column should I use instead? Available columns: {available}."
            )
            return _clarification_response(
                request=request,
                content=content,
                dataset_profile=dataset_profile,
                column_names=column_names,
                rag_ctx=rag_ctx,
                question=question,
                validation_status="failed",
                observation=observation,
                affected_step={"type": step_type, "column": missing_col} if step_type and missing_col else None,
            )
        relevant = _relevant_steps(rag_ctx)
        planner_hint = msg if msg != "The request cannot be handled with the supported transformations." else None
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


def _explicit_missing_column(query: str, column_names: list[str]) -> str | None:
    available = set(column_names)
    available_lower = {c.lower() for c in column_names}
    identifier = r"([\w]+)"
    patterns = [
        r"\bwhere\s+" + identifier + r"\b",
        r"(?:sort(?:ed)?\s+by|order\s+by)\s+" + identifier + r"\b",
        identifier + r"\s*(?:大于等于|小于等于|不等于|大于|小于|等于|高于|低于)",
        r"(?:按|根据)\s*" + identifier + r"\s*(?:排序|降序|升序|排列)",
    ]
    for pattern in patterns:
        match = re.search(pattern, query, flags=re.IGNORECASE)
        if match:
            col = match.group(1)
            if col not in available and col.lower() not in available_lower:
                return col
    return None


def _extract_column_from_error(msg: str) -> str | None:
    match = re.search(r"[Cc]olumn ['\"]?([\w]+)['\"]?", msg)
    return match.group(1) if match else None


def _clarification_answer(value: str | ClarificationContext | None) -> str | None:
    if isinstance(value, ClarificationContext):
        return value.user_answer or value.resolved_parameter
    return value


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
    """Run slot extraction and schema validation before workflow planning."""
    if clarification and clarification.user_answer:
        return None

    try:
        slot_output = extract_slots(query)
    except Exception:
        logger.debug("Slot extraction raised; falling back to planner-only path.", exc_info=True)
        return None

    if slot_output.parse_error or slot_output.result.intent == "unknown":
        return None
    if slot_output.result.confidence < _SLOT_MIN_CONFIDENCE:
        return None

    validation = validate_slots(slot_output.result, dataset_profile)

    if validation.blocked:
        return None

    if validation.needs_clarification:
        question = validation.clarification_question or "Please clarify your request."
        slots = slot_output.result.slots
        step_type = _INTENT_TO_STEP_TYPE.get(slot_output.result.intent)
        affected_step = {"type": step_type, "column": slots.column} if step_type and slots.column else None
        observation = signal_rules.from_validation_failure(
            question,
            workflow_state="needs_clarification",
        )
        return _SlotClarificationSignal(
            question=question,
            affected_step=affected_step,
            observation=observation,
        )

    if validation.is_valid:
        return slot_output.result

    return None


class _SlotClarificationSignal:
    """Sentinel returned when slot validation needs user input."""

    __slots__ = ("question", "affected_step", "observation")

    def __init__(self, *, question: str, affected_step: dict | None, observation: ObservationSummary):
        self.question = question
        self.affected_step = affected_step
        self.observation = observation


_SORT_PATTERN = re.compile(r"(?:sort(?:ed)?\s+by|order\s+by|按|根据).*", re.IGNORECASE)
_GROUP_PATTERN = re.compile(r"(?:group\s+by|grouped\s+by|汇总|分组)", re.IGNORECASE)
_FILTER_PATTERN = re.compile(r"(?:\bwhere\b|filter|过滤|删除|移除|保留)", re.IGNORECASE)


def _detect_step_type_from_query(query: str) -> str | None:
    if _SORT_PATTERN.search(query):
        return "sort_values"
    if _GROUP_PATTERN.search(query):
        return "group_by"
    if _FILTER_PATTERN.search(query):
        return "filter_rows"
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
