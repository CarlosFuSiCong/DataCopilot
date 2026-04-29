"""Chat endpoint — full pipeline orchestration.

POST /api/chat runs the complete pipeline:
  RAG retrieval → LLM planner → validator → pandas executor

The response includes the planned workflow and execution result so the
frontend can display all pipeline stages transparently.
"""
import logging

from fastapi import APIRouter

from app.models.chat import ChatRequest, ChatResponse
from app.services import dataset_store, executor as executor_service
from app.services import rag_service, validator as validator_service
from app.services import workflow_planner
from app.services.profiler import profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    content = dataset_store.load(request.dataset_id)
    dataset_profile = profile(content, filename="<cached>")

    rag_ctx = rag_service.build_context(
        query=request.query,
        dataset_profile=dataset_profile,
        top_k=request.rag_top_k,
    )

    steps = workflow_planner.plan(query=request.query, ctx=rag_ctx)

    planned_steps = [step.model_dump() for step in steps]

    column_names = [col.name for col in dataset_profile.columns]
    validator_service.validate(steps, column_names)

    execution_result = executor_service.execute(steps, content)

    logger.info(
        "Chat pipeline complete: query=%r steps=%d rows=%d",
        request.query,
        len(steps),
        execution_result.row_count,
    )

    return ChatResponse(
        query=request.query,
        planned_steps=planned_steps,
        execution_result=execution_result,
        rag_context=rag_ctx,
    )
