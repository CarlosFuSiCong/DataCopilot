"""Tests for Task 9 workflow capability expansion.

Covers:
  - limit_rows
  - group_by multi-column
  - derive_column
  - date_extract
  - validator rules for each new step type
"""
import pytest

from app.core.exceptions import ExecutionError, WorkflowValidationError
from app.models.workflow import (
    DateExtractStep,
    DeriveColumnStep,
    GroupByStep,
    LimitRowsStep,
    SortValuesStep,
)
from app.services.executor import execute
from app.services.validator import validate

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
