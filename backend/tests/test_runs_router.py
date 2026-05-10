"""Unit tests for run history response shaping."""
from datetime import datetime, timedelta, timezone

from app.api.runs import _to_run_record
from app.services import run_store


def _run_row(status: str | None = "success") -> dict:
    return {
        "id": "run-1",
        "dataset_id": "dataset-1",
        "query": "test query",
        "status": status,
        "step_count": 1,
        "row_count": 2,
        "created_at": datetime.now(timezone.utc),
        "parent_run_id": None,
        "explanation": "done",
        "planned_steps": [{"type": "remove_missing_values"}],
        "trace": {"attempts": []},
        "context_summary": {
            "query": "test query",
            "dataset_hash": "abc123",
            "schema_columns": ["region", "sales"],
            "row_count": 2,
            "retrieved_docs": [],
            "planned_step_types": ["remove_missing_values"],
            "status": "executed",
            "boundary": "executed",
            "validation_status": "passed",
            "warning_count": 0,
            "error_count": 0,
        },
    }


def test_to_run_record_normalizes_legacy_success_status_in_detail():
    record = _to_run_record(_run_row("success"), include_detail=True)

    assert record.status == "executed"
    assert record.state == "executed"


def test_to_run_record_normalizes_legacy_success_status_in_list():
    record = _to_run_record(_run_row("success"), include_detail=False)

    assert record.status == "executed"
    assert record.state is None


def test_to_run_record_preserves_non_legacy_status():
    record = _to_run_record(_run_row("warning_review"), include_detail=True)

    assert record.status == "warning_review"
    assert record.state == "warning_review"


async def test_list_for_dataset_filters_legacy_success_as_executed(mock_database):
    conn = mock_database.conn
    conn._runs["legacy-run"] = _run_row("success")
    conn._runs["legacy-run"]["id"] = "legacy-run"
    conn._runs["preview-run"] = _run_row("warning_review")
    conn._runs["preview-run"]["id"] = "preview-run"

    rows, total = await run_store.list_for_dataset(
        "dataset-1",
        status="executed",
    )

    assert total == 1
    assert rows[0]["id"] == "legacy-run"


async def test_list_for_dataset_total_count_is_before_limit(mock_database):
    conn = mock_database.conn
    base_time = datetime.now(timezone.utc)
    for index in range(3):
        run = _run_row("warning_review")
        run["id"] = f"run-{index}"
        run["created_at"] = base_time - timedelta(minutes=index)
        conn._runs[run["id"]] = run

    rows, total = await run_store.list_for_dataset(
        "dataset-1",
        limit=1,
        status="warning_review",
    )

    assert len(rows) == 1
    assert total == 3
