"""Deterministic risk rules for workflow step results.

Each rule inspects the execution metrics of a single step and returns
StepIssue objects with a stable code.  All codes are module-level constants
so tests and callers can reference them without hard-coding strings.

Rules
-----
EMPTY_OUTPUT      (warning) : step produced 0 output rows.
NO_ROWS_MATCHED   (warning) : filter step matched 0 rows.
AFFECTS_MOST_ROWS (warning) : step affected > 90 % of input rows.
MISSING_COLUMN    (error)   : referenced column not found in the dataset.
                              This code is raised by the validator before
                              execution; it is defined here so all issue
                              codes live in one registry.

Warning issues do NOT stop workflow execution.
Error issues stop execution immediately.
"""
import logging

from app.models.workflow_execution import StepIssue

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stable issue codes
# ---------------------------------------------------------------------------

EMPTY_OUTPUT = "empty_output"
NO_ROWS_MATCHED = "no_rows_matched"
AFFECTS_MOST_ROWS = "affects_most_rows"
MISSING_COLUMN = "missing_column"

_AFFECTS_THRESHOLD = 0.9

# Exported so tests can assert boundary conditions without hard-coding 0.9.
AFFECTS_THRESHOLD = _AFFECTS_THRESHOLD


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check(
    *,
    step_type: str,
    output_row_count: int,
    match_rate: float | None,
    affected_rate: float | None,
) -> list[StepIssue]:
    """Return issues detected for a single executed step.

    Rules are evaluated independently; more than one issue can apply.
    """
    issues: list[StepIssue] = []

    # empty_output: any step that produces zero rows
    if output_row_count == 0:
        issues.append(StepIssue(
            severity="warning",
            code=EMPTY_OUTPUT,
            message="This step produced no output rows.",
        ))

    # no_rows_matched: filter step where the condition matched nothing
    if match_rate is not None and match_rate == 0.0:
        issues.append(StepIssue(
            severity="warning",
            code=NO_ROWS_MATCHED,
            message="No rows matched this filter condition.",
        ))

    # affects_most_rows: filter keeps > 90% of rows (loose condition)
    if match_rate is not None and match_rate > _AFFECTS_THRESHOLD:
        issues.append(StepIssue(
            severity="warning",
            code=AFFECTS_MOST_ROWS,
            message=f"This filter matches {match_rate:.0%} of input rows.",
        ))

    # affects_most_rows: row-reducing step removes > 90% of rows
    if affected_rate is not None and affected_rate > _AFFECTS_THRESHOLD:
        issues.append(StepIssue(
            severity="warning",
            code=AFFECTS_MOST_ROWS,
            message=f"This step affects {affected_rate:.0%} of input rows.",
        ))

    if issues:
        logger.info(
            "Risk check '%s': %d issue(s) — %s",
            step_type,
            len(issues),
            [i.code for i in issues],
        )

    return issues


def worst_status(issues: list[StepIssue]) -> str:
    """Return 'error', 'warning', or 'success' based on highest severity."""
    if any(i.severity == "error" for i in issues):
        return "error"
    if any(i.severity == "warning" for i in issues):
        return "warning"
    return "success"
