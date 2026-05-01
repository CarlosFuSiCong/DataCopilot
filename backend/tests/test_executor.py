"""Unit tests for app.services.executor."""
import pytest

from app.core.exceptions import ExecutionError
from app.models.workflow import (
    FilterRowsStep,
    GenerateSummaryStep,
    GroupByStep,
    RemoveMissingValuesStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
)
from app.services.executor import execute

# ---------------------------------------------------------------------------
# CSV fixtures
# ---------------------------------------------------------------------------

BASE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
    b"South,900,Feb\n"
    b"West,,Feb\n"
)


# ---------------------------------------------------------------------------
# remove_missing_values
# ---------------------------------------------------------------------------

def test_remove_missing_drops_rows_with_nan():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    assert result.row_count == 4


def test_remove_missing_log_message_mentions_removed_count():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    assert "1" in result.logs[0].message


# ---------------------------------------------------------------------------
# select_columns
# ---------------------------------------------------------------------------

def test_select_columns_keeps_only_specified():
    result = execute(
        [SelectColumnsStep(type="select_columns", columns=["region", "sales"])],
        BASE_CSV,
    )
    assert result.columns == ["region", "sales"]
    assert result.column_count == 2


def test_select_columns_preserves_row_count():
    result = execute(
        [SelectColumnsStep(type="select_columns", columns=["region"])],
        BASE_CSV,
    )
    assert result.row_count == 5


# ---------------------------------------------------------------------------
# filter_rows
# ---------------------------------------------------------------------------

def test_filter_greater_than_keeps_matching_rows():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="sales", operator=">", value=1000)],
        BASE_CSV,
    )
    assert result.row_count == 2


def test_filter_equal_operator():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="region", operator="=", value="North")],
        BASE_CSV,
    )
    assert result.row_count == 2


def test_filter_not_equal_operator():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="region", operator="!=", value="North")],
        BASE_CSV,
    )
    assert result.row_count == 3


def test_filter_less_than_or_equal():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="sales", operator="<=", value=900)],
        BASE_CSV,
    )
    assert result.row_count == 2


# ---------------------------------------------------------------------------
# group_by
# ---------------------------------------------------------------------------

def test_group_by_sum_produces_one_row_per_group():
    result = execute(
        [GroupByStep(type="group_by", column="region", target="sales", agg="sum")],
        BASE_CSV,
    )
    # North, South, West → 3 groups
    assert result.row_count == 3


def test_group_by_sum_aggregates_correctly():
    result = execute(
        [GroupByStep(type="group_by", column="region", target="sales", agg="sum")],
        BASE_CSV,
    )
    north_row = next(r for r in result.preview if r["region"] == "North")
    assert north_row["sales"] == pytest.approx(2700.0)


def test_group_by_mean_agg():
    result = execute(
        [GroupByStep(type="group_by", column="region", target="sales", agg="mean")],
        BASE_CSV,
    )
    north_row = next(r for r in result.preview if r["region"] == "North")
    assert north_row["sales"] == pytest.approx(1350.0)


def test_group_by_count_agg():
    result = execute(
        [GroupByStep(type="group_by", column="region", target="sales", agg="count")],
        BASE_CSV,
    )
    assert result.column_count == 2


# ---------------------------------------------------------------------------
# sort_values
# ---------------------------------------------------------------------------

def test_sort_descending_first_row_is_max():
    result = execute(
        [SortValuesStep(type="sort_values", column="sales", ascending=False)],
        BASE_CSV,
    )
    assert result.preview[0]["sales"] == pytest.approx(1500.0)


def test_sort_ascending_first_row_is_min():
    result = execute(
        [SortValuesStep(type="sort_values", column="sales", ascending=True)],
        BASE_CSV,
    )
    # NaN sorts last with pandas default; first non-NaN min is 850
    assert result.preview[0]["sales"] == pytest.approx(850.0)


# ---------------------------------------------------------------------------
# rename_columns
# ---------------------------------------------------------------------------

def test_rename_changes_column_name():
    result = execute(
        [RenameColumnsStep(type="rename_columns", mapping={"sales": "total_sales"})],
        BASE_CSV,
    )
    assert "total_sales" in result.columns
    assert "sales" not in result.columns


# ---------------------------------------------------------------------------
# generate_summary
# ---------------------------------------------------------------------------

def test_generate_summary_sets_has_summary_flag():
    result = execute([GenerateSummaryStep(type="generate_summary")], BASE_CSV)
    assert result.has_summary is True


def test_generate_summary_does_not_change_data():
    result = execute([GenerateSummaryStep(type="generate_summary")], BASE_CSV)
    assert result.row_count == 5


def test_workflow_without_summary_has_summary_false():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    assert result.has_summary is False


# ---------------------------------------------------------------------------
# Multi-step workflows
# ---------------------------------------------------------------------------

def test_chained_steps_apply_in_order():
    result = execute(
        [
            RemoveMissingValuesStep(type="remove_missing_values"),
            GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
            SortValuesStep(type="sort_values", column="sales", ascending=False),
        ],
        BASE_CSV,
    )
    # North (2700) should come first after sorting descending
    assert result.preview[0]["region"] == "North"


def test_step_logs_count_matches_step_count():
    steps = [
        RemoveMissingValuesStep(type="remove_missing_values"),
        GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
    ]
    result = execute(steps, BASE_CSV)
    assert len(result.logs) == 2


def test_step_log_records_rows_before_and_after():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    log = result.logs[0]
    assert log.rows_before == 5
    assert log.rows_after == 4


def test_step_results_count_matches_step_count():
    steps = [
        RemoveMissingValuesStep(type="remove_missing_values"),
        GroupByStep(type="group_by", column="region", target="sales", agg="sum"),
    ]
    result = execute(steps, BASE_CSV)
    assert len(result.step_results) == 2


def test_step_result_records_row_and_column_counts():
    result = execute(
        [SelectColumnsStep(type="select_columns", columns=["region", "sales"])],
        BASE_CSV,
    )
    step_result = result.step_results[0]
    assert step_result.input_row_count == 5
    assert step_result.output_row_count == 5
    assert step_result.input_column_count == 3
    assert step_result.output_column_count == 2


def test_filter_step_result_records_match_rate():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="sales", operator=">", value=1000)],
        BASE_CSV,
    )
    assert result.step_results[0].match_rate == pytest.approx(2 / 5)


def test_remove_missing_step_result_records_affected_rate():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    assert result.step_results[0].affected_rate == pytest.approx(1 / 5)


def test_step_result_includes_preview():
    result = execute(
        [FilterRowsStep(type="filter_rows", column="region", operator="=", value="North")],
        BASE_CSV,
    )
    assert result.step_results[0].preview == result.preview


def test_step_result_defaults_to_success_without_issues():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    step_result = result.step_results[0]
    assert step_result.status == "success"
    assert step_result.issues == []


def test_select_columns_affected_rate_is_none():
    result = execute(
        [SelectColumnsStep(type="select_columns", columns=["region"])],
        BASE_CSV,
    )
    assert result.step_results[0].affected_rate is None


def test_rename_columns_affected_rate_is_none():
    result = execute(
        [RenameColumnsStep(type="rename_columns", mapping={"sales": "revenue"})],
        BASE_CSV,
    )
    assert result.step_results[0].affected_rate is None


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def test_preview_is_list_of_dicts():
    result = execute([RemoveMissingValuesStep(type="remove_missing_values")], BASE_CSV)
    assert isinstance(result.preview, list)
    assert all(isinstance(r, dict) for r in result.preview)


def test_preview_nan_replaced_with_none():
    result = execute([], BASE_CSV)
    west_row = next((r for r in result.preview if r.get("region") == "West"), None)
    if west_row:
        assert west_row["sales"] is None
