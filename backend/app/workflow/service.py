"""Workflow assistant service — chat pipeline orchestration.

Public API: run_chat(), confirm_workflow().

Query analysis helpers live in service_nlu.py.
Response and trace builders live in service_response.py.
"""
import logging

from app.workflow.context import rag_service
from app.workflow.execution import executor as executor_service
from app.workflow.response import result_explainer
from app.workflow import runtime as workflow_runtime
from app.workflow.observation import signal_rules
from app.workflow.planning import workflow_planner, workflow_builder
from app.workflow.planning import parameter_resolver
from app.workflow.planning import tool_router
from app.workflow.planning.query_classifier import classify
from app.workflow.policy import action_policy
from app.workflow.policy import tool_policy
from app.workflow.validation.workflow_validator import simulate_columns
from app.core.exceptions import ClarificationNeeded, ExecutionError, PlannerError, WorkflowValidationError
from app.models.chat import ChatRequest, ChatResponse
from app.models.clarification_context import (
    ClarificationContext,
    resolve_context,
    validate_scope,
)
from app.models.rag import RAGContext
from app.models.workflow_execution import ExecutionResult
from app.models.workflow_responses import ConfirmResponse
from app.models.workflow_transport import ConfirmRequest, WorkflowRequest
from app.services import dataset_store, run_store
from app.services.profiler import get_column_names, profile
from app.workflow.service_nlu import (
    _SlotClarificationSignal,
    _run_slot_extraction,
    _explicit_missing_column,
    _extract_column_from_error,
    _detect_step_type_from_query,
    _detect_complex_tool_hint,
)
from app.workflow.service_response import (
    _build_minimal_rag_ctx,
    _ask_mode_response,
    _clarification_response,
    _build_trace_after_preview,
    _persist_run_artifact,
    _relevant_steps,
)

logger = logging.getLogger(__name__)

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

    # --- Stage 1: Query Classification ---
    # Skip classifier when the user is answering a clarification question so
    # the resolved query passes through to the planner without re-routing.
    route_decision = None
    if not (clarification and clarification.user_answer):
        route_decision = classify(request.query, column_names)
        logger.info(
            "RouteDecision: query=%r type=%s route=%s confidence=%.2f reason=%r evidence=%s",
            request.query,
            route_decision.query_type,
            route_decision.route,
            route_decision.confidence,
            route_decision.reason,
            route_decision.evidence,
        )

        if route_decision.route == "ask_mode":
            return _ask_mode_response(
                request=request,
                dataset_profile=dataset_profile,
                column_names=column_names,
                route_decision=route_decision,
            )

        if route_decision.route == "unsupported":
            raise WorkflowValidationError(
                f"This type of request is not supported: {route_decision.reason}",
                error_code="unsupported_request",
                context={
                    "query_type": route_decision.query_type,
                    "evidence": route_decision.evidence,
                    "suggestion": (
                        "DataCopilot supports filtering, sorting, aggregation, profiling, "
                        "diagnosis, comparison, and data cleaning. "
                        "Prediction, ML models, and visualizations are not supported."
                    ),
                },
            )

    # ---------------------------------------------------------------------------
    # Planning pipeline
    # Stage 2: Route to Level 1 (deterministic) or Level 2 (LLM planner)
    # Full decomposition: classify → tool_router → parameter_resolver →
    #   workflow_builder → validator → preview/confirm → executor
    # ---------------------------------------------------------------------------
    new_steps: list = []
    rag_ctx: RAGContext | None = None
    planner_raw_output: str | None = None
    _level1_done = False

    # --- Level 1: Deterministic Tool Router (no RAG, no LLM) ---
    # Invoked when classifier is confident about the tool + parameters can be
    # resolved from query evidence and schema alone.
    if (
        route_decision
        and route_decision.route == "deterministic_tool"
        and not (clarification and clarification.user_answer)
    ):
        _min_rag = _build_minimal_rag_ctx(request.query, dataset_profile, column_names)

        # Stage 2a: Tool Selection — select concrete tool and draft raw step
        _tr = tool_router.route(
            query=request.query,
            column_names=column_names,
            dataset_profile=dataset_profile,
            route_decision=route_decision,
        )
        if _tr.clarification_question:
            return _clarification_response(
                request=request,
                content=content,
                dataset_profile=dataset_profile,
                column_names=column_names,
                rag_ctx=_min_rag,
                question=_tr.clarification_question,
                clarification_type="deterministic_tool",
            )

        # Stage 2b: Parameter Resolver — validate column references against schema
        _resolved_raw: list[dict] = []
        for _raw_step in _tr.raw_steps:
            _res = parameter_resolver.resolve_parameters(_raw_step, column_names)
            if _res.column_errors or _res.missing_required_fields:
                _err = (_res.column_errors + _res.missing_required_fields)[0]
                return _clarification_response(
                    request=request,
                    content=content,
                    dataset_profile=dataset_profile,
                    column_names=column_names,
                    rag_ctx=_min_rag,
                    question=f"{_err} Available columns: {', '.join(column_names)}.",
                    clarification_type="deterministic_tool",
                )
            _resolved_raw.append(_res.resolved_step)

        # Stage 2c: Workflow Builder — assemble WorkflowStep objects
        try:
            _parsed = WorkflowRequest(dataset_id=request.dataset_id, steps=_resolved_raw)
            _wf = workflow_builder.build_workflow(request.dataset_id, list(_parsed.steps))
            new_steps = list(_wf.steps)
            rag_ctx = _min_rag
            planner_raw_output = None
            _level1_done = True
            logger.info(
                "Level 1 deterministic route: tool=%s steps=%d",
                route_decision.selected_tool,
                len(new_steps),
            )
        except Exception as exc:
            logger.warning(
                "Deterministic workflow build failed (%s) — falling back to LLM planner.", exc
            )

    # --- Level 2: LLM Workflow Planner (runs when Level 1 didn't succeed) ---
    # Pipeline: explicit_column_check → RAG retrieval → slot extraction → LLM planner
    if not _level1_done:
        from app.models.clarification_context import planner_query_with_context
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
            complex_hint = _detect_complex_tool_hint(request.query, column_names)
            if complex_hint:
                return _clarification_response(
                    request=request,
                    content=content,
                    dataset_profile=dataset_profile,
                    column_names=column_names,
                    rag_ctx=rag_ctx,
                    question=complex_hint,
                    clarification_type="planning",
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

    # --- Stage 3: Validate + Preview/Confirm + Execute (common to both Level 1 & 2) ---
    steps = list(request.previous_steps) + new_steps
    planned_steps = [step.model_dump() for step in steps]

    # --- Read-only fast path: skip preview/confirm, skip run persistence ---
    # When every step in the workflow is a read-only analytical tool (e.g. profile_column,
    # distribution_summary, compare_groups), we execute directly without the confirm gate
    # and do not save a run artifact to the transformation history.
    _step_types = [s.type for s in steps]
    if _level1_done and tool_policy.all_read_only(_step_types):
        try:
            steps, _ro_attempts, _ro_val_status = workflow_runtime.validate_with_single_repair(
                steps,
                column_names,
                query=request.query,
                rag_ctx=rag_ctx,
                planner_raw_output=planner_raw_output,
            )
            planned_steps = [step.model_dump() for step in steps]
            execution_result = executor_service.execute(steps, content)
            explanation = result_explainer.explain(
                query=request.query,
                planned_steps=planned_steps,
                execution_result=execution_result,
                dataset_summary=rag_ctx.dataset_summary.model_dump(),
            )
            logger.info(
                "Read-only fast path: tool=%s steps=%d rows=%d",
                route_decision.selected_tool if route_decision else "?",
                len(steps),
                execution_result.row_count,
            )
            return ChatResponse(
                query=request.query,
                planned_steps=planned_steps,
                step_results=[],
                has_warnings=False,
                has_errors=False,
                rag_context=rag_ctx,
                explanation=explanation,
                execution_result=execution_result,
                run_id=None,
                state="executed",
                is_read_only=True,
                ask_mode_type="analytical",
                evidence_source="analytical_execution",
                route_decision=route_decision.model_dump() if route_decision else None,
            )
        except Exception as exc:
            logger.warning("Read-only fast path failed (%s) — falling through to normal Stage 3.", exc)

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
        route_decision=route_decision.model_dump() if route_decision else None,
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


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

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
