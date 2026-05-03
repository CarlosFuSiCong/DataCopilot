"""Workflow validator.

Validates a list of WorkflowStep against the dataset's column names before
any execution takes place. Raises WorkflowValidationError on the first issue.
"""
import logging

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    DateExtractStep,
    DeriveColumnStep,
    FilterRowsStep,
    GroupByStep,
    LimitRowsStep,
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
        group_cols = step.columns if step.columns else [step.column]
        _require_columns(group_cols + [step.target], col_set, label)

    elif isinstance(step, SortValuesStep):
        _require_columns([step.column], col_set, label)

    elif isinstance(step, RenameColumnsStep):
        _require_columns(list(step.mapping.keys()), col_set, label)

    elif isinstance(step, LimitRowsStep):
        if step.n <= 0:
            raise WorkflowValidationError(
                f"{label}: n must be a positive integer, got {step.n}."
            )

    elif isinstance(step, DeriveColumnStep):
        _require_columns([step.column], col_set, label)
        if step.other_column:
            _require_columns([step.other_column], col_set, label)
        if step.value is not None and step.other_column:
            raise WorkflowValidationError(
                f"{label}: derive_column requires exactly one of 'value' or 'other_column', not both."
            )
        if step.value is None and not step.other_column:
            raise WorkflowValidationError(
                f"{label}: derive_column requires either 'value' or 'other_column'."
            )

    elif isinstance(step, DateExtractStep):
        _require_columns([step.column], col_set, label)


def _require_columns(cols: list[str], col_set: set[str], label: str) -> None:
    for col in cols:
        if col not in col_set:
            raise WorkflowValidationError(
                f"{label}: column '{col}' does not exist in the dataset."
            )
