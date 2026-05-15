"""Focused tests for the MVP5 planner decomposition layers.

Each layer is tested in isolation with deterministic inputs — no LLM calls.
The old workflow_planner.plan() is not imported here; it remains the fallback.
"""
import pytest

from app.agent.planning.intent_parser import parse_intent
from app.agent.planning.tool_selector import select_tools
from app.agent.planning.parameter_resolver import resolve_parameters
from app.agent.planning.workflow_builder import build_from_raw, build_workflow
from app.agent.task_intake.intent import ParsedTaskIntent
from app.core.exceptions import PlannerError
from app.models.rag import RetrievedDoc
from app.models.workflow import FilterRowsStep, GroupByStep, SortValuesStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(tool_type: str, score: float = 2.0) -> RetrievedDoc:
    return RetrievedDoc(
        doc_type="transformation",
        type=tool_type,
        title=tool_type,
        description=f"Tool: {tool_type}",
        keywords=[tool_type],
        score=score,
    )


def _transform_intent() -> ParsedTaskIntent:
    return ParsedTaskIntent(intent="transform_dataset", goal="filter completed orders")


def _inspect_intent() -> ParsedTaskIntent:
    return ParsedTaskIntent(intent="inspect_dataset", goal="show a summary")


# ---------------------------------------------------------------------------
# IntentParser
# ---------------------------------------------------------------------------

class TestIntentParser:
    def test_classifies_filter_query_as_transform(self):
        result = parse_intent("filter rows where sales > 100")

        assert result.parsed.intent == "transform_dataset"

    def test_classifies_group_by_query_as_transform(self):
        result = parse_intent("group by region and sum sales")

        assert result.parsed.intent == "transform_dataset"

    def test_classifies_show_query_as_inspect(self):
        result = parse_intent("show summary of the dataset")

        assert result.parsed.intent == "inspect_dataset"

    def test_unknown_query_returns_unknown_intent_with_missing_info(self):
        result = parse_intent("do something with the data")

        assert result.parsed.intent == "unknown"
        assert result.parsed.missing_information

    def test_extracts_candidate_columns_from_query(self):
        result = parse_intent("sort by sales descending", column_names=["sales", "region", "month"])

        assert "sales" in result.parsed.candidate_columns

    def test_candidate_columns_are_case_insensitive(self):
        result = parse_intent("filter where REGION = North", column_names=["region", "sales"])

        assert "region" in result.parsed.candidate_columns

    def test_extracts_where_constraint(self):
        result = parse_intent("filter rows where amount > 500")

        assert any("amount" in c for c in result.parsed.constraints)

    def test_match_ratio_reflects_column_coverage(self):
        result = parse_intent(
            "filter sales where region = North",
            column_names=["sales", "region", "month"],
        )

        assert result.candidate_column_match_ratio > 0

    def test_preserves_raw_query_in_result(self):
        query = "group by region and sum sales"
        result = parse_intent(query)

        assert result.raw_query == query

    def test_chinese_query_classifies_as_transform(self):
        result = parse_intent("按地区分组统计销售额")

        assert result.parsed.intent == "transform_dataset"


# ---------------------------------------------------------------------------
# ToolSelector
# ---------------------------------------------------------------------------

class TestToolSelector:
    def test_selects_transform_tool_from_retrieved_docs(self):
        result = select_tools(_transform_intent(), [_doc("filter_rows", score=3)])

        assert result.selected_tool == "filter_rows"
        assert "filter_rows" in result.candidate_tools

    def test_transform_intent_gives_bonus_to_transform_tools(self):
        result = select_tools(
            _transform_intent(),
            [_doc("filter_rows", score=2), _doc("generate_summary", score=2)],
        )

        assert result.scores["filter_rows"] > result.scores["generate_summary"]
        assert result.candidate_tools[0] == "filter_rows"

    def test_inspect_intent_gives_bonus_to_inspect_tools(self):
        result = select_tools(
            _inspect_intent(),
            [_doc("generate_summary", score=2), _doc("filter_rows", score=2)],
        )

        assert result.scores["generate_summary"] > result.scores["filter_rows"]
        assert result.candidate_tools[0] == "generate_summary"

    def test_non_transformation_docs_are_excluded(self):
        failure_doc = RetrievedDoc(
            doc_type="failure_case",
            type="",
            title="empty result",
            description="Empty result warning",
            keywords=["empty"],
            score=5,
        )
        result = select_tools(_transform_intent(), [failure_doc, _doc("filter_rows", score=1)])

        assert "failure_case" not in result.candidate_tools
        assert result.selected_tool == "filter_rows"

    def test_no_docs_returns_empty_result(self):
        result = select_tools(_transform_intent(), [])

        assert result.candidate_tools == []
        assert result.selected_tool is None

    def test_result_preserves_intent_and_raw_scores(self):
        result = select_tools(_transform_intent(), [_doc("sort_values", score=2.5)])

        assert result.intent == "transform_dataset"
        assert "sort_values" in result.scores


# ---------------------------------------------------------------------------
# ParameterResolver
# ---------------------------------------------------------------------------

class TestParameterResolver:
    def test_passes_valid_step_unchanged(self):
        step = {"type": "filter_rows", "column": "sales", "operator": ">", "value": 100}
        result = resolve_parameters(step, ["sales", "region"])

        assert result.resolved_step["column"] == "sales"
        assert result.column_errors == []

    def test_fixes_column_case_mismatch(self):
        step = {"type": "filter_rows", "column": "Sales", "operator": ">", "value": 100}
        result = resolve_parameters(step, ["sales", "region"])

        assert result.resolved_step["column"] == "sales"
        assert any("case_fixed" in f for f in result.defaulted_fields)
        assert result.column_errors == []

    def test_reports_column_error_when_column_not_found(self):
        step = {"type": "filter_rows", "column": "revenue", "operator": ">", "value": 0}
        result = resolve_parameters(step, ["sales", "region"])

        assert result.column_errors
        assert "revenue" in result.column_errors[0]

    def test_applies_default_n_for_limit_rows(self):
        step = {"type": "limit_rows"}
        result = resolve_parameters(step, [])

        assert result.resolved_step["n"] == 10
        assert "n" in result.defaulted_fields

    def test_applies_default_ascending_for_sort_values(self):
        step = {"type": "sort_values", "column": "sales"}
        result = resolve_parameters(step, ["sales"])

        assert result.resolved_step["ascending"] is True
        assert "ascending" in result.defaulted_fields

    def test_fixes_column_in_list_field(self):
        step = {"type": "select_columns", "columns": ["Region", "sales"]}
        result = resolve_parameters(step, ["region", "sales"])

        assert "region" in result.resolved_step["columns"]
        assert any("case_fixed" in f for f in result.defaulted_fields)

    def test_raw_step_is_preserved_unchanged(self):
        step = {"type": "filter_rows", "column": "Sales", "operator": ">", "value": 0}
        result = resolve_parameters(step, ["sales"])

        assert result.raw_step["column"] == "Sales"
        assert result.resolved_step["column"] == "sales"


# ---------------------------------------------------------------------------
# WorkflowBuilder
# ---------------------------------------------------------------------------

class TestWorkflowBuilder:
    def test_build_from_raw_returns_typed_steps(self):
        raw = [{"type": "remove_missing_values"}]
        result = build_from_raw("dataset-1", raw)

        assert result.step_count == 1
        assert result.steps[0].type == "remove_missing_values"

    def test_build_from_raw_preserves_raw_steps(self):
        raw = [{"type": "limit_rows", "n": 5}]
        result = build_from_raw("dataset-1", raw)

        assert result.raw_steps == raw
        assert result.steps[0].n == 5

    def test_build_from_raw_multiple_steps(self):
        raw = [
            {"type": "remove_missing_values"},
            {"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
            {"type": "sort_values", "column": "sales", "ascending": False},
        ]
        result = build_from_raw("dataset-1", raw)

        assert result.step_count == 3
        assert [s.type for s in result.steps] == [
            "remove_missing_values", "group_by", "sort_values"
        ]

    def test_build_from_raw_raises_planner_error_for_invalid_step(self):
        raw = [{"type": "filter_rows"}]  # missing column, operator, value
        with pytest.raises(PlannerError, match="invalid"):
            build_from_raw("dataset-1", raw)

    def test_build_from_raw_raises_planner_error_for_unknown_step_type(self):
        raw = [{"type": "nonexistent_step"}]
        with pytest.raises(PlannerError):
            build_from_raw("dataset-1", raw)

    def test_build_workflow_legacy_api_unchanged(self):
        steps = [
            FilterRowsStep(type="filter_rows", column="sales", operator=">", value=100),
        ]
        request = build_workflow("dataset-1", steps)

        assert request.dataset_id == "dataset-1"
        assert len(request.steps) == 1
