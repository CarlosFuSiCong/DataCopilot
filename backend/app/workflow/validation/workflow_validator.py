"""Workflow validator.

Validates a list of WorkflowStep against the dataset's column names before
any execution takes place. Raises WorkflowValidationError on the first issue.

Column state is tracked across steps: each step is validated against the
columns that exist *after* all previous steps have run, not the original
column set. This ensures chained workflows (e.g. select_columns followed by
filter_rows) are validated correctly.
"""
import logging

from app.workflow.registry import registry
from app.core.exceptions import WorkflowValidationError
from app.models.workflow_steps import WorkflowStep

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
        registry.validate_step(step, col_set, idx)
        col_set = registry.advance_columns(step, col_set)

    logger.info("Workflow validated: %d steps against columns %s", len(steps), column_names)


def validate_against_original_columns(
    steps: list[WorkflowStep],
    column_names: list[str],
) -> None:
    """Validate each step only against the original dataset columns.

    Preview uses this as a fallback when strict column-state validation fails:
    if every referenced column exists in the raw dataset, the executor preview
    can surface the failure as a partial step result instead of a 400 response.
    """
    if not steps:
        raise WorkflowValidationError("Workflow must contain at least one step.")

    original_col_set = set(column_names)
    for idx, step in enumerate(steps):
        registry.validate_step(step, original_col_set, idx)


def simulate_columns(steps: list[WorkflowStep], initial_column_names: list[str]) -> list[str]:
    """Return the column names that would exist after running all steps.

    Used externally (e.g. chat endpoint) to compute the intermediate column
    state for chained workflow validation and error context.
    """
    col_set = set(initial_column_names)
    for step in steps:
        col_set = registry.advance_columns(step, col_set)
    return sorted(col_set)
