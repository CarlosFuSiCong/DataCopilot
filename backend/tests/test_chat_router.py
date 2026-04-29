"""Integration tests for POST /api/chat.

The LLM planner is mocked so tests run without a real API key.
Each test uploads a CSV, then calls /api/chat with a predefined
mock planner response.
"""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.workflow import GroupByStep, RemoveMissingValuesStep, SortValuesStep

client = TestClient(app)

BASE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
    b"South,900,Feb\n"
    b"West,,Feb\n"
)

MOCK_STEPS_GROUP_BY = [
    RemoveMissingValuesStep(type="remove_missing_values"),
    GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
    SortValuesStep(type="sort_values", column="sales", ascending=False),
]


def _upload(csv_bytes: bytes = BASE_CSV) -> str:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


# ---------------------------------------------------------------------------
# Successful chat pipeline
# ---------------------------------------------------------------------------

def test_chat_returns_200_with_mocked_planner():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        resp = client.post("/api/chat", json={"dataset_id": did, "query": "按地区统计销售额"})
    assert resp.status_code == 200


def test_chat_response_has_required_fields():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    for field in ("query", "planned_steps", "execution_result", "rag_context"):
        assert field in data


def test_chat_planned_steps_match_mock():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    types = [s["type"] for s in data["planned_steps"]]
    assert types == ["remove_missing_values", "group_by", "sort_values"]


def test_chat_execution_result_has_correct_groups():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    # After remove_missing (drops West row) + group_by region: North and South
    assert data["execution_result"]["row_count"] == 2


def test_chat_rag_context_includes_dataset_summary():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    summary = data["rag_context"]["dataset_summary"]
    assert summary["row_count"] == 5
    col_names = [c["name"] for c in summary["columns"]]
    assert "region" in col_names
    assert "sales" in col_names


def test_chat_rag_context_has_debug_info():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    assert data["rag_context"]["debug"]["method"] == "keyword_matching"


def test_chat_query_echoed_in_response():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        data = client.post("/api/chat", json={"dataset_id": did, "query": "按地区统计"}).json()
    assert data["query"] == "按地区统计"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_chat_unknown_dataset_returns_400():
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        resp = client.post("/api/chat", json={"dataset_id": "no-such-id", "query": "test"})
    assert resp.status_code == 400


def test_chat_planner_error_returns_400():
    from app.core.exceptions import PlannerError
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", side_effect=PlannerError("unsupported request")):
        resp = client.post("/api/chat", json={"dataset_id": did, "query": "画一张图"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_chat_validation_error_returns_400():
    from app.models.workflow import FilterRowsStep
    bad_steps = [FilterRowsStep(type="filter_rows", column="nonexistent_col", operator=">", value=0)]
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=bad_steps):
        resp = client.post("/api/chat", json={"dataset_id": did, "query": "test"})
    assert resp.status_code == 400
    assert "nonexistent_col" in resp.json()["error"]
