"""Integration tests for POST /api/chat.

Both the LLM planner and the result explainer are mocked so tests run
without a real API key and produce deterministic results.
"""
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import PlannerError
from app.main import app
from app.models.workflow import FilterRowsStep, GroupByStep, RemoveMissingValuesStep, SortValuesStep
from app.workflow.planning.route_decision import RouteDecision

client = TestClient(app)

BASE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
    b"South,900,Feb\n"
    b"West,,Feb\n"
)

# Steps that produce no warnings against BASE_CSV
MOCK_STEPS_GROUP_BY = [
    RemoveMissingValuesStep(type="remove_missing_values"),
    GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
    SortValuesStep(type="sort_values", column="sales", ascending=False),
]

# Steps that produce no_rows_matched + empty_output warnings against BASE_CSV
MOCK_STEPS_ZERO_MATCH = [
    FilterRowsStep(type="filter_rows", column="sales", operator=">", value=9999),
]

_MOCK_EXPLANATION = "Mock explanation for testing."


def _upload(csv_bytes: bytes = BASE_CSV) -> str:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


def _chat(did: str, query: str = "test", auto_confirm: bool = True) -> dict:
    """Call /api/chat with planner mocked to MOCK_STEPS_GROUP_BY (no warnings)."""
    mock_route = RouteDecision(
        route="llm_planner",
        query_type="aggregation",
        confidence=0.9,
        reason="mocked",
    )
    with patch("app.workflow.service.classify", return_value=mock_route):
        with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
            with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
                return client.post(
                    "/api/chat",
                    json={"dataset_id": did, "query": query, "auto_confirm": auto_confirm},
                )


def _chat_with_warnings(did: str, auto_confirm: bool = True) -> dict:
    """Call /api/chat with planner mocked to steps that produce warnings."""
    mock_route = RouteDecision(
        route="llm_planner",
        query_type="filtering",
        confidence=0.9,
        reason="mocked",
    )
    with patch("app.workflow.service.classify", return_value=mock_route):
        with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_ZERO_MATCH):
            return client.post(
                "/api/chat",
                json={"dataset_id": did, "query": "test", "auto_confirm": auto_confirm},
            )


# ---------------------------------------------------------------------------
# Response shape — always-present fields
# ---------------------------------------------------------------------------

def test_chat_returns_200():
    did = _upload()
    resp = _chat(did, "按地区统计销售额")
    assert resp.status_code == 200


def test_chat_response_has_required_fields():
    did = _upload()
    data = _chat(did).json()
    for field in (
        "query",
        "planned_steps",
        "step_results",
        "has_warnings",
        "has_errors",
        "rag_context",
        "state",
        "attempts",
        "context_summary",
    ):
        assert field in data


def test_chat_planned_steps_match_mock():
    did = _upload()
    data = _chat(did).json()
    types = [s["type"] for s in data["planned_steps"]]
    assert types == ["remove_missing_values", "group_by", "sort_values"]


def test_chat_step_results_count_matches_steps():
    did = _upload()
    data = _chat(did).json()
    assert len(data["step_results"]) == len(MOCK_STEPS_GROUP_BY)


def test_chat_rag_context_includes_dataset_summary():
    did = _upload()
    data = _chat(did).json()
    summary = data["rag_context"]["dataset_summary"]
    assert summary["row_count"] == 5
    col_names = [c["name"] for c in summary["columns"]]
    assert "region" in col_names
    assert "sales" in col_names


def test_chat_rag_context_has_debug_info():
    did = _upload()
    data = _chat(did).json()
    assert data["rag_context"]["debug"]["method"] == "keyword_matching"


def test_chat_query_echoed_in_response():
    did = _upload()
    data = _chat(did, "按地区统计").json()
    assert data["query"] == "按地区统计"


# ---------------------------------------------------------------------------
# auto_confirm=True (default) — no warnings: full result returned
# ---------------------------------------------------------------------------

def test_chat_auto_confirm_true_no_warnings_returns_explanation():
    did = _upload()
    data = _chat(did).json()
    assert data["explanation"] == _MOCK_EXPLANATION


def test_chat_auto_confirm_true_no_warnings_returns_execution_result():
    did = _upload()
    data = _chat(did).json()
    assert data["execution_result"] is not None
    assert data["execution_result"]["row_count"] == 2


def test_chat_auto_confirm_true_no_warnings_sets_has_warnings_false():
    did = _upload()
    data = _chat(did).json()
    assert data["has_warnings"] is False
    assert data["has_errors"] is False


def test_chat_auto_confirm_true_no_warnings_sets_executed_state():
    did = _upload()
    data = _chat(did).json()
    assert data["state"] == "executed"
    assert data["context_summary"]["status"] == "executed"
    assert data["attempts"][0]["summary"]["validation_status"] == "passed"


# ---------------------------------------------------------------------------
# auto_confirm=True — with warnings: preview-only returned
# ---------------------------------------------------------------------------

def test_chat_auto_confirm_true_with_warnings_returns_200():
    did = _upload()
    resp = _chat_with_warnings(did, auto_confirm=True)
    assert resp.status_code == 200


def test_chat_auto_confirm_true_with_warnings_sets_has_warnings():
    did = _upload()
    data = _chat_with_warnings(did, auto_confirm=True).json()
    assert data["has_warnings"] is True


def test_chat_auto_confirm_true_with_warnings_explanation_is_none():
    did = _upload()
    data = _chat_with_warnings(did, auto_confirm=True).json()
    assert data["explanation"] is None


def test_chat_auto_confirm_true_with_warnings_execution_result_is_none():
    did = _upload()
    data = _chat_with_warnings(did, auto_confirm=True).json()
    assert data["execution_result"] is None


def test_chat_auto_confirm_true_with_warnings_does_not_call_explainer():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_ZERO_MATCH):
        with patch("app.api.chat.result_explainer.explain") as mock_explain:
            client.post("/api/chat", json={"dataset_id": did, "query": "test", "auto_confirm": True})
    mock_explain.assert_not_called()


def test_chat_auto_confirm_true_with_warnings_sets_warning_review_state():
    did = _upload()
    data = _chat_with_warnings(did, auto_confirm=True).json()
    assert data["state"] == "warning_review"
    assert data["context_summary"]["warning_count"] >= 1


# ---------------------------------------------------------------------------
# auto_confirm=False — always preview-only
# ---------------------------------------------------------------------------

def test_chat_auto_confirm_false_returns_200():
    did = _upload()
    resp = _chat(did, auto_confirm=False)
    assert resp.status_code == 200


def test_chat_auto_confirm_false_explanation_is_none():
    did = _upload()
    data = _chat(did, auto_confirm=False).json()
    assert data["explanation"] is None


def test_chat_auto_confirm_false_execution_result_is_none():
    did = _upload()
    data = _chat(did, auto_confirm=False).json()
    assert data["execution_result"] is None


def test_chat_auto_confirm_false_still_returns_step_results():
    did = _upload()
    data = _chat(did, auto_confirm=False).json()
    assert len(data["step_results"]) == len(MOCK_STEPS_GROUP_BY)


def test_chat_auto_confirm_false_does_not_call_explainer():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        with patch("app.api.chat.result_explainer.explain") as mock_explain:
            client.post("/api/chat", json={"dataset_id": did, "query": "test", "auto_confirm": False})
    mock_explain.assert_not_called()


def test_chat_auto_confirm_false_sets_preview_ready_state():
    did = _upload()
    data = _chat(did, auto_confirm=False).json()
    assert data["state"] == "preview_ready"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_chat_unknown_dataset_returns_400():
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post("/api/chat", json={"dataset_id": "no-such-id", "query": "test"})
    assert resp.status_code == 400


def test_chat_planner_error_returns_400():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", side_effect=PlannerError("unsupported request")):
        resp = client.post("/api/chat", json={"dataset_id": did, "query": "画一张图"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_chat_missing_column_validation_asks_clarification():
    bad_steps = [FilterRowsStep(type="filter_rows", column="nonexistent_col", operator=">", value=0)]
    did = _upload()
    mock_route = RouteDecision(
        route="llm_planner",
        query_type="filtering",
        confidence=0.9,
        reason="mocked",
    )
    with patch("app.workflow.service.classify", return_value=mock_route):
        with patch("app.api.chat.workflow_planner.plan", return_value=bad_steps):
            with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
                resp = client.post("/api/chat", json={"dataset_id": did, "query": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert data["state"] == "needs_clarification"
    assert "nonexistent_col" in data["clarification_question"]
    assert "sales" in data["clarification_question"]


def test_chat_explicit_missing_column_asks_clarification_before_planning():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan") as mock_plan:
        resp = client.post(
            "/api/chat",
            json={"dataset_id": did, "query": "filter rows where revenue > 100"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_clarification"] is True
    assert "revenue" in data["clarification_question"]
    assert "sales" in data["clarification_question"]
    mock_plan.assert_not_called()


def test_chat_clarification_context_uses_original_query_scope_when_followup_query_is_answer():
    did = _upload()
    first = client.post(
        "/api/chat",
        json={"dataset_id": did, "query": "filter rows where revenue > 100"},
    )
    assert first.status_code == 200
    context = first.json()["clarification_context"]
    context["user_answer"] = "sales"

    with patch(
        "app.api.chat.workflow_planner.plan",
        return_value=[FilterRowsStep(type="filter_rows", column="sales", operator=">", value=100)],
    ):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            second = client.post(
                "/api/chat",
                json={
                    "dataset_id": did,
                    "query": "sales",
                    "clarification_context": context,
                },
            )

    assert second.status_code == 200
    assert second.json().get("error_code") != "clarification_context_scope_mismatch"


def test_chat_planner_missing_group_column_clarification_tracks_affected_step():
    did = _upload()
    original_query = "Calculate total sales by customer_type"

    with patch(
        "app.api.chat.workflow_planner.plan",
        side_effect=PlannerError("Column 'customer_type' does not exist in the dataset."),
    ):
        first = client.post("/api/chat", json={"dataset_id": did, "query": original_query})

    assert first.status_code == 200
    context = first.json()["clarification_context"]
    assert context["affected_step"] == {"type": "group_by", "column": "customer_type"}


def test_chat_validation_missing_column_clarification_rewrites_failed_step_column():
    did = _upload()
    original_query = "Calculate total sales by customer_type"
    bad_steps = [GroupByStep(type="group_by", column="customer_type", target="sales", agg="sum")]

    with patch("app.api.chat.workflow_planner.plan", return_value=bad_steps):
        first = client.post("/api/chat", json={"dataset_id": did, "query": original_query})

    assert first.status_code == 200
    context = first.json()["clarification_context"]
    assert context["affected_step"] == {"type": "group_by", "column": "customer_type"}
    context["user_answer"] = "region"

    captured = {}

    def fake_plan(query, ctx, client=None, slot_context=None):
        captured["query"] = query
        return [GroupByStep(type="group_by", column="region", target="sales", agg="sum")]

    with patch("app.api.chat.workflow_planner.plan", side_effect=fake_plan):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            second = client.post(
                "/api/chat",
                json={
                    "dataset_id": did,
                    "query": "region",
                    "clarification_context": context,
                },
            )

    assert second.status_code == 200
    assert captured["query"] == "Calculate total sales by region"
    assert second.json()["planned_steps"][0]["column"] == "region"


def test_broad_analysis_missing_choice_returns_read_only_ask_mode():
    did = _upload()
    broad_route = RouteDecision(
        route="clarification",
        query_type="broad_analysis_request",
        confidence=0.9,
        reason="mocked broad analysis",
    )
    missing_route = RouteDecision(
        route="ask_mode",
        query_type="diagnosis",
        confidence=0.95,
        reason="mocked missing value check",
        selected_tool="detect_missing_values",
    )
    with patch("app.workflow.service.classify", side_effect=[broad_route, missing_route]):
        first = client.post(
            "/api/chat",
            json={"dataset_id": did, "query": "Analyze this dataset for issues"},
        )
        assert first.status_code == 200
        context = first.json()["clarification_context"]
        context["user_answer"] = "Check for missing values in the dataset"

        with patch("app.api.chat.workflow_planner.plan") as mock_plan:
            second = client.post(
                "/api/chat",
                json={
                    "dataset_id": did,
                    "query": "Analyze this dataset for issues",
                    "clarification_context": context,
                },
            )

    assert second.status_code == 200
    data = second.json()
    assert data["is_read_only"] is True
    assert data["ask_mode_type"] == "missing_values"
    assert data["planned_steps"] == []
    assert data["execution_result"] is None
    assert data["route_decision"]["route"] == "ask_mode"
    assert "sales: 1 missing (20.0%)" in data["explanation"]
    mock_plan.assert_not_called()


def test_chat_validation_failure_allows_one_case_repair():
    bad_case_steps = [FilterRowsStep(type="filter_rows", column="Sales", operator=">", value=1000)]
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=bad_case_steps):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post("/api/chat", json={"dataset_id": did, "query": "filter Sales"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["planned_steps"][0]["column"] == "sales"
    assert len(data["attempts"]) == 2
    assert data["attempts"][1]["repair_reason"] == "case_insensitive_column_match"


def test_chat_persisted_run_detail_includes_trace_summary():
    did = _upload()
    run_id = _chat(did).json()["run_id"]
    resp = client.get(f"/api/runs/{run_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "executed"
    assert data["context_summary"]["status"] == "executed"
    assert data["attempts"][0]["summary"]["final_status"] == "executed"
