"""Unit tests for app.workflow.planning.workflow_planner.

All tests mock the OpenAI client to avoid real API calls.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ClarificationNeeded, PlannerError
from app.models.dataset import ColumnProfile, DatasetProfile
from app.models.rag import DatasetSummary, RAGContext, RetrievalDebug, RetrievedDoc
from app.workflow.planning.workflow_planner import _build_messages, _parse_steps, plan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CTX = RAGContext(
    query="按地区统计销售额",
    retrieved_docs=[
        RetrievedDoc(
            type="group_by",
            description="Group rows by a column and aggregate a numeric target.",
            keywords=["group", "aggregate", "sum", "分组"],
            parameters=[
                {"name": "column", "type": "str", "required": True, "description": "Group column."},
                {"name": "target", "type": "str", "required": True, "description": "Numeric column."},
                {"name": "agg", "type": "str", "required": True, "description": "Aggregation."},
            ],
            example={"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
            score=3,
        )
    ],
    dataset_summary=DatasetSummary(
        filename="sales.csv",
        row_count=100,
        column_count=2,
        columns=[
            {"name": "region", "dtype": "object", "missing_count": 0, "missing_pct": 0.0},
            {"name": "sales", "dtype": "float64", "missing_count": 0, "missing_pct": 0.0},
        ],
    ),
    debug=RetrievalDebug(
        method="keyword_matching",
        query_tokens=["按地区统计销售额"],
        all_scores={"group_by": 3},
    ),
)


def _make_mock_client(content: str) -> MagicMock:
    """Build a mock OpenAI client that returns the given content string."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# _parse_steps
# ---------------------------------------------------------------------------

def test_parse_steps_valid_group_by():
    raw = json.dumps({"steps": [{"type": "group_by", "column": "region", "target": "sales", "agg": "sum"}]})
    steps = _parse_steps(raw)
    assert len(steps) == 1
    assert steps[0].type == "group_by"


def test_parse_steps_multi_step():
    raw = json.dumps({
        "steps": [
            {"type": "remove_missing_values"},
            {"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
            {"type": "sort_values", "column": "sales", "ascending": False},
        ]
    })
    steps = _parse_steps(raw)
    assert len(steps) == 3
    assert steps[0].type == "remove_missing_values"
    assert steps[2].type == "sort_values"


def test_parse_steps_empty_array_raises():
    raw = json.dumps({"steps": []})
    with pytest.raises(PlannerError, match="cannot be handled"):
        _parse_steps(raw)


def test_parse_steps_invalid_json_raises():
    with pytest.raises(PlannerError, match="invalid JSON"):
        _parse_steps("not json at all")


def test_parse_steps_missing_steps_key_raises():
    with pytest.raises(PlannerError, match="'steps' key"):
        _parse_steps(json.dumps({"result": []}))


def test_parse_steps_steps_not_list_raises():
    with pytest.raises(PlannerError, match="JSON array"):
        _parse_steps(json.dumps({"steps": "remove_missing_values"}))


def test_parse_steps_unknown_type_raises():
    raw = json.dumps({"steps": [{"type": "chart", "column": "sales"}]})
    with pytest.raises(PlannerError, match="invalid step structure"):
        _parse_steps(raw)


def test_parse_steps_missing_required_field_asks_clarification():
    raw = json.dumps({"steps": [{"type": "filter_rows", "column": "sales", "operator": ">"}]})
    with pytest.raises(ClarificationNeeded, match="value"):
        _parse_steps(raw)


# ---------------------------------------------------------------------------
# _build_messages
# ---------------------------------------------------------------------------

def test_build_messages_includes_query():
    messages = _build_messages("按地区统计销售额", SAMPLE_CTX)
    user_content = messages[1]["content"]
    assert "按地区统计销售额" in user_content


def test_build_messages_system_contains_columns():
    messages = _build_messages("test query", SAMPLE_CTX)
    system_content = messages[0]["content"]
    assert "region" in system_content
    assert "sales" in system_content


def test_build_messages_system_contains_doc_type():
    messages = _build_messages("test query", SAMPLE_CTX)
    system_content = messages[0]["content"]
    assert "group_by" in system_content


def test_build_messages_returns_two_messages():
    messages = _build_messages("test", SAMPLE_CTX)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


# ---------------------------------------------------------------------------
# plan — with mocked OpenAI client
# ---------------------------------------------------------------------------

def test_plan_returns_steps_from_llm():
    llm_response = json.dumps({
        "steps": [{"type": "group_by", "column": "region", "target": "sales", "agg": "sum"}]
    })
    mock_client = _make_mock_client(llm_response)

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        steps = plan("按地区统计销售额", SAMPLE_CTX, client=mock_client)

    assert len(steps) == 1
    assert steps[0].type == "group_by"


def test_plan_raises_planner_error_when_llm_returns_empty_steps():
    mock_client = _make_mock_client(json.dumps({"steps": []}))

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        with pytest.raises(PlannerError, match="cannot be handled"):
            plan("画一张图", SAMPLE_CTX, client=mock_client)


def test_plan_raises_planner_error_when_no_api_key():
    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = ""
        with pytest.raises(PlannerError, match="API key"):
            plan("test", SAMPLE_CTX)


def test_plan_raises_planner_error_when_llm_call_fails():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("connection timeout")

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        with pytest.raises(PlannerError, match="API call failed"):
            plan("test", SAMPLE_CTX, client=mock_client)


def test_plan_raises_planner_error_on_empty_choices():
    """Empty choices array must raise PlannerError, not an unhandled IndexError."""
    mock_response = MagicMock()
    mock_response.choices = []
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        with pytest.raises(PlannerError, match="unexpected response structure"):
            plan("test", SAMPLE_CTX, client=mock_client)
