"""Workflow validator.

Validates a list of WorkflowStep against the dataset's column names before
any execution takes place. Raises WorkflowValidationError on the first issue.
"""
import logging

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    FilterRowsStep,
    GroupByStep,
    RenameColumnsStep,
    SelectColumnsStep,
    SortValuesStep,
    WorkflowStep,
)

logger = logging.getLogger(__name__)


def validate(steps: list[WorkflowStep], column_names: list[str]) -> None:
    """Raise WorkflowValidationError if any step is invalid."""
    if not steps:
        raise WorkflowValidationError("Workflow must contain at least one step.")

    col_set = set(column_names)

    for idx, step in enumerate(steps):
        _validate_step(step, col_set, idx)

    logger.info("Workflow validated: %d steps against columns %s", len(steps), column_names)


def _validate_step(step: WorkflowStep, col_set: set[str], idx: int) -> None:
    label = f"Step {idx} ({step.type})"

    if isinstance(step, SelectColumnsStep):
        _require_columns(step.columns, col_set, label)

    elif isinstance(step, FilterRowsStep):
        _require_columns([step.column], col_set, label)

    elif isinstance(step, GroupByStep):
        _require_columns([step.column, step.target], col_set, label)

    elif isinstance(step, SortValuesStep):
        _require_columns([step.column], col_set, label)

    elif isinstance(step, RenameColumnsStep):
        _require_columns(list(step.mapping.keys()), col_set, label)


def _require_columns(cols: list[str], col_set: set[str], label: str) -> None:
    for col in cols:
        if col not in col_set:
            raise WorkflowValidationError(
                f"{label}: column '{col}' does not exist in the dataset."
            )
