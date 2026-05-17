"""Runtime helpers for workflow state, attempts, summaries, and one repair pass."""
import hashlib
from typing import Any

from app.core.exceptions import WorkflowValidationError
from app.agent.analyst.flow_planner import AnalystFlowPlan, plan_analyst_flow
from app.agent.observation.models import ObservationSummary
from app.agent.planning.tool_selector import suggest_tools_from_observation
from app.models.dataset import DatasetProfile
from app.models.runtime_trace import (
    AttemptSummary,
    WorkflowAttempt,
    WorkflowContext,
    WorkflowContextSummary,
    WorkflowRunState,
    WorkflowTrace,
)
from app.agent.validation import workflow_validator as validator_service
from app.models.rag import RAGContext
from app.models.workflow_steps import WorkflowStep
from app.models.workflow_transport import PreviewResponse, WorkflowRequest


def dataset_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_context(
    *,
    dataset_id: str,
    content: bytes,
    query: str,
    dataset_profile: Any,
    column_names: list[str],
    previous_steps: list[WorkflowStep],
    current_steps: list[WorkflowStep],
    rag_ctx: RAGContext | None = None,
    clarification_answer: str | None = None,
    execution_boundary: str = "preview",
) -> WorkflowContext:
    return WorkflowContext(
        dataset_id=dataset_id,
        dataset_hash=dataset_hash(content),
        query=query,
        clarification_answer=clarification_answer,
        dataset_profile=dataset_profile.model_dump(),
        current_schema=column_names,
        previous_steps=[step.model_dump() for step in previous_steps],
        current_steps=[step.model_dump() for step in current_steps],
        retrieval_method=rag_ctx.debug.method if rag_ctx else None,
        retrieved_docs=[doc.model_dump() for doc in rag_ctx.retrieved_docs] if rag_ctx else [],
        retrieval_debug=rag_ctx.debug.model_dump() if rag_ctx else None,
        execution_boundary=execution_boundary,
    )


def make_attempt(
    *,
    attempt_index: int,
    query: str,
    steps: list[WorkflowStep],
    final_status: WorkflowRunState,
    rag_ctx: RAGContext | None = None,
    planner_raw_output: str | None = None,
    validation_result: dict[str, Any] | None = None,
    preview_result: PreviewResponse | None = None,
    repair_reason: str | None = None,
) -> WorkflowAttempt:
    doc_labels = _doc_labels(rag_ctx)
    warning_count, error_count, preview_status = _preview_counts(preview_result)
    validation_status = "not_run"
    if validation_result:
        validation_status = "passed" if validation_result.get("ok") else "failed"
    summary = AttemptSummary(
        attempt_index=attempt_index,
        query=query,
        retrieval_method=rag_ctx.debug.method if rag_ctx else None,
        retrieved_docs=doc_labels,
        planner_raw_output=planner_raw_output,
        parsed_step_types=[step.type for step in steps],
        validation_status=validation_status,
        preview_status=preview_status,
        warning_count=warning_count,
        error_count=error_count,
        repair_reason=repair_reason,
        final_status=final_status,
    )
    return WorkflowAttempt(
        attempt_index=attempt_index,
        query=query,
        retrieval_method=rag_ctx.debug.method if rag_ctx else None,
        retrieved_docs=[doc.model_dump() for doc in rag_ctx.retrieved_docs] if rag_ctx else [],
        planner_raw_output=planner_raw_output,
        parsed_steps=[step.model_dump() for step in steps],
        validation_result=validation_result,
        repair_reason=repair_reason,
        final_status=final_status,
        summary=summary,
    )


def make_context_summary(
    *,
    context: WorkflowContext,
    state: WorkflowRunState,
    validation_status: str | None = None,
    preview_result: PreviewResponse | None = None,
    observation: ObservationSummary | None = None,
) -> WorkflowContextSummary:
    warning_count, error_count, _ = _preview_counts(preview_result)
    columns = context.current_schema
    row_count = int(context.dataset_profile.get("row_count", 0))
    tool_suggestions = (
        [s.model_dump() for s in suggest_tools_from_observation(observation)]
        if observation and observation.signals
        else []
    )
    planned_types = [step.get("type", "?") for step in context.current_steps]
    analyst_flow_suggestions = _build_analyst_flow_suggestions(
        context.dataset_profile, planned_types, observation
    )
    return WorkflowContextSummary(
        query=context.query,
        dataset_hash=context.dataset_hash,
        schema_columns=columns,
        row_count=row_count,
        retrieved_docs=[
            str(doc.get("title") or doc.get("type") or doc.get("source_path"))
            for doc in context.retrieved_docs
        ],
        planned_step_types=planned_types,
        status=state,
        boundary=context.execution_boundary,
        validation_status=validation_status,
        warning_count=warning_count,
        error_count=error_count,
        last_observation=observation,
        tool_suggestions=tool_suggestions,
        analyst_flow_suggestions=analyst_flow_suggestions,
    )


def make_trace(
    *,
    state: WorkflowRunState,
    context: WorkflowContext,
    attempts: list[WorkflowAttempt],
    validation_status: str | None = None,
    preview_result: PreviewResponse | None = None,
    observation: ObservationSummary | None = None,
) -> WorkflowTrace:
    return WorkflowTrace(
        state=state,
        context=context,
        context_summary=make_context_summary(
            context=context,
            state=state,
            validation_status=validation_status,
            preview_result=preview_result,
            observation=observation,
        ),
        attempts=attempts,
    )


def make_next_decision_input(
    *,
    context_summary: WorkflowContextSummary,
    observation: ObservationSummary,
) -> dict[str, Any]:
    """Compact deterministic input for the next Agent decision."""
    return {
        "workflow_context_summary": context_summary.model_dump(),
        "observation": observation.model_dump(),
    }


def validate_with_single_repair(
    steps: list[WorkflowStep],
    column_names: list[str],
    *,
    query: str = "",
    rag_ctx: RAGContext | None = None,
    planner_raw_output: str | None = None,
) -> tuple[list[WorkflowStep], list[WorkflowAttempt], str | None]:
    """Validate steps; if validation fails, try one deterministic column repair."""
    try:
        validator_service.validate(steps, column_names)
        return steps, [
            make_attempt(
                attempt_index=0,
                query=query,
                steps=steps,
                final_status="planned",
                rag_ctx=rag_ctx,
                planner_raw_output=planner_raw_output,
                validation_result={"ok": True},
            )
        ], "passed"
    except WorkflowValidationError as exc:
        failed_attempt = make_attempt(
            attempt_index=0,
            query=query,
            steps=steps,
            final_status="validation_failed",
            rag_ctx=rag_ctx,
            planner_raw_output=planner_raw_output,
            validation_result={"ok": False, "error": str(exc)},
        )
        repaired_steps, reason = _repair_column_case(steps, column_names)
        if repaired_steps is None:
            raise

    try:
        validator_service.validate(repaired_steps, column_names)
    except WorkflowValidationError as exc:
        repaired_attempt = make_attempt(
            attempt_index=1,
            query=query,
            steps=repaired_steps,
            final_status="failed",
            rag_ctx=rag_ctx,
            planner_raw_output=planner_raw_output,
            validation_result={"ok": False, "error": str(exc)},
            repair_reason=reason,
        )
        exc.context = {**getattr(exc, "context", {}), "repair_attempted": True}
        raise exc

    repaired_attempt = make_attempt(
        attempt_index=1,
        query=query,
        steps=repaired_steps,
        final_status="repair_attempted",
        rag_ctx=rag_ctx,
        planner_raw_output=planner_raw_output,
        validation_result={"ok": True},
        repair_reason=reason,
    )
    return repaired_steps, [failed_attempt, repaired_attempt], "repaired"


def _repair_column_case(
    steps: list[WorkflowStep],
    column_names: list[str],
) -> tuple[list[WorkflowStep] | None, str | None]:
    by_lower = {column.lower(): column for column in column_names}
    repaired: list[dict[str, Any]] = []
    changed = False

    for step in steps:
        data = step.model_dump()
        new_data, step_changed = _repair_step_columns(data, by_lower)
        repaired.append(new_data)
        changed = changed or step_changed

    if not changed:
        return None, None

    parsed = WorkflowRequest(dataset_id="__repair__", steps=repaired).steps
    return parsed, "case_insensitive_column_match"


def _repair_step_columns(
    data: dict[str, Any],
    by_lower: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    changed = False

    for key in ("column", "target", "other_column", "condition_column", "values", "columns"):
        if key not in data:
            continue
        value = data[key]
        if isinstance(value, str):
            replacement = _match_column(value, by_lower)
            if replacement and replacement != value:
                data[key] = replacement
                changed = True
        elif isinstance(value, list):
            new_values = []
            for item in value:
                replacement = _match_column(item, by_lower) if isinstance(item, str) else None
                new_values.append(replacement or item)
                changed = changed or bool(replacement and replacement != item)
            data[key] = new_values

    if "mapping" in data and isinstance(data["mapping"], dict):
        new_mapping = {}
        for key, value in data["mapping"].items():
            replacement = _match_column(str(key), by_lower)
            new_mapping[replacement or key] = value
            changed = changed or bool(replacement and replacement != key)
        data["mapping"] = new_mapping

    if data.get("type") == "pivot_table":
        for key in ("index", "columns", "values"):
            value = data.get(key)
            if isinstance(value, list):
                fixed = [_match_column(item, by_lower) or item for item in value]
                changed = changed or fixed != value
                data[key] = fixed
            elif isinstance(value, str):
                fixed = _match_column(value, by_lower)
                if fixed and fixed != value:
                    data[key] = fixed
                    changed = True

    return data, changed


def _match_column(value: str, by_lower: dict[str, str]) -> str | None:
    return by_lower.get(value.lower())


def _doc_labels(rag_ctx: RAGContext | None) -> list[str]:
    if not rag_ctx:
        return []
    return [
        doc.title or doc.type or doc.source_path
        for doc in rag_ctx.retrieved_docs
    ]


def _preview_counts(
    preview_result: PreviewResponse | None,
) -> tuple[int, int, str]:
    if preview_result is None:
        return 0, 0, "not_run"
    warnings = 0
    errors = 0
    for step_result in preview_result.step_results:
        warnings += sum(1 for issue in step_result.issues if issue.severity == "warning")
        errors += sum(1 for issue in step_result.issues if issue.severity == "error")
    if preview_result.has_errors:
        return warnings, errors, "error"
    if preview_result.has_warnings:
        return warnings, errors, "warning"
    return warnings, errors, "passed"


def _build_analyst_flow_suggestions(
    dataset_profile_dict: dict[str, Any],
    planned_types: list[str],
    observation: ObservationSummary | None,
) -> list[dict[str, Any]]:
    """Build analyst flow suggestions when suggest_analysis_steps is in the plan.

    Only activates when the planned workflow includes suggest_analysis_steps,
    which signals that the user is in an exploratory mode and benefits from
    a structured multi-step flow.  Returns serialised AnalystStepSuggestion
    dicts for inclusion in WorkflowContextSummary.
    """
    if "suggest_analysis_steps" not in planned_types:
        return []
    try:
        profile = DatasetProfile(**dataset_profile_dict)
        plan: AnalystFlowPlan = plan_analyst_flow(profile, observation)
        return [s.model_dump() for s in plan.suggestions[: plan.max_steps]]
    except Exception:
        return []
