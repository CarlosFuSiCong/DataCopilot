import logging

from fastapi import APIRouter

from app.models.workflow import ExecutionResult, WorkflowRequest
from app.services import dataset_store, executor as executor_service
from app.services import validator as validator_service
from app.services.profiler import get_column_names

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/execute", response_model=ExecutionResult)
async def execute_workflow(request: WorkflowRequest) -> ExecutionResult:
    content = dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)
    validator_service.validate(request.steps, column_names)
    return executor_service.execute(request.steps, content)
