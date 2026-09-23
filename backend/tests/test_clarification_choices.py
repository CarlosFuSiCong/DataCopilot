"""Tests for productized clarification: types, choices, and ChatResponse fields."""
import pytest

from app.models.clarification_context import (
    ClarificationChoice,
    ClarificationContext,
    ambiguous_request_question,
    broad_analysis_choices,
    new_pending_context,
)
from app.models.chat import ChatResponse
from app.models.dataset import ColumnProfile, DatasetProfile
from app.models.rag import RAGContext, DatasetSummary, RetrievalDebug


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(columns: list[tuple[str, str, int]]) -> DatasetProfile:
    """Build a minimal DatasetProfile from (name, dtype, missing_count) tuples."""
    return DatasetProfile(
        filename="test.csv",
        row_count=1000,
        column_count=len(columns),
        columns=[
            ColumnProfile(name=n, dtype=d, missing_count=m, missing_pct=m / 10.0)
            for n, d, m in columns
        ],
        preview=[],
    )


def _make_rag_ctx() -> RAGContext:
    return RAGContext(
        query="test",
        retrieved_docs=[],
        dataset_summary=DatasetSummary(
            filename="test.csv",
            row_count=100,
            column_count=2,
            columns=[{"name": "a", "dtype": "object", "missing_count": 0, "missing_pct": 0.0}],
        ),
        debug=RetrievalDebug(method="test", query_tokens=[], all_scores={}),
    )


_MIXED_PROFILE = _make_profile([
    ("region", "object", 0),
    ("amount", "float64", 5),
    ("quantity", "int64", 0),
    ("category", "object", 2),
])

_NUMERIC_ONLY_PROFILE = _make_profile([
    ("revenue", "float64", 0),
    ("cost", "int64", 3),
])

_CATEGORICAL_ONLY_PROFILE = _make_profile([
    ("status", "object", 0),
    ("country", "object", 1),
])


# ---------------------------------------------------------------------------
# ClarificationType enum
# ---------------------------------------------------------------------------

class TestClarificationType:
    def test_broad_analysis_request_is_valid(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="Analyse my data",
            question="What would you like to analyse?",
            clarification_type="broad_analysis_request",
        )
        assert ctx.clarification_type == "broad_analysis_request"

    def test_missing_column_is_valid(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="filter revenue > 100",
            question="revenue is not a column here. Which column did you mean?",
            clarification_type="missing_column",
            affected_step={"type": "filter_rows", "column": "revenue"},
        )
        assert ctx.clarification_type == "missing_column"
        assert ctx.affected_step["column"] == "revenue"

    def test_unsupported_operation_is_valid(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="Predict sales",
            question="Prediction is not supported.",
            clarification_type="unsupported_operation",
        )
        assert ctx.clarification_type == "unsupported_operation"

    def test_planning_is_valid_legacy_type(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="do something",
            question="What do you want?",
            clarification_type="planning",
        )
        assert ctx.clarification_type == "planning"

    def test_clarification_type_defaults_to_none(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="query",
            question="question",
        )
        assert ctx.clarification_type is None


# ---------------------------------------------------------------------------
# ClarificationContext.choices field
# ---------------------------------------------------------------------------

class TestClarificationContextChoices:
    def test_choices_stored_in_context(self):
        choices = [
            {"id": "missing_values", "label": "Check for missing values",
             "description": "...", "query": "Check for missing values", "tool": "detect_missing_values"},
        ]
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="Analyse my data",
            question="Pick a direction",
            clarification_type="broad_analysis_request",
            choices=choices,
        )
        assert ctx.choices is not None
        assert len(ctx.choices) == 1
        assert ctx.choices[0]["id"] == "missing_values"

    def test_choices_defaults_to_none(self):
        ctx = new_pending_context(
            dataset_id="d1",
            original_query="query",
            question="question",
        )
        assert ctx.choices is None


# ---------------------------------------------------------------------------
# broad_analysis_choices()
# ---------------------------------------------------------------------------

class TestBroadAnalysisChoices:
    def test_always_includes_missing_values(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        ids = [c["id"] for c in choices]
        assert "missing_values" in ids

    def test_always_includes_duplicate_rows(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        ids = [c["id"] for c in choices]
        assert "duplicate_rows" in ids

    def test_includes_numeric_profile_when_numeric_cols_exist(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        ids = [c["id"] for c in choices]
        assert "profile_numeric" in ids

    def test_includes_compare_groups_when_categorical_and_numeric(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        ids = [c["id"] for c in choices]
        assert "compare_groups" in ids

    def test_includes_correlation_when_two_or_more_numeric(self):
        choices = broad_analysis_choices(["revenue", "cost"], _NUMERIC_ONLY_PROFILE)
        ids = [c["id"] for c in choices]
        assert "correlation" in ids

    def test_no_profile_numeric_for_categorical_only_dataset(self):
        choices = broad_analysis_choices(["status", "country"], _CATEGORICAL_ONLY_PROFILE)
        ids = [c["id"] for c in choices]
        assert "profile_numeric" not in ids

    def test_no_compare_groups_for_numeric_only_dataset(self):
        choices = broad_analysis_choices(["revenue", "cost"], _NUMERIC_ONLY_PROFILE)
        ids = [c["id"] for c in choices]
        assert "compare_groups" not in ids

    def test_maximum_five_choices_returned(self):
        choices = broad_analysis_choices(
            ["region", "amount", "quantity", "category"],
            _MIXED_PROFILE,
        )
        assert len(choices) <= 5

    def test_each_choice_has_required_fields(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        for choice in choices:
            assert "id" in choice
            assert "label" in choice
            assert "description" in choice
            assert "query" in choice
            assert "tool" in choice

    def test_missing_column_count_shown_in_label(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        mv = next(c for c in choices if c["id"] == "missing_values")
        assert "affected" in mv["label"] or "missing" in mv["label"].lower()

    def test_choices_use_first_numeric_column_in_profile_label(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        profile_choice = next(c for c in choices if c["id"] == "profile_numeric")
        assert "amount" in profile_choice["label"]

    def test_compare_groups_references_both_columns(self):
        choices = broad_analysis_choices(["region", "amount"], _MIXED_PROFILE)
        cg = next(c for c in choices if c["id"] == "compare_groups")
        assert "amount" in cg["label"]
        assert "region" in cg["label"]


# ---------------------------------------------------------------------------
# ambiguous_request_question()
# ---------------------------------------------------------------------------

class TestAmbiguousRequestQuestion:
    def test_question_contains_example_operations(self):
        question = ambiguous_request_question(["region", "amount"])
        assert "Filter" in question or "filter" in question.lower()

    def test_question_lists_available_columns(self):
        question = ambiguous_request_question(["region", "amount"])
        assert "region" in question
        assert "amount" in question

    def test_question_truncates_long_column_list(self):
        columns = [f"col_{i}" for i in range(20)]
        question = ambiguous_request_question(columns)
        # Only first 6 are shown
        for col in columns[:6]:
            assert col in question
        # Not all 20 are expected to appear
        assert "..." in question

    def test_question_returns_string(self):
        question = ambiguous_request_question(["a", "b", "c"])
        assert isinstance(question, str)
        assert len(question) > 10


# ---------------------------------------------------------------------------
# ChatResponse.clarification_choices field
# ---------------------------------------------------------------------------

class TestChatResponseClarificationChoices:
    def test_clarification_choices_defaults_to_none(self):
        resp = ChatResponse(
            query="q",
            planned_steps=[],
            step_results=[],
            has_warnings=False,
            has_errors=False,
            rag_context=_make_rag_ctx(),
            explanation=None,
            execution_result=None,
        )
        assert resp.clarification_choices is None

    def test_clarification_choices_accepts_list(self):
        choices = [
            {"id": "missing_values", "label": "Check for missing values",
             "description": "desc", "query": "Check for missing values", "tool": "detect_missing_values"},
        ]
        resp = ChatResponse(
            query="q",
            planned_steps=[],
            step_results=[],
            has_warnings=False,
            has_errors=False,
            rag_context=_make_rag_ctx(),
            explanation=None,
            execution_result=None,
            clarification_choices=choices,
        )
        assert resp.clarification_choices is not None
        assert len(resp.clarification_choices) == 1
        assert resp.clarification_choices[0]["id"] == "missing_values"


# ---------------------------------------------------------------------------
# ClarificationChoice Pydantic model
# ---------------------------------------------------------------------------

class TestClarificationChoiceModel:
    def test_valid_choice(self):
        c = ClarificationChoice(
            id="missing_values",
            label="Check for missing values",
            description="Find columns with missing data.",
            query="Check for missing values",
            tool="detect_missing_values",
        )
        assert c.id == "missing_values"
        assert c.tool == "detect_missing_values"

    def test_tool_is_optional(self):
        c = ClarificationChoice(
            id="explore",
            label="Explore the data",
            description="Open-ended exploration.",
            query="Explore the data",
        )
        assert c.tool is None
