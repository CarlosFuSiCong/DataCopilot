from datetime import datetime

from pydantic import BaseModel


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    missing_count: int
    missing_pct: float


class DatasetProfile(BaseModel):
    filename: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    # First 5 rows serialised as records for the preview panel
    preview: list[dict]


class UploadResponse(BaseModel):
    dataset_id: str
    profile: DatasetProfile


class DatasetRowsResponse(BaseModel):
    rows: list[dict]
    total_rows: int
    offset: int
    limit: int


class DiffRowsResponse(BaseModel):
    rows: list[dict]          # original rows, each has a "_kept" bool field
    total_original: int
    total_result: int
    offset: int
    limit: int


class DatasetRecord(BaseModel):
    """Mirrors the `datasets` table in Postgres.

    Raw CSV content is not stored here.
    storage_uri points to the actual file: local://datasets/{id}/raw.csv
    user_id is nullable; reserved for future multi-user support (no FK in MVP3).
    """

    id: str
    user_id: str | None = None
    filename: str
    storage_backend: str = "local"
    storage_uri: str
    content_type: str = "text/csv"
    size_bytes: int | None = None
    row_count: int | None = None
    column_count: int | None = None
    profile_json: dict | None = None
    created_at: datetime
