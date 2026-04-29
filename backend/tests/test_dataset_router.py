"""Integration tests for the dataset upload router.

Uses FastAPI's TestClient (backed by httpx) to exercise the full HTTP
layer: routing, file parsing, error handling, and response schema.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_CSV = (
    b"region,sales,month\n"
    b"North,1200,Jan\n"
    b"South,850,Jan\n"
)

CSV_WITH_MISSING = (
    b"region,sales\n"
    b"North,1200\n"
    b"South,\n"
)


# ---------------------------------------------------------------------------
# Health check (smoke test — confirms the app boots correctly)
# ---------------------------------------------------------------------------


def test_health_check_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Successful upload
# ---------------------------------------------------------------------------


def test_upload_valid_csv_returns_200():
    response = _upload(VALID_CSV, "sales.csv")
    assert response.status_code == 200


def test_upload_response_contains_profile_key():
    response = _upload(VALID_CSV, "sales.csv")
    assert "profile" in response.json()


def test_upload_response_profile_has_correct_row_count():
    data = _upload(VALID_CSV, "sales.csv").json()
    assert data["profile"]["row_count"] == 2


def test_upload_response_profile_has_correct_column_count():
    data = _upload(VALID_CSV, "sales.csv").json()
    assert data["profile"]["column_count"] == 3


def test_upload_response_profile_columns_list_length():
    data = _upload(VALID_CSV, "sales.csv").json()
    assert len(data["profile"]["columns"]) == 3


def test_upload_response_preview_is_list():
    data = _upload(VALID_CSV, "sales.csv").json()
    assert isinstance(data["profile"]["preview"], list)


def test_upload_response_filename_matches_uploaded_name():
    data = _upload(VALID_CSV, "my_data.csv").json()
    assert data["profile"]["filename"] == "my_data.csv"


def test_upload_missing_values_reflected_in_profile():
    data = _upload(CSV_WITH_MISSING, "partial.csv").json()
    sales_col = next(c for c in data["profile"]["columns"] if c["name"] == "sales")
    assert sales_col["missing_count"] == 1


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_upload_non_csv_extension_returns_400():
    response = _upload(VALID_CSV, "report.txt")
    assert response.status_code == 400


def test_upload_non_csv_extension_returns_error_message():
    response = _upload(VALID_CSV, "report.txt")
    assert "error" in response.json()


def test_upload_empty_file_returns_400():
    response = _upload(b"", "empty.csv")
    assert response.status_code == 400


def test_upload_headers_only_csv_returns_400():
    response = _upload(b"region,sales\n", "headers.csv")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upload(content: bytes, filename: str):
    return client.post(
        "/api/datasets/upload",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )
