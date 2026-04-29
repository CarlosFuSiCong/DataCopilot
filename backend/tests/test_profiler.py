"""Unit tests for app.services.profiler.

Each test exercises the profiler function directly with raw CSV bytes,
with no HTTP layer involved.
"""
from unittest.mock import patch

import pytest

from app.core.exceptions import InvalidDatasetError, ProfilerError
from app.services.profiler import profile

# ---------------------------------------------------------------------------
# CSV fixtures
# ---------------------------------------------------------------------------

SIMPLE_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
    b"North,1500,Feb\n"
)

CSV_WITH_MISSING = (
    b"region,sales\n"
    b"North,1200\n"
    b"South,\n"
    b"West,500\n"
)

# More than 5 rows to verify preview is capped.
LONG_CSV = b"id\n" + b"".join(f"{i}\n".encode() for i in range(10))

HEADERS_ONLY_CSV = b"region,sales,month\n"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


def test_profile_returns_correct_filename():
    result = profile(SIMPLE_CSV, "sales.csv")
    assert result.filename == "sales.csv"


def test_profile_returns_correct_row_and_column_count():
    result = profile(SIMPLE_CSV, "sales.csv")
    assert result.row_count == 3
    assert result.column_count == 3


def test_profile_column_names_match_csv_headers():
    result = profile(SIMPLE_CSV, "sales.csv")
    names = [c.name for c in result.columns]
    assert names == ["region", "sales", "month"]


def test_profile_dtype_is_non_empty_string():
    result = profile(SIMPLE_CSV, "sales.csv")
    for col in result.columns:
        assert isinstance(col.dtype, str)
        assert len(col.dtype) > 0


def test_profile_no_missing_when_csv_is_clean():
    result = profile(SIMPLE_CSV, "sales.csv")
    for col in result.columns:
        assert col.missing_count == 0
        assert col.missing_pct == 0.0


def test_profile_missing_count_detected():
    result = profile(CSV_WITH_MISSING, "data.csv")
    sales_col = next(c for c in result.columns if c.name == "sales")
    assert sales_col.missing_count == 1


def test_profile_missing_pct_calculated_correctly():
    result = profile(CSV_WITH_MISSING, "data.csv")
    # 1 missing out of 3 rows → 33.33 %
    sales_col = next(c for c in result.columns if c.name == "sales")
    assert abs(sales_col.missing_pct - 33.33) < 0.01


def test_profile_preview_limited_to_five_rows():
    result = profile(LONG_CSV, "long.csv")
    assert len(result.preview) == 5


def test_profile_preview_contains_all_columns():
    result = profile(SIMPLE_CSV, "sales.csv")
    for row in result.preview:
        assert set(row.keys()) == {"region", "sales", "month"}


def test_profile_preview_nan_replaced_with_none():
    result = profile(CSV_WITH_MISSING, "data.csv")
    # The second row has a missing sales value — it must be None, not NaN.
    missing_row = next(r for r in result.preview if r["region"] == "South")
    assert missing_row["sales"] is None


def test_profile_preview_row_count_matches_csv_when_fewer_than_five():
    result = profile(SIMPLE_CSV, "sales.csv")  # 3 rows
    assert len(result.preview) == 3


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------


def test_empty_bytes_raises_invalid_dataset_error():
    with pytest.raises(InvalidDatasetError, match="empty"):
        profile(b"", "empty.csv")


def test_headers_only_csv_raises_invalid_dataset_error():
    with pytest.raises(InvalidDatasetError, match="no data rows"):
        profile(HEADERS_ONLY_CSV, "headers.csv")


def test_parse_failure_raises_profiler_error():
    import pandas as pd

    with patch("app.services.profiler.pd.read_csv", side_effect=pd.errors.ParserError("bad")):
        with pytest.raises(ProfilerError, match="Could not parse CSV"):
            profile(b"some bytes", "broken.csv")
