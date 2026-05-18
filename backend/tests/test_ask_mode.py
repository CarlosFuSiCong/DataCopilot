"""Tests for Ask Mode and the Tool Policy matrix.

Coverage:
  - tool_policy: is_read_only, can_run_in_ask_mode, requires_confirm, all_read_only
  - _ask_mode_sub_type: correct classification of schema/column/dataset queries
  - _ask_mode_response: schema_overview, column_detail, dataset_overview content
  - ChatResponse: new fields is_read_only, evidence_source, ask_mode_type
"""
import pytest

from app.workflow.policy.tool_policy import (
    all_read_only,
    can_run_in_ask_mode,
    get_tool_kind,
    is_read_only,
    requires_confirm,
)
from app.workflow.service_response import _ask_mode_response, _ask_mode_sub_type
from app.models.chat import ChatRequest, ChatResponse
from app.models.dataset import DatasetProfile, ColumnProfile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_profile() -> DatasetProfile:
    return DatasetProfile(
        filename="test.csv",
        row_count=200,
        column_count=3,
        columns=[
            ColumnProfile(name="amount", dtype="float64", missing_count=0, missing_pct=0.0),
            ColumnProfile(name="region", dtype="object", missing_count=5, missing_pct=2.5),
            ColumnProfile(name="order_date", dtype="datetime64[ns]", missing_count=0, missing_pct=0.0),
        ],
        preview=[],
    )


def _make_request(query: str) -> ChatRequest:
    return ChatRequest(dataset_id="ds-1", query=query)


# ---------------------------------------------------------------------------
# Tool Policy Matrix
# ---------------------------------------------------------------------------

class TestToolPolicyReadOnly:
    """Read-only tools must be classified as read_only."""

    @pytest.mark.parametrize("tool", [
        "profile_column",
        "distribution_summary",
        "compare_groups",
        "detect_missing_values",
        "detect_duplicates",
        "correlation_summary",
        "inspect_unique_values",
        "summarize_numeric_column",
        "suggest_analysis_steps",
    ])
    def test_is_read_only_true(self, tool):
        assert is_read_only(tool) is True

    @pytest.mark.parametrize("tool", [
        "profile_column",
        "distribution_summary",
        "inspect_unique_values",
    ])
    def test_can_run_in_ask_mode_true(self, tool):
        assert can_run_in_ask_mode(tool) is True

    @pytest.mark.parametrize("tool", [
        "profile_column",
        "correlation_summary",
        "detect_duplicates",
    ])
    def test_requires_confirm_false(self, tool):
        assert requires_confirm(tool) is False


class TestToolPolicyMutating:
    """Mutating tools must require confirmation."""

    @pytest.mark.parametrize("tool", [
        "filter_rows",
        "select_columns",
        "group_by",
        "sort_values",
        "rename_columns",
        "remove_missing_values",
        "fill_missing_values",
        "drop_columns",
        "derive_column",
        "date_extract",
        "limit_rows",
        "generate_summary",
        "pivot_table",
        "trim_text",
        "extract_text",
        "date_diff",
        "cast_column",
        "replace_values",
        "remove_duplicates",
    ])
    def test_is_read_only_false(self, tool):
        assert is_read_only(tool) is False

    @pytest.mark.parametrize("tool", [
        "filter_rows",
        "group_by",
        "sort_values",
    ])
    def test_requires_confirm_true(self, tool):
        assert requires_confirm(tool) is True

    @pytest.mark.parametrize("tool", [
        "filter_rows",
        "sort_values",
    ])
    def test_can_run_in_ask_mode_false(self, tool):
        assert can_run_in_ask_mode(tool) is False


class TestToolPolicyGetKind:
    def test_known_read_only(self):
        assert get_tool_kind("profile_column") == "read_only"

    def test_known_mutating(self):
        assert get_tool_kind("filter_rows") == "mutating"

    def test_unknown_tool_defaults_to_mutating(self):
        assert get_tool_kind("nonexistent_tool") == "mutating"


class TestAllReadOnly:
    def test_empty_list_returns_false(self):
        assert all_read_only([]) is False

    def test_all_read_only(self):
        assert all_read_only(["profile_column", "distribution_summary"]) is True

    def test_mixed_returns_false(self):
        assert all_read_only(["profile_column", "filter_rows"]) is False

    def test_single_mutating_returns_false(self):
        assert all_read_only(["sort_values"]) is False

    def test_single_read_only_returns_true(self):
        assert all_read_only(["detect_duplicates"]) is True


# ---------------------------------------------------------------------------
# Ask Mode Sub-type Detection
# ---------------------------------------------------------------------------

class TestAskModeSubType:
    COLUMN_NAMES = ["amount", "region", "order_date"]

    def test_schema_overview_no_column_mentioned(self):
        # "dataset" keyword triggers dataset_overview, which still shows column list
        assert _ask_mode_sub_type("What columns are in this dataset?", self.COLUMN_NAMES) == "dataset_overview"

    def test_schema_overview_list_columns(self):
        assert _ask_mode_sub_type("Show me all the columns", self.COLUMN_NAMES) == "schema_overview"

    def test_column_detail_when_column_mentioned(self):
        assert _ask_mode_sub_type("Tell me about the amount column", self.COLUMN_NAMES) == "column_detail"

    def test_column_detail_any_column_match(self):
        assert _ask_mode_sub_type("What is the dtype of region?", self.COLUMN_NAMES) == "column_detail"

    def test_dataset_overview_how_many_rows(self):
        assert _ask_mode_sub_type("How many rows does this dataset have?", self.COLUMN_NAMES) == "dataset_overview"

    def test_dataset_overview_keyword(self):
        assert _ask_mode_sub_type("Give me an overview of this dataset", self.COLUMN_NAMES) == "dataset_overview"

    def test_dataset_overview_describe(self):
        assert _ask_mode_sub_type("Describe this dataset", self.COLUMN_NAMES) == "dataset_overview"

    def test_missing_value_check(self):
        assert _ask_mode_sub_type("Check for missing values", self.COLUMN_NAMES) == "missing_values"


# ---------------------------------------------------------------------------
# Ask Mode Response Content
# ---------------------------------------------------------------------------

class TestAskModeResponse:
    def _call(self, query: str) -> ChatResponse:
        return _ask_mode_response(
            request=_make_request(query),
            dataset_profile=_make_profile(),
            column_names=["amount", "region", "order_date"],
            route_decision=None,
        )

    def test_schema_overview_contains_column_names(self):
        resp = self._call("What columns are in this dataset?")
        assert "amount" in resp.explanation
        assert "region" in resp.explanation
        assert "order_date" in resp.explanation

    def test_schema_overview_contains_row_count(self):
        resp = self._call("What columns are there?")
        assert "200" in resp.explanation

    def test_schema_overview_has_correct_fields(self):
        resp = self._call("List the columns")
        assert resp.is_read_only is True
        assert resp.ask_mode_type == "schema_overview"
        assert resp.evidence_source == "schema"
        assert resp.planned_steps == []
        assert resp.state == "executed"
        assert resp.needs_clarification is False

    def test_column_detail_contains_dtype(self):
        resp = self._call("What is the dtype of the amount column?")
        assert resp.ask_mode_type == "column_detail"
        assert "float64" in resp.explanation
        assert "amount" in resp.explanation

    def test_column_detail_shows_missing(self):
        resp = self._call("Tell me about the region column")
        assert "region" in resp.explanation
        assert "5" in resp.explanation  # missing_count

    def test_dataset_overview_shows_row_and_column_count(self):
        resp = self._call("How many rows does this dataset have?")
        assert resp.ask_mode_type == "dataset_overview"
        assert "200" in resp.explanation
        assert "3" in resp.explanation  # column count

    def test_missing_value_answer_is_read_only(self):
        resp = self._call("Check for missing values")
        assert resp.ask_mode_type == "missing_values"
        assert resp.is_read_only is True
        assert resp.execution_result is None
        assert resp.planned_steps == []
        assert "region: 5 missing (2.5%)" in resp.explanation
        assert "did not modify the dataset" in resp.explanation

    def test_response_has_rag_context(self):
        resp = self._call("What columns are in this dataset?")
        assert resp.rag_context is not None
        assert resp.rag_context.debug.method == "ask_mode"

    def test_no_run_id(self):
        resp = self._call("Describe this dataset")
        assert resp.run_id is None

    def test_no_execution_result(self):
        resp = self._call("What columns exist?")
        assert resp.execution_result is None

    def test_missing_column_in_query_reports_not_found(self):
        resp = self._call("Tell me about the nonexistent column")
        # "nonexistent" is not in column names so it falls back to schema_overview
        assert resp.ask_mode_type == "schema_overview"


# ---------------------------------------------------------------------------
# ChatResponse new fields default values
# ---------------------------------------------------------------------------

class TestChatResponseNewFields:
    def test_is_read_only_defaults_false(self):
        from app.models.rag import RAGContext, DatasetSummary, RetrievalDebug
        rag = RAGContext(
            query="q",
            retrieved_docs=[],
            dataset_summary=DatasetSummary(filename="f", row_count=1, column_count=1, columns=[]),
            debug=RetrievalDebug(method="m", query_tokens=[], all_scores={}),
        )
        resp = ChatResponse(
            query="q", planned_steps=[], step_results=[],
            has_warnings=False, has_errors=False, rag_context=rag,
        )
        assert resp.is_read_only is False
        assert resp.evidence_source is None
        assert resp.ask_mode_type is None
