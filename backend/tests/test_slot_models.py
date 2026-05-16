"""Unit tests for SlotExtractionResult and ExtractedSlots Pydantic contracts."""
import pytest
from pydantic import ValidationError

from app.agent.nlu.slot_models import (
    AggregationFunction,
    ExtractedSlots,
    QueryLocale,
    SlotExtractionResult,
    SlotIntent,
    SlotOperator,
    SortDirection,
)


# --------------------------------------------------------------------------- #
# ExtractedSlots
# --------------------------------------------------------------------------- #

class TestExtractedSlots:
    def test_all_fields_optional(self):
        slots = ExtractedSlots()
        assert slots.column is None
        assert slots.operator is None
        assert slots.value is None
        assert slots.target_column is None
        assert slots.aggregation is None
        assert slots.sort_direction is None
        assert slots.limit is None

    def test_filter_slots(self):
        slots = ExtractedSlots(column="amount", operator="gt", value="1000")
        assert slots.column == "amount"
        assert slots.operator == "gt"
        assert slots.value == "1000"

    def test_sort_slots(self):
        slots = ExtractedSlots(column="date", sort_direction="desc")
        assert slots.column == "date"
        assert slots.sort_direction == "desc"

    def test_group_aggregate_slots(self):
        slots = ExtractedSlots(
            column="region",
            target_column="sales",
            aggregation="sum",
        )
        assert slots.column == "region"
        assert slots.target_column == "sales"
        assert slots.aggregation == "sum"

    def test_limit_slot(self):
        slots = ExtractedSlots(limit=10)
        assert slots.limit == 10

    def test_limit_must_be_positive(self):
        with pytest.raises(ValidationError):
            ExtractedSlots(limit=0)

    def test_invalid_operator_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedSlots(operator="between")

    def test_invalid_aggregation_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedSlots(aggregation="variance")

    def test_invalid_sort_direction_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedSlots(sort_direction="random")


# --------------------------------------------------------------------------- #
# SlotExtractionResult defaults
# --------------------------------------------------------------------------- #

class TestSlotExtractionResultDefaults:
    def test_minimal_construction(self):
        result = SlotExtractionResult(raw_query="show me the data")
        assert result.raw_query == "show me the data"
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert result.missing_slots == []
        assert result.ambiguities == []
        assert result.query_locale == "en"
        assert isinstance(result.slots, ExtractedSlots)

    def test_raw_query_is_preserved(self):
        raw = "筛选 amount 大于 1000"
        result = SlotExtractionResult(raw_query=raw)
        assert result.raw_query == raw

    def test_confidence_bounds(self):
        SlotExtractionResult(raw_query="q", confidence=0.0)
        SlotExtractionResult(raw_query="q", confidence=1.0)
        SlotExtractionResult(raw_query="q", confidence=0.75)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            SlotExtractionResult(raw_query="q", confidence=-0.1)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            SlotExtractionResult(raw_query="q", confidence=1.01)

    def test_invalid_intent_rejected(self):
        with pytest.raises(ValidationError):
            SlotExtractionResult(raw_query="q", intent="predict")

    def test_invalid_locale_rejected(self):
        with pytest.raises(ValidationError):
            SlotExtractionResult(raw_query="q", query_locale="fr")


# --------------------------------------------------------------------------- #
# Realistic extraction scenarios
# --------------------------------------------------------------------------- #

class TestSlotExtractionResultScenarios:
    def test_english_filter_query(self):
        result = SlotExtractionResult(
            raw_query="filter rows where amount > 1000",
            intent="filter",
            slots=ExtractedSlots(column="amount", operator="gt", value="1000"),
            confidence=0.95,
            query_locale="en",
        )
        assert result.intent == "filter"
        assert result.slots.column == "amount"
        assert result.slots.operator == "gt"
        assert result.slots.value == "1000"
        assert result.missing_slots == []

    def test_chinese_filter_query(self):
        result = SlotExtractionResult(
            raw_query="筛选 amount 大于 1000 的行",
            intent="filter",
            slots=ExtractedSlots(column="amount", operator="gt", value="1000"),
            confidence=0.90,
            query_locale="zh",
        )
        assert result.query_locale == "zh"
        assert result.intent == "filter"
        assert result.slots.operator == "gt"

    def test_mixed_language_query(self):
        result = SlotExtractionResult(
            raw_query="filter amount 大于 1000",
            intent="filter",
            slots=ExtractedSlots(column="amount", operator="gt", value="1000"),
            confidence=0.85,
            query_locale="mixed",
        )
        assert result.query_locale == "mixed"

    def test_sort_query(self):
        result = SlotExtractionResult(
            raw_query="sort by date descending",
            intent="sort",
            slots=ExtractedSlots(column="date", sort_direction="desc"),
            confidence=0.92,
        )
        assert result.intent == "sort"
        assert result.slots.sort_direction == "desc"

    def test_group_aggregate_query(self):
        result = SlotExtractionResult(
            raw_query="total sales by region",
            intent="group_aggregate",
            slots=ExtractedSlots(
                column="region",
                target_column="sales",
                aggregation="sum",
            ),
            confidence=0.88,
        )
        assert result.intent == "group_aggregate"
        assert result.slots.aggregation == "sum"

    def test_limit_query(self):
        result = SlotExtractionResult(
            raw_query="show top 5 rows",
            intent="limit",
            slots=ExtractedSlots(limit=5),
            confidence=0.99,
        )
        assert result.intent == "limit"
        assert result.slots.limit == 5

    def test_missing_slots_reported(self):
        result = SlotExtractionResult(
            raw_query="filter rows where amount",
            intent="filter",
            slots=ExtractedSlots(column="amount"),
            confidence=0.60,
            missing_slots=["operator", "value"],
        )
        assert "operator" in result.missing_slots
        assert "value" in result.missing_slots

    def test_ambiguities_reported(self):
        result = SlotExtractionResult(
            raw_query="filter by date",
            intent="filter",
            slots=ExtractedSlots(),
            confidence=0.40,
            missing_slots=["column", "operator", "value"],
            ambiguities=["'date' could refer to column 'order_date' or 'ship_date'"],
        )
        assert len(result.ambiguities) == 1
        assert "date" in result.ambiguities[0]

    def test_inspect_intent(self):
        result = SlotExtractionResult(
            raw_query="inspect the dataset",
            intent="inspect",
            confidence=0.80,
        )
        assert result.intent == "inspect"

    def test_clean_intent(self):
        result = SlotExtractionResult(
            raw_query="remove duplicate rows",
            intent="clean",
            confidence=0.75,
        )
        assert result.intent == "clean"

    def test_slot_extraction_does_not_contain_workflow_fields(self):
        """SlotExtractionResult must not expose workflow JSON structure."""
        result = SlotExtractionResult(raw_query="q")
        assert not hasattr(result, "steps")
        assert not hasattr(result, "workflow")
        assert not hasattr(result, "transformations")
