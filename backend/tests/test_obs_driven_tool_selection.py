"""Focused tests for Task 8: Observation-Driven Tool Selection.

Covers:
- ObservationToolSuggestion model contract.
- suggest_tools_from_observation: each signal maps to correct tools.
- No duplicate tools in suggestions (first signal wins).
- select_tools with observation: observation tools appear in candidates.
- Observation bonus lifts suggested tools above no-RAG baseline.
- Observation bonus stacks on top of existing RAG + intent scores.
- Exploratory-intent observation (needs_inspection) surfaces suggest_analysis_steps.
- Empty signals produce no suggestions.
- tool_suggestions written to WorkflowContextSummary trace.
- Existing select_tools behavior unchanged when observation=None.
"""
import pytest

from app.agent.observation.models import ObservationSummary
from app.agent.planning.pipeline_models import ObservationToolSuggestion, ToolSelectionResult
from app.agent.planning.tool_selector import (
    _OBS_BONUS,
    _SIGNAL_TOOL_MAP,
    select_tools,
    suggest_tools_from_observation,
)
from app.agent.task_intake.intent import ParsedTaskIntent
from app.models.rag import RetrievedDoc


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _intent() -> ParsedTaskIntent:
    return ParsedTaskIntent(intent="unknown", goal="test")


def _doc(step_type: str, *, score: float = 1.0) -> RetrievedDoc:
    return RetrievedDoc(
        type=step_type,
        doc_type="transformation",
        score=score,
        title=f"doc:{step_type}",
        description="",
        example={},
        keywords=[],
    )


def _obs(*signals: str) -> ObservationSummary:
    return ObservationSummary(status="warning", signals=list(signals))


# --------------------------------------------------------------------------- #
# 1. ObservationToolSuggestion model
# --------------------------------------------------------------------------- #

class TestObservationToolSuggestionModel:
    def test_fields(self):
        s = ObservationToolSuggestion(
            tool_type="profile_column",
            signal="empty_result",
            reason="Profile to understand values.",
        )
        assert s.tool_type == "profile_column"
        assert s.signal == "empty_result"
        assert s.reason == "Profile to understand values."

    def test_all_signals_in_map_are_valid_observation_signals(self):
        from app.agent.observation.models import ObservationSummary
        valid_signals = set(ObservationSummary.model_fields["signals"].annotation.__args__[0].__args__)
        for signal in _SIGNAL_TOOL_MAP:
            assert signal in valid_signals, f"Signal '{signal}' in _SIGNAL_TOOL_MAP is not a valid ObservationSignal"


# --------------------------------------------------------------------------- #
# 2. suggest_tools_from_observation — individual signal mappings
# --------------------------------------------------------------------------- #

class TestSuggestToolsFromObservation:
    def test_empty_result_suggests_inspect_unique_values(self):
        obs = _obs("empty_result")
        suggestions = suggest_tools_from_observation(obs)
        tool_types = [s.tool_type for s in suggestions]
        assert "inspect_unique_values" in tool_types

    def test_empty_result_suggests_profile_column(self):
        obs = _obs("empty_result")
        suggestions = suggest_tools_from_observation(obs)
        tool_types = [s.tool_type for s in suggestions]
        assert "profile_column" in tool_types

    def test_suspected_wrong_value_suggests_inspect_unique_values(self):
        obs = _obs("suspected_wrong_value")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "inspect_unique_values" for s in suggestions)

    def test_suspected_wrong_column_suggests_profile_column(self):
        obs = _obs("suspected_wrong_column")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "profile_column" for s in suggestions)

    def test_data_quality_issue_suggests_remove_missing_values(self):
        obs = _obs("data_quality_issue")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "remove_missing_values" for s in suggestions)

    def test_data_quality_issue_suggests_fill_missing_values(self):
        obs = _obs("data_quality_issue")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "fill_missing_values" for s in suggestions)

    def test_data_quality_issue_suggests_distribution_summary(self):
        obs = _obs("data_quality_issue")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "distribution_summary" for s in suggestions)

    def test_large_row_removal_suggests_distribution_summary(self):
        obs = _obs("large_row_removal")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "distribution_summary" for s in suggestions)

    def test_large_row_removal_suggests_summarize_numeric_column(self):
        obs = _obs("large_row_removal")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "summarize_numeric_column" for s in suggestions)

    def test_high_warning_rate_suggests_suggest_analysis_steps(self):
        obs = _obs("high_warning_rate")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "suggest_analysis_steps" for s in suggestions)

    def test_needs_inspection_suggests_suggest_analysis_steps(self):
        obs = _obs("needs_inspection")
        suggestions = suggest_tools_from_observation(obs)
        assert any(s.tool_type == "suggest_analysis_steps" for s in suggestions)

    def test_no_signals_returns_empty_list(self):
        obs = ObservationSummary(status="ok", signals=[])
        suggestions = suggest_tools_from_observation(obs)
        assert suggestions == []

    def test_unknown_signal_returns_empty_list(self):
        # If no entry in map, should silently produce nothing.
        obs = ObservationSummary(status="warning", signals=["schema_changed"])
        suggestions = suggest_tools_from_observation(obs)
        assert suggestions == []

    def test_suggestion_includes_correct_signal_field(self):
        obs = _obs("empty_result")
        suggestions = suggest_tools_from_observation(obs)
        for s in suggestions:
            assert s.signal == "empty_result"

    def test_suggestion_includes_non_empty_reason(self):
        obs = _obs("data_quality_issue")
        suggestions = suggest_tools_from_observation(obs)
        for s in suggestions:
            assert s.reason


# --------------------------------------------------------------------------- #
# 3. Deduplication: first signal wins when multiple signals suggest same tool
# --------------------------------------------------------------------------- #

class TestDeduplication:
    def test_no_duplicate_tool_types(self):
        obs = _obs("empty_result", "suspected_wrong_value")
        suggestions = suggest_tools_from_observation(obs)
        tool_types = [s.tool_type for s in suggestions]
        assert len(tool_types) == len(set(tool_types)), "Duplicate tool types found"

    def test_first_signal_wins_for_shared_tool(self):
        # Both empty_result and suspected_wrong_value suggest inspect_unique_values.
        # The signal recorded should be empty_result (first).
        obs = _obs("empty_result", "suspected_wrong_value")
        suggestions = suggest_tools_from_observation(obs)
        iv_suggestions = [s for s in suggestions if s.tool_type == "inspect_unique_values"]
        assert len(iv_suggestions) == 1
        assert iv_suggestions[0].signal == "empty_result"


# --------------------------------------------------------------------------- #
# 4. select_tools with observation — scoring and candidate_tools
# --------------------------------------------------------------------------- #

class TestSelectToolsWithObservation:
    def test_observation_tools_appear_in_candidates(self):
        obs = _obs("empty_result")
        result = select_tools(_intent(), [], observation=obs)
        assert "inspect_unique_values" in result.candidate_tools

    def test_observation_bonus_appears_in_scores(self):
        obs = _obs("empty_result")
        result = select_tools(_intent(), [], observation=obs)
        assert result.scores.get("inspect_unique_values", 0) > 0

    def test_observation_bonus_value_matches_obs_bonus_constant(self):
        obs = _obs("data_quality_issue")
        result = select_tools(_intent(), [], observation=obs)
        # remove_missing_values only gets obs bonus (no RAG doc).
        assert abs(result.scores["remove_missing_values"] - _OBS_BONUS) < 0.01

    def test_observation_bonus_stacks_on_rag_score(self):
        obs = _obs("empty_result")
        rag_score = 2.0
        result = select_tools(_intent(), [_doc("inspect_unique_values", score=rag_score)], observation=obs)
        # Score should be rag_score + obs_bonus (intent bonus may also apply).
        assert result.scores["inspect_unique_values"] >= rag_score + _OBS_BONUS

    def test_observation_suggestions_field_populated(self):
        obs = _obs("large_row_removal")
        result = select_tools(_intent(), [], observation=obs)
        assert len(result.observation_suggestions) > 0

    def test_observation_suggestions_have_correct_tool_types(self):
        obs = _obs("large_row_removal")
        result = select_tools(_intent(), [], observation=obs)
        types = [s.tool_type for s in result.observation_suggestions]
        assert "distribution_summary" in types

    def test_no_observation_leaves_suggestions_empty(self):
        result = select_tools(_intent(), [_doc("filter_rows", score=1)])
        assert result.observation_suggestions == []

    def test_no_observation_scores_unchanged(self):
        # Existing behavior: no observation → same score as before.
        result = select_tools(_intent(), [_doc("filter_rows", score=3)])
        assert result.selected_tool == "filter_rows"
        assert "filter_rows" in result.scores


# --------------------------------------------------------------------------- #
# 5. Exploratory analysis — needs_inspection and high_warning_rate
# --------------------------------------------------------------------------- #

class TestExploratoryAnalysis:
    def test_needs_inspection_surfaces_analytical_tools(self):
        obs = _obs("needs_inspection")
        result = select_tools(_intent(), [], observation=obs)
        analytical = {"suggest_analysis_steps", "profile_column"}
        assert any(t in result.candidate_tools for t in analytical)

    def test_high_warning_rate_surfaces_suggest_analysis_steps(self):
        obs = _obs("high_warning_rate")
        result = select_tools(_intent(), [], observation=obs)
        assert "suggest_analysis_steps" in result.candidate_tools

    def test_combined_signals_produce_comprehensive_candidates(self):
        obs = _obs("empty_result", "data_quality_issue", "needs_inspection")
        result = select_tools(_intent(), [], observation=obs)
        expected = {"inspect_unique_values", "profile_column", "remove_missing_values", "suggest_analysis_steps"}
        assert expected.issubset(set(result.candidate_tools))


# --------------------------------------------------------------------------- #
# 6. Backward-compatibility: existing tests pass unchanged
# --------------------------------------------------------------------------- #

class TestBackwardCompatibility:
    def test_select_tools_no_observation_returns_correct_intent(self):
        result = select_tools(
            _intent(),
            [_doc("filter_rows", score=2), _doc("sort_values", score=2), _doc("generate_summary", score=2)],
        )
        assert result.intent == "transform_dataset"

    def test_select_tools_no_observation_selected_tool_is_top_score(self):
        result = select_tools(_intent(), [_doc("filter_rows", score=3), _doc("sort_values", score=1)])
        assert result.selected_tool == "filter_rows"

    def test_observation_none_produces_same_scores_as_omitted(self):
        docs = [_doc("filter_rows", score=2)]
        result_none = select_tools(_intent(), docs, observation=None)
        result_omit = select_tools(_intent(), docs)
        assert result_none.scores == result_omit.scores

    def test_observation_does_not_change_derived_intent(self):
        obs = _obs("empty_result")
        docs = [_doc("filter_rows", score=3), _doc("sort_values", score=3)]
        result = select_tools(_intent(), docs, observation=obs)
        assert result.intent == "transform_dataset"


# --------------------------------------------------------------------------- #
# 7. Tool suggestions written to WorkflowContextSummary trace
# --------------------------------------------------------------------------- #

class TestToolSuggestionsInTrace:
    def test_context_summary_has_tool_suggestions_field(self):
        from app.models.runtime_trace import WorkflowContextSummary
        summary = WorkflowContextSummary(
            query="test",
            dataset_hash="abc",
            schema_columns=["a"],
            row_count=10,
            status="preview_ready",
            boundary="preview",
        )
        assert hasattr(summary, "tool_suggestions")
        assert summary.tool_suggestions == []

    def test_context_summary_tool_suggestions_populated_from_observation(self):
        from app.agent.observation.models import ObservationSummary
        from app.models.runtime_trace import WorkflowContextSummary
        obs = ObservationSummary(status="warning", signals=["empty_result"])
        suggestions = [s.model_dump() for s in suggest_tools_from_observation(obs)]
        summary = WorkflowContextSummary(
            query="test",
            dataset_hash="abc",
            schema_columns=["a"],
            row_count=10,
            status="preview_ready",
            boundary="preview",
            tool_suggestions=suggestions,
        )
        tool_types = [s["tool_type"] for s in summary.tool_suggestions]
        assert "inspect_unique_values" in tool_types

    def test_workflow_runtime_populates_tool_suggestions_for_warning_observation(self):
        """Integration: make_context_summary adds tool_suggestions when signals present."""
        from app.agent.loop import workflow_runtime
        from app.agent.observation.models import ObservationSummary

        obs = ObservationSummary(status="warning", signals=["empty_result", "suspected_wrong_value"])
        context = workflow_runtime.WorkflowContext(
            dataset_id="d",
            dataset_hash="h",
            query="q",
            dataset_profile={"row_count": 100},
            current_schema=["col1"],
        )
        summary = workflow_runtime.make_context_summary(
            context=context,
            state="preview_ready",
            observation=obs,
        )
        assert len(summary.tool_suggestions) > 0
        tool_types = [s["tool_type"] for s in summary.tool_suggestions]
        assert "inspect_unique_values" in tool_types

    def test_workflow_runtime_no_suggestions_for_ok_observation(self):
        from app.agent.loop import workflow_runtime
        from app.agent.observation.models import ObservationSummary

        obs = ObservationSummary(status="ok", signals=[])
        context = workflow_runtime.WorkflowContext(
            dataset_id="d",
            dataset_hash="h",
            query="q",
            dataset_profile={"row_count": 100},
            current_schema=["col1"],
        )
        summary = workflow_runtime.make_context_summary(
            context=context,
            state="executed",
            observation=obs,
        )
        assert summary.tool_suggestions == []

    def test_workflow_runtime_no_suggestions_when_observation_is_none(self):
        from app.agent.loop import workflow_runtime

        context = workflow_runtime.WorkflowContext(
            dataset_id="d",
            dataset_hash="h",
            query="q",
            dataset_profile={"row_count": 100},
            current_schema=["col1"],
        )
        summary = workflow_runtime.make_context_summary(
            context=context,
            state="planned",
            observation=None,
        )
        assert summary.tool_suggestions == []
