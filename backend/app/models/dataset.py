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
