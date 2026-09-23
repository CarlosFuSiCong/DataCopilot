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


def test_plan_adds_descending_sort_for_total_by_group():
    llm_response = json.dumps({
        "steps": [{"type": "group_by", "column": "region", "target": "sales", "agg": "sum"}]
    })
    mock_client = _make_mock_client(llm_response)

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        steps = plan("Calculate total sales by region", SAMPLE_CTX, client=mock_client)

    assert [step.type for step in steps] == ["group_by", "sort_values"]
    assert steps[1].column == "sales"
    assert steps[1].ascending is False


def test_plan_does_not_duplicate_existing_aggregate_sort():
    llm_response = json.dumps({
        "steps": [
            {"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
            {"type": "sort_values", "column": "sales", "ascending": False},
        ]
    })
    mock_client = _make_mock_client(llm_response)

    with patch("app.workflow.planning.workflow_planner.settings") as mock_settings:
        mock_settings.llm_api_key = "test-key"
        mock_settings.llm_model = "gpt-4o-mini"
        mock_settings.llm_max_tokens = 512
        steps = plan("Calculate total sales by region", SAMPLE_CTX, client=mock_client)

    assert [step.type for step in steps] == ["group_by", "sort_values"]


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


# ---------------------------------------------------------------------------
# Focused planner tests: pivot_table, trim_text, extract_text, date_diff
# ---------------------------------------------------------------------------


class TestComplexToolParsing:
    """Verify _parse_steps handles complex transformation types correctly.

    These tests cover the contract between the LLM output and the step models:
    valid responses parse cleanly; missing required fields raise ClarificationNeeded
    rather than an opaque PlannerError.
    """

    # --- pivot_table ---

    def test_parse_valid_pivot_table(self):
        raw = json.dumps({"steps": [
            {"type": "pivot_table", "index": ["region"], "values": "amount", "agg": "sum"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "pivot_table"

    def test_parse_pivot_table_with_columns_field(self):
        raw = json.dumps({"steps": [
            {"type": "pivot_table", "index": ["region"], "columns": "category", "values": "amount", "agg": "mean"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "pivot_table"

    def test_parse_pivot_table_normalizes_column_and_target_aliases(self):
        raw = json.dumps({"steps": [
            {"type": "pivot_table", "column": "region", "columns": "category", "target": "amount", "agg": "sum"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "pivot_table"
        assert steps[0].index == ["region"]
        assert steps[0].values == "amount"

    def test_parse_pivot_table_normalizes_rows_and_value_column_aliases(self):
        raw = json.dumps({"steps": [
            {"type": "pivot_table", "rows": "region", "columns": "category", "value_column": "amount", "agg": "sum"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "pivot_table"
        assert steps[0].index == ["region"]
        assert steps[0].values == "amount"

    def test_parse_pivot_table_normalizes_params_wrapper(self):
        raw = json.dumps({"steps": [
            {"type": "pivot_table", "params": {"index": ["region"], "columns": "category", "values": "amount", "agg": "sum"}}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "pivot_table"
        assert steps[0].index == ["region"]
        assert steps[0].columns == "category"
        assert steps[0].values == "amount"

    def test_pivot_table_missing_index_asks_clarification(self):
        raw = json.dumps({"steps": [{"type": "pivot_table", "values": "amount", "agg": "sum"}]})
        with pytest.raises(ClarificationNeeded, match="index"):
            _parse_steps(raw)

    def test_pivot_table_missing_values_asks_clarification(self):
        raw = json.dumps({"steps": [{"type": "pivot_table", "index": ["region"], "agg": "sum"}]})
        with pytest.raises(ClarificationNeeded, match="values"):
            _parse_steps(raw)

    def test_pivot_table_missing_agg_asks_clarification(self):
        raw = json.dumps({"steps": [{"type": "pivot_table", "index": ["region"], "values": "amount"}]})
        with pytest.raises(ClarificationNeeded, match="agg"):
            _parse_steps(raw)

    # --- trim_text ---

    def test_parse_valid_trim_text(self):
        raw = json.dumps({"steps": [{"type": "trim_text", "column": "customer_name"}]})
        steps = _parse_steps(raw)
        assert steps[0].type == "trim_text"

    def test_parse_trim_text_with_collapse_whitespace(self):
        raw = json.dumps({"steps": [{"type": "trim_text", "column": "notes", "collapse_whitespace": True}]})
        steps = _parse_steps(raw)
        assert steps[0].type == "trim_text"

    def test_trim_text_missing_column_asks_clarification(self):
        raw = json.dumps({"steps": [{"type": "trim_text"}]})
        with pytest.raises(ClarificationNeeded, match="column"):
            _parse_steps(raw)

    # --- extract_text ---

    def test_parse_valid_extract_text(self):
        raw = json.dumps({"steps": [
            {"type": "extract_text", "column": "order_code", "pattern": r"([A-Z]+)-\d+",
             "new_column": "order_prefix"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "extract_text"

    def test_extract_text_missing_pattern_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "extract_text", "column": "order_code", "new_column": "order_prefix"}
        ]})
        with pytest.raises(ClarificationNeeded, match="pattern"):
            _parse_steps(raw)

    def test_extract_text_missing_new_column_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "extract_text", "column": "order_code", "pattern": r"(\d+)"}
        ]})
        with pytest.raises(ClarificationNeeded, match="new_column"):
            _parse_steps(raw)

    def test_extract_text_missing_column_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "extract_text", "pattern": r"(\d+)", "new_column": "num"}
        ]})
        with pytest.raises(ClarificationNeeded, match="column"):
            _parse_steps(raw)

    # --- date_diff ---

    def test_parse_valid_date_diff(self):
        raw = json.dumps({"steps": [
            {"type": "date_diff", "start_column": "order_date",
             "end_column": "ship_date", "new_column": "ship_days"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "date_diff"

    def test_parse_date_diff_with_unit_and_errors(self):
        raw = json.dumps({"steps": [
            {"type": "date_diff", "start_column": "order_date", "end_column": "ship_date",
             "new_column": "ship_days", "unit": "days", "errors": "coerce"}
        ]})
        steps = _parse_steps(raw)
        assert steps[0].type == "date_diff"

    def test_date_diff_missing_start_column_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "date_diff", "end_column": "ship_date", "new_column": "ship_days"}
        ]})
        with pytest.raises(ClarificationNeeded, match="start_column"):
            _parse_steps(raw)

    def test_date_diff_missing_end_column_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "date_diff", "start_column": "order_date", "new_column": "ship_days"}
        ]})
        with pytest.raises(ClarificationNeeded, match="end_column"):
            _parse_steps(raw)

    def test_date_diff_missing_new_column_asks_clarification(self):
        raw = json.dumps({"steps": [
            {"type": "date_diff", "start_column": "order_date", "end_column": "ship_date"}
        ]})
        with pytest.raises(ClarificationNeeded, match="new_column"):
            _parse_steps(raw)
