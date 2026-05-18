"""Tests for the query type classifier.

LLM path: tested by injecting a mock OpenAI client via the `_client` param.
Fallback path: tested by calling `classify_deterministic()` directly.
Route/tool derivation: tested independently of classification path.
"""
import json
from unittest.mock import MagicMock

import pytest

from app.workflow.planning.query_classifier import (
    classify,
    classify_deterministic,
    _derive_route,
    _selected_tool,
)
from app.workflow.planning.route_decision import RouteDecision

SAMPLE_COLUMNS = ["order_id", "amount", "region", "status", "order_date", "quantity"]


# ---------------------------------------------------------------------------
# Helper to build a mock OpenAI client returning a fixed classification
# ---------------------------------------------------------------------------

def _mock_client(query_type: str, confidence: float = 0.9, reason: str = "test", evidence: list | None = None) -> MagicMock:
    content = json.dumps({
        "query_type": query_type,
        "confidence": confidence,
        "reason": reason,
        "evidence": evidence or [],
    })
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


# ---------------------------------------------------------------------------
# LLM path: classify() with mocked client
# ---------------------------------------------------------------------------


class TestLLMPath:
    def test_ask_mode_returned_for_ask_type(self):
        rd = classify("What columns are in this dataset?", SAMPLE_COLUMNS, _client=_mock_client("ask", 0.9))
        assert rd.query_type == "ask"
        assert rd.route == "ask_mode"

    def test_unsupported_route_for_unsupported_type(self):
        rd = classify("Predict next month sales", SAMPLE_COLUMNS, _client=_mock_client("unsupported_request", 0.95))
        assert rd.route == "unsupported"

    def test_visual_analysis_routes_unsupported(self):
        rd = classify("Plot a bar chart", SAMPLE_COLUMNS, _client=_mock_client("visual_analysis", 0.9))
        assert rd.route == "unsupported"
        assert rd.query_type == "visual_analysis"

    def test_high_confidence_profiling_gets_deterministic_tool(self):
        rd = classify("Profile the amount column", SAMPLE_COLUMNS, _client=_mock_client("profiling", 0.9))
        assert rd.route == "deterministic_tool"
        assert rd.selected_tool == "profile_column"

    def test_low_confidence_profiling_goes_to_llm_planner(self):
        rd = classify("Profile xyz", SAMPLE_COLUMNS, _client=_mock_client("profiling", 0.6))
        assert rd.route == "llm_planner"

    def test_high_confidence_missing_diagnosis_gets_ask_mode(self):
        rd = classify("Detect missing values", SAMPLE_COLUMNS, _client=_mock_client("diagnosis", 0.9))
        assert rd.route == "ask_mode"
        assert rd.selected_tool == "detect_missing_values"

    def test_diagnosis_duplicate_selects_detect_duplicates(self):
        rd = classify("Check for duplicate rows", SAMPLE_COLUMNS, _client=_mock_client("diagnosis", 0.9))
        assert rd.selected_tool == "detect_duplicates"

    def test_high_confidence_comparison_gets_deterministic_tool(self):
        rd = classify("Compare average amount by region", SAMPLE_COLUMNS, _client=_mock_client("comparison", 0.9))
        assert rd.route == "deterministic_tool"
        assert rd.selected_tool == "compare_groups"

    def test_filtering_goes_to_llm_planner(self):
        rd = classify("Filter rows where amount > 1000", SAMPLE_COLUMNS, _client=_mock_client("filtering", 0.85))
        assert rd.route == "llm_planner"

    def test_aggregation_goes_to_llm_planner(self):
        rd = classify("Group by region and sum amount", SAMPLE_COLUMNS, _client=_mock_client("aggregation", 0.85))
        assert rd.route == "llm_planner"

    def test_sorting_goes_to_llm_planner(self):
        rd = classify("Sort by amount descending", SAMPLE_COLUMNS, _client=_mock_client("sorting", 0.85))
        assert rd.route == "llm_planner"

    def test_cleaning_goes_to_llm_planner(self):
        rd = classify("Remove missing values", SAMPLE_COLUMNS, _client=_mock_client("cleaning", 0.85))
        assert rd.route == "llm_planner"

    def test_broad_analysis_goes_to_clarification(self):
        rd = classify("Analyze this data", SAMPLE_COLUMNS, _client=_mock_client("broad_analysis_request", 0.55))
        assert rd.route == "clarification"
        assert rd.query_type == "broad_analysis_request"

    def test_ambiguous_goes_to_clarification(self):
        rd = classify("Do something", SAMPLE_COLUMNS, _client=_mock_client("ambiguous_request", 0.3))
        assert rd.route == "clarification"

    def test_column_evidence_appended_to_evidence(self):
        rd = classify("Profile amount", SAMPLE_COLUMNS, _client=_mock_client("profiling", 0.9, evidence=["profile"]))
        assert "amount" in rd.evidence

    def test_result_is_valid_pydantic_model(self):
        rd = classify("Filter rows where amount > 100", SAMPLE_COLUMNS, _client=_mock_client("filtering", 0.8))
        assert isinstance(rd, RouteDecision)
        assert 0.0 <= rd.confidence <= 1.0

    def test_invalid_query_type_from_llm_becomes_ambiguous(self):
        rd = classify("something", SAMPLE_COLUMNS, _client=_mock_client("totally_made_up_type", 0.9))
        assert rd.query_type == "ambiguous_request"

    def test_llm_failure_falls_back_to_deterministic(self, monkeypatch):
        """When the LLM call raises, classify() falls back without crashing."""
        monkeypatch.setattr("app.core.config.settings.llm_api_key", "fake-key")
        bad_client = MagicMock()
        bad_client.chat.completions.create.side_effect = RuntimeError("network error")
        rd = classify("What columns?", SAMPLE_COLUMNS, _client=bad_client)
        assert isinstance(rd, RouteDecision)
        assert rd.query_type == "ask"

    def test_no_api_key_uses_deterministic(self, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.llm_api_key", "")
        rd = classify("What columns are in this dataset?", SAMPLE_COLUMNS)
        assert rd.query_type == "ask"
        assert rd.route == "ask_mode"

    def test_chinese_query_ask_mode(self):
        rd = classify("这个数据有哪些字段？", SAMPLE_COLUMNS, _client=_mock_client("ask", 0.9))
        assert rd.query_type == "ask"
        assert rd.route == "ask_mode"

    def test_chinese_predict_unsupported(self):
        rd = classify("预测下个月的销售额", SAMPLE_COLUMNS, _client=_mock_client("unsupported_request", 0.95))
        assert rd.route == "unsupported"

    def test_chinese_broad_analysis(self):
        rd = classify("帮我分析一下这个数据", SAMPLE_COLUMNS, _client=_mock_client("broad_analysis_request", 0.55))
        assert rd.route == "clarification"

    def test_confidence_clipped_above_1(self):
        rd = classify("Profile amount", SAMPLE_COLUMNS, _client=_mock_client("profiling", 1.5))
        assert rd.confidence <= 1.0

    def test_confidence_clipped_below_0(self):
        rd = classify("Profile amount", SAMPLE_COLUMNS, _client=_mock_client("profiling", -0.5))
        assert rd.confidence >= 0.0


# ---------------------------------------------------------------------------
# Deterministic fallback: classify_deterministic()
# ---------------------------------------------------------------------------


class TestDeterministicFallback:
    def test_ask_mode(self):
        rd = classify_deterministic("What columns are in this dataset?", SAMPLE_COLUMNS)
        assert rd.query_type == "ask"
        assert rd.route == "ask_mode"

    def test_predict_unsupported(self):
        rd = classify_deterministic("Predict next month sales", SAMPLE_COLUMNS)
        assert rd.route == "unsupported"

    def test_plot_unsupported(self):
        rd = classify_deterministic("Plot a bar chart of amount by region", SAMPLE_COLUMNS)
        assert rd.route == "unsupported"

    def test_profile_column(self):
        rd = classify_deterministic("Profile amount", SAMPLE_COLUMNS)
        assert rd.query_type == "profiling"

    def test_detect_missing(self):
        rd = classify_deterministic("Detect missing values", SAMPLE_COLUMNS)
        assert rd.query_type == "diagnosis"
        assert rd.route == "ask_mode"
        assert rd.selected_tool == "detect_missing_values"

    def test_detect_duplicates(self):
        rd = classify_deterministic("Check for duplicate rows", SAMPLE_COLUMNS)
        assert rd.query_type == "diagnosis"
        assert rd.selected_tool == "detect_duplicates"

    def test_compare_groups(self):
        rd = classify_deterministic("Compare average amount by region", SAMPLE_COLUMNS)
        assert rd.query_type == "comparison"

    def test_group_by_aggregation(self):
        rd = classify_deterministic("Group by region and sum amount", SAMPLE_COLUMNS)
        assert rd.query_type == "aggregation"

    def test_filter_rows(self):
        rd = classify_deterministic("Filter rows where amount > 1000", SAMPLE_COLUMNS)
        assert rd.query_type == "filtering"

    def test_sort_by(self):
        rd = classify_deterministic("Sort by amount descending", SAMPLE_COLUMNS)
        assert rd.query_type == "sorting"

    def test_remove_missing_is_cleaning(self):
        rd = classify_deterministic("Remove missing values", SAMPLE_COLUMNS)
        assert rd.query_type == "cleaning"

    def test_drop_duplicates_is_cleaning(self):
        rd = classify_deterministic("Drop duplicate rows", SAMPLE_COLUMNS)
        assert rd.query_type == "cleaning"

    def test_fill_missing_is_cleaning(self):
        rd = classify_deterministic("Fill missing values with mean", SAMPLE_COLUMNS)
        assert rd.query_type == "cleaning"

    def test_broad_analysis(self):
        rd = classify_deterministic("Analyze this data", SAMPLE_COLUMNS)
        assert rd.query_type == "broad_analysis_request"
        assert rd.route == "clarification"

    def test_chinese_ask(self):
        rd = classify_deterministic("这个数据有哪些字段？", SAMPLE_COLUMNS)
        assert rd.query_type == "ask"

    def test_chinese_missing_values(self):
        rd = classify_deterministic("这个数据有哪些缺失值？", SAMPLE_COLUMNS)
        assert rd.query_type == "diagnosis"
        assert rd.route == "ask_mode"

    def test_chinese_predict(self):
        rd = classify_deterministic("预测下个月的销售额", SAMPLE_COLUMNS)
        assert rd.route == "unsupported"

    def test_chinese_broad_analysis(self):
        rd = classify_deterministic("帮我分析一下这个数据", SAMPLE_COLUMNS)
        assert rd.query_type == "broad_analysis_request"

    def test_empty_query_returns_ambiguous(self):
        rd = classify_deterministic("", SAMPLE_COLUMNS)
        assert rd.query_type == "ambiguous_request"
        assert rd.route == "clarification"

    def test_no_columns_still_works(self):
        rd = classify_deterministic("Show me the schema")
        assert rd.query_type == "ask"

    def test_returns_route_decision_model(self):
        rd = classify_deterministic("Filter rows where amount > 100", SAMPLE_COLUMNS)
        assert isinstance(rd, RouteDecision)
        assert 0.0 <= rd.confidence <= 1.0

    def test_column_match_boosts_confidence(self):
        rd_no_col  = classify_deterministic("Profile xyz_unknown_column", SAMPLE_COLUMNS)
        rd_known   = classify_deterministic("Profile amount", SAMPLE_COLUMNS)
        assert rd_known.confidence >= rd_no_col.confidence


# ---------------------------------------------------------------------------
# Route derivation unit tests (_derive_route)
# ---------------------------------------------------------------------------


class TestDeriveRoute:
    def test_ask_always_ask_mode(self):
        assert _derive_route("ask", 0.3) == "ask_mode"
        assert _derive_route("ask", 0.99) == "ask_mode"

    def test_unsupported_always_unsupported(self):
        assert _derive_route("unsupported_request", 0.95) == "unsupported"

    def test_visual_always_unsupported(self):
        assert _derive_route("visual_analysis", 0.9) == "unsupported"

    def test_broad_always_clarification(self):
        assert _derive_route("broad_analysis_request", 0.9) == "clarification"

    def test_ambiguous_always_clarification(self):
        assert _derive_route("ambiguous_request", 0.8) == "clarification"

    def test_profiling_high_conf_deterministic(self):
        assert _derive_route("profiling", 0.8) == "deterministic_tool"

    def test_profiling_low_conf_llm_planner(self):
        assert _derive_route("profiling", 0.6) == "llm_planner"

    def test_diagnosis_high_conf_deterministic(self):
        assert _derive_route("diagnosis", 0.85) == "deterministic_tool"

    def test_comparison_high_conf_deterministic(self):
        assert _derive_route("comparison", 0.8) == "deterministic_tool"

    def test_filtering_goes_to_llm_planner(self):
        assert _derive_route("filtering", 0.9) == "llm_planner"

    def test_sorting_goes_to_llm_planner(self):
        assert _derive_route("sorting", 0.9) == "llm_planner"

    def test_aggregation_goes_to_llm_planner(self):
        assert _derive_route("aggregation", 0.9) == "llm_planner"

    def test_cleaning_goes_to_llm_planner(self):
        assert _derive_route("cleaning", 0.9) == "llm_planner"

    def test_low_confidence_any_type_clarification(self):
        assert _derive_route("filtering", 0.3) == "clarification"
        assert _derive_route("sorting", 0.4) == "clarification"


# ---------------------------------------------------------------------------
# Tool selection unit tests (_selected_tool)
# ---------------------------------------------------------------------------


class TestSelectedTool:
    def test_profiling_returns_profile_column(self):
        assert _selected_tool("profiling", "profile amount") == "profile_column"

    def test_diagnosis_missing_returns_detect_missing(self):
        assert _selected_tool("diagnosis", "detect missing values") == "detect_missing_values"

    def test_diagnosis_duplicate_returns_detect_duplicates(self):
        assert _selected_tool("diagnosis", "check duplicate rows") == "detect_duplicates"

    def test_comparison_returns_compare_groups(self):
        assert _selected_tool("comparison", "compare amount by region") == "compare_groups"

    def test_filtering_returns_none(self):
        assert _selected_tool("filtering", "filter where amount > 100") is None

    def test_aggregation_returns_none(self):
        assert _selected_tool("aggregation", "group by region") is None
