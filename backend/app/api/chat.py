"""Chat endpoint — RAG + Planner + Preview/Confirm pipeline.

POST /api/chat runs:
  RAG retrieval → LLM planner → validator → executor.preview() → risk check

If auto_confirm=True (default) and no warnings or errors are detected, the
endpoint also runs the full executor and result explainer, returning a
complete result in one round-trip.

If auto_confirm=False, or if the preview detects warnings/errors, only the
preview result is returned so the frontend can surface issues and ask the
user to confirm before calling POST /api/workflows/confirm.
"""
import logging

from fastapi import APIRouter

from app.models.chat import ChatRequest, ChatResponse
from app.models.workflow import ExecutionResult
from app.services import dataset_store, executor as executor_service
from app.services import rag_service, result_explainer, validator as validator_service
from app.services import workflow_planner
from app.services.profiler import profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    content = await dataset_store.load(request.dataset_id)
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

    preview_result = executor_service.preview(steps, content)

    explanation: str | None = None
    execution_result: ExecutionResult | None = None

    if (
        request.auto_confirm
        and not preview_result.has_warnings
        and not preview_result.has_errors
    ):
        execution_result = executor_service.execute(steps, content)
        explanation = result_explainer.explain(
            query=request.query,
            planned_steps=planned_steps,
            execution_result=execution_result,
            dataset_summary=rag_ctx.dataset_summary.model_dump(),
        )
        logger.info(
            "Chat auto-confirm complete: query=%r steps=%d rows=%d",
            request.query,
            len(steps),
            execution_result.row_count,
        )
    else:
        logger.info(
            "Chat preview-only: query=%r auto_confirm=%s has_warnings=%s has_errors=%s",
            request.query,
            request.auto_confirm,
            preview_result.has_warnings,
            preview_result.has_errors,
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
    )
