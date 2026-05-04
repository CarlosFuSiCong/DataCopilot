"""Runs API — download persisted workflow result CSVs.

GET /api/runs/{run_id}/download
    Returns the result CSV produced by a confirmed workflow execution.
    run_id is a UUID, making URLs non-guessable by enumeration.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import Response

from app.core.exceptions import DatasetNotFoundError
from app.services import run_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("/{run_id}/download")
async def download_run(run_id: str) -> Response:
    """Download the persisted result CSV for a confirmed workflow run."""
    try:
        csv_bytes, filename = await run_store.load(run_id)
    except DatasetNotFoundError as exc:
        raise DatasetNotFoundError(
            str(exc),
            error_code="download_not_found",
            context={"suggestion": "The run result may have been removed. Re-execute the workflow to regenerate it."},
        ) from exc
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
