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


# ---------------------------------------------------------------------------
# Preview flow tests
# ---------------------------------------------------------------------------

ZERO_MATCH_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
)


def _preview(dataset_id: str, steps: list) -> dict:
    return client.post(
        "/api/workflows/preview",
        json={"dataset_id": dataset_id, "steps": steps},
    )


def test_preview_returns_200():
    did = _upload()
    resp = _preview(did, [{"type": "remove_missing_values"}])
    assert resp.status_code == 200


def test_preview_response_has_required_fields():
    did = _upload()
    resp = _preview(did, [{"type": "remove_missing_values"}])
    data = resp.json()
    for field in ("planned_steps", "step_results", "has_warnings", "has_errors", "blocked_at_step"):
        assert field in data


def test_preview_returns_planned_steps():
    did = _upload()
    steps = [{"type": "remove_missing_values"}]
    data = _preview(did, steps).json()
    assert data["planned_steps"] == steps


def test_preview_step_results_count_matches_steps():
    did = _upload()
    steps = [
        {"type": "remove_missing_values"},
        {"type": "sort_values", "column": "sales", "ascending": False},
    ]
    data = _preview(did, steps).json()
    assert len(data["step_results"]) == 2


def test_preview_step_result_has_standard_fields():
    did = _upload()
    data = _preview(did, [{"type": "remove_missing_values"}]).json()
    sr = data["step_results"][0]
    for field in (
        "step_index", "step_type", "status", "issues",
        "input_row_count", "output_row_count",
        "input_column_count", "output_column_count",
        "preview", "message",
    ):
        assert field in sr


def test_preview_clean_workflow_has_no_warnings_or_errors():
    did = _upload()
    data = _preview(
        did,
        [{"type": "filter_rows", "column": "region", "operator": "=", "value": "North"}],
    ).json()
    assert data["has_warnings"] is False
    assert data["has_errors"] is False
    assert data["blocked_at_step"] is None


def test_preview_zero_match_filter_sets_has_warnings():
    did = _upload(ZERO_MATCH_CSV)
    data = _preview(
        did,
        [{"type": "filter_rows", "column": "sales", "operator": ">", "value": 9999}],
    ).json()
    assert data["has_warnings"] is True
    assert data["has_errors"] is False


def test_preview_zero_match_filter_issues_appear_in_step_result():
    did = _upload(ZERO_MATCH_CSV)
    data = _preview(
        did,
        [{"type": "filter_rows", "column": "sales", "operator": ">", "value": 9999}],
    ).json()
    codes = [i["code"] for i in data["step_results"][0]["issues"]]
    assert "no_rows_matched" in codes
    assert "empty_output" in codes


def test_preview_blocked_at_step_is_none_on_success():
    did = _upload()
    data = _preview(did, [{"type": "remove_missing_values"}]).json()
    assert data["blocked_at_step"] is None


def test_preview_runtime_error_captured_without_500():
    """Executor fails at step 1 when 'sales' is dropped by step 0."""
    did = _upload()
    steps = [
        {"type": "select_columns", "columns": ["region"]},
        {"type": "filter_rows", "column": "sales", "operator": ">", "value": 0},
    ]
    resp = _preview(did, steps)
    assert resp.status_code == 200


def test_preview_runtime_error_sets_has_errors():
    did = _upload()
    steps = [
        {"type": "select_columns", "columns": ["region"]},
        {"type": "filter_rows", "column": "sales", "operator": ">", "value": 0},
    ]
    data = _preview(did, steps).json()
    assert data["has_errors"] is True


def test_preview_runtime_error_sets_blocked_at_step():
    did = _upload()
    steps = [
        {"type": "select_columns", "columns": ["region"]},
        {"type": "filter_rows", "column": "sales", "operator": ">", "value": 0},
    ]
    data = _preview(did, steps).json()
    assert data["blocked_at_step"] == 1


def test_preview_runtime_error_returns_partial_step_results():
    """Step 0 succeeds; step 1 fails — two step_results are returned."""
    did = _upload()
    steps = [
        {"type": "select_columns", "columns": ["region"]},
        {"type": "filter_rows", "column": "sales", "operator": ">", "value": 0},
    ]
    data = _preview(did, steps).json()
    assert len(data["step_results"]) == 2
    assert data["step_results"][0]["status"] == "success"
    assert data["step_results"][1]["status"] == "error"


def test_preview_unknown_dataset_returns_400():
    resp = _preview("nonexistent-id", [{"type": "remove_missing_values"}])
    assert resp.status_code == 400


def test_preview_missing_column_returns_400():
    """Validator catches missing column before execution → 400."""
    did = _upload()
    resp = _preview(
        did,
        [{"type": "filter_rows", "column": "nonexistent", "operator": ">", "value": 0}],
    )
    assert resp.status_code == 400
