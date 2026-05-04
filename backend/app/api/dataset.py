import io
import logging
import uuid

import pandas as pd
from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.core import database
from app.core.exceptions import InvalidDatasetError
from app.models.dataset import DatasetRowsResponse, DiffRowsResponse, UploadResponse
from app.models.workflow import WorkflowRequest
from app.services import dataset_store, executor, profiler as profiler_service

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


class ExportRequest(BaseModel):
    steps: list[dict]
    filename: str = "result.csv"


class ExecuteRowsRequest(BaseModel):
    steps: list[dict]
    offset: int = 0
    limit: int = 50


@router.post("/{dataset_id}/execute-rows", response_model=DatasetRowsResponse)
async def execute_rows(dataset_id: str, body: ExecuteRowsRequest) -> DatasetRowsResponse:
    """Paginate over the full result of a workflow execution."""
    content = await dataset_store.load(dataset_id)
    request = WorkflowRequest(dataset_id=dataset_id, steps=body.steps)
    df = executor.execute_to_df(request.steps, content)
    total = len(df)
    page = df.iloc[body.offset: body.offset + body.limit]
    rows = page.where(pd.notna(page), None).to_dict(orient="records")
    return DatasetRowsResponse(rows=rows, total_rows=total, offset=body.offset, limit=body.limit)


@router.post("/{dataset_id}/execute-diff", response_model=DiffRowsResponse)
async def execute_diff(dataset_id: str, body: ExecuteRowsRequest) -> DiffRowsResponse:
    """Return a page of original rows annotated with _kept=True/False against the workflow result."""
    content = await dataset_store.load(dataset_id)
    original_df = pd.read_csv(io.BytesIO(content))
    request = WorkflowRequest(dataset_id=dataset_id, steps=body.steps)
    result_df = executor.execute_to_df(request.steps, content)

    # Build a key set from result rows using columns shared between original and result
    shared_cols = [c for c in result_df.columns if c in original_df.columns]
    result_keys: set[str] = set(
        "|".join(str(v) for v in row)
        for row in result_df[shared_cols].itertuples(index=False, name=None)
    )

    page = original_df.iloc[body.offset: body.offset + body.limit]
    rows_out = []
    for row in page.itertuples(index=False, name=None):
        record = dict(zip(original_df.columns, row))
        key = "|".join(str(record.get(c, "")) for c in shared_cols)
        record["_kept"] = key in result_keys
        # Replace NaN with None for JSON
        record = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in record.items()}
        rows_out.append(record)

    return DiffRowsResponse(
        rows=rows_out,
        total_original=len(original_df),
        total_result=len(result_df),
        offset=body.offset,
        limit=body.limit,
    )


@router.post("/{dataset_id}/export")
async def export_result(dataset_id: str, body: ExportRequest) -> Response:
    """Re-execute workflow steps on the full dataset and return complete CSV."""
    content = await dataset_store.load(dataset_id)
    request = WorkflowRequest(dataset_id=dataset_id, steps=body.steps)
    df = executor.execute_to_df(request.steps, content)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    safe_name = body.filename.rsplit(".", 1)[0] + "_result.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
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
