"""Persistent store for workflow run result CSVs.

save():  writes result CSV to {storage_root}/runs/{run_id}/result.csv and
         inserts a record into the workflow_runs table.
load():  resolves storage_uri from Postgres and reads the file.
list_for_dataset(): returns recent run records for a dataset.
get_run(): returns a single run record by run_id.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import database
from app.core.config import settings
from app.core.exceptions import DatasetNotFoundError

logger = logging.getLogger(__name__)


def _local_path(run_id: str) -> Path:
    return Path(settings.storage_root) / "runs" / run_id / "result.csv"


def _storage_uri(run_id: str) -> str:
    return f"local://runs/{run_id}/result.csv"


def steps_hash(steps: list[dict]) -> str:
    """SHA-256 of the canonical JSON representation of the workflow steps."""
    canonical = json.dumps(steps, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


async def save(
    *,
    dataset_id: str,
    csv_bytes: bytes,
    filename: str,
    planned_steps: list[dict],
    row_count: int,
    query: str | None = None,
    status: str = "success",
    explanation: str | None = None,
    parent_run_id: str | None = None,
    trace: dict[str, Any] | None = None,
    context_summary: dict[str, Any] | None = None,
) -> str:
    """Persist the result CSV and return the new run_id."""
    run_id = str(uuid.uuid4())
    path = _local_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(csv_bytes)

    steps_json = json.dumps(planned_steps, ensure_ascii=False)
    trace_json = json.dumps(trace, ensure_ascii=False) if trace is not None else None
    context_summary_json = (
        json.dumps(context_summary, ensure_ascii=False)
        if context_summary is not None
        else None
    )
    step_count = len(planned_steps)

    async with database.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workflow_runs
                (id, dataset_id, steps_hash, filename, storage_uri, row_count, size_bytes,
                 query, status, explanation, planned_steps, step_count, parent_run_id,
                 trace, context_summary)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13,
                    $14::jsonb, $15::jsonb)
            """,
            run_id,
            dataset_id,
            steps_hash(planned_steps),
            filename,
            _storage_uri(run_id),
            row_count,
            len(csv_bytes),
            query,
            status,
            explanation,
            steps_json,
            step_count,
            parent_run_id,
            trace_json,
            context_summary_json,
        )

    logger.info(
        "Saved run '%s' (%d bytes, %d rows, %d steps) for dataset '%s'",
        run_id, len(csv_bytes), row_count, step_count, dataset_id,
    )
    return run_id


async def load(run_id: str) -> tuple[bytes, str]:
    """Return (csv_bytes, filename) for the given run_id."""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT storage_uri, filename FROM workflow_runs WHERE id = $1",
            run_id,
        )

    if row is None:
        raise DatasetNotFoundError(f"Run '{run_id}' not found.")

    relative = row["storage_uri"].removeprefix("local://")
    path = Path(settings.storage_root) / relative

    if not path.exists():
        raise DatasetNotFoundError(
            f"Run '{run_id}' result file missing at storage path."
        )

    return path.read_bytes(), row["filename"]


async def list_for_dataset(
    dataset_id: str,
    limit: int = 20,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Return (records, total_count) for a dataset, newest first.

    total_count reflects all rows matching dataset_id, not just the page.
    Uses a window function so only one DB round-trip is needed.
    """
    status_values: tuple[str, ...] | None = None
    if status:
        normalized = "executed" if status == "success" else status
        status_values = ("executed", "success") if normalized == "executed" else (normalized,)

    async with database.pool.acquire() as conn:
        if status_values:
            rows = await conn.fetch(
                """
                SELECT id, dataset_id, query, status, step_count, row_count,
                       created_at, parent_run_id,
                       COUNT(*) OVER () AS total_count
                FROM workflow_runs
                WHERE dataset_id = $1 AND status = ANY($3::text[])
                ORDER BY created_at DESC
                LIMIT $2
                """,
                dataset_id,
                limit,
                list(status_values),
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, dataset_id, query, status, step_count, row_count,
                       created_at, parent_run_id,
                       COUNT(*) OVER () AS total_count
                FROM workflow_runs
                WHERE dataset_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                dataset_id,
                limit,
            )
    if not rows:
        return [], 0
    total = rows[0]["total_count"]
    return [dict(row) for row in rows], total


async def get_run(run_id: str) -> dict[str, Any]:
    """Return full metadata for a single run, including explanation and planned_steps."""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, dataset_id, query, status, step_count, row_count,
                   created_at, parent_run_id, explanation, planned_steps,
                   trace, context_summary
            FROM workflow_runs
            WHERE id = $1
            """,
            run_id,
        )

    if row is None:
        raise DatasetNotFoundError(f"Run '{run_id}' not found.")

    data = dict(row)
    # planned_steps is stored as JSONB; asyncpg returns it as a string.
    if data.get("planned_steps") and isinstance(data["planned_steps"], str):
        data["planned_steps"] = json.loads(data["planned_steps"])
    if data.get("trace") and isinstance(data["trace"], str):
        data["trace"] = json.loads(data["trace"])
    if data.get("context_summary") and isinstance(data["context_summary"], str):
        data["context_summary"] = json.loads(data["context_summary"])
    return data
