"""Tests for MVP4 workflow and observation tools."""
import pandas as pd
import pytest

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    BinColumnStep,
    CastColumnStep,
    ConditionalColumnStep,
    DateDiffStep,
    DeduplicateRowsStep,
    ExtractTextStep,
    NormalizeTextStep,
    PivotTableStep,
    ReplaceValuesStep,
    SortValuesStep,
    TrimTextStep,
)
from app.agent.execution.executor import execute
from app.agent.observation.observations import (
    detect_duplicates,
    detect_missing_values,
    detect_outliers,
    observation_tools,
    suggest_cleaning_steps,
)
from app.agent.validation.workflow_validator import validate


BASE_CSV = (
    b"customer_id,region,category,status,amount,quantity\n"
    b"1,North,A,pending,1200,2\n"
    b"1,North,A,pending,1200,2\n"
    b"2,South,B,done,850,1\n"
    b"3,West,A,,50,5\n"
    b"4,West,B,done,3000,3\n"
)

COLUMNS = ["customer_id", "region", "category", "status", "amount", "quantity"]


def test_deduplicate_rows_all_columns_removes_duplicate():
    result = execute([DeduplicateRowsStep(type="deduplicate_rows")], BASE_CSV)

    assert result.row_count == 4
    assert "Removed 1 duplicate" in result.logs[0].message


def test_deduplicate_rows_subset_validates_columns():
    with pytest.raises(WorkflowValidationError, match="missing"):
        validate(
            [DeduplicateRowsStep(type="deduplicate_rows", columns=["missing"])],
            COLUMNS,
        )


def test_replace_values_supports_string_mapping():
    result = execute(
        [ReplaceValuesStep(type="replace_values", column="status", mapping={"pending": "open"})],
        BASE_CSV,
    )

    statuses = [row["status"] for row in result.preview]
    assert "open" in statuses
    assert "pending" not in statuses


def test_replace_values_supports_numeric_mapping():
    result = execute(
        [ReplaceValuesStep(type="replace_values", column="amount", mapping={50: 100})],
        BASE_CSV,
    )

    amounts = [row["amount"] for row in result.preview]
    assert 100 in amounts
    assert 50 not in amounts


def test_replace_values_changed_count_ignores_unchanged_missing_values():
    csv = b"status\npending\n\npending\n"
    result = execute(
        [ReplaceValuesStep(type="replace_values", column="status", mapping={"pending": "open"})],
        csv,
    )

    assert result.logs[0].message == "Replaced 2 value(s) in 'status'."


def test_cast_column_to_float():
    result = execute(
        [CastColumnStep(type="cast_column", column="amount", target_type="float")],
        BASE_CSV,
    )

    assert result.row_count == 5
    assert result.columns == COLUMNS


def test_conditional_column_adds_new_flag():
    result = execute(
        [ConditionalColumnStep(
            type="conditional_column",
            new_column="is_large",
            condition_column="amount",
            operator=">",
            value=1000,
            true_value=True,
            false_value=False,
        )],
        BASE_CSV,
    )

    assert "is_large" in result.columns
    assert result.preview[0]["is_large"] is True


def test_bin_column_adds_labeled_band():
    result = execute(
        [BinColumnStep(
            type="bin_column",
            column="amount",
            new_column="amount_band",
            bins=[0, 1000, 5000],
            labels=["small", "large"],
        )],
        BASE_CSV,
    )

    assert "amount_band" in result.columns
    assert result.preview[0]["amount_band"] == "large"


def test_bin_column_rejects_mismatched_labels():
    with pytest.raises(WorkflowValidationError, match="labels length"):
        validate(
            [BinColumnStep(
                type="bin_column",
                column="amount",
                new_column="amount_band",
                bins=[0, 1000, 5000],
                labels=["small"],
            )],
            COLUMNS,
        )


def test_bin_column_rejects_duplicate_bins_before_execution():
    with pytest.raises(WorkflowValidationError, match="strictly increasing"):
        validate(
            [BinColumnStep(
                type="bin_column",
                column="amount",
                new_column="amount_band",
                bins=[0, 1000, 1000, 5000],
            )],
            COLUMNS,
        )


def test_pivot_table_groups_and_flattens_columns():
    result = execute(
        [PivotTableStep(
            type="pivot_table",
            index=["region"],
            columns="category",
            values="amount",
            agg="sum",
        )],
        BASE_CSV,
    )

    assert "region" in result.columns
    assert "A" in result.columns
    assert result.row_count == 3


def test_pivot_table_removes_values_column_from_validation_state():
    steps = [
        PivotTableStep(
            type="pivot_table",
            index=["region"],
            columns="category",
            values="amount",
            agg="sum",
        ),
        SortValuesStep(type="sort_values", column="amount"),
    ]

    with pytest.raises(WorkflowValidationError, match="'amount'"):
        validate(steps, COLUMNS)


def test_trim_text_strips_and_collapses_whitespace():
    csv = b"customer_name\n  Alice   Smith  \nBob\n"
    result = execute(
        [TrimTextStep(type="trim_text", column="customer_name", collapse_whitespace=True)],
        csv,
    )

    assert result.preview[0]["customer_name"] == "Alice Smith"
    assert result.logs[0].message == "Trimmed text in 'customer_name' for 1 row(s)."


def test_normalize_text_lowercases_column():
    csv = b"status\nPending\nDONE\n"
    result = execute(
        [NormalizeTextStep(type="normalize_text", column="status", case="lower")],
        csv,
    )

    assert [row["status"] for row in result.preview] == ["pending", "done"]


def test_extract_text_adds_new_column_with_no_match_value():
    csv = b"order_code\nABC-123\nmissing\n"
    result = execute(
        [ExtractTextStep(
            type="extract_text",
            column="order_code",
            pattern=r"([A-Z]+)-\d+",
            new_column="order_prefix",
            group=1,
            no_match="unknown",
        )],
        csv,
    )

    assert "order_prefix" in result.columns
    assert [row["order_prefix"] for row in result.preview] == ["ABC", "unknown"]


def test_extract_text_validates_regex_group_before_execution():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [ExtractTextStep(
                type="extract_text",
                column="category",
                pattern=r"([A-Z]+)",
                new_column="category_prefix",
                group=2,
            )],
            COLUMNS,
        )


def test_date_diff_adds_day_difference_column():
    csv = b"order_date,ship_date\n2024-01-01,2024-01-04\n2024-02-10,2024-02-10\n"
    result = execute(
        [DateDiffStep(
            type="date_diff",
            start_column="order_date",
            end_column="ship_date",
            new_column="ship_days",
        )],
        csv,
    )

    assert [row["ship_days"] for row in result.preview] == [3, 0]


def test_date_diff_coerce_outputs_missing_for_bad_dates():
    csv = b"order_date,ship_date\nbad-date,2024-01-04\n2024-02-10,2024-02-12\n"
    result = execute(
        [DateDiffStep(
            type="date_diff",
            start_column="order_date",
            end_column="ship_date",
            new_column="ship_days",
            errors="coerce",
        )],
        csv,
    )

    assert pd.isna(result.preview[0]["ship_days"])
    assert result.preview[1]["ship_days"] == 2


def test_date_diff_validates_both_date_columns():
    with pytest.raises(WorkflowValidationError, match="'missing_ship_date'"):
        validate(
            [DateDiffStep(
                type="date_diff",
                start_column="customer_id",
                end_column="missing_ship_date",
                new_column="ship_days",
            )],
            COLUMNS,
        )


def test_observation_tools_are_separate_from_workflow_json():
    specs = observation_tools()

    assert specs
    assert all(spec.enters_workflow_json is False for spec in specs)


def test_detect_missing_values_reports_columns():
    df = pd.DataFrame({"a": [1, None], "b": ["x", "y"]})

    result = detect_missing_values(df)

    assert result["columns"][0]["column"] == "a"
    assert result["columns"][0]["missing_count"] == 1


def test_detect_duplicates_reports_duplicate_count():
    df = pd.DataFrame({"a": [1, 1, 2]})

    result = detect_duplicates(df)

    assert result["duplicate_count"] == 1


def test_detect_outliers_reports_numeric_outlier():
    df = pd.DataFrame({"x": [10, 11, 12, 13, 1000]})

    result = detect_outliers(df)

    assert result["columns"][0]["column"] == "x"
    assert result["columns"][0]["outlier_count"] == 1


def test_suggest_cleaning_steps_returns_workflow_suggestions():
    df = pd.DataFrame({"a": [1, None], "b": ["x", "x"]})

    result = suggest_cleaning_steps(df)

    assert result["suggestions"]
    assert result["suggestions"][0]["step"]["type"] == "fill_missing_values"
