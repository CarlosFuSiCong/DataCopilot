"""Unit and executor integration tests for Task 7 analytical / diagnostic tools.

Covers:
- Step model validation (Pydantic contracts).
- Registry validate: column existence, column count checks.
- Registry execute: correct DataFrame shape and content, message format, error paths.
- Tool registration: all 7 tools present in the registry.
- Tool selector: all 7 tools classified as inspect.
"""
import pytest
import pandas as pd
import numpy as np

from app.models.workflow_steps import (
    CompareGroupsStep,
    CorrelationSummaryStep,
    DistributionSummaryStep,
    InspectUniqueValuesStep,
    ProfileColumnStep,
    SuggestAnalysisStepsStep,
    SummarizeNumericColumnStep,
)
from app.workflow.registry import registry


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _sample_df() -> pd.DataFrame:
    """Small DataFrame with numeric, categorical, and missing-value columns."""
    return pd.DataFrame({
        "region": ["North", "South", "North", "East", "South", "East"],
        "sales": [100.0, 200.0, 150.0, 300.0, 250.0, 175.0],
        "quantity": [1, 2, 1, 3, 2, 2],
        "score": [8.5, 7.0, 9.0, None, 6.5, 8.0],
    })


# --------------------------------------------------------------------------- #
# 1. Step model contracts
# --------------------------------------------------------------------------- #

class TestStepModels:
    def test_profile_column_requires_column(self):
        s = ProfileColumnStep(type="profile_column", column="sales")
        assert s.column == "sales"

    def test_inspect_unique_values_defaults(self):
        s = InspectUniqueValuesStep(type="inspect_unique_values", column="region")
        assert s.max_values == 20

    def test_inspect_unique_values_custom_max(self):
        s = InspectUniqueValuesStep(type="inspect_unique_values", column="region", max_values=5)
        assert s.max_values == 5

    def test_inspect_unique_values_max_ge_1(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            InspectUniqueValuesStep(type="inspect_unique_values", column="region", max_values=0)

    def test_summarize_numeric_column(self):
        s = SummarizeNumericColumnStep(type="summarize_numeric_column", column="sales")
        assert s.column == "sales"

    def test_compare_groups_defaults(self):
        s = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales")
        assert s.agg == "mean"

    def test_compare_groups_custom_agg(self):
        s = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales", agg="sum")
        assert s.agg == "sum"

    def test_correlation_summary_empty_columns(self):
        s = CorrelationSummaryStep(type="correlation_summary")
        assert s.columns == []

    def test_distribution_summary(self):
        s = DistributionSummaryStep(type="distribution_summary", column="sales")
        assert s.column == "sales"

    def test_suggest_analysis_steps(self):
        s = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        assert s.type == "suggest_analysis_steps"


# --------------------------------------------------------------------------- #
# 2. Tool registration
# --------------------------------------------------------------------------- #

class TestToolRegistration:
    _ANALYTICAL_TOOLS = [
        "profile_column",
        "inspect_unique_values",
        "summarize_numeric_column",
        "compare_groups",
        "correlation_summary",
        "distribution_summary",
        "suggest_analysis_steps",
    ]

    def test_all_analytical_tools_registered(self):
        for tool_type in self._ANALYTICAL_TOOLS:
            assert registry.get_tool(tool_type) is not None, f"{tool_type} not in registry"

    def test_analytical_tools_have_descriptions(self):
        for tool_type in self._ANALYTICAL_TOOLS:
            spec = registry.get_tool(tool_type)
            assert spec.description, f"{tool_type} has no description"

    def test_analytical_tools_have_examples(self):
        for tool_type in self._ANALYTICAL_TOOLS:
            spec = registry.get_tool(tool_type)
            assert spec.examples, f"{tool_type} has no examples"


# --------------------------------------------------------------------------- #
# 4. Validate — column existence
# --------------------------------------------------------------------------- #

class TestValidate:
    def test_profile_column_valid(self):
        step = ProfileColumnStep(type="profile_column", column="sales")
        registry.validate_step(step, ["sales", "region"], 0)  # no exception

    def test_profile_column_missing_column(self):
        from app.core.exceptions import WorkflowValidationError
        step = ProfileColumnStep(type="profile_column", column="nonexistent")
        with pytest.raises(WorkflowValidationError):
            registry.validate_step(step, ["sales", "region"], 0)

    def test_inspect_unique_values_missing_column(self):
        from app.core.exceptions import WorkflowValidationError
        step = InspectUniqueValuesStep(type="inspect_unique_values", column="bad")
        with pytest.raises(WorkflowValidationError):
            registry.validate_step(step, ["sales"], 0)

    def test_compare_groups_both_columns_required(self):
        from app.core.exceptions import WorkflowValidationError
        step = CompareGroupsStep(type="compare_groups", group_column="region", value_column="missing")
        with pytest.raises(WorkflowValidationError):
            registry.validate_step(step, ["region", "sales"], 0)

    def test_correlation_summary_specified_columns_validated(self):
        from app.core.exceptions import WorkflowValidationError
        step = CorrelationSummaryStep(type="correlation_summary", columns=["sales", "ghost"])
        with pytest.raises(WorkflowValidationError):
            registry.validate_step(step, ["sales", "region"], 0)

    def test_correlation_summary_empty_columns_always_valid(self):
        step = CorrelationSummaryStep(type="correlation_summary", columns=[])
        registry.validate_step(step, ["sales", "region"], 0)  # no exception

    def test_suggest_analysis_steps_always_valid(self):
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        registry.validate_step(step, [], 0)  # no exception even with empty columns


# --------------------------------------------------------------------------- #
# 5. Execute — profile_column
# --------------------------------------------------------------------------- #

class TestExecuteProfileColumn:
    def test_returns_stat_value_dataframe(self):
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="sales")
        result, msg, metrics = registry.execute_step(step, df, 0)
        assert list(result.columns) == ["stat", "value"]
        stat_names = result["stat"].tolist()
        assert "dtype" in stat_names
        assert "missing_pct" in stat_names
        assert "unique_count" in stat_names

    def test_numeric_column_includes_min_max_mean(self):
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="sales")
        result, _, _ = registry.execute_step(step, df, 0)
        stat_names = result["stat"].tolist()
        assert "min" in stat_names
        assert "max" in stat_names
        assert "mean" in stat_names

    def test_categorical_column_no_min_max(self):
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="region")
        result, _, _ = registry.execute_step(step, df, 0)
        stat_names = result["stat"].tolist()
        assert "min" not in stat_names
        assert "max" not in stat_names

    def test_message_contains_column_name(self):
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="sales")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "sales" in msg

    def test_missing_column_raises(self):
        from app.core.exceptions import ExecutionError
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="ghost")
        with pytest.raises(ExecutionError):
            registry.execute_step(step, df, 0)

    def test_affected_rate_is_zero(self):
        df = _sample_df()
        step = ProfileColumnStep(type="profile_column", column="sales")
        _, _, metrics = registry.execute_step(step, df, 0)
        assert metrics.affected_rate == 0.0


# --------------------------------------------------------------------------- #
# 6. Execute — inspect_unique_values
# --------------------------------------------------------------------------- #

class TestExecuteInspectUniqueValues:
    def test_returns_value_count_pct(self):
        df = _sample_df()
        step = InspectUniqueValuesStep(type="inspect_unique_values", column="region")
        result, msg, _ = registry.execute_step(step, df, 0)
        assert list(result.columns) == ["value", "count", "pct"]
        assert len(result) > 0

    def test_max_values_respected(self):
        df = pd.DataFrame({"x": list(range(100))})
        step = InspectUniqueValuesStep(type="inspect_unique_values", column="x", max_values=5)
        result, _, _ = registry.execute_step(step, df, 0)
        assert len(result) <= 5

    def test_message_contains_column_name(self):
        df = _sample_df()
        step = InspectUniqueValuesStep(type="inspect_unique_values", column="region")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "region" in msg


# --------------------------------------------------------------------------- #
# 7. Execute — summarize_numeric_column
# --------------------------------------------------------------------------- #

class TestExecuteSummarizeNumericColumn:
    def test_returns_stat_value_dataframe(self):
        df = _sample_df()
        step = SummarizeNumericColumnStep(type="summarize_numeric_column", column="sales")
        result, msg, _ = registry.execute_step(step, df, 0)
        assert list(result.columns) == ["stat", "value"]
        stats = result["stat"].tolist()
        for expected in ["count", "mean", "median", "std", "min", "q25", "q75", "max", "outlier_count_iqr"]:
            assert expected in stats

    def test_outlier_count_is_int(self):
        df = _sample_df()
        step = SummarizeNumericColumnStep(type="summarize_numeric_column", column="sales")
        result, _, _ = registry.execute_step(step, df, 0)
        oc = result.loc[result["stat"] == "outlier_count_iqr", "value"].iloc[0]
        assert float(oc) == int(float(oc)), "outlier_count_iqr should be a whole number"

    def test_non_numeric_column_raises(self):
        from app.core.exceptions import ExecutionError
        df = _sample_df()
        step = SummarizeNumericColumnStep(type="summarize_numeric_column", column="region")
        with pytest.raises(ExecutionError, match="not numeric"):
            registry.execute_step(step, df, 0)

    def test_message_contains_mean_and_median(self):
        df = _sample_df()
        step = SummarizeNumericColumnStep(type="summarize_numeric_column", column="sales")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "mean" in msg
        assert "median" in msg


# --------------------------------------------------------------------------- #
# 8. Execute — compare_groups
# --------------------------------------------------------------------------- #

class TestExecuteCompareGroups:
    def test_returns_grouped_dataframe(self):
        df = _sample_df()
        step = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales", agg="mean")
        result, msg, _ = registry.execute_step(step, df, 0)
        assert "region" in result.columns
        assert "mean" in result.columns
        assert "count" in result.columns

    def test_sorted_descending_by_agg(self):
        df = _sample_df()
        step = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales", agg="mean")
        result, _, _ = registry.execute_step(step, df, 0)
        values = result["mean"].tolist()
        assert values == sorted(values, reverse=True)

    def test_sum_aggregation(self):
        df = _sample_df()
        step = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales", agg="sum")
        result, _, _ = registry.execute_step(step, df, 0)
        assert "sum" in result.columns

    def test_non_numeric_value_column_raises(self):
        from app.core.exceptions import ExecutionError
        df = _sample_df()
        step = CompareGroupsStep(type="compare_groups", group_column="sales", value_column="region", agg="mean")
        with pytest.raises(ExecutionError, match="not numeric"):
            registry.execute_step(step, df, 0)

    def test_message_contains_group_column(self):
        df = _sample_df()
        step = CompareGroupsStep(type="compare_groups", group_column="region", value_column="sales")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "region" in msg
        assert "sales" in msg


# --------------------------------------------------------------------------- #
# 9. Execute — correlation_summary
# --------------------------------------------------------------------------- #

class TestExecuteCorrelationSummary:
    def test_returns_col_a_col_b_correlation(self):
        df = _sample_df()
        step = CorrelationSummaryStep(type="correlation_summary", columns=[])
        result, msg, _ = registry.execute_step(step, df, 0)
        assert list(result.columns) == ["col_a", "col_b", "correlation"]

    def test_no_self_pairs(self):
        df = _sample_df()
        step = CorrelationSummaryStep(type="correlation_summary")
        result, _, _ = registry.execute_step(step, df, 0)
        for _, row in result.iterrows():
            assert row["col_a"] != row["col_b"]

    def test_sorted_by_absolute_correlation(self):
        df = _sample_df()
        step = CorrelationSummaryStep(type="correlation_summary")
        result, _, _ = registry.execute_step(step, df, 0)
        abs_vals = result["correlation"].abs().tolist()
        assert abs_vals == sorted(abs_vals, reverse=True)

    def test_single_numeric_column_raises(self):
        from app.core.exceptions import ExecutionError
        df = pd.DataFrame({"x": [1, 2, 3], "label": ["a", "b", "c"]})
        step = CorrelationSummaryStep(type="correlation_summary")
        with pytest.raises(ExecutionError, match="at least 2"):
            registry.execute_step(step, df, 0)

    def test_specified_columns_filter(self):
        df = _sample_df()
        step = CorrelationSummaryStep(type="correlation_summary", columns=["sales", "quantity"])
        result, _, _ = registry.execute_step(step, df, 0)
        for col in ["col_a", "col_b"]:
            for val in result[col]:
                assert val in ("sales", "quantity")


# --------------------------------------------------------------------------- #
# 10. Execute — distribution_summary
# --------------------------------------------------------------------------- #

class TestExecuteDistributionSummary:
    def test_returns_stat_value_dataframe(self):
        df = _sample_df()
        step = DistributionSummaryStep(type="distribution_summary", column="sales")
        result, msg, _ = registry.execute_step(step, df, 0)
        assert list(result.columns) == ["stat", "value"]
        stats = result["stat"].tolist()
        for expected in ["min", "q25", "median", "q75", "max", "skewness", "skew_label", "outlier_count_iqr"]:
            assert expected in stats

    def test_skew_label_is_string(self):
        df = _sample_df()
        step = DistributionSummaryStep(type="distribution_summary", column="sales")
        result, _, _ = registry.execute_step(step, df, 0)
        label = result.loc[result["stat"] == "skew_label", "value"].iloc[0]
        assert label in ("symmetric", "right-skewed", "left-skewed")

    def test_non_numeric_raises(self):
        from app.core.exceptions import ExecutionError
        df = _sample_df()
        step = DistributionSummaryStep(type="distribution_summary", column="region")
        with pytest.raises(ExecutionError, match="not numeric"):
            registry.execute_step(step, df, 0)

    def test_message_contains_skew_label(self):
        df = _sample_df()
        step = DistributionSummaryStep(type="distribution_summary", column="sales")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert any(label in msg for label in ("symmetric", "right-skewed", "left-skewed"))


# --------------------------------------------------------------------------- #
# 11. Execute — suggest_analysis_steps
# --------------------------------------------------------------------------- #

class TestExecuteSuggestAnalysisSteps:
    def test_returns_original_dataframe_unchanged(self):
        df = _sample_df()
        original_shape = df.shape
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        result, _, _ = registry.execute_step(step, df, 0)
        assert result.shape == original_shape

    def test_message_mentions_numeric_column(self):
        df = _sample_df()
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "sales" in msg or "quantity" in msg or "score" in msg

    def test_message_mentions_missing_values_when_present(self):
        df = _sample_df()  # score has one NaN
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert "missing" in msg.lower() or "score" in msg

    def test_message_no_crash_on_empty_dataframe(self):
        df = pd.DataFrame({"x": pd.Series([], dtype="float64")})
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        _, msg, _ = registry.execute_step(step, df, 0)
        assert isinstance(msg, str)

    def test_affected_rate_is_zero(self):
        df = _sample_df()
        step = SuggestAnalysisStepsStep(type="suggest_analysis_steps")
        _, _, metrics = registry.execute_step(step, df, 0)
        assert metrics.affected_rate == 0.0


# --------------------------------------------------------------------------- #
# 12. Workflow validator integration (step survives validate + advance_columns)
# --------------------------------------------------------------------------- #

class TestWorkflowValidatorIntegration:
    def test_profile_column_survives_validation(self):
        from app.workflow.validation.workflow_validator import validate as validate_workflow
        steps_raw = [{"type": "profile_column", "column": "sales"}]
        from app.models.workflow_transport import WorkflowRequest
        req = WorkflowRequest(dataset_id="d", steps=steps_raw)
        validate_workflow(req.steps, ["sales", "region"])  # no exception

    def test_compare_groups_survives_validation(self):
        from app.workflow.validation.workflow_validator import validate as validate_workflow
        from app.models.workflow_transport import WorkflowRequest
        steps_raw = [{"type": "compare_groups", "group_column": "region", "value_column": "sales", "agg": "mean"}]
        req = WorkflowRequest(dataset_id="d", steps=steps_raw)
        validate_workflow(req.steps, ["region", "sales"])

    def test_suggest_analysis_steps_survives_validation_with_empty_columns(self):
        from app.workflow.validation.workflow_validator import validate as validate_workflow
        from app.models.workflow_transport import WorkflowRequest
        steps_raw = [{"type": "suggest_analysis_steps"}]
        req = WorkflowRequest(dataset_id="d", steps=steps_raw)
        validate_workflow(req.steps, [])  # no columns needed
