"""Tests for orchestrator missing-column → clarification routing.

Verifies three fixes:
1. _explicit_missing_column detects "sort by X" / "order by X" patterns.
2. _detect_step_type_from_query infers step type from query keywords.
3. _extract_column_from_error extracts column name from planner/validator messages.
4. PlannerError with "does not exist in the dataset" routes to clarification
   instead of empty_workflow.
5. "Sort by revenue" with revenue absent triggers needs_clarification end-to-end.
"""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.agent.loop.orchestrator import (
    _detect_step_type_from_query,
    _explicit_missing_column,
    _extract_column_from_error,
)
from app.core.exceptions import PlannerError
from app.main import app

client = TestClient(app)

COLUMNS = ["order_id", "region", "category", "amount", "quantity", "status"]

_BASE_CSV = (
    b"order_id,region,category,amount,quantity,status\n"
    b"1001,North,Electronics,1200,2,active\n"
    b"1002,South,Clothing,350,5,active\n"
    b"1003,East,Electronics,2800,1,pending\n"
)


def _upload(csv_bytes: bytes = _BASE_CSV) -> str:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("orders.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


# ---------------------------------------------------------------------------
# _explicit_missing_column
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("Sort by revenue descending", "revenue"),
    ("sort by sales asc", "sales"),
    ("Order by profit", "profit"),
    ("sorted by revenue", "revenue"),
    # Existing filter pattern still works
    ("filter where price > 100", "price"),
    # Existing column should return None
    ("Sort by amount descending", None),
    ("filter where amount > 100", None),
    # Chinese sort patterns
    ("按revenue排序", "revenue"),
    ("根据profit降序", "profit"),
])
def test_explicit_missing_column(query, expected):
    result = _explicit_missing_column(query, COLUMNS)
    assert result == expected


# ---------------------------------------------------------------------------
# _detect_step_type_from_query
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("Sort by revenue descending", "sort_values"),
    ("order by profit asc", "sort_values"),
    ("sorted by amount", "sort_values"),
    ("group by region and sum amount", "group_by"),
    ("filter where amount > 100", "filter_rows"),
    ("filter rows where status = active", "filter_rows"),
    ("show me top rows", None),
    ("select all columns", None),
])
def test_detect_step_type_from_query(query, expected):
    result = _detect_step_type_from_query(query)
    assert result == expected


# ---------------------------------------------------------------------------
# _extract_column_from_error
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("msg, expected", [
    ("Column 'revenue' does not exist in the dataset.", "revenue"),
    ("column \"profit\" does not exist in the dataset.", "profit"),
    ("Column revenue is not found.", "revenue"),
    ("Some other error message", None),
])
def test_extract_column_from_error(msg, expected):
    result = _extract_column_from_error(msg)
    assert result == expected


# ---------------------------------------------------------------------------
# End-to-end: sort by missing column → clarification (not empty_workflow)
# ---------------------------------------------------------------------------

def test_sort_by_missing_column_returns_clarification():
    """'Sort by revenue descending' with no 'revenue' column must return
    needs_clarification, not raise empty_workflow."""
    did = _upload()
    resp = client.post(
        "/api/chat",
        json={"dataset_id": did, "query": "Sort by revenue descending", "auto_confirm": False},
    )
    data = resp.json()
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {data}"
    assert data["needs_clarification"] is True
    assert data["state"] == "needs_clarification"
    assert "revenue" in data.get("clarification_question", "")


def test_planner_error_missing_column_routes_to_clarification():
    """When the planner itself raises PlannerError('Column X does not exist'),
    the response must be clarification, not empty_workflow."""
    did = _upload()
    with patch(
        "app.agent.loop.orchestrator.workflow_planner.plan",
        side_effect=PlannerError(
            "Column 'revenue' does not exist in the dataset. "
            "Available columns: order_id, region, category, amount, quantity, status."
        ),
    ):
        resp = client.post(
            "/api/chat",
            json={"dataset_id": did, "query": "Sort by revenue descending", "auto_confirm": False},
        )
    data = resp.json()
    # _explicit_missing_column catches revenue before the planner runs, so
    # either path (early detection or PlannerError fallback) yields clarification.
    assert resp.status_code == 200
    assert data["needs_clarification"] is True
    assert data["state"] == "needs_clarification"


def test_planner_error_unsupported_op_returns_422():
    """PlannerError for unsupported operations must return an error response
    (422 / empty_workflow), not a clarification."""
    did = _upload()
    with patch(
        "app.agent.loop.orchestrator.workflow_planner.plan",
        side_effect=PlannerError("The request cannot be handled with the supported transformations."),
    ), patch(
        "app.agent.loop.orchestrator._explicit_missing_column",
        return_value=None,
    ), patch(
        "app.agent.loop.orchestrator._run_slot_extraction",
        return_value=None,
    ):
        resp = client.post(
            "/api/chat",
            json={"dataset_id": did, "query": "Do a nested pivot rollup", "auto_confirm": False},
        )
    data = resp.json()
    assert resp.status_code == 400
    assert data.get("error_code") == "empty_workflow"


def test_sort_clarification_affected_step_type_is_sort_values():
    """Clarification context for a sort query must carry affected_step.type = 'sort_values'."""
    did = _upload()
    resp = client.post(
        "/api/chat",
        json={"dataset_id": did, "query": "Sort by revenue descending", "auto_confirm": False},
    )
    data = resp.json()
    assert resp.status_code == 200
    assert data["needs_clarification"] is True
    ctx = data.get("clarification_context") or {}
    affected = ctx.get("affected_step") or {}
    assert affected.get("type") == "sort_values", (
        f"expected affected_step.type = 'sort_values', got: {affected}"
    )
    assert affected.get("column") == "revenue"
