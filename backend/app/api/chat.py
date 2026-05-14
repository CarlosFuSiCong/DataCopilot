"""Chat endpoint boundary."""
from fastapi import APIRouter

from app.agent.final_response import result_explainer
from app.agent.loop import orchestrator
from app.agent.planning import workflow_planner
from app.models.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    return await orchestrator.run_chat(request)
