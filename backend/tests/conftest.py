"""Shared test fixtures.

Provides mock_database: an autouse fixture that replaces the asyncpg pool and
redirects storage_root to a temporary directory so tests run without a real
Postgres or persistent file system.

The mock connection is stateful within each test: save() stores the uri and
load() resolves it, mirroring the real round-trip through the datasets table.
"""
import pytest
from unittest.mock import AsyncMock


class _MockConnection:
    """Stateful asyncpg connection mock.

    Tracks dataset_id → storage_uri from INSERT calls so fetchrow can
    return the correct row for subsequent SELECT calls in the same test.
    """

    def __init__(self) -> None:
        self._datasets: dict[str, str] = {}

    async def execute(self, query: str, *args) -> None:
        if "INSERT INTO datasets" in query:
            # args: id, filename, storage_uri, size_bytes, row_count, col_count, profile_json
            dataset_id = str(args[0])
            storage_uri = str(args[2])
            self._datasets[dataset_id] = storage_uri

    async def fetchrow(self, query: str, *args) -> dict | None:
        dataset_id = str(args[0]) if args else ""
        if "SELECT storage_uri" in query:
            uri = self._datasets.get(dataset_id)
            return {"storage_uri": uri} if uri else None
        if "SELECT id" in query:
            return {"id": dataset_id} if dataset_id in self._datasets else None
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

    yield pool
