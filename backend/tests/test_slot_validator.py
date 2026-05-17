"""Unit tests for slot_validator.py — deterministic schema validation."""
import pytest
from datetime import datetime

from app.workflow.nlu.slot_models import ExtractedSlots, SlotExtractionResult
from app.workflow.nlu.slot_validator import validate_slots, SlotValidationOutcome
from app.models.dataset import ColumnProfile, DatasetProfile


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _profile(*columns: tuple[str, str]) -> DatasetProfile:
    """Build a minimal DatasetProfile from (name, dtype) pairs."""
    return DatasetProfile(
        filename="test.csv",
        row_count=100,
        column_count=len(columns),
        columns=[ColumnProfile(name=n, dtype=d, missing_count=0, missing_pct=0.0) for n, d in columns],
        preview=[],
    )


def _extraction(
    intent: str = "filter",
    column: str | None = "amount",
    operator: str | None = "gt",
    value: str | None = "1000",
    target_column: str | None = None,
    aggregation: str | None = None,
    sort_direction: str | None = None,
    limit: int | None = None,
    missing_slots: list[str] | None = None,
    ambiguities: list[str] | None = None,
    query_locale: str = "en",
) -> SlotExtractionResult:
    return SlotExtractionResult(
        raw_query="test query",
        intent=intent,
        slots=ExtractedSlots(
            column=column,
            operator=operator,
            value=value,
            target_column=target_column,
            aggregation=aggregation,
            sort_direction=sort_direction,
            limit=limit,
        ),
        confidence=0.9,
        missing_slots=missing_slots or [],
        ambiguities=ambiguities or [],
        query_locale=query_locale,
    )


ORDERS_PROFILE = _profile(
    ("order_id", "int64"),
    ("amount", "float64"),
    ("region", "object"),
    ("status", "object"),
    ("order_date", "datetime64[ns]"),
)


# --------------------------------------------------------------------------- #
# Valid outcomes
# --------------------------------------------------------------------------- #

class TestValidOutcomes:
    def test_valid_filter(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value="1000"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True
        assert result.status == "valid"
        assert result.needs_clarification is False

    def test_valid_sort(self):
        result = validate_slots(
            _extraction(intent="sort", column="order_date", operator=None, value=None,
                        sort_direction="desc"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_group_aggregate(self):
        result = validate_slots(
            _extraction(intent="group_aggregate", column="region", operator=None, value=None,
                        target_column="amount", aggregation="sum"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_limit(self):
        result = validate_slots(
            _extraction(intent="limit", column=None, operator=None, value=None, limit=10),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_inspect_no_slots(self):
        result = validate_slots(
            _extraction(intent="inspect", column=None, operator=None, value=None),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_clean_no_slots(self):
        result = validate_slots(
            _extraction(intent="clean", column=None, operator=None, value=None),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_string_value_on_string_column(self):
        result = validate_slots(
            _extraction(intent="filter", column="region", operator="eq", value="North"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_valid_column_case_insensitive(self):
        result = validate_slots(
            _extraction(intent="filter", column="AMOUNT", operator="gt", value="500"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True


# --------------------------------------------------------------------------- #
# Unsupported intent
# --------------------------------------------------------------------------- #

class TestUnsupportedIntent:
    def test_unknown_intent_blocked(self):
        result = validate_slots(
            _extraction(intent="unknown"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is False
        assert result.blocked is True
        assert result.status == "unsupported_intent"
        assert result.needs_clarification is False


# --------------------------------------------------------------------------- #
# Missing required slots
# --------------------------------------------------------------------------- #

class TestMissingRequiredSlots:
    def test_filter_missing_operator(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator=None, value="1000"),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"
        assert result.needs_clarification is True
        assert result.clarification_question is not None
        assert "operator" in result.clarification_question

    def test_filter_missing_value(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value=None),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"
        assert "value" in (result.details or "")

    def test_filter_missing_all_slots(self):
        result = validate_slots(
            _extraction(intent="filter", column=None, operator=None, value=None),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"
        assert result.needs_clarification is True

    def test_sort_missing_sort_direction(self):
        result = validate_slots(
            _extraction(intent="sort", column="amount", operator=None, value=None,
                        sort_direction=None),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"
        assert "sort_direction" in (result.details or "")

    def test_group_aggregate_missing_aggregation(self):
        result = validate_slots(
            _extraction(intent="group_aggregate", column="region", operator=None, value=None,
                        aggregation=None),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"
        assert "aggregation" in (result.details or "")

    def test_limit_missing_limit_value(self):
        result = validate_slots(
            _extraction(intent="limit", column=None, operator=None, value=None, limit=None),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_required_slot"


# --------------------------------------------------------------------------- #
# Missing column (no fuzzy match)
# --------------------------------------------------------------------------- #

class TestMissingColumn:
    def test_column_not_in_schema(self):
        result = validate_slots(
            _extraction(intent="filter", column="revenue", operator="gt", value="500"),
            ORDERS_PROFILE,
        )
        assert result.status == "missing_column"
        assert result.needs_clarification is True
        assert "revenue" in (result.clarification_question or "")
        assert result.candidate_columns == []

    def test_clarification_lists_available_columns(self):
        result = validate_slots(
            _extraction(intent="filter", column="xyz_no_such", operator="gt", value="1"),
            ORDERS_PROFILE,
        )
        assert "amount" in (result.clarification_question or "")


# --------------------------------------------------------------------------- #
# Ambiguous column (fuzzy match)
# --------------------------------------------------------------------------- #

class TestAmbiguousColumn:
    def test_close_match_returns_ambiguous(self):
        result = validate_slots(
            _extraction(intent="filter", column="amout", operator="gt", value="500"),
            ORDERS_PROFILE,
        )
        assert result.status == "ambiguous_column"
        assert result.needs_clarification is True
        assert "amount" in result.candidate_columns
        assert "amout" in (result.clarification_question or "")

    def test_candidate_columns_in_clarification_question(self):
        result = validate_slots(
            _extraction(intent="sort", column="ordr_date", operator=None, value=None,
                        sort_direction="asc"),
            ORDERS_PROFILE,
        )
        if result.status == "ambiguous_column":
            assert len(result.candidate_columns) >= 1
            for cand in result.candidate_columns:
                assert cand in (result.clarification_question or "")


# --------------------------------------------------------------------------- #
# Invalid type
# --------------------------------------------------------------------------- #

class TestInvalidType:
    def test_non_numeric_value_for_numeric_column(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value="large"),
            ORDERS_PROFILE,
        )
        assert result.status == "invalid_type"
        assert result.needs_clarification is True
        assert "large" in (result.clarification_question or "")
        assert "amount" in (result.clarification_question or "")

    def test_numeric_value_string_representation_valid(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value="1500.50"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_string_value_on_object_column_valid(self):
        result = validate_slots(
            _extraction(intent="filter", column="status", operator="eq", value="active"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True

    def test_type_check_only_for_filter_intent(self):
        # group_aggregate should not trigger type check even if value present
        result = validate_slots(
            _extraction(intent="group_aggregate", column="region", operator=None, value=None,
                        target_column="amount", aggregation="sum"),
            ORDERS_PROFILE,
        )
        assert result.is_valid is True


# --------------------------------------------------------------------------- #
# SlotValidationOutcome model
# --------------------------------------------------------------------------- #

class TestSlotValidationOutcomeModel:
    def test_valid_outcome_has_no_question(self):
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value="100"),
            ORDERS_PROFILE,
        )
        assert result.clarification_question is None

    def test_blocked_outcome_is_not_clarification(self):
        result = validate_slots(_extraction(intent="unknown"), ORDERS_PROFILE)
        assert result.blocked is True
        assert result.needs_clarification is False

    def test_missing_slot_outcome_not_blocked(self):
        result = validate_slots(
            _extraction(intent="filter", column=None, operator=None, value=None),
            ORDERS_PROFILE,
        )
        assert result.blocked is False
        assert result.needs_clarification is True


# --------------------------------------------------------------------------- #
# Bug regression: falsy value slot check
# Previously `if not slot_dict.get(r)` treated any falsy value (e.g. empty
# string) as a missing required slot.  The fix uses `is None` so only absent
# slots trigger clarification.
# --------------------------------------------------------------------------- #

class TestFalsyValueSlotCheck:
    def test_empty_string_value_is_not_treated_as_missing(self):
        # value="" is a valid filter target (match empty strings).
        # The old falsy check would wrongly flag it as missing and request clarification.
        result = validate_slots(
            _extraction(intent="filter", column="status", operator="eq", value=""),
            ORDERS_PROFILE,
        )
        assert result.needs_clarification is False, (
            "Empty string value should not be reported as a missing slot"
        )

    def test_none_value_is_correctly_treated_as_missing(self):
        # Actual None should still be reported as missing.
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="gt", value=None),
            ORDERS_PROFILE,
        )
        assert result.needs_clarification is True

    def test_zero_string_value_is_not_treated_as_missing(self):
        # "0" is a valid numeric filter value; falsy check would mishandle it.
        result = validate_slots(
            _extraction(intent="filter", column="amount", operator="eq", value="0"),
            ORDERS_PROFILE,
        )
        assert result.needs_clarification is False, (
            'String "0" value should not be reported as a missing slot'
        )
