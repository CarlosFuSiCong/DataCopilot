"""Regression tests for workflow reliability (Task 2).

Covers common failure scenarios for the validator, executor, and preview path:
- Missing column errors include available columns
- Executor error messages are user-readable
- affected_rows is always computed correctly
- Preview captures errors without raising
- Preview and execute share the same step execution path
- Sequential column-state tracking in the validator (chained workflow bug fix)
"""
import io
import pytest
import pandas as pd

from app.core.exceptions import ExecutionError, WorkflowValidationError
from app.agent.execution import executor as executor_service
from app.agent.execution import validator as validator_service
from app.agent.execution.validator import simulate_columns
from app.models.workflow import (
    FilterRowsStep,
    GroupByStep,
    SelectColumnsStep,
    SortValuesStep,
    RenameColumnsStep,
    DeriveColumnStep,
    DateExtractStep,
    DropColumnsStep,
    FillMissingValuesStep,
    LimitRowsStep,
    RemoveMissingValuesStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(data: dict) -> bytes:
    return pd.DataFrame(data).to_csv(index=False).encode()


SAMPLE = _csv({"name": ["Alice", "Bob", None], "score": [90, 80, 70], "age": [25, 30, 22]})


# ---------------------------------------------------------------------------
# Validator: available columns in error messages
# ---------------------------------------------------------------------------

class TestValidatorErrorMessages:
    def test_missing_column_includes_available_columns(self):
        step = FilterRowsStep(type="filter_rows", column="nonexistent", operator="=", value=1)
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate([step], ["name", "score", "age"])
        msg = str(exc_info.value)
        assert "nonexistent" in msg
        assert "Available columns" in msg
        assert "name" in msg

    def test_select_missing_column_includes_available_columns(self):
        step = SelectColumnsStep(type="select_columns", columns=["ghost"])
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate([step], ["name", "score"])
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_group_by_missing_target_includes_available_columns(self):
        step = GroupByStep(type="group_by", column="name", target="missing_col", agg="sum")
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate([step], ["name", "score"])
        msg = str(exc_info.value)
        assert "missing_col" in msg
        assert "Available columns" in msg

    def test_rename_missing_column_includes_available_columns(self):
        step = RenameColumnsStep(type="rename_columns", mapping={"ghost": "new_name"})
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate([step], ["name", "score"])
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_empty_steps_raises_validation_error(self):
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate([], ["name", "score"])
        assert "at least one step" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Executor: user-readable error messages with available columns
# ---------------------------------------------------------------------------

class TestExecutorErrorMessages:
    def test_filter_missing_column_message_is_readable(self):
        step = FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1)
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg
        assert "name" in msg

    def test_select_missing_column_message_includes_columns(self):
        step = SelectColumnsStep(type="select_columns", columns=["name", "ghost"])
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_sort_missing_column_message_includes_columns(self):
        step = SortValuesStep(type="sort_values", column="ghost")
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_derive_missing_column_message_includes_columns(self):
        step = DeriveColumnStep(
            type="derive_column", new_column="result", column="ghost", operator="*", value=2.0
        )
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_drop_missing_column_message_includes_columns(self):
        step = DropColumnsStep(type="drop_columns", columns=["ghost"])
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg

    def test_fill_missing_column_message_includes_columns(self):
        step = FillMissingValuesStep(type="fill_missing_values", column="ghost", strategy="mean")
        with pytest.raises(ExecutionError) as exc_info:
            executor_service.execute([step], SAMPLE)
        msg = str(exc_info.value)
        assert "ghost" in msg
        assert "Available columns" in msg


# ---------------------------------------------------------------------------
# StepResult: affected_rows always computed
# ---------------------------------------------------------------------------

class TestAffectedRows:
    def test_filter_affected_rows_equals_removed_rows(self):
        step = FilterRowsStep(type="filter_rows", column="score", operator=">", value=85)
        result = executor_service.execute([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == sr.input_row_count - sr.output_row_count

    def test_remove_missing_affected_rows_equals_dropped(self):
        step = RemoveMissingValuesStep(type="remove_missing_values")
        result = executor_service.execute([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == sr.input_row_count - sr.output_row_count
        assert sr.affected_rows == 1  # one row has missing name

    def test_limit_rows_affected_rows(self):
        step = LimitRowsStep(type="limit_rows", n=2)
        result = executor_service.execute([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == 1  # 3 rows → 2 rows, 1 removed

    def test_select_columns_affected_rows_is_zero(self):
        # select_columns doesn't remove rows
        step = SelectColumnsStep(type="select_columns", columns=["name"])
        result = executor_service.execute([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == 0

    def test_derive_column_affected_rows_is_zero(self):
        step = DeriveColumnStep(
            type="derive_column", new_column="double_score", column="score", operator="*", value=2.0
        )
        result = executor_service.execute([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == 0


# ---------------------------------------------------------------------------
# Preview: captures errors without raising, preview/execute consistency
# ---------------------------------------------------------------------------

class TestPreviewReliability:
    def test_preview_captures_missing_column_error(self):
        step = FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1)
        # Bypass validator to test executor-level preview error capture.
        result = executor_service.preview([step], SAMPLE)
        assert result.has_errors
        assert result.blocked_at_step == 0
        assert any("ghost" in i.message for i in result.step_results[0].issues)

    def test_preview_captures_error_and_stops(self):
        good_step = SelectColumnsStep(type="select_columns", columns=["name", "score"])
        bad_step = FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1)
        result = executor_service.preview([good_step, bad_step], SAMPLE)
        # First step should succeed, second should fail
        assert result.step_results[0].status == "success"
        assert result.step_results[1].status == "error"
        assert result.blocked_at_step == 1

    def test_preview_and_execute_produce_same_row_count(self):
        step = FilterRowsStep(type="filter_rows", column="score", operator=">", value=75)
        preview_result = executor_service.preview([step], SAMPLE)
        exec_result = executor_service.execute([step], SAMPLE)
        preview_output_rows = preview_result.step_results[0].output_row_count
        assert preview_output_rows == exec_result.row_count

    def test_preview_affected_rows_computed(self):
        step = LimitRowsStep(type="limit_rows", n=1)
        result = executor_service.preview([step], SAMPLE)
        sr = result.step_results[0]
        assert sr.affected_rows == sr.input_row_count - sr.output_row_count

    def test_preview_error_step_has_affected_rows_as_input_count(self):
        step = FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1)
        result = executor_service.preview([step], SAMPLE)
        sr = result.step_results[0]
        # When step errors, affected_rows = input_row_count (all rows lost to the error)
        assert sr.affected_rows == sr.input_row_count


# ---------------------------------------------------------------------------
# Regression: chained workflow with a mid-chain error
# ---------------------------------------------------------------------------

class TestChainedWorkflowRegression:
    def test_preview_partial_results_on_mid_chain_error(self):
        """Preview should return partial step results up to the failing step."""
        csv = _csv({"a": [1, 2, 3], "b": [10, 20, 30]})
        steps = [
            SelectColumnsStep(type="select_columns", columns=["a", "b"]),
            FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1),
            SortValuesStep(type="sort_values", column="a"),
        ]
        result = executor_service.preview(steps, csv)
        assert len(result.step_results) == 2  # step 0 ok, step 1 error, step 2 not reached
        assert result.step_results[0].status == "success"
        assert result.step_results[1].status == "error"
        assert result.blocked_at_step == 1

    def test_execute_raises_on_first_error(self):
        csv = _csv({"a": [1, 2, 3]})
        step = FilterRowsStep(type="filter_rows", column="ghost", operator="=", value=1)
        with pytest.raises(ExecutionError):
            executor_service.execute([step], csv)

    def test_fill_missing_no_op_still_returns_affected_rows_zero(self):
        csv = _csv({"x": [1, 2, 3]})  # no missing values
        step = FillMissingValuesStep(type="fill_missing_values", column="x", strategy="mean")
        result = executor_service.execute([step], csv)
        sr = result.step_results[0]
        assert sr.affected_rows == 0
        assert sr.output_row_count == sr.input_row_count


# ---------------------------------------------------------------------------
# Bug fix: sequential column-state tracking in validator (chained workflows)
# ---------------------------------------------------------------------------

class TestValidatorColumnStateTracking:
    """The validator must update its column set after each step.

    Previously it validated all steps against the original columns, so a
    filter_rows on a column dropped by an earlier select_columns would
    incorrectly PASS validation and then fail at execution time.
    """

    def test_filter_after_select_rejects_dropped_column(self):
        """select_columns([a, b]) then filter_rows(c) must raise — c was dropped."""
        steps = [
            SelectColumnsStep(type="select_columns", columns=["name", "score"]),
            FilterRowsStep(type="filter_rows", column="age", operator=">", value=20),
        ]
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate(steps, ["name", "score", "age"])
        assert "age" in str(exc_info.value)

    def test_filter_after_drop_rejects_dropped_column(self):
        """drop_columns([age]) then sort_values(age) must raise."""
        steps = [
            DropColumnsStep(type="drop_columns", columns=["age"]),
            SortValuesStep(type="sort_values", column="age"),
        ]
        with pytest.raises(WorkflowValidationError):
            validator_service.validate(steps, ["name", "score", "age"])

    def test_filter_after_select_passes_for_kept_column(self):
        """select_columns([name, score]) then filter_rows(score) must pass — score was kept."""
        steps = [
            SelectColumnsStep(type="select_columns", columns=["name", "score"]),
            FilterRowsStep(type="filter_rows", column="score", operator=">", value=50),
        ]
        # should not raise
        validator_service.validate(steps, ["name", "score", "age"])

    def test_derive_column_then_filter_on_new_column_passes(self):
        """derive_column adds new_col; filter_rows(new_col) on the same workflow must pass."""
        steps = [
            DeriveColumnStep(
                type="derive_column",
                new_column="double_score",
                column="score",
                operator="*",
                value=2.0,
            ),
            FilterRowsStep(type="filter_rows", column="double_score", operator=">", value=100),
        ]
        # should not raise — double_score was added by the first step
        validator_service.validate(steps, ["name", "score"])

    def test_rename_then_filter_on_old_name_rejects(self):
        """rename score→points; filter_rows(score) must raise — score no longer exists."""
        steps = [
            RenameColumnsStep(type="rename_columns", mapping={"score": "points"}),
            FilterRowsStep(type="filter_rows", column="score", operator=">", value=50),
        ]
        with pytest.raises(WorkflowValidationError) as exc_info:
            validator_service.validate(steps, ["name", "score"])
        assert "score" in str(exc_info.value)

    def test_rename_then_filter_on_new_name_passes(self):
        """rename score→points; filter_rows(points) must pass."""
        steps = [
            RenameColumnsStep(type="rename_columns", mapping={"score": "points"}),
            FilterRowsStep(type="filter_rows", column="points", operator=">", value=50),
        ]
        validator_service.validate(steps, ["name", "score"])

    def test_group_by_then_filter_on_non_group_column_rejects(self):
        """group_by(name, score=sum) discards all other columns; filter on 'age' must raise."""
        steps = [
            GroupByStep(type="group_by", column="name", target="score", agg="sum"),
            FilterRowsStep(type="filter_rows", column="age", operator=">", value=20),
        ]
        with pytest.raises(WorkflowValidationError):
            validator_service.validate(steps, ["name", "score", "age"])

    def test_group_by_then_sort_on_group_column_passes(self):
        """After group_by(name, score=sum), sort_values(name) must pass — name is a group key."""
        steps = [
            GroupByStep(type="group_by", column="name", target="score", agg="sum"),
            SortValuesStep(type="sort_values", column="name"),
        ]
        validator_service.validate(steps, ["name", "score", "age"])

    def test_date_extract_then_filter_on_new_column_passes(self):
        """date_extract adds new_col; filter on it must pass."""
        steps = [
            DateExtractStep(type="date_extract", column="score", part="year", new_column="yr"),
            FilterRowsStep(type="filter_rows", column="yr", operator=">", value=2020),
        ]
        validator_service.validate(steps, ["name", "score"])

    def test_simulate_columns_select(self):
        initial = ["a", "b", "c"]
        step = SelectColumnsStep(type="select_columns", columns=["a", "b"])
        result = simulate_columns([step], initial)
        assert sorted(result) == ["a", "b"]

    def test_simulate_columns_drop(self):
        initial = ["a", "b", "c"]
        step = DropColumnsStep(type="drop_columns", columns=["c"])
        result = simulate_columns([step], initial)
        assert sorted(result) == ["a", "b"]

    def test_simulate_columns_rename(self):
        initial = ["a", "b"]
        step = RenameColumnsStep(type="rename_columns", mapping={"a": "x"})
        result = simulate_columns([step], initial)
        assert sorted(result) == ["b", "x"]

    def test_simulate_columns_derive(self):
        initial = ["a", "b"]
        step = DeriveColumnStep(
            type="derive_column", new_column="c", column="a", operator="+", value=1.0
        )
        result = simulate_columns([step], initial)
        assert sorted(result) == ["a", "b", "c"]

    def test_simulate_columns_group_by(self):
        initial = ["region", "amount", "quantity"]
        step = GroupByStep(type="group_by", column="region", target="amount", agg="sum")
        result = simulate_columns([step], initial)
        assert sorted(result) == ["amount", "region"]

    def test_simulate_columns_chained(self):
        """select → derive → rename chain should reflect all transformations."""
        initial = ["a", "b", "c"]
        steps = [
            SelectColumnsStep(type="select_columns", columns=["a", "b"]),
            DeriveColumnStep(
                type="derive_column", new_column="d", column="a", operator="*", value=2.0
            ),
            RenameColumnsStep(type="rename_columns", mapping={"b": "y"}),
        ]
        result = simulate_columns(steps, initial)
        assert sorted(result) == ["a", "d", "y"]


class TestExecutionErrorContextChainedWorkflow:
    """Verify that execution-phase errors return columns available at the
    failing step, not the original dataset columns (Bug 1 fix)."""

    def _csv(self, df: pd.DataFrame) -> bytes:
        return df.to_csv(index=False).encode()

    def test_preview_error_context_uses_cols_after_previous_steps(self):
        """When select_columns narrows the schema and a later filter references
        a removed column, simulate_columns on steps[:blocked] returns only the
        narrowed set — not the original full set."""
        original_cols = ["a", "b", "c"]
        previous = [SelectColumnsStep(type="select_columns", columns=["a", "b"])]
        steps_combined = previous + [
            FilterRowsStep(type="filter_rows", column="c", operator="eq", value="x"),
        ]
        # Columns at the failing step (index 1) = simulate previous steps
        cols_at_failure = simulate_columns(steps_combined[:1], original_cols)
        assert cols_at_failure == ["a", "b"]
        assert "c" not in cols_at_failure

    def test_simulate_columns_empty_previous_steps_returns_original(self):
        """With no previous steps, simulate_columns on an empty slice returns
        the original column set unchanged."""
        original_cols = ["x", "y", "z"]
        cols_at_failure = simulate_columns([], original_cols)
        assert sorted(cols_at_failure) == ["x", "y", "z"]

    def test_simulate_columns_blocked_at_step_zero(self):
        """When blocked_at_step is 0, steps[:0] is empty so original columns
        are returned — correct because no prior step has changed the schema."""
        original_cols = ["order_id", "amount", "category"]
        steps = [FilterRowsStep(type="filter_rows", column="nonexistent", operator="eq", value=1)]
        cols_at_failure = simulate_columns(steps[:0], original_cols)
        assert sorted(cols_at_failure) == sorted(original_cols)
