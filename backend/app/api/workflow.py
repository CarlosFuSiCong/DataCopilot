import logging

from fastapi import APIRouter

from app.models.workflow import (
    ConfirmRequest,
    ConfirmResponse,
    ExecutionResult,
    PreviewResponse,
    WorkflowRequest,
)
from app.services import dataset_store, executor as executor_service
from app.services import result_explainer, validator as validator_service
from app.services.profiler import get_column_names, profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/execute", response_model=ExecutionResult, deprecated=True)
async def execute_workflow(request: WorkflowRequest) -> ExecutionResult:
    """Direct workflow execution without preview or explainer (MVP1 style).

    Deprecated: use POST /preview → user review → POST /confirm instead.
    Will be removed once the frontend completes the preview-confirm migration.
    """
    content = dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    validator_service.validate(request.steps, column_names)
    return executor_service.execute(request.steps, content)


@router.post("/preview", response_model=PreviewResponse)
async def preview_workflow(request: WorkflowRequest) -> PreviewResponse:
    """Validate and dry-run the workflow without calling the result explainer.

    Returns step_results with risk-rule issues so the client can surface
    warnings and errors before asking the user to confirm execution.
    """
    content = dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    validator_service.validate(request.steps, column_names)
    return executor_service.preview(request.steps, content)


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_workflow(request: ConfirmRequest) -> ConfirmResponse:
    """Execute a pre-reviewed workflow and return the result with an explanation.

    The client calls this endpoint after showing the user the /preview result
    and receiving explicit confirmation.  The full executor runs (not the
    preview path) and the result explainer is called to generate the
    natural-language explanation.
    """
    content = dataset_store.load(request.dataset_id)
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

    logger.info(
        "Confirm complete: query=%r steps=%d rows=%d",
        request.query,
        len(request.steps),
        execution_result.row_count,
    )

    return ConfirmResponse(
        query=request.query,
        planned_steps=planned_steps,
        execution_result=execution_result,
        explanation=explanation,
    )
