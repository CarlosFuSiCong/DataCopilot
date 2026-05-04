"""Persistent store for workflow run result CSVs.

save():  writes result CSV to {storage_root}/runs/{run_id}/result.csv and
         inserts a record into the workflow_runs table.
load():  resolves storage_uri from Postgres and reads the file.
"""
import hashlib
import json
import logging
import uuid
from pathlib import Path

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
) -> str:
    """Persist the result CSV and return the new run_id."""
    run_id = str(uuid.uuid4())
    path = _local_path(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(csv_bytes)

    async with database.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO workflow_runs
                (id, dataset_id, steps_hash, filename, storage_uri, row_count, size_bytes)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            run_id,
            dataset_id,
            steps_hash(planned_steps),
            filename,
            _storage_uri(run_id),
            row_count,
            len(csv_bytes),
        )

    logger.info("Saved run '%s' (%d bytes, %d rows) for dataset '%s'", run_id, len(csv_bytes), row_count, dataset_id)
    return run_id


async def load(run_id: str) -> tuple[bytes, str]:
    """Return (csv_bytes, filename) for the given run_id."""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT storage_uri, filename FROM workflow_runs WHERE id = $1",
            run_id,
        )

    if row is None:
        raise DatasetNotFoundError(
            f"Run '{run_id}' not found."
        )

    relative = row["storage_uri"].removeprefix("local://")
    path = Path(settings.storage_root) / relative

    if not path.exists():
        raise DatasetNotFoundError(
            f"Run '{run_id}' result file missing at storage path."
        )

    return path.read_bytes(), row["filename"]
