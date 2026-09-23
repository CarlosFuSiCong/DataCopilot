"""Unit tests for app.workflow.observation.risk_rules."""
import pytest

from app.workflow.observation import risk_rules
from app.workflow.observation.risk_rules import (
    AFFECTS_MOST_ROWS,
    AFFECTS_THRESHOLD,
    BULK_REMOVAL_THRESHOLD,
    EMPTY_OUTPUT,
    LARGE_ROW_REMOVAL,
    NO_ROWS_MATCHED,
)
from app.models.workflow import StepIssue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check(**kwargs) -> list[StepIssue]:
    defaults = dict(
        step_type="filter_rows",
        output_row_count=5,
        match_rate=None,
        affected_rate=None,
    )
    defaults.update(kwargs)
    return risk_rules.check(**defaults)


def _codes(issues: list[StepIssue]) -> list[str]:
    return [i.code for i in issues]


# ---------------------------------------------------------------------------
# empty_output
# ---------------------------------------------------------------------------

def test_empty_output_warning_when_no_rows():
    issues = _check(output_row_count=0)
    assert EMPTY_OUTPUT in _codes(issues)


def test_no_issue_when_rows_present():
    issues = _check(output_row_count=1)
    assert EMPTY_OUTPUT not in _codes(issues)


def test_empty_output_severity_is_warning():
    issues = _check(output_row_count=0)
    issue = next(i for i in issues if i.code == EMPTY_OUTPUT)
    assert issue.severity == "warning"


# ---------------------------------------------------------------------------
# no_rows_matched
# ---------------------------------------------------------------------------

def test_no_rows_matched_when_match_rate_is_zero():
    issues = _check(match_rate=0.0, output_row_count=0)
    assert NO_ROWS_MATCHED in _codes(issues)


def test_no_rows_matched_not_raised_when_match_rate_positive():
    issues = _check(match_rate=0.1, output_row_count=1)
    assert NO_ROWS_MATCHED not in _codes(issues)


def test_no_rows_matched_not_raised_when_match_rate_is_none():
    issues = _check(match_rate=None, output_row_count=5)
    assert NO_ROWS_MATCHED not in _codes(issues)


def test_no_rows_matched_severity_is_warning():
    issues = _check(match_rate=0.0, output_row_count=0)
    issue = next(i for i in issues if i.code == NO_ROWS_MATCHED)
    assert issue.severity == "warning"


# ---------------------------------------------------------------------------
# affects_most_rows — via match_rate
# ---------------------------------------------------------------------------

def test_affects_most_rows_when_match_rate_above_threshold():
    issues = _check(match_rate=0.95, output_row_count=19)
    assert AFFECTS_MOST_ROWS in _codes(issues)


def test_affects_most_rows_not_raised_at_threshold_boundary():
    issues = _check(match_rate=AFFECTS_THRESHOLD, output_row_count=18)
    assert AFFECTS_MOST_ROWS not in _codes(issues)


def test_affects_most_rows_not_raised_below_threshold():
    issues = _check(match_rate=0.5, output_row_count=10)
    assert AFFECTS_MOST_ROWS not in _codes(issues)


# ---------------------------------------------------------------------------
# affects_most_rows — via affected_rate
# ---------------------------------------------------------------------------

def test_affects_most_rows_when_affected_rate_above_threshold():
    issues = _check(
        step_type="remove_missing_values",
        affected_rate=0.95,
        output_row_count=1,
    )
    assert AFFECTS_MOST_ROWS in _codes(issues)


def test_affects_most_rows_not_raised_when_affected_rate_at_threshold():
    issues = _check(
        step_type="remove_missing_values",
        affected_rate=AFFECTS_THRESHOLD,
        output_row_count=2,
    )
    assert AFFECTS_MOST_ROWS not in _codes(issues)


def test_affects_most_rows_not_raised_when_affected_rate_is_none():
    issues = _check(affected_rate=None, output_row_count=5)
    assert AFFECTS_MOST_ROWS not in _codes(issues)


# ---------------------------------------------------------------------------
# large_row_removal
# ---------------------------------------------------------------------------

def test_large_row_removal_fires_when_filter_removes_more_than_threshold():
    match_rate = round(1.0 - BULK_REMOVAL_THRESHOLD - 0.01, 4)
    issues = _check(match_rate=match_rate, output_row_count=10)
    assert LARGE_ROW_REMOVAL in _codes(issues)


def test_large_row_removal_not_fired_at_boundary():
    match_rate = round(1.0 - BULK_REMOVAL_THRESHOLD, 4)
    issues = _check(match_rate=match_rate, output_row_count=10)
    assert LARGE_ROW_REMOVAL not in _codes(issues)


def test_large_row_removal_only_fires_for_filter_rows_step():
    issues = risk_rules.check(
        step_type="sort_values",
        output_row_count=2,
        match_rate=0.1,
        affected_rate=None,
    )
    assert LARGE_ROW_REMOVAL not in [i.code for i in issues]


# ---------------------------------------------------------------------------
# Multiple issues in the same step
# ---------------------------------------------------------------------------

def test_empty_output_and_no_rows_matched_both_fire():
    issues = _check(match_rate=0.0, output_row_count=0)
    codes = _codes(issues)
    assert EMPTY_OUTPUT in codes
    assert NO_ROWS_MATCHED in codes


def test_no_issues_for_normal_step():
    issues = _check(match_rate=0.8, output_row_count=5)
    assert issues == []


# ---------------------------------------------------------------------------
# worst_status
# ---------------------------------------------------------------------------

def test_worst_status_returns_success_with_no_issues():
    assert risk_rules.worst_status([]) == "success"


def test_worst_status_returns_warning_with_warning_issue():
    issues = [StepIssue(severity="warning", code=EMPTY_OUTPUT, message="x")]
    assert risk_rules.worst_status(issues) == "warning"


def test_worst_status_returns_error_when_error_present():
    issues = [
        StepIssue(severity="warning", code=EMPTY_OUTPUT, message="x"),
        StepIssue(severity="error", code="missing_column", message="y"),
    ]
    assert risk_rules.worst_status(issues) == "error"


def test_worst_status_error_takes_priority_over_warning():
    issues = [
        StepIssue(severity="error", code="missing_column", message="y"),
        StepIssue(severity="warning", code=NO_ROWS_MATCHED, message="z"),
    ]
    assert risk_rules.worst_status(issues) == "error"
