"""Contract tests for the controlled Agent API surface."""
import io
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.workflow import FilterRowsStep, GroupByStep, RemoveMissingValuesStep, SortValuesStep

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

MOCK_STEPS_ZERO_MATCH = [
    FilterRowsStep(type="filter_rows", column="sales", operator=">", value=9999),
]

_MOCK_EXPLANATION = "Mock explanation for Agent API testing."


def _upload(csv_bytes: bytes = BASE_CSV) -> str:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


def _start_agent(
    did: str,
    *,
    query: str = "按地区统计销售额",
    auto_confirm: bool = True,
    steps=None,
):
    with patch("app.api.agent.orchestrator.workflow_planner.plan", return_value=steps or MOCK_STEPS_GROUP_BY):
        with patch("app.api.agent.orchestrator.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            return client.post(
                "/api/agent/runs",
                json={"dataset_id": did, "query": query, "auto_confirm": auto_confirm},
            )


def test_agent_run_endpoint_returns_contract_fields():
    did = _upload()
    resp = _start_agent(did)

    assert resp.status_code == 200
    data = resp.json()
    for field in (
        "agent_run_id",
        "agent_state",
        "iteration_summary",
        "workflow_state",
        "next_required_user_action",
        "workflow_response",
    ):
        assert field in data


def test_agent_run_auto_confirm_success_completes_without_user_action():
    did = _upload()
    data = _start_agent(did).json()

    assert data["agent_state"] == "completed"
    assert data["workflow_state"] == "executed"
    assert data["next_required_user_action"] is None
    assert data["iteration_summary"][0]["action"] == "stop_with_result"
    assert data["workflow_response"]["execution_result"]["row_count"] == 2


def test_agent_run_preview_only_requires_confirmation_action():
    did = _upload()
    data = _start_agent(did, auto_confirm=False).json()

    action = data["next_required_user_action"]
    assert data["agent_state"] == "waiting_confirmation"
    assert data["workflow_state"] == "preview_ready"
    assert data["iteration_summary"][0]["action"] == "confirm_required"
    assert action["type"] == "confirm_workflow"
    assert action["endpoint"] == "/api/workflows/confirm"
    assert action["payload"]["dataset_id"] == did
    assert action["payload"]["steps"][0]["type"] == "remove_missing_values"


def test_agent_run_warning_result_requires_confirmation_action():
    did = _upload()
    data = _start_agent(did, steps=MOCK_STEPS_ZERO_MATCH).json()

    assert data["agent_state"] == "waiting_confirmation"
    assert data["workflow_state"] == "warning_review"
    assert data["workflow_response"]["has_warnings"] is True
    assert data["next_required_user_action"]["type"] == "confirm_workflow"


def test_agent_run_missing_column_returns_clarification_action():
    did = _upload()
    with patch("app.api.agent.orchestrator.workflow_planner.plan") as mock_plan:
        resp = client.post(
            "/api/agent/runs",
            json={"dataset_id": did, "query": "filter rows where revenue > 100"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_state"] == "needs_clarification"
    assert data["workflow_state"] == "needs_clarification"
    assert data["iteration_summary"][0]["action"] == "clarify"
    assert data["next_required_user_action"]["type"] == "answer_clarification"
    assert data["next_required_user_action"]["endpoint"].endswith("/continue")
    assert "revenue" in data["next_required_user_action"]["message"]
    mock_plan.assert_not_called()


def test_agent_continue_answers_clarification_and_runs_next_iteration():
    did = _upload()
    first = client.post(
        "/api/agent/runs",
        json={"dataset_id": did, "query": "filter rows where revenue > 100"},
    )
    assert first.status_code == 200
    agent_run_id = first.json()["agent_run_id"]

    with patch("app.api.agent.orchestrator.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY) as mock_plan:
        with patch("app.api.agent.orchestrator.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post(
                f"/api/agent/runs/{agent_run_id}/continue",
                json={"answer": "sales"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_state"] == "completed"
    assert [item["action"] for item in data["iteration_summary"]] == ["clarify", "stop_with_result"]
    planner_query = mock_plan.call_args.kwargs["query"]
    assert "User clarification: sales" in planner_query
    assert data["workflow_response"]["clarification_context"]["status"] == "resolved"


def test_agent_continue_unknown_run_returns_structured_error():
    resp = client.post("/api/agent/runs/not-a-run/continue", json={"answer": "sales"})

    assert resp.status_code == 400
    assert resp.json()["error_code"] == "agent_run_not_found"


def test_agent_cancel_marks_run_cancelled():
    did = _upload()
    first = _start_agent(did, auto_confirm=False)
    agent_run_id = first.json()["agent_run_id"]

    resp = client.post(
        f"/api/agent/runs/{agent_run_id}/cancel",
        json={"reason": "user stopped the run"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_state"] == "cancelled"
    assert data["iteration_summary"][-1]["agent_state"] == "cancelled"
    assert data["iteration_summary"][-1]["stop_reason"] == "user stopped the run"
    assert data["next_required_user_action"] is None


def test_chat_endpoint_remains_legacy_boundary_without_agent_run_id():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post("/api/chat", json={"dataset_id": did, "query": "test"})

    assert resp.status_code == 200
    assert "agent_run_id" not in resp.json()
