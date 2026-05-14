import logging

from fastapi import APIRouter

from app.agent.execution import executor as executor_service
from app.agent.execution import validator as validator_service
from app.agent.final_response import result_explainer
from app.agent.loop import workflow_runtime
from app.agent.policy import action_policy
from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    ConfirmRequest,
    ConfirmResponse,
    ExecutionResult,
    PreviewResponse,
    WorkflowRequest,
)
from app.services import dataset_store, run_store
from app.services.profiler import get_column_names, profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/execute", response_model=ExecutionResult, deprecated=True)
async def execute_workflow(request: WorkflowRequest) -> ExecutionResult:
    """Direct workflow execution without preview or explainer (MVP1 style).

    Deprecated: use POST /preview → user review → POST /confirm instead.
    Will be removed once the frontend completes the preview-confirm migration.
    """
    content = await dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    validator_service.validate(request.steps, column_names)
    preview_result = executor_service.preview(request.steps, content)
    policy_result = action_policy.evaluate_workflow_action(
        "execute_workflow",
        preview_result=preview_result,
        confirmed=False,
    )
    action_policy.enforce_policy(policy_result)
    return executor_service.execute(request.steps, content)


@router.post("/preview", response_model=PreviewResponse)
async def preview_workflow(request: WorkflowRequest) -> PreviewResponse:
    """Validate and dry-run the workflow without calling the result explainer.

    Returns step_results with risk-rule issues so the client can surface
    warnings and errors before asking the user to confirm execution.
    """
    action_policy.evaluate_workflow_action("preview_workflow")
    content = await dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    try:
        validator_service.validate(request.steps, column_names)
    except WorkflowValidationError as exc:
        try:
            validator_service.validate_against_original_columns(request.steps, column_names)
        except WorkflowValidationError:
            raise exc
    return executor_service.preview(request.steps, content)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_workflow(request: ConfirmRequest) -> ConfirmResponse:
    """Execute a pre-reviewed workflow and return the result with an explanation.

    The client calls this endpoint after showing the user the /preview result
    and receiving explicit confirmation.  The full executor runs (not the
    preview path) and the result explainer is called to generate the
    natural-language explanation.
    """
    content = await dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    steps, attempts, validation_status = workflow_runtime.validate_with_single_repair(
        request.steps,
        column_names,
        query=request.query,
    )

    planned_steps = [step.model_dump() for step in steps]
    preview_result = executor_service.preview(steps, content)
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
    )

    # Persist the result CSV so the frontend can download it via GET /api/runs/{id}/download.
    # execute_to_df re-runs the workflow to get a full (un-previewed) DataFrame.
    run_id: str | None = None
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
            status="executed",
            explanation=explanation,
            parent_run_id=request.parent_run_id,
            trace=trace.model_dump(),
            context_summary=trace.context_summary.model_dump(),
        )
    except Exception:
        logger.warning("Failed to persist run artifact for dataset %s", request.dataset_id, exc_info=True)

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
