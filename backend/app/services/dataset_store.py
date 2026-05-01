"""Persistent dataset store backed by local file storage and Postgres.

save():  writes raw CSV to {storage_root}/datasets/{id}/raw.csv and inserts
         metadata into the datasets table.
load():  queries storage_uri from Postgres, then reads the file from local storage.
exists(): checks Postgres for the dataset record.

The service boundary is preserved: routers call this module; no router touches
the database or file system directly.
All three functions are async because they perform database I/O.
"""
import json
import logging
from pathlib import Path

from app.core import database
from app.core.config import settings
from app.core.exceptions import DatasetNotFoundError

logger = logging.getLogger(__name__)


def _local_path(dataset_id: str) -> Path:
    return Path(settings.storage_root) / "datasets" / dataset_id / "raw.csv"


def _storage_uri(dataset_id: str) -> str:
    return f"local://datasets/{dataset_id}/raw.csv"


async def save(
    dataset_id: str,
    content: bytes,
    *,
    filename: str,
    profile_data: dict,
) -> None:
    """Write raw CSV to local storage and insert metadata into Postgres."""
    path = _local_path(dataset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)

    async with database.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO datasets
                (id, filename, storage_backend, storage_uri, size_bytes,
                 row_count, column_count, profile_json)
            VALUES ($1, $2, 'local', $3, $4, $5, $6, $7::jsonb)
            """,
            dataset_id,
            filename,
            _storage_uri(dataset_id),
            len(content),
            profile_data.get("row_count"),
            profile_data.get("column_count"),
            json.dumps(profile_data),
        )

    logger.info("Saved dataset '%s' (%d bytes) to %s", dataset_id, len(content), path)


async def load(dataset_id: str) -> bytes:
    """Resolve storage URI from Postgres and read the raw CSV from local storage."""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT storage_uri FROM datasets WHERE id = $1",
            dataset_id,
        )

    if row is None:
        raise DatasetNotFoundError(
            f"Dataset '{dataset_id}' not found. Please upload first."
        )

    # Parse local:// URI → relative path → absolute path
    relative = row["storage_uri"].removeprefix("local://")
    path = Path(settings.storage_root) / relative

    if not path.exists():
        raise DatasetNotFoundError(
            f"Dataset '{dataset_id}' raw file missing at storage path."
        )

    return path.read_bytes()


async def exists(dataset_id: str) -> bool:
    """Return True if a dataset record exists in Postgres."""
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM datasets WHERE id = $1",
            dataset_id,
        )
    return row is not None
