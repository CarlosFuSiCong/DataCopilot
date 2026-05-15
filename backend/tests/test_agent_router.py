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
        "agent_trace_summary",
        "agent_trace",
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
    assert data["agent_trace"] is None
    assert data["agent_trace_summary"]["state"] == "completed"
    assert data["agent_trace_summary"]["iteration_count"] == 1
    assert data["iteration_summary"][0]["action"] == "stop_with_result"
    assert data["workflow_response"]["execution_result"]["row_count"] == 2


def test_agent_run_can_expand_full_agent_trace_without_raw_dataset_rows():
    did = _upload()
    with patch("app.api.agent.orchestrator.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        with patch("app.api.agent.orchestrator.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post(
                "/api/agent/runs?include_trace=true",
                json={"dataset_id": did, "query": "按地区统计销售额"},
            )

    assert resp.status_code == 200
    data = resp.json()
    trace = data["agent_trace"]
    iteration = trace["iterations"][0]
    assert trace["summary"] == data["agent_trace_summary"]
    assert iteration["input"]["workflow_context_summary"]["schema_columns"] == ["region", "sales", "month"]
    assert iteration["decision"]["decision"] == "stop_with_result"
    assert iteration["action"]["type"] == "stop_with_result"
    assert iteration["validation"]["status"] == "passed"
    assert iteration["observation"]["status"] in {"ok", "warning"}
    assert iteration["observation"]["message"]
    assert iteration["stop_reason"] == "Workflow completed successfully."
    assert "preview" not in str(iteration["input"])


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
    assert data["agent_trace_summary"]["state"] == "cancelled"
    assert data["agent_trace_summary"]["last_action"] == "stop_with_error"
    assert data["next_required_user_action"] is None


def test_agent_cancel_iteration_summaries_do_not_raise_index_error():
    """Regression: cancel appends a synthetic iteration with no corresponding event.

    Before the fix, _iteration_summaries used object equality to detect the
    cancel iteration and fell back to record.events[index] for all others.
    This is safe when object equality works, but fragile.  The fix uses index
    bounds checking instead.  This test confirms that:
    - All non-cancel iterations resolve agent_state from the event.
    - The cancel iteration resolves agent_state from agent_trace.state.
    - No IndexError is raised.
    """
    did = _upload()
    first = _start_agent(did, auto_confirm=False)
    agent_run_id = first.json()["agent_run_id"]

    resp = client.post(
        f"/api/agent/runs/{agent_run_id}/cancel",
        json={"reason": "regression test cancel"},
    )

    assert resp.status_code == 200
    data = resp.json()
    summaries = data["iteration_summary"]

    # There should be at least 2 entries: the real event + the cancel iteration.
    assert len(summaries) >= 2

    # Every non-last entry must not have the cancelled state.
    for entry in summaries[:-1]:
        assert entry["agent_state"] != "cancelled"

    # The last entry (the cancel iteration) must be cancelled.
    assert summaries[-1]["agent_state"] == "cancelled"
    assert summaries[-1]["stop_reason"] == "regression test cancel"
    # The cancel iteration has no corresponding workflow event so workflow_state is None.
    assert summaries[-1]["workflow_state"] is None


def test_chat_endpoint_remains_legacy_boundary_without_agent_run_id():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS_GROUP_BY):
        with patch("app.api.chat.result_explainer.explain", return_value=_MOCK_EXPLANATION):
            resp = client.post("/api/chat", json={"dataset_id": did, "query": "test"})

    assert resp.status_code == 200
    assert "agent_run_id" not in resp.json()
