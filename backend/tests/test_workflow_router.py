"""Integration tests for the workflow execute router.

Uses FastAPI TestClient. Each test uploads a CSV first to get a dataset_id,
then POSTs a workflow to /api/workflows/execute.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BASE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
    b"South,900,Feb\n"
    b"West,,Feb\n"
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _upload(csv_bytes: bytes = BASE_CSV) -> str:
    """Upload a CSV and return the dataset_id."""
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


def _execute(dataset_id: str, steps: list) -> dict:
    resp = client.post(
        "/api/workflows/execute",
        json={"dataset_id": dataset_id, "steps": steps},
    )
    return resp


# ---------------------------------------------------------------------------
# Upload response now includes dataset_id
# ---------------------------------------------------------------------------

def test_upload_response_includes_dataset_id():
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(BASE_CSV), "text/csv")},
    )
    assert resp.status_code == 200
    assert "dataset_id" in resp.json()
    assert resp.json()["dataset_id"]  # non-empty


# ---------------------------------------------------------------------------
# Successful executions
# ---------------------------------------------------------------------------

def test_execute_remove_missing_returns_200():
    did = _upload()
    resp = _execute(did, [{"type": "remove_missing_values"}])
    assert resp.status_code == 200


def test_execute_result_has_required_fields():
    did = _upload()
    resp = _execute(did, [{"type": "remove_missing_values"}])
    data = resp.json()
    for field in (
        "row_count",
        "column_count",
        "columns",
        "preview",
        "step_results",
        "logs",
        "has_summary",
    ):
        assert field in data


def test_execute_remove_missing_reduces_row_count():
    did = _upload()
    data = _execute(did, [{"type": "remove_missing_values"}]).json()
    assert data["row_count"] == 4


def test_execute_group_by_returns_correct_groups():
    did = _upload()
    data = _execute(
        did,
        [{"type": "group_by", "column": "region", "target": "sales", "agg": "sum"}],
    ).json()
    assert data["row_count"] == 3


def test_execute_select_columns_reduces_column_count():
    did = _upload()
    data = _execute(
        did, [{"type": "select_columns", "columns": ["region"]}]
    ).json()
    assert data["column_count"] == 1


def test_execute_filter_rows_reduces_row_count():
    did = _upload()
    data = _execute(
        did,
        [{"type": "filter_rows", "column": "sales", "operator": ">", "value": 1000}],
    ).json()
    assert data["row_count"] == 2


def test_execute_generate_summary_sets_flag():
    did = _upload()
    data = _execute(did, [{"type": "generate_summary"}]).json()
    assert data["has_summary"] is True


def test_execute_logs_count_matches_step_count():
    did = _upload()
    steps = [
        {"type": "remove_missing_values"},
        {"type": "sort_values", "column": "sales", "ascending": False},
    ]
    data = _execute(did, steps).json()
    assert len(data["logs"]) == 2


def test_execute_step_result_includes_standard_fields():
    did = _upload()
    data = _execute(did, [{"type": "remove_missing_values"}]).json()
    step_result = data["step_results"][0]
    for field in (
        "step_index",
        "step_type",
        "status",
        "issues",
        "input_row_count",
        "output_row_count",
        "input_column_count",
        "output_column_count",
        "match_rate",
        "affected_rate",
        "preview",
        "message",
    ):
        assert field in step_result


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_execute_unknown_dataset_id_returns_400():
    resp = _execute("nonexistent-id", [{"type": "remove_missing_values"}])
    assert resp.status_code == 400


def test_execute_unknown_dataset_returns_error_message():
    resp = _execute("nonexistent-id", [{"type": "remove_missing_values"}])
    assert "error" in resp.json()


def test_execute_empty_steps_returns_400():
    did = _upload()
    resp = _execute(did, [])
    assert resp.status_code == 400


def test_execute_unknown_column_returns_400():
    did = _upload()
    resp = _execute(
        did,
        [{"type": "filter_rows", "column": "nonexistent", "operator": ">", "value": 0}],
    )
    assert resp.status_code == 400


def test_execute_unknown_column_error_message_names_column():
    did = _upload()
    resp = _execute(
        did,
        [{"type": "select_columns", "columns": ["missing_col"]}],
    )
    assert "missing_col" in resp.json()["error"]
