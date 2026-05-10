"""Shared test fixtures.

Provides mock_database: an autouse fixture that replaces the asyncpg pool and
redirects storage_root to a temporary directory so tests run without a real
Postgres or persistent file system.

The mock connection is stateful within each test: save() stores the uri and
load() resolves it, mirroring the real round-trip through the datasets table.
"""
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone


class _MockConnection:
    """Stateful asyncpg connection mock.

    Tracks dataset_id → storage_uri from INSERT calls so fetchrow can
    return the correct row for subsequent SELECT calls in the same test.
    """

    def __init__(self) -> None:
        self._datasets: dict[str, str] = {}
        self._runs: dict[str, dict] = {}

    async def execute(self, query: str, *args) -> None:
        if "INSERT INTO datasets" in query:
            # args: id, filename, storage_uri, size_bytes, row_count, col_count, profile_json
            dataset_id = str(args[0])
            storage_uri = str(args[2])
            self._datasets[dataset_id] = storage_uri
        if "INSERT INTO workflow_runs" in query:
            run_id = str(args[0])
            self._runs[run_id] = {
                "id": run_id,
                "dataset_id": str(args[1]),
                "filename": str(args[3]),
                "storage_uri": str(args[4]),
                "row_count": args[5],
                "query": args[7],
                "status": args[8],
                "explanation": args[9],
                "planned_steps": args[10],
                "step_count": args[11],
                "parent_run_id": args[12],
                "trace": args[13],
                "context_summary": args[14],
                "created_at": datetime.now(timezone.utc),
            }

    async def fetchrow(self, query: str, *args) -> dict | None:
        record_id = str(args[0]) if args else ""
        if "FROM workflow_runs" in query and "SELECT storage_uri, filename" in query:
            run = self._runs.get(record_id)
            return {"storage_uri": run["storage_uri"], "filename": run["filename"]} if run else None
        if "FROM workflow_runs" in query:
            return self._runs.get(record_id)
        if "SELECT storage_uri" in query:
            uri = self._datasets.get(record_id)
            return {"storage_uri": uri} if uri else None
        if "SELECT id" in query:
            return {"id": record_id} if record_id in self._datasets else None
        return None


class _MockPool:
    """asyncpg.Pool-compatible mock that provides a _MockConnection."""

    def __init__(self) -> None:
        self.conn = _MockConnection()

    def acquire(self) -> "_MockPool":
        return self

    async def __aenter__(self) -> _MockConnection:
        return self.conn

    async def __aexit__(self, *args) -> None:
        pass

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def mock_database(tmp_path, monkeypatch):
    """Replace the asyncpg pool with an in-memory mock and redirect storage."""
    pool = _MockPool()

    monkeypatch.setattr("app.core.database.pool", pool)
    monkeypatch.setattr("app.core.database.connect", AsyncMock())
    monkeypatch.setattr("app.core.database.disconnect", AsyncMock())
    monkeypatch.setattr("app.core.config.settings.storage_root", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.retrieval_method", "keyword")

    yield pool
