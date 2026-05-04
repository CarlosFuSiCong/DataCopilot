"""Workflow validator.

Validates a list of WorkflowStep against the dataset's column names before
any execution takes place. Raises WorkflowValidationError on the first issue.

Column state is tracked across steps: each step is validated against the
columns that exist *after* all previous steps have run, not the original
column set. This ensures chained workflows (e.g. select_columns followed by
filter_rows) are validated correctly.
"""
import logging

from app.core.exceptions import WorkflowValidationError
from app.models.workflow import (
    DateExtractStep,
    DeriveColumnStep,
    DropColumnsStep,
    FillMissingValuesStep,
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
    """Raise WorkflowValidationError if any step is invalid.

    Column state is propagated between steps so that each step is checked
    against the columns that actually exist at that point in the workflow.
    """
    if not steps:
        raise WorkflowValidationError("Workflow must contain at least one step.")

    col_set = set(column_names)

    for idx, step in enumerate(steps):
        _validate_step(step, col_set, idx)
        col_set = _advance_columns(step, col_set)

    logger.info("Workflow validated: %d steps against columns %s", len(steps), column_names)


def simulate_columns(steps: list[WorkflowStep], initial_column_names: list[str]) -> list[str]:
    """Return the column names that would exist after running all steps.

    Used externally (e.g. chat endpoint) to compute the intermediate column
    state for chained workflow validation and error context.
    """
    col_set = set(initial_column_names)
    for step in steps:
        col_set = _advance_columns(step, col_set)
    return sorted(col_set)


def _advance_columns(step: WorkflowStep, col_set: set[str]) -> set[str]:
    """Return the updated column set after this step executes.

    Only steps that structurally change columns (add, remove, rename) need
    explicit handling; all others leave the column set unchanged.
    """
    if isinstance(step, SelectColumnsStep):
        # Only the requested columns survive.
        return set(step.columns)

    if isinstance(step, DropColumnsStep):
        return col_set - set(step.columns)

    if isinstance(step, RenameColumnsStep):
        return {step.mapping.get(c, c) for c in col_set}

    if isinstance(step, DeriveColumnStep):
        # Adds new_column; existing columns are preserved.
        return col_set | {step.new_column}

    if isinstance(step, DateExtractStep):
        return col_set | {step.new_column}

    if isinstance(step, GroupByStep):
        # The aggregation collapses all other columns; result contains only
        # the grouping keys and the aggregated target column.
        group_cols = set(step.columns) if step.columns else {step.column}
        return group_cols | {step.target}

    # filter_rows, sort_values, limit_rows, remove_missing_values,
    # fill_missing_values, generate_summary — no structural column change.
    return col_set


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

    elif isinstance(step, DropColumnsStep):
        if not step.columns:
            raise WorkflowValidationError(f"{label}: columns list must not be empty.")
        _require_columns(step.columns, col_set, label)

    elif isinstance(step, FillMissingValuesStep):
        _require_columns([step.column], col_set, label)
        if step.strategy == "constant" and step.value is None:
            raise WorkflowValidationError(
                f"{label}: fill_missing_values with strategy 'constant' requires a 'value'."
            )


def _require_columns(cols: list[str], col_set: set[str], label: str) -> None:
    for col in cols:
        if col not in col_set:
            available = sorted(col_set)
            raise WorkflowValidationError(
                f"{label}: column '{col}' does not exist in the dataset. "
                f"Available columns: {available}"
            )
