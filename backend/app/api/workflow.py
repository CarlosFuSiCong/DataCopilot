import logging

from fastapi import APIRouter

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    ConfirmRequest,
    ConfirmResponse,
    ExecutionResult,
    PreviewResponse,
    WorkflowRequest,
)
from app.services import dataset_store, executor as executor_service
from app.services import result_explainer, run_store, validator as validator_service
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
    return executor_service.execute(request.steps, content)


@router.post("/preview", response_model=PreviewResponse)
async def preview_workflow(request: WorkflowRequest) -> PreviewResponse:
    """Validate and dry-run the workflow without calling the result explainer.

    Returns step_results with risk-rule issues so the client can surface
    warnings and errors before asking the user to confirm execution.
    """
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
    validator_service.validate(request.steps, column_names)

    planned_steps = [step.model_dump() for step in request.steps]
    execution_result = executor_service.execute(request.steps, content)

    dataset_profile = profile(content, filename="<dataset>")
    explanation = result_explainer.explain(
        query=request.query,
        planned_steps=planned_steps,
        execution_result=execution_result,
        dataset_summary=dataset_profile.model_dump(),
    )

    # Persist the result CSV so the frontend can download it via GET /api/runs/{id}/download.
    # execute_to_df re-runs the workflow to get a full (un-previewed) DataFrame.
    run_id: str | None = None
    try:
        result_df = executor_service.execute_to_df(request.steps, content)
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
            parent_run_id=request.parent_run_id,
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
    )
