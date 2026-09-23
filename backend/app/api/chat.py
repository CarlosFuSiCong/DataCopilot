"""Chat endpoint boundary."""
from fastapi import APIRouter

from app.workflow.response import result_explainer
from app.workflow import service
from app.workflow.planning import workflow_planner
from app.models.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await service.run_chat(request)
