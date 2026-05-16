"""Unit tests for _failed_new_step in orchestrator.py."""
from unittest.mock import patch

import pytest

from app.agent.loop.orchestrator import _failed_new_step
from app.models.workflow_steps import FilterRowsStep, LimitRowsStep, SortValuesStep

COLUMNS = ["amount", "region", "status"]


def _filter(column: str, value: float = 100) -> FilterRowsStep:
    return FilterRowsStep(type="filter_rows", column=column, operator=">", value=value)


def _sort(column: str) -> SortValuesStep:
    return SortValuesStep(type="sort_values", column=column, ascending=True)


def _limit(n: int = 10) -> LimitRowsStep:
    return LimitRowsStep(type="limit_rows", n=n)


# --------------------------------------------------------------------------- #
# Empty new_steps
# --------------------------------------------------------------------------- #

def test_no_new_steps_returns_none():
    assert _failed_new_step(previous_steps=[], new_steps=[], column_names=COLUMNS) is None


# --------------------------------------------------------------------------- #
# First step is the culprit
# --------------------------------------------------------------------------- #

def test_first_step_fails_returns_first_step():
    new_steps = [_filter("nonexistent"), _filter("amount")]
    result = _failed_new_step(previous_steps=[], new_steps=new_steps, column_names=COLUMNS)
    assert result is not None
    assert result["column"] == "nonexistent"


# --------------------------------------------------------------------------- #
# Second step is the culprit (first passes)
# --------------------------------------------------------------------------- #

def test_second_step_fails_returns_second_step():
    # first step is valid; second step references a missing column
    new_steps = [_filter("amount"), _filter("revenue")]
    result = _failed_new_step(previous_steps=[], new_steps=new_steps, column_names=COLUMNS)
    assert result is not None
    assert result["column"] == "revenue"


# --------------------------------------------------------------------------- #
# Third step is the culprit
# --------------------------------------------------------------------------- #

def test_third_step_fails_returns_third_step():
    new_steps = [_filter("amount"), _sort("region"), _filter("nonexistent")]
    result = _failed_new_step(previous_steps=[], new_steps=new_steps, column_names=COLUMNS)
    assert result is not None
    assert result["column"] == "nonexistent"


# --------------------------------------------------------------------------- #
# previous_steps interact with new_steps
# --------------------------------------------------------------------------- #

def test_previous_steps_passed_through_to_validator():
    # previous step is valid; new step references a bad column — still caught.
    previous = [_filter("amount")]
    new_steps = [_filter("bad_column")]
    result = _failed_new_step(
        previous_steps=previous, new_steps=new_steps, column_names=COLUMNS
    )
    assert result is not None
    assert result["column"] == "bad_column"


def test_valid_previous_steps_do_not_mask_new_step_failure():
    previous = [_sort("amount")]
    new_steps = [_filter("ok_column_missing")]
    result = _failed_new_step(
        previous_steps=previous, new_steps=new_steps, column_names=COLUMNS
    )
    assert result is not None


# --------------------------------------------------------------------------- #
# Fallback: no prefix raises — must return None, NOT new_steps[-1]
# --------------------------------------------------------------------------- #

def test_fallback_returns_none_not_last_step():
    """Bug regression: fallback must be None, not an arbitrary last step.

    If the incremental prefix search finds no failing step (e.g. the validator
    is non-deterministic or state is inconsistent), returning None is the only
    honest answer.  The old code returned new_steps[-1].model_dump(), which
    incorrectly blamed the last step without evidence.
    """
    new_steps = [_filter("amount"), _sort("region")]

    # Patch validate_workflow so it never raises — simulates the 'impossible'
    # scenario where all incremental checks pass despite a known outer failure.
    with patch(
        "app.agent.loop.orchestrator.validate_workflow",
        return_value=None,
    ):
        result = _failed_new_step(
            previous_steps=[], new_steps=new_steps, column_names=COLUMNS
        )

    assert result is None, (
        "Fallback must return None, not arbitrarily blame the last step."
    )


# --------------------------------------------------------------------------- #
# Return shape
# --------------------------------------------------------------------------- #

def test_returned_step_is_a_plain_dict():
    new_steps = [_filter("bad")]
    result = _failed_new_step(previous_steps=[], new_steps=new_steps, column_names=COLUMNS)
    assert isinstance(result, dict)


def test_returned_dict_has_type_field():
    new_steps = [_filter("bad")]
    result = _failed_new_step(previous_steps=[], new_steps=new_steps, column_names=COLUMNS)
    assert result is not None
    assert result.get("type") == "filter_rows"
