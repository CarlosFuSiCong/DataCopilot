import io
import logging
import math

import pandas as pd

from app.core.exceptions import InvalidDatasetError, ProfilerError
from app.models.dataset import ColumnProfile, DatasetProfile

logger = logging.getLogger(__name__)

_PREVIEW_ROWS = 5


def profile(content: bytes, filename: str) -> DatasetProfile:
    """Read a CSV file from raw bytes and return a DatasetProfile.

    Raises InvalidDatasetError for empty files.
    Raises ProfilerError when pandas cannot parse the content.
    """
    if not content:
        raise InvalidDatasetError("Uploaded file is empty.")

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        logger.warning("Failed to parse CSV '%s': %s", filename, exc)
        raise ProfilerError(f"Could not parse CSV: {exc}") from exc

    if df.empty:
        raise InvalidDatasetError("CSV file contains no data rows.")

    row_count, column_count = df.shape

    columns = [
        ColumnProfile(
            name=col,
            dtype=str(df[col].dtype),
            missing_count=int(df[col].isna().sum()),
            missing_pct=_round(df[col].isna().mean() * 100),
        )
        for col in df.columns
    ]

    # Serialise preview rows; replace NaN with None so JSON stays valid.
    # DataFrame.where keeps NaN in numeric columns even when other=None,
    # so we walk the records manually.
    raw_preview = df.head(_PREVIEW_ROWS).to_dict(orient="records")
    preview = [
        {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items()}
        for row in raw_preview
    ]

    logger.info("Profiled '%s': %d rows, %d columns", filename, row_count, column_count)
    return DatasetProfile(
        filename=filename,
        row_count=row_count,
        column_count=column_count,
        columns=columns,
        preview=preview,
    )


def _round(value: float) -> float:
    return round(value, 2) if not math.isnan(value) else 0.0
