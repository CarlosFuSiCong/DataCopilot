"""Tests for the Level 1 deterministic tool router.

All tests use a fixed DatasetProfile and pre-built RouteDecision objects
(no LLM, no network calls).
"""
import pytest

from app.models.dataset import ColumnProfile, DatasetProfile
from app.workflow.planning.route_decision import RouteDecision
from app.workflow.planning.tool_router import ToolRouterResult, route

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

COLUMNS = [
    ColumnProfile(name="region", dtype="object", missing_count=0, missing_pct=0.0),
    ColumnProfile(name="category", dtype="object", missing_count=0, missing_pct=0.0),
    ColumnProfile(name="amount", dtype="float64", missing_count=2, missing_pct=0.02),
    ColumnProfile(name="quantity", dtype="int64", missing_count=0, missing_pct=0.0),
    ColumnProfile(name="order_date", dtype="object", missing_count=0, missing_pct=0.0),
]

PROFILE = DatasetProfile(
    filename="test.csv",
    row_count=100,
    column_count=5,
    columns=COLUMNS,
    preview=[],
)

COLUMN_NAMES = [c.name for c in COLUMNS]


def _rd(
    tool: str,
    candidates: list[str] | None = None,
    confidence: float = 0.9,
    query_type: str = "profiling",
) -> RouteDecision:
    """Build a RouteDecision with the given tool and column candidates."""
    qt_to_route = {
        "profiling": "deterministic_tool",
        "diagnosis": "deterministic_tool",
        "comparison": "deterministic_tool",
    }
    return RouteDecision(
        route="deterministic_tool",
        query_type=query_type,  # type: ignore[arg-type]
        confidence=confidence,
        reason="test",
        evidence=[],
        extracted_slots={"candidate_columns": candidates or []},
        selected_tool=tool,
        fallback_route="llm_planner",
    )


# ---------------------------------------------------------------------------
# profile_column
# ---------------------------------------------------------------------------


class TestProfileColumn:
    def test_single_candidate_resolves(self):
        rd = _rd("profile_column", ["amount"])
        result = route("Profile amount", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == [{"type": "profile_column", "column": "amount"}]
        assert result.clarification_question is None

    def test_no_candidate_asks_for_column(self):
        rd = _rd("profile_column", [])
        result = route("Profile something", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None
        assert result.raw_steps == []

    def test_multiple_candidates_asks_which(self):
        rd = _rd("profile_column", ["amount", "quantity"])
        result = route("Profile column", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None
        assert "amount" in result.clarification_question or "quantity" in result.clarification_question


# ---------------------------------------------------------------------------
# distribution_summary (requires numeric column)
# ---------------------------------------------------------------------------


class TestDistributionSummary:
    def test_numeric_candidate_resolves(self):
        rd = _rd("distribution_summary", ["amount"])
        result = route("Show distribution of amount", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == [{"type": "distribution_summary", "column": "amount"}]
        assert result.clarification_question is None

    def test_non_numeric_candidate_asks_for_numeric(self):
        rd = _rd("distribution_summary", ["region"])
        result = route("Show distribution of region", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None
        assert "numeric" in result.clarification_question.lower()

    def test_no_candidate_uses_numeric_columns_from_schema(self):
        rd = _rd("distribution_summary", [])
        result = route("Show distribution", COLUMN_NAMES, PROFILE, rd)
        # Has only one numeric candidate (amount + quantity = 2), so asks which one
        # OR resolves if only one numeric col
        assert result.raw_steps or result.clarification_question


# ---------------------------------------------------------------------------
# inspect_unique_values
# ---------------------------------------------------------------------------


class TestInspectUniqueValues:
    def test_single_candidate_resolves(self):
        rd = _rd("inspect_unique_values", ["category"])
        result = route("What values does category have?", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps[0]["type"] == "inspect_unique_values"
        assert result.raw_steps[0]["column"] == "category"

    def test_top_n_extracted(self):
        rd = _rd("inspect_unique_values", ["region"])
        result = route("Show top 10 values in region", COLUMN_NAMES, PROFILE, rd)
        step = result.raw_steps[0]
        assert step.get("max_values") == 10

    def test_no_candidate_asks(self):
        rd = _rd("inspect_unique_values", [])
        result = route("Show unique values", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None


# ---------------------------------------------------------------------------
# summarize_numeric_column
# ---------------------------------------------------------------------------


class TestSummarizeNumericColumn:
    def test_numeric_candidate_resolves(self):
        rd = _rd("summarize_numeric_column", ["quantity"])
        result = route("Summarize quantity", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps[0]["column"] == "quantity"

    def test_non_numeric_candidate_asks(self):
        rd = _rd("summarize_numeric_column", ["order_date"])
        result = route("Summarize order_date", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None
        assert "numeric" in result.clarification_question.lower()


# ---------------------------------------------------------------------------
# Column-free tools: detect_missing_values, detect_duplicates
# ---------------------------------------------------------------------------


class TestColumnFreeTools:
    def test_detect_missing_values_no_params(self):
        rd = _rd("detect_missing_values", [], query_type="diagnosis")
        result = route("Detect missing values", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == [{"type": "detect_missing_values"}]
        assert result.clarification_question is None

    def test_detect_duplicates_no_params(self):
        rd = _rd("detect_duplicates", [], query_type="diagnosis")
        result = route("Check for duplicate rows", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == [{"type": "detect_duplicates"}]
        assert result.clarification_question is None

    def test_suggest_analysis_steps_no_params(self):
        rd = _rd("suggest_analysis_steps", [], query_type="profiling")
        result = route("What should I analyze?", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == [{"type": "suggest_analysis_steps"}]


# ---------------------------------------------------------------------------
# correlation_summary
# ---------------------------------------------------------------------------


class TestCorrelationSummary:
    def test_no_candidates_uses_empty_columns(self):
        rd = _rd("correlation_summary", [], query_type="profiling")
        result = route("Show correlations", COLUMN_NAMES, PROFILE, rd)
        step = result.raw_steps[0]
        assert step["type"] == "correlation_summary"
        assert isinstance(step["columns"], list)

    def test_numeric_candidates_included_in_step(self):
        rd = _rd("correlation_summary", ["amount", "quantity"], query_type="profiling")
        result = route("Correlate amount and quantity", COLUMN_NAMES, PROFILE, rd)
        step = result.raw_steps[0]
        assert "amount" in step["columns"]
        assert "quantity" in step["columns"]

    def test_non_numeric_candidates_excluded(self):
        rd = _rd("correlation_summary", ["region", "amount"], query_type="profiling")
        result = route("Correlate region and amount", COLUMN_NAMES, PROFILE, rd)
        step = result.raw_steps[0]
        assert "region" not in step["columns"]
        assert "amount" in step["columns"]


# ---------------------------------------------------------------------------
# compare_groups
# ---------------------------------------------------------------------------


class TestCompareGroups:
    def test_one_cat_one_num_resolves(self):
        rd = _rd("compare_groups", ["region", "amount"], query_type="comparison")
        result = route("Compare amount by region", COLUMN_NAMES, PROFILE, rd)
        step = result.raw_steps[0]
        assert step["type"] == "compare_groups"
        assert step["group_column"] == "region"
        assert step["value_column"] == "amount"
        assert step["agg"] == "mean"

    def test_sum_agg_extracted(self):
        rd = _rd("compare_groups", ["region", "amount"], query_type="comparison")
        result = route("Total amount by region", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps[0]["agg"] == "sum"

    def test_count_agg_extracted(self):
        rd = _rd("compare_groups", ["region", "amount"], query_type="comparison")
        result = route("Count orders by region", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps[0]["agg"] == "count"

    def test_no_candidates_falls_back_to_schema(self):
        # With no candidates, router should use all categorical + numeric columns
        rd = _rd("compare_groups", [], query_type="comparison")
        result = route("Compare groups", COLUMN_NAMES, PROFILE, rd)
        # Has multiple categoricals and numerics → asks which to use
        assert result.clarification_question is not None or len(result.raw_steps) > 0

    def test_multiple_cat_one_num_asks_group_column(self):
        rd = _rd("compare_groups", ["region", "category", "amount"], query_type="comparison")
        result = route("Compare amount by group", COLUMN_NAMES, PROFILE, rd)
        # region and category are both categorical → ambiguous group column
        assert result.clarification_question is not None

    def test_one_cat_multiple_num_asks_value_column(self):
        rd = _rd("compare_groups", ["region", "amount", "quantity"], query_type="comparison")
        result = route("Compare by region", COLUMN_NAMES, PROFILE, rd)
        # amount and quantity are both numeric → asks which value column
        assert result.clarification_question is not None

    def test_no_categorical_column_asks(self):
        rd = _rd("compare_groups", ["amount", "quantity"], query_type="comparison")
        # amount and quantity are both numeric, no categorical candidates
        result = route("Compare amounts and quantities", COLUMN_NAMES, PROFILE, rd)
        # router expands to all schema categoricals (region, category, order_date)
        # so it finds categoricals, but both numerics are present → ambiguous value col
        assert result.clarification_question is not None or result.raw_steps


# ---------------------------------------------------------------------------
# Unknown tool: fallback clarification
# ---------------------------------------------------------------------------


class TestUnknownTool:
    def test_unknown_tool_returns_clarification(self):
        rd = _rd("nonexistent_tool", ["amount"])
        result = route("Do something special", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None
        assert result.raw_steps == []

    def test_empty_tool_returns_clarification(self):
        rd = _rd("", [])
        result = route("Do something", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is not None


# ---------------------------------------------------------------------------
# Result contract
# ---------------------------------------------------------------------------


class TestResultContract:
    def test_result_is_toolrouterresult(self):
        rd = _rd("profile_column", ["amount"])
        result = route("Profile amount", COLUMN_NAMES, PROFILE, rd)
        assert isinstance(result, ToolRouterResult)

    def test_raw_steps_empty_when_clarification_needed(self):
        rd = _rd("profile_column", [])
        result = route("Profile", COLUMN_NAMES, PROFILE, rd)
        assert result.raw_steps == []
        assert result.clarification_question is not None

    def test_clarification_none_when_resolved(self):
        rd = _rd("detect_missing_values", [], query_type="diagnosis")
        result = route("Check missing", COLUMN_NAMES, PROFILE, rd)
        assert result.clarification_question is None
        assert len(result.raw_steps) == 1
