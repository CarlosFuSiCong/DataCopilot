"""RAG context API.

POST /api/rag/context — retrieve transformation docs and dataset profile
context for a given query. Used by the planner and for debug inspection.
"""
import logging

from fastapi import APIRouter

from app.models.rag import RAGContext, RAGContextRequest
from app.services import dataset_store, rag_service
from app.services.profiler import profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/context", response_model=RAGContext)
async def get_rag_context(request: RAGContextRequest) -> RAGContext:
    content = dataset_store.load(request.dataset_id)
    dataset_profile = profile(content, filename="<cached>")
    return rag_service.build_context(
        query=request.query,
        dataset_profile=dataset_profile,
        top_k=request.top_k,
    )
