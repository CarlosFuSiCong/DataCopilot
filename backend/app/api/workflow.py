from fastapi import APIRouter

from app.agent.execution import executor as executor_service
from app.agent.final_response import result_explainer
from app.agent.loop import orchestrator
from app.agent.policy import action_policy
from app.agent.validation import workflow_validator as validator_service
from app.core.exceptions import WorkflowValidationError
from app.models.workflow_execution import ExecutionResult
from app.models.workflow_responses import ConfirmResponse
from app.models.workflow_transport import ConfirmRequest, PreviewResponse, WorkflowRequest
from app.services import dataset_store
from app.services.profiler import get_column_names

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
    return await orchestrator.confirm_workflow(request)
