"""Unit and integration tests for app.workflow.response.result_explainer."""
import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.workflow.response.result_explainer import detect_language, explain
from app.models.workflow import (
    ExecutionResult,
    GroupByStep,
    RemoveMissingValuesStep,
    SortValuesStep,
    StepLog,
    StepResult,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_RESULT = ExecutionResult(
    row_count=4,
    column_count=2,
    columns=["region", "sales"],
    preview=[
        {"region": "South", "sales": 7500.0},
        {"region": "West", "sales": 6670.0},
        {"region": "North", "sales": 5400.0},
        {"region": "East", "sales": 4390.0},
    ],
    step_results=[
        StepResult(
            step_index=0,
            step_type="group_by",
            input_row_count=20,
            output_row_count=4,
            input_column_count=4,
            output_column_count=2,
            affected_rate=0.8,
            preview=[
                {"region": "South", "sales": 7500.0},
                {"region": "West", "sales": 6670.0},
                {"region": "North", "sales": 5400.0},
                {"region": "East", "sales": 4390.0},
            ],
            message="Grouped by 'region', aggregated 'sales' with sum.",
        ),
        StepResult(
            step_index=1,
            step_type="sort_values",
            input_row_count=4,
            output_row_count=4,
            input_column_count=2,
            output_column_count=2,
            preview=[
                {"region": "South", "sales": 7500.0},
                {"region": "West", "sales": 6670.0},
                {"region": "North", "sales": 5400.0},
                {"region": "East", "sales": 4390.0},
            ],
            message="Sorted by 'sales' descending.",
        ),
    ],
    logs=[
        StepLog(step_index=0, step_type="group_by", rows_before=20, rows_after=4,
                message="Grouped by 'region', aggregated 'sales' with sum."),
        StepLog(step_index=1, step_type="sort_values", rows_before=4, rows_after=4,
                message="Sorted by 'sales' descending."),
    ],
    has_summary=False,
)

SAMPLE_DATASET_SUMMARY = {
    "filename": "sales.csv",
    "row_count": 20,
    "column_count": 4,
    "columns": [
        {"name": "region", "dtype": "object", "missing_count": 0, "missing_pct": 0.0},
        {"name": "sales", "dtype": "float64", "missing_count": 2, "missing_pct": 10.0},
    ],
}

SAMPLE_STEPS = [
    {"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
    {"type": "sort_values", "column": "sales", "ascending": False},
]


def _make_mock_client(text: str) -> MagicMock:
    mock_message = MagicMock()
    mock_message.content = text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

def test_detect_language_chinese_query():
    assert detect_language("按地区统计销售额") == "Chinese"


def test_detect_language_english_query():
    assert detect_language("group by region and sum sales") == "English"


def test_detect_language_mixed_query_is_chinese():
    assert detect_language("show me 销售额 by region") == "Chinese"


def test_detect_language_empty_query_is_english():
    assert detect_language("") == "English"


def test_detect_language_japanese_is_chinese_family():
    # Japanese hiragana counts as CJK → Chinese branch
    assert detect_language("売上を集計してください") == "Chinese"


# ---------------------------------------------------------------------------
# explain — unit (mock client)
# ---------------------------------------------------------------------------

def test_explain_returns_string():
    mock_client = _make_mock_client("South 地区销售额最高。")
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = "test-key"
        s.llm_model = "gpt-4o-mini"
        s.llm_max_tokens = 512
        result = explain("按地区统计", SAMPLE_STEPS, SAMPLE_RESULT,
                         SAMPLE_DATASET_SUMMARY, client=mock_client)
    assert isinstance(result, str)
    assert len(result) > 0


def test_explain_passes_language_chinese_to_prompt():
    mock_client = _make_mock_client("解释文本")
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = "test-key"
        s.llm_model = "gpt-4o-mini"
        s.llm_max_tokens = 512
        explain("按地区统计", SAMPLE_STEPS, SAMPLE_RESULT,
                SAMPLE_DATASET_SUMMARY, client=mock_client)
    call_args = mock_client.chat.completions.create.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "Chinese" in system_content


def test_explain_passes_language_english_to_prompt():
    mock_client = _make_mock_client("South region has the highest sales.")
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = "test-key"
        s.llm_model = "gpt-4o-mini"
        s.llm_max_tokens = 512
        explain("group by region", SAMPLE_STEPS, SAMPLE_RESULT,
                SAMPLE_DATASET_SUMMARY, client=mock_client)
    call_args = mock_client.chat.completions.create.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "English" in system_content


def test_explain_raises_when_no_api_key():
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = ""
        with pytest.raises(Exception, match="API key"):
            explain("test", SAMPLE_STEPS, SAMPLE_RESULT, SAMPLE_DATASET_SUMMARY)


def test_explain_raises_when_llm_call_fails():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("timeout")
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = "test-key"
        s.llm_model = "gpt-4o-mini"
        s.llm_max_tokens = 512
        with pytest.raises(Exception, match="Explainer LLM API call failed"):
            explain("test", SAMPLE_STEPS, SAMPLE_RESULT,
                    SAMPLE_DATASET_SUMMARY, client=mock_client)


def test_explain_raises_planner_error_on_empty_choices():
    """Empty choices array must raise PlannerError, not an unhandled IndexError."""
    mock_response = MagicMock()
    mock_response.choices = []
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    with patch("app.workflow.response.result_explainer.settings") as s:
        s.llm_api_key = "test-key"
        s.llm_model = "gpt-4o-mini"
        s.llm_max_tokens = 512
        with pytest.raises(Exception, match="unexpected response structure"):
            explain("test", SAMPLE_STEPS, SAMPLE_RESULT,
                    SAMPLE_DATASET_SUMMARY, client=mock_client)


# ---------------------------------------------------------------------------
# chat router integration — explanation field present
# ---------------------------------------------------------------------------

BASE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
    b"South,900,Feb\n"
    b"West,,Feb\n"
)

MOCK_STEPS = [
    RemoveMissingValuesStep(type="remove_missing_values"),
    GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
    SortValuesStep(type="sort_values", column="sales", ascending=False),
]


def _upload() -> str:
    resp = client.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(BASE_CSV), "text/csv")},
    )
    return resp.json()["dataset_id"]


def test_chat_response_includes_explanation_field():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS):
        with patch("app.api.chat.result_explainer.explain", return_value="North 最高。"):
            data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    assert "explanation" in data


def test_chat_explanation_contains_mock_text():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS):
        with patch("app.api.chat.result_explainer.explain", return_value="North 最高。"):
            data = client.post("/api/chat", json={"dataset_id": did, "query": "test"}).json()
    assert data["explanation"] == "North 最高。"


def test_chat_explanation_is_string():
    did = _upload()
    with patch("app.api.chat.workflow_planner.plan", return_value=MOCK_STEPS):
        with patch("app.api.chat.result_explainer.explain",
                   return_value="South region leads with total sales of 1750."):
            data = client.post("/api/chat", json={"dataset_id": did, "query": "sales by region"}).json()
    assert isinstance(data["explanation"], str)
