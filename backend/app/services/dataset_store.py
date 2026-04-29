"""In-memory store for uploaded CSV content.

Keyed by dataset_id (UUID string). Supports one active dataset per id.
Single-process only — sufficient for the MVP's single-user scope.
"""
import logging

from app.core.exceptions import DatasetNotFoundError

logger = logging.getLogger(__name__)

_store: dict[str, bytes] = {}


def save(dataset_id: str, content: bytes) -> None:
    _store[dataset_id] = content
    logger.info("Stored dataset '%s' (%d bytes)", dataset_id, len(content))


def load(dataset_id: str) -> bytes:
    if dataset_id not in _store:
        raise DatasetNotFoundError(f"Dataset '{dataset_id}' not found. Please upload first.")
    return _store[dataset_id]


def exists(dataset_id: str) -> bool:
    return dataset_id in _store
