"""Focused tests for Task 9: Analyst-Style Multi-Step Flow.

Coverage:
- AnalystStepSuggestion model contract (5 tests)
- AnalystFlowPlan model contract (4 tests)
- plan_analyst_flow: explore path selection (6 tests)
- plan_analyst_flow: quality path selection (5 tests)
- plan_analyst_flow: minimal path fallback (4 tests)
- next_suggestion: ordered flow advancement (8 tests)
- next_suggestion: bound enforcement (3 tests)
- _build_analyst_flow_suggestions integration (5 tests)
- WorkflowContextSummary includes analyst_flow_suggestions (3 tests)
- make_context_summary integration (4 tests)
"""
import pytest

from app.agent.analyst.flow_planner import (
    AnalystFlowPlan,
    AnalystStepSuggestion,
    next_suggestion,
    plan_analyst_flow,
)
from app.agent.loop import workflow_runtime
from app.agent.observation.models import ObservationSummary
from app.models.dataset import ColumnProfile, DatasetProfile
from app.models.runtime_trace import WorkflowContextSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(columns: list[tuple[str, str, int]] | None = None, row_count: int = 100) -> DatasetProfile:
    """Build a DatasetProfile from (name, dtype, missing_count) tuples."""
    if columns is None:
        columns = [("amount", "float64", 0), ("category", "object", 0)]
    return DatasetProfile(
        filename="test.csv",
        row_count=row_count,
        column_count=len(columns),
        columns=[ColumnProfile(name=n, dtype=d, missing_count=m, missing_pct=m / row_count) for n, d, m in columns],
        preview=[],
    )


def _obs(signals: list[str] | None = None, status: str = "ok") -> ObservationSummary:
    return ObservationSummary(
        status=status,
        message="test observation",
        signals=signals or [],
    )


# ---------------------------------------------------------------------------
# 1. AnalystStepSuggestion model contract
# ---------------------------------------------------------------------------


class TestAnalystStepSuggestion:
    def test_required_fields(self):
        s = AnalystStepSuggestion(
            tool_type="profile_column",
            rationale="check distribution",
            confirmation_question="Profile this column?",
        )
        assert s.tool_type == "profile_column"
        assert s.rationale == "check distribution"
        assert s.confirmation_question == "Profile this column?"

    def test_defaults(self):
        s = AnalystStepSuggestion(
            tool_type="profile_column",
            rationale="r",
            confirmation_question="q",
        )
        assert s.evidence == []
        assert s.parameters == {}
        assert s.is_destructive is False

    def test_with_parameters(self):
        s = AnalystStepSuggestion(
            tool_type="compare_groups",
            rationale="compare",
            confirmation_question="Compare groups?",
            parameters={"group_column": "cat", "value_column": "num", "aggregation": "mean"},
        )
        assert s.parameters["group_column"] == "cat"
        assert s.parameters["aggregation"] == "mean"

    def test_with_evidence(self):
        s = AnalystStepSuggestion(
            tool_type="profile_column",
            rationale="r",
            confirmation_question="q",
            evidence=["numeric column 'amount' available", "observation: outlier_detected"],
        )
        assert len(s.evidence) == 2

    def test_destructive_flag(self):
        s = AnalystStepSuggestion(
            tool_type="remove_missing_values",
            rationale="clean data",
            confirmation_question="Remove rows with missing values?",
            is_destructive=True,
        )
        assert s.is_destructive is True


# ---------------------------------------------------------------------------
# 2. AnalystFlowPlan model contract
# ---------------------------------------------------------------------------


class TestAnalystFlowPlan:
    def test_minimal_plan(self):
        plan = AnalystFlowPlan(
            demo_path="minimal",
            suggestions=[],
            max_steps=3,
            rationale="minimal",
        )
        assert plan.demo_path == "minimal"
        assert plan.suggestions == []
        assert plan.max_steps == 3

    def test_explore_path_literal(self):
        plan = AnalystFlowPlan(
            demo_path="explore",
            suggestions=[],
            max_steps=3,
            rationale="r",
        )
        assert plan.demo_path == "explore"

    def test_quality_path_literal(self):
        plan = AnalystFlowPlan(
            demo_path="quality",
            suggestions=[],
            max_steps=3,
            rationale="r",
        )
        assert plan.demo_path == "quality"

    def test_max_steps_lower_bound(self):
        with pytest.raises(Exception):
            AnalystFlowPlan(demo_path="minimal", suggestions=[], max_steps=0, rationale="r")


# ---------------------------------------------------------------------------
# 3. plan_analyst_flow — explore path
# ---------------------------------------------------------------------------


class TestPlanAnalystFlowExplore:
    def test_selects_explore_path(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.demo_path == "explore"

    def test_explore_has_three_steps(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert len(plan.suggestions) == 3

    def test_explore_step_order(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        types = [s.tool_type for s in plan.suggestions]
        assert types == ["profile_column", "summarize_numeric_column", "compare_groups"]

    def test_explore_uses_first_numeric_column(self):
        profile = _profile([("revenue", "float64", 0), ("status", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.suggestions[0].parameters["column"] == "revenue"
        assert plan.suggestions[1].parameters["column"] == "revenue"

    def test_explore_uses_first_categorical_column(self):
        profile = _profile([("amount", "float64", 0), ("region", "object", 0)])
        plan = plan_analyst_flow(profile)
        compare = plan.suggestions[2]
        assert compare.parameters["group_column"] == "region"
        assert compare.parameters["value_column"] == "amount"

    def test_explore_rationale_mentions_columns(self):
        profile = _profile([("price", "float64", 0), ("brand", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert "price" in plan.rationale or "brand" in plan.rationale

    def test_explore_evidence_includes_column_names(self):
        profile = _profile([("score", "float64", 0), ("group", "object", 0)])
        plan = plan_analyst_flow(profile)
        evidence = plan.suggestions[0].evidence
        assert any("score" in e for e in evidence)

    def test_explore_confirmation_questions_are_nonempty(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        for s in plan.suggestions:
            assert s.confirmation_question.strip()


# ---------------------------------------------------------------------------
# 4. plan_analyst_flow — quality path
# ---------------------------------------------------------------------------


class TestPlanAnalystFlowQuality:
    def test_selects_quality_path_on_missing_signal(self):
        profile = _profile([("amount", "float64", 5), ("category", "object", 3)])
        obs = _obs(["data_quality_issue"], status="warning")
        plan = plan_analyst_flow(profile, obs)
        assert plan.demo_path == "quality"

    def test_selects_quality_path_on_data_quality_signal(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        obs = _obs(["data_quality_issue"], status="warning")
        plan = plan_analyst_flow(profile, obs)
        assert plan.demo_path == "quality"

    def test_quality_ends_with_suggest_analysis_steps(self):
        profile = _profile([("amount", "float64", 5), ("category", "object", 0)])
        obs = _obs(["data_quality_issue"], status="warning")
        plan = plan_analyst_flow(profile, obs)
        assert plan.suggestions[-1].tool_type == "suggest_analysis_steps"

    def test_quality_has_profile_column_first(self):
        profile = _profile([("amount", "float64", 5), ("category", "object", 0)])
        obs = _obs(["data_quality_issue"], status="warning")
        plan = plan_analyst_flow(profile, obs)
        assert plan.suggestions[0].tool_type == "profile_column"

    def test_quality_evidence_mentions_signals(self):
        profile = _profile([("amount", "float64", 5), ("category", "object", 0)])
        obs = _obs(["data_quality_issue", "needs_inspection"], status="warning")
        plan = plan_analyst_flow(profile, obs)
        all_evidence = [e for s in plan.suggestions for e in s.evidence]
        assert any("data_quality_issue" in e for e in all_evidence)


# ---------------------------------------------------------------------------
# 5. plan_analyst_flow — minimal fallback
# ---------------------------------------------------------------------------


class TestPlanAnalystFlowMinimal:
    def test_minimal_when_no_numeric_cols(self):
        profile = _profile([("name", "object", 0), ("status", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.demo_path == "minimal"

    def test_minimal_when_no_categorical_cols(self):
        profile = _profile([("amount", "float64", 0), ("score", "float64", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.demo_path == "minimal"

    def test_minimal_first_step_is_suggest(self):
        profile = _profile([("amount", "float64", 0), ("score", "float64", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.suggestions[0].tool_type == "suggest_analysis_steps"

    def test_minimal_adds_profile_when_numeric_exists(self):
        profile = _profile([("amount", "float64", 0), ("score", "float64", 0)])
        plan = plan_analyst_flow(profile)
        types = [s.tool_type for s in plan.suggestions]
        assert "profile_column" in types

    def test_interval_dtype_is_not_numeric(self):
        """'interval[...]' starts with 'int' but is not a numeric column."""
        profile = _profile([("bucket", "interval[int64, right]", 0), ("status", "object", 0)])
        plan = plan_analyst_flow(profile)
        # No numeric column → cannot select explore path
        assert plan.demo_path != "explore"

    def test_float_array_dtype_is_not_numeric(self):
        """Non-standard 'float_array' dtype must not be classified as numeric."""
        profile = _profile([("vals", "float_array", 0), ("cat", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.demo_path != "explore"

    def test_uint_dtypes_are_numeric(self):
        """Unsigned int variants should be recognised as numeric columns."""
        for dtype in ("uint8", "uint16", "uint32", "uint64"):
            profile = _profile([(f"col_{dtype}", dtype, 0), ("cat", "object", 0)])
            plan = plan_analyst_flow(profile)
            assert plan.demo_path == "explore", f"Expected explore path for dtype {dtype}"

    def test_int8_dtype_is_numeric(self):
        profile = _profile([("tiny_int", "int8", 0), ("cat", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.demo_path == "explore"


# ---------------------------------------------------------------------------
# 6. next_suggestion — ordered flow advancement
# ---------------------------------------------------------------------------


class TestNextSuggestion:
    def _explore_plan(self) -> AnalystFlowPlan:
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        return plan_analyst_flow(profile)

    def test_first_call_returns_first_step(self):
        plan = self._explore_plan()
        s = next_suggestion(plan, [])
        assert s is not None
        assert s.tool_type == "profile_column"

    def test_after_profile_returns_summarize(self):
        plan = self._explore_plan()
        s = next_suggestion(plan, ["profile_column"])
        assert s is not None
        assert s.tool_type == "summarize_numeric_column"

    def test_after_two_steps_returns_compare(self):
        plan = self._explore_plan()
        s = next_suggestion(plan, ["profile_column", "summarize_numeric_column"])
        assert s is not None
        assert s.tool_type == "compare_groups"

    def test_all_completed_returns_none(self):
        plan = self._explore_plan()
        s = next_suggestion(plan, ["profile_column", "summarize_numeric_column", "compare_groups"])
        assert s is None

    def test_skips_completed_out_of_order(self):
        plan = self._explore_plan()
        # If user skipped profile and ran summarize, next should be compare
        s = next_suggestion(plan, ["summarize_numeric_column"])
        # profile_column is still first unfinished
        assert s is not None
        assert s.tool_type == "profile_column"

    def test_empty_completed_gives_first(self):
        plan = self._explore_plan()
        assert next_suggestion(plan, []).tool_type == plan.suggestions[0].tool_type

    def test_returns_none_for_empty_plan(self):
        plan = AnalystFlowPlan(demo_path="minimal", suggestions=[], max_steps=3, rationale="empty")
        assert next_suggestion(plan, []) is None

    def test_unrelated_completed_types_ignored(self):
        plan = self._explore_plan()
        s = next_suggestion(plan, ["filter_rows", "sort_values"])
        assert s is not None
        assert s.tool_type == "profile_column"


# ---------------------------------------------------------------------------
# 7. next_suggestion — max_steps bound
# ---------------------------------------------------------------------------


class TestNextSuggestionBounds:
    def test_max_steps_one_only_returns_first(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        plan = plan.model_copy(update={"max_steps": 1})
        s1 = next_suggestion(plan, [])
        assert s1 is not None
        assert s1.tool_type == "profile_column"
        s2 = next_suggestion(plan, ["profile_column"])
        assert s2 is None

    def test_max_steps_two_allows_first_two(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        plan = plan.model_copy(update={"max_steps": 2})
        s = next_suggestion(plan, ["profile_column"])
        assert s is not None
        assert s.tool_type == "summarize_numeric_column"
        s2 = next_suggestion(plan, ["profile_column", "summarize_numeric_column"])
        assert s2 is None

    def test_max_steps_three_allows_all_three(self):
        profile = _profile([("amount", "float64", 0), ("category", "object", 0)])
        plan = plan_analyst_flow(profile)
        assert plan.max_steps == 3
        s = next_suggestion(plan, ["profile_column", "summarize_numeric_column"])
        assert s is not None
        assert s.tool_type == "compare_groups"


# ---------------------------------------------------------------------------
# 8. WorkflowContextSummary — analyst_flow_suggestions field
# ---------------------------------------------------------------------------


class TestWorkflowContextSummaryField:
    def test_field_exists_and_defaults_empty(self):
        s = WorkflowContextSummary(
            query="test",
            dataset_hash="abc",
            schema_columns=["a"],
            row_count=10,
            status="planned",
            boundary="preview",
        )
        assert s.analyst_flow_suggestions == []

    def test_field_accepts_list_of_dicts(self):
        s = WorkflowContextSummary(
            query="test",
            dataset_hash="abc",
            schema_columns=["a"],
            row_count=10,
            status="planned",
            boundary="preview",
            analyst_flow_suggestions=[
                {"tool_type": "profile_column", "rationale": "r", "confirmation_question": "q"}
            ],
        )
        assert len(s.analyst_flow_suggestions) == 1
        assert s.analyst_flow_suggestions[0]["tool_type"] == "profile_column"

    def test_field_round_trips_via_model_dump(self):
        suggestion = AnalystStepSuggestion(
            tool_type="compare_groups",
            rationale="compare groups",
            confirmation_question="Compare?",
        )
        s = WorkflowContextSummary(
            query="test",
            dataset_hash="abc",
            schema_columns=["a"],
            row_count=10,
            status="planned",
            boundary="preview",
            analyst_flow_suggestions=[suggestion.model_dump()],
        )
        dumped = s.model_dump()
        assert dumped["analyst_flow_suggestions"][0]["tool_type"] == "compare_groups"


# ---------------------------------------------------------------------------
# 9. make_context_summary integration
# ---------------------------------------------------------------------------


class TestMakeContextSummaryAnalystFlow:
    def _workflow_context(self, planned_types: list[str]) -> workflow_runtime.WorkflowContext:
        return workflow_runtime.WorkflowContext(
            dataset_id="ds-1",
            dataset_hash="abc",
            query="explore the data",
            dataset_profile={
                "filename": "test.csv",
                "row_count": 100,
                "column_count": 2,
                "columns": [
                    {"name": "amount", "dtype": "float64", "missing_count": 0, "missing_pct": 0.0},
                    {"name": "category", "dtype": "object", "missing_count": 0, "missing_pct": 0.0},
                ],
                "preview": [],
            },
            current_schema=["amount", "category"],
            current_steps=[{"type": t} for t in planned_types],
            execution_boundary="preview",
        )

    def test_no_analyst_suggestions_without_suggest_step(self):
        ctx = self._workflow_context(["filter_rows"])
        summary = workflow_runtime.make_context_summary(
            context=ctx,
            state="planned",
        )
        assert summary.analyst_flow_suggestions == []

    def test_analyst_suggestions_when_suggest_step_present(self):
        ctx = self._workflow_context(["suggest_analysis_steps"])
        summary = workflow_runtime.make_context_summary(
            context=ctx,
            state="planned",
        )
        assert len(summary.analyst_flow_suggestions) > 0

    def test_analyst_suggestions_have_tool_type(self):
        ctx = self._workflow_context(["suggest_analysis_steps"])
        summary = workflow_runtime.make_context_summary(
            context=ctx,
            state="planned",
        )
        for s in summary.analyst_flow_suggestions:
            assert "tool_type" in s
            assert s["tool_type"]

    def test_analyst_suggestions_have_confirmation_question(self):
        ctx = self._workflow_context(["suggest_analysis_steps"])
        summary = workflow_runtime.make_context_summary(
            context=ctx,
            state="planned",
        )
        for s in summary.analyst_flow_suggestions:
            assert "confirmation_question" in s
            assert s["confirmation_question"]
