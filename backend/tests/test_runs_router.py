"""Unit tests for run history response shaping."""
from datetime import datetime, timezone

from app.api.runs import _to_run_record


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
