"""Tests for Task 9 workflow capability expansion.

Covers:
  - limit_rows
  - group_by multi-column
  - derive_column
  - date_extract
  - drop_columns
  - fill_missing_values
  - validator rules for each new step type
"""
import pytest

from app.core.exceptions import ExecutionError, WorkflowValidationError
from app.models.workflow import (
    DateExtractStep,
    DeriveColumnStep,
    DropColumnsStep,
    FillMissingValuesStep,
    GroupByStep,
    LimitRowsStep,
    SortValuesStep,
)
from app.agent.execution.executor import execute
from app.agent.execution.validator import validate

# ---------------------------------------------------------------------------
# CSV fixtures
# ---------------------------------------------------------------------------

BASE_CSV = (
    b"region,category,sales,date\n"
    b"North,A,1200,2024-01-15\n"
    b"South,B,850,2024-02-20\n"
    b"North,B,1500,2024-03-10\n"
    b"South,A,900,2024-04-05\n"
    b"West,A,700,2024-01-22\n"
)

COLUMNS = ["region", "category", "sales", "date"]


# ===========================================================================
# limit_rows
# ===========================================================================

def test_limit_rows_keeps_n_rows():
    result = execute([LimitRowsStep(type="limit_rows", n=3)], BASE_CSV)
    assert result.row_count == 3


def test_limit_rows_larger_than_dataset():
    result = execute([LimitRowsStep(type="limit_rows", n=100)], BASE_CSV)
    assert result.row_count == 5


def test_limit_rows_after_sort():
    steps = [
        SortValuesStep(type="sort_values", column="sales", ascending=False),
        LimitRowsStep(type="limit_rows", n=2),
    ]
    result = execute(steps, BASE_CSV)
    assert result.row_count == 2
    top_sales = [row["sales"] for row in result.preview]
    assert top_sales[0] >= top_sales[1]


def test_limit_rows_validator_rejects_zero():
    with pytest.raises(WorkflowValidationError, match="positive integer"):
        validate([LimitRowsStep(type="limit_rows", n=0)], COLUMNS)


def test_limit_rows_validator_rejects_negative():
    with pytest.raises(WorkflowValidationError, match="positive integer"):
        validate([LimitRowsStep(type="limit_rows", n=-5)], COLUMNS)


# ===========================================================================
# group_by multi-column
# ===========================================================================

def test_group_by_single_column_unchanged():
    result = execute(
        [GroupByStep(type="group_by", column="region", target="sales", agg="sum")],
        BASE_CSV,
    )
    assert result.row_count == 3  # North, South, West


def test_group_by_multi_column():
    result = execute(
        [GroupByStep(
            type="group_by",
            column="region",
            columns=["region", "category"],
            target="sales",
            agg="sum",
        )],
        BASE_CSV,
    )
    # 5 combinations: North/A, South/B, North/B, South/A, West/A
    assert result.row_count == 5


def test_group_by_multi_column_count():
    result = execute(
        [GroupByStep(
            type="group_by",
            column="region",
            columns=["region", "category"],
            target="sales",
            agg="count",
        )],
        BASE_CSV,
    )
    assert "region" in result.columns
    assert "category" in result.columns


def test_group_by_multi_column_validator_rejects_missing():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [GroupByStep(
                type="group_by",
                column="region",
                columns=["region", "nonexistent"],
                target="sales",
                agg="sum",
            )],
            COLUMNS,
        )


# ===========================================================================
# derive_column
# ===========================================================================

def test_derive_column_constant_multiply():
    result = execute(
        [DeriveColumnStep(
            type="derive_column",
            new_column="sales_tax",
            column="sales",
            operator="*",
            value=0.1,
        )],
        BASE_CSV,
    )
    assert "sales_tax" in result.columns
    assert result.column_count == 5


def test_derive_column_add_constant():
    result = execute(
        [DeriveColumnStep(
            type="derive_column",
            new_column="sales_plus_100",
            column="sales",
            operator="+",
            value=100,
        )],
        BASE_CSV,
    )
    first = result.preview[0]
    assert first["sales_plus_100"] == first["sales"] + 100


def test_derive_column_other_column():
    csv = b"a,b\n1,2\n3,4\n"
    result = execute(
        [DeriveColumnStep(
            type="derive_column",
            new_column="sum_ab",
            column="a",
            operator="+",
            other_column="b",
        )],
        csv,
    )
    assert result.preview[0]["sum_ab"] == 3
    assert result.preview[1]["sum_ab"] == 7


def test_derive_column_validator_rejects_missing_column():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [DeriveColumnStep(
                type="derive_column",
                new_column="x",
                column="nonexistent",
                operator="+",
                value=1,
            )],
            COLUMNS,
        )


def test_derive_column_validator_rejects_no_operand():
    with pytest.raises(WorkflowValidationError, match="value.*other_column"):
        validate(
            [DeriveColumnStep(
                type="derive_column",
                new_column="x",
                column="sales",
                operator="+",
            )],
            COLUMNS,
        )


def test_derive_column_validator_rejects_both_operands():
    with pytest.raises(WorkflowValidationError, match="exactly one"):
        validate(
            [DeriveColumnStep(
                type="derive_column",
                new_column="x",
                column="sales",
                operator="+",
                value=10.0,
                other_column="sales",
            )],
            COLUMNS,
        )


# ===========================================================================
# date_extract
# ===========================================================================

def test_date_extract_month():
    result = execute(
        [DateExtractStep(
            type="date_extract",
            column="date",
            part="month",
            new_column="order_month",
        )],
        BASE_CSV,
    )
    assert "order_month" in result.columns
    months = [row["order_month"] for row in result.preview]
    assert months[0] == 1   # 2024-01-15 → January
    assert months[1] == 2   # 2024-02-20 → February


def test_date_extract_year():
    result = execute(
        [DateExtractStep(
            type="date_extract",
            column="date",
            part="year",
            new_column="order_year",
        )],
        BASE_CSV,
    )
    years = [row["order_year"] for row in result.preview]
    assert all(y == 2024 for y in years)


def test_date_extract_quarter():
    result = execute(
        [DateExtractStep(
            type="date_extract",
            column="date",
            part="quarter",
            new_column="order_quarter",
        )],
        BASE_CSV,
    )
    quarters = [row["order_quarter"] for row in result.preview]
    assert quarters[0] == 1  # Jan → Q1
    assert quarters[2] == 1  # Mar → Q1
    assert quarters[3] == 2  # Apr → Q2


def test_date_extract_validator_rejects_missing_column():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [DateExtractStep(
                type="date_extract",
                column="nonexistent",
                part="year",
                new_column="yr",
            )],
            COLUMNS,
        )


def test_date_extract_unparseable_column_raises():
    csv = b"col\nabc\ndef\n"
    with pytest.raises(ExecutionError, match="could not parse"):
        execute(
            [DateExtractStep(
                type="date_extract",
                column="col",
                part="year",
                new_column="yr",
            )],
            csv,
        )


# ===========================================================================
# drop_columns
# ===========================================================================

def test_drop_columns_removes_listed_columns():
    result = execute(
        [DropColumnsStep(type="drop_columns", columns=["region", "category"])],
        BASE_CSV,
    )
    assert "region" not in result.columns
    assert "category" not in result.columns
    assert result.column_count == 2  # sales, date remain


def test_drop_columns_single_column():
    result = execute(
        [DropColumnsStep(type="drop_columns", columns=["date"])],
        BASE_CSV,
    )
    assert "date" not in result.columns
    assert result.column_count == 3
    assert result.row_count == 5


def test_drop_columns_preserves_row_count():
    result = execute(
        [DropColumnsStep(type="drop_columns", columns=["sales"])],
        BASE_CSV,
    )
    assert result.row_count == 5


def test_drop_columns_validator_rejects_missing_column():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [DropColumnsStep(type="drop_columns", columns=["nonexistent"])],
            COLUMNS,
        )


def test_drop_columns_validator_rejects_empty_list():
    with pytest.raises(WorkflowValidationError, match="must not be empty"):
        validate(
            [DropColumnsStep(type="drop_columns", columns=[])],
            COLUMNS,
        )


# ===========================================================================
# fill_missing_values
# ===========================================================================

MISSING_CSV = (
    b"name,score,region\n"
    b"Alice,90,North\n"
    b"Bob,,South\n"
    b"Carol,80,\n"
    b"Dave,,North\n"
    b"Eve,70,South\n"
)

MISSING_COLUMNS = ["name", "score", "region"]


def test_fill_missing_values_constant_numeric():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="score",
            strategy="constant",
            value=0,
        )],
        MISSING_CSV,
    )
    scores = [row["score"] for row in result.preview]
    assert scores[1] == 0
    assert scores[3] == 0


def test_fill_missing_values_mean():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="score",
            strategy="mean",
        )],
        MISSING_CSV,
    )
    # mean of [90, 80, 70] = 80.0
    scores = [row["score"] for row in result.preview]
    assert scores[1] == 80.0
    assert scores[3] == 80.0


def test_fill_missing_values_median():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="score",
            strategy="median",
        )],
        MISSING_CSV,
    )
    # median of [90, 80, 70] = 80.0
    scores = [row["score"] for row in result.preview]
    assert scores[1] == 80.0


def test_fill_missing_values_mode_categorical():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="region",
            strategy="mode",
        )],
        MISSING_CSV,
    )
    # mode of [North, South, North, South] → North or South (both 2); fillna uses first mode
    regions = [row["region"] for row in result.preview]
    assert regions[2] is not None


def test_fill_missing_values_constant_string():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="region",
            strategy="constant",
            value="Unknown",
        )],
        MISSING_CSV,
    )
    regions = [row["region"] for row in result.preview]
    assert regions[2] == "Unknown"


def test_fill_missing_values_ffill():
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="score",
            strategy="ffill",
        )],
        MISSING_CSV,
    )
    # row 1 (Bob): ffill from Alice=90
    scores = [row["score"] for row in result.preview]
    assert scores[1] == 90.0


def test_fill_missing_values_no_op_when_no_missing():
    csv = b"a,b\n1,2\n3,4\n"
    result = execute(
        [FillMissingValuesStep(
            type="fill_missing_values",
            column="a",
            strategy="mean",
        )],
        csv,
    )
    assert result.row_count == 2
    assert "nothing to fill" in result.step_results[0].message


def test_fill_missing_values_validator_rejects_missing_column():
    with pytest.raises(WorkflowValidationError, match="does not exist"):
        validate(
            [FillMissingValuesStep(
                type="fill_missing_values",
                column="nonexistent",
                strategy="mean",
            )],
            MISSING_COLUMNS,
        )


def test_fill_missing_values_validator_rejects_constant_without_value():
    with pytest.raises(WorkflowValidationError, match="requires a 'value'"):
        validate(
            [FillMissingValuesStep(
                type="fill_missing_values",
                column="score",
                strategy="constant",
            )],
            MISSING_COLUMNS,
        )

