"""Runs API — workflow run history, detail, rerun, and download.

GET  /api/runs?dataset_id=...&limit=20     List recent runs for a dataset.
GET  /api/runs/{run_id}                    Full run metadata + explanation + steps.
GET  /api/runs/{run_id}/preview-csv        First 100 rows of the result CSV.
POST /api/runs/{run_id}/rerun              Rerun with (possibly edited) steps.
GET  /api/runs/{run_id}/download           Download the result CSV file.
"""
import csv
import io
import json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.exceptions import DatasetNotFoundError, WorkflowValidationError
from app.models.runs import RerunRequest, RunListResponse, RunRecord
from app.models.workflow import PreviewResponse
from app.services import dataset_store, executor as executor_service
from app.services import run_store, validator as validator_service
from app.services.profiler import get_column_names

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


def _normalize_run_status(status: str | None) -> str:
    value = status or "success"
    return "executed" if value == "success" else value


def _to_run_record(row: dict, include_detail: bool = False) -> RunRecord:
    status = _normalize_run_status(row.get("status"))
    return RunRecord(
        run_id=str(row["id"]),
        dataset_id=str(row["dataset_id"]),
        query=row.get("query"),
        status=status,
        step_count=row.get("step_count"),
        row_count=row.get("row_count"),
        created_at=row["created_at"],
        parent_run_id=str(row["parent_run_id"]) if row.get("parent_run_id") else None,
        explanation=row.get("explanation") if include_detail else None,
        planned_steps=row.get("planned_steps") if include_detail else None,
        state=status if include_detail else None,
        attempts=(row.get("trace") or {}).get("attempts") if include_detail and row.get("trace") else None,
        context_summary=row.get("context_summary") if include_detail else None,
    )


@router.get("", response_model=RunListResponse)
async def list_runs(
    dataset_id: str = Query(..., description="Filter runs by dataset UUID"),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter runs by normalized workflow status"),
) -> RunListResponse:
    """List recent workflow runs for a dataset, newest first."""
    rows, total = await run_store.list_for_dataset(dataset_id, limit=limit, status=status)
    records = [_to_run_record(r) for r in rows]
    return RunListResponse(runs=records, total=total)


@router.get("/{run_id}", response_model=RunRecord)
async def get_run(run_id: str) -> RunRecord:
    """Return full metadata for a single run including explanation and workflow steps."""
    try:
        row = await run_store.get_run(run_id)
    except DatasetNotFoundError as exc:
        raise DatasetNotFoundError(
            str(exc), error_code="download_not_found",
        ) from exc
    return _to_run_record(row, include_detail=True)


@router.get("/{run_id}/preview-csv")
async def preview_run_csv(run_id: str, rows: int = Query(100, ge=1, le=500)) -> Response:
    """Return the first N rows of the result CSV as JSON for frontend display."""
    try:
        csv_bytes, _ = await run_store.load(run_id)
    except DatasetNotFoundError as exc:
        raise DatasetNotFoundError(
            str(exc), error_code="download_not_found",
        ) from exc

    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    preview_rows = []
    for i, row in enumerate(reader):
        if i >= rows:
            break
        preview_rows.append(row)

    columns = reader.fieldnames or []
    return Response(
        content=json.dumps({"columns": columns, "rows": preview_rows}),
        media_type="application/json",
    )


@router.post("/{run_id}/rerun", response_model=PreviewResponse)
async def rerun(run_id: str, request: RerunRequest) -> PreviewResponse:
    """Rerun a previous workflow with (optionally edited) steps.

    Always goes through the validator and returns a preview — the user must
    confirm via POST /api/workflows/confirm before results are persisted.
    Records parent_run_id so the rerun lineage is traceable.
    """
    # Load dataset content.
    content = await dataset_store.load(request.dataset_id)
    column_names = get_column_names(content)

    # Validate the (possibly edited) steps before any execution.
    try:
        validator_service.validate(request.steps, column_names)
    except WorkflowValidationError:
        raise

    # Return a preview — never auto-execute or persist on rerun directly.
    preview_result = executor_service.preview(request.steps, content)

    logger.info(
        "Rerun preview: parent_run_id=%s dataset=%s steps=%d has_warnings=%s",
        run_id,
        request.dataset_id,
        len(request.steps),
        preview_result.has_warnings,
    )

    return preview_result


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
