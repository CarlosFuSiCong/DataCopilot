"""Unit tests for app.workflow.validation.workflow_validator."""
import pytest

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    FilterRowsStep,
    GroupByStep,
    RemoveMissingValuesStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
    GenerateSummaryStep,
)
from app.workflow.validation.workflow_validator import validate

COLUMNS = ["region", "sales", "month"]


# ---------------------------------------------------------------------------
# Valid workflows — should not raise
# ---------------------------------------------------------------------------

def test_single_remove_missing_is_valid():
    validate([RemoveMissingValuesStep(type="remove_missing_values")], COLUMNS)


def test_generate_summary_is_valid():
    validate([GenerateSummaryStep(type="generate_summary")], COLUMNS)


def test_select_existing_columns_is_valid():
    validate([SelectColumnsStep(type="select_columns", columns=["region", "sales"])], COLUMNS)


def test_filter_existing_column_is_valid():
    validate(
        [FilterRowsStep(type="filter_rows", column="sales", operator=">", value=1000)],
        COLUMNS,
    )


def test_group_by_existing_columns_is_valid():
    validate(
        [GroupByStep(type="group_by", column="region", target="sales", agg="sum")],
        COLUMNS,
    )


def test_sort_existing_column_is_valid():
    validate(
        [SortValuesStep(type="sort_values", column="sales", ascending=False)],
        COLUMNS,
    )


def test_rename_existing_column_is_valid():
    validate(
        [RenameColumnsStep(type="rename_columns", mapping={"sales": "total_sales"})],
        COLUMNS,
    )


def test_multi_step_workflow_is_valid():
    validate(
        [
            RemoveMissingValuesStep(type="remove_missing_values"),
            GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
            GenerateSummaryStep(type="generate_summary"),
        ],
        COLUMNS,
    )


# ---------------------------------------------------------------------------
# Invalid workflows — should raise WorkflowValidationError
# ---------------------------------------------------------------------------

def test_empty_steps_raises():
    with pytest.raises(WorkflowValidationError, match="at least one step"):
        validate([], COLUMNS)


def test_select_unknown_column_raises():
    with pytest.raises(WorkflowValidationError, match="'revenue'"):
        validate(
            [SelectColumnsStep(type="select_columns", columns=["region", "revenue"])],
            COLUMNS,
        )


def test_filter_unknown_column_raises():
    with pytest.raises(WorkflowValidationError, match="'price'"):
        validate(
            [FilterRowsStep(type="filter_rows", column="price", operator=">", value=0)],
            COLUMNS,
        )


def test_group_by_unknown_group_column_raises():
    with pytest.raises(WorkflowValidationError, match="'country'"):
        validate(
            [GroupByStep(type="group_by", column="country", target="sales", agg="sum")],
            COLUMNS,
        )


def test_group_by_unknown_target_column_raises():
    with pytest.raises(WorkflowValidationError, match="'revenue'"):
        validate(
            [GroupByStep(type="group_by", column="region", target="revenue", agg="sum")],
            COLUMNS,
        )


def test_sort_unknown_column_raises():
    with pytest.raises(WorkflowValidationError, match="'profit'"):
        validate(
            [SortValuesStep(type="sort_values", column="profit")],
            COLUMNS,
        )


def test_rename_unknown_source_column_raises():
    with pytest.raises(WorkflowValidationError, match="'cost'"):
        validate(
            [RenameColumnsStep(type="rename_columns", mapping={"cost": "expense"})],
            COLUMNS,
        )


def test_error_message_includes_step_index():
    with pytest.raises(WorkflowValidationError, match="Step 1"):
        validate(
            [
                RemoveMissingValuesStep(type="remove_missing_values"),
                SelectColumnsStep(type="select_columns", columns=["missing_col"]),
            ],
            COLUMNS,
        )
