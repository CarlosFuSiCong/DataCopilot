import logging
import uuid

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.core import database
from app.core.exceptions import InvalidDatasetError
from app.models.dataset import DatasetRowsResponse, UploadResponse
from app.services import dataset_store, profiler as profiler_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/upload", response_model=UploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise InvalidDatasetError("Only .csv files are accepted.")

    content = await file.read()
    profile = profiler_service.profile(content, file.filename)

    dataset_id = str(uuid.uuid4())
    await dataset_store.save(
        dataset_id,
        content,
        filename=file.filename,
        profile_data=profile.model_dump(),
    )

    return UploadResponse(dataset_id=dataset_id, profile=profile)


@router.get("/{dataset_id}/rows", response_model=DatasetRowsResponse)
async def get_dataset_rows(
    dataset_id: str,
    offset: int = Query(default=0, ge=0, description="Row offset (0-based)"),
    limit: int = Query(default=50, ge=1, le=500, description="Rows per page (max 500)"),
) -> DatasetRowsResponse:
    rows, total_rows = await dataset_store.load_rows(dataset_id, offset, limit)
    return DatasetRowsResponse(
        rows=rows,
        total_rows=total_rows,
        offset=offset,
        limit=limit,
    )


@router.get("/{dataset_id}/download")
async def download_dataset(dataset_id: str) -> Response:
    content = await dataset_store.load(dataset_id)
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filename FROM datasets WHERE id = $1", dataset_id
        )
    filename = row["filename"] if row else f"{dataset_id}.csv"
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
