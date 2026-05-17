"""Unit tests for slot_extractor.py.

All LLM calls are mocked; no real OpenAI key is needed.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.workflow.nlu.slot_extractor import SlotExtractorOutput, extract_slots, _parse_llm_output
from app.workflow.nlu.slot_models import SlotExtractionResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_client(content: str) -> MagicMock:
    """Build a mock OpenAI client that returns the given content string."""
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _slot_json(**overrides) -> str:
    base = {
        "intent": "filter",
        "slots": {
            "column": "amount",
            "operator": "gt",
            "value": "1000",
            "target_column": None,
            "aggregation": None,
            "sort_direction": None,
            "limit": None,
        },
        "confidence": 0.95,
        "missing_slots": [],
        "ambiguities": [],
        "query_locale": "en",
    }
    base.update(overrides)
    return json.dumps(base)


# --------------------------------------------------------------------------- #
# _parse_llm_output
# --------------------------------------------------------------------------- #

class TestParseLLMOutput:
    def test_valid_filter_output(self):
        result, err = _parse_llm_output(_slot_json(), "filter amount > 1000")
        assert err is None
        assert result.intent == "filter"
        assert result.slots.column == "amount"
        assert result.slots.operator == "gt"
        assert result.slots.value == "1000"
        assert result.confidence == pytest.approx(0.95)

    def test_empty_string_returns_unknown(self):
        result, err = _parse_llm_output("", "some query")
        assert err is not None
        assert result.intent == "unknown"
        assert result.confidence == 0.0

    def test_whitespace_only_returns_unknown(self):
        result, err = _parse_llm_output("   ", "some query")
        assert err is not None
        assert result.intent == "unknown"

    def test_invalid_json_returns_error(self):
        result, err = _parse_llm_output("{not valid json}", "q")
        assert err is not None
        assert "Invalid JSON" in err

    def test_non_object_json_returns_error(self):
        result, err = _parse_llm_output('["filter", "sort"]', "q")
        assert err is not None
        assert "not a JSON object" in err

    def test_missing_slots_preserved(self):
        raw = _slot_json(
            intent="filter",
            slots={"column": "amount", "operator": None, "value": None,
                   "target_column": None, "aggregation": None, "sort_direction": None, "limit": None},
            missing_slots=["operator", "value"],
            confidence=0.6,
        )
        result, err = _parse_llm_output(raw, "filter amount")
        assert err is None
        assert "operator" in result.missing_slots
        assert "value" in result.missing_slots

    def test_ambiguities_preserved(self):
        raw = _slot_json(
            intent="unknown",
            ambiguities=["Could mean filter or sort"],
            confidence=0.3,
        )
        result, err = _parse_llm_output(raw, "show me something")
        assert err is None
        assert len(result.ambiguities) == 1

    def test_sort_intent(self):
        raw = json.dumps({
            "intent": "sort",
            "slots": {"column": "date", "operator": None, "value": None,
                      "target_column": None, "aggregation": None,
                      "sort_direction": "desc", "limit": None},
            "confidence": 0.95, "missing_slots": [], "ambiguities": [], "query_locale": "en",
        })
        result, err = _parse_llm_output(raw, "sort by date descending")
        assert err is None
        assert result.intent == "sort"
        assert result.slots.sort_direction == "desc"

    def test_group_aggregate_intent(self):
        raw = json.dumps({
            "intent": "group_aggregate",
            "slots": {"column": "region", "operator": None, "value": None,
                      "target_column": "sales", "aggregation": "sum",
                      "sort_direction": None, "limit": None},
            "confidence": 0.88, "missing_slots": [], "ambiguities": [], "query_locale": "en",
        })
        result, err = _parse_llm_output(raw, "total sales by region")
        assert err is None
        assert result.intent == "group_aggregate"
        assert result.slots.aggregation == "sum"
        assert result.slots.target_column == "sales"

    def test_limit_intent(self):
        raw = json.dumps({
            "intent": "limit",
            "slots": {"column": None, "operator": None, "value": None,
                      "target_column": None, "aggregation": None,
                      "sort_direction": None, "limit": 5},
            "confidence": 0.99, "missing_slots": [], "ambiguities": [], "query_locale": "en",
        })
        result, err = _parse_llm_output(raw, "show top 5 rows")
        assert err is None
        assert result.intent == "limit"
        assert result.slots.limit == 5

    def test_chinese_locale(self):
        raw = _slot_json(query_locale="zh")
        result, err = _parse_llm_output(raw, "筛选 amount 大于 1000")
        assert err is None
        assert result.query_locale == "zh"

    def test_mixed_locale(self):
        raw = _slot_json(query_locale="mixed")
        result, err = _parse_llm_output(raw, "filter amount 大于 1000")
        assert err is None
        assert result.query_locale == "mixed"

    def test_invalid_operator_returns_parse_error(self):
        raw = _slot_json(
            slots={
                "column": "amount", "operator": "greater_than",  # invalid
                "value": "1000", "target_column": None, "aggregation": None,
                "sort_direction": None, "limit": None,
            }
        )
        result, err = _parse_llm_output(raw, "q")
        assert err is not None

    def test_raw_query_preserved(self):
        query = "filter amount > 1000 and status is active"
        result, err = _parse_llm_output(_slot_json(), query)
        assert result.raw_query == query


# --------------------------------------------------------------------------- #
# extract_slots (with mocked client)
# --------------------------------------------------------------------------- #

class TestExtractSlots:
    def test_returns_slot_extractor_output(self):
        client = _make_client(_slot_json())
        output = extract_slots("filter amount > 1000", client=client)
        assert isinstance(output, SlotExtractorOutput)
        assert isinstance(output.result, SlotExtractionResult)

    def test_successful_filter_extraction(self):
        client = _make_client(_slot_json())
        output = extract_slots("filter amount > 1000", client=client)
        assert output.parse_error is None
        assert output.result.intent == "filter"
        assert output.result.slots.column == "amount"

    def test_raw_llm_output_preserved(self):
        payload = _slot_json()
        client = _make_client(payload)
        output = extract_slots("q", client=client)
        assert output.raw_llm_output == payload

    def test_llm_failure_returns_unknown(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("network error")
        output = extract_slots("q", client=client)
        assert output.result.intent == "unknown"
        assert output.parse_error is not None

    def test_llm_empty_output_returns_unknown(self):
        client = _make_client("")
        output = extract_slots("q", client=client)
        assert output.result.intent == "unknown"
        assert output.parse_error is not None

    def test_llm_invalid_json_returns_unknown(self):
        client = _make_client("not json at all")
        output = extract_slots("q", client=client)
        assert output.result.intent == "unknown"
        assert output.parse_error is not None

    def test_missing_slots_forwarded(self):
        raw = _slot_json(
            slots={"column": "amount", "operator": None, "value": None,
                   "target_column": None, "aggregation": None, "sort_direction": None, "limit": None},
            missing_slots=["operator", "value"],
            confidence=0.6,
        )
        client = _make_client(raw)
        output = extract_slots("filter amount", client=client)
        assert output.parse_error is None
        assert "operator" in output.result.missing_slots
        assert "value" in output.result.missing_slots

    def test_client_receives_query_in_user_message(self):
        client = _make_client(_slot_json())
        extract_slots("my specific query", client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else []
        if not messages:
            messages = call_args[1].get("messages", [])
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        assert "my specific query" in user_content

    def test_json_mode_requested(self):
        client = _make_client(_slot_json())
        extract_slots("q", client=client)
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}

    def test_temperature_zero(self):
        client = _make_client(_slot_json())
        extract_slots("q", client=client)
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("temperature") == 0


# --------------------------------------------------------------------------- #
# Bug 2 regression: missing API key must produce a clear parse_error
# --------------------------------------------------------------------------- #

class TestMissingApiKey:
    def test_no_api_key_returns_parse_error_not_silent_fallback(self):
        """extract_slots must set parse_error when LLM_API_KEY is absent.

        Regression: previously extract_slots created the OpenAI client
        unconditionally; a missing key caused a silent auth failure that was
        swallowed by the broad except clause, producing intent='unknown' with
        no indication of the real problem.
        """
        with patch("app.workflow.nlu.slot_extractor.settings") as mock_settings:
            mock_settings.llm_api_key = None
            output = extract_slots("filter amount > 1000")

        assert output.parse_error is not None
        assert "LLM_API_KEY" in output.parse_error or "api key" in output.parse_error.lower()

    def test_no_api_key_result_intent_is_unknown(self):
        with patch("app.workflow.nlu.slot_extractor.settings") as mock_settings:
            mock_settings.llm_api_key = None
            output = extract_slots("filter amount > 1000")

        assert output.result.intent == "unknown"

    def test_no_api_key_does_not_call_openai(self):
        """No OpenAI client should be created when the API key is missing."""
        with patch("app.workflow.nlu.slot_extractor.settings") as mock_settings:
            mock_settings.llm_api_key = None
            with patch("app.workflow.nlu.slot_extractor.OpenAI") as mock_openai:
                extract_slots("test query")
        mock_openai.assert_not_called()

    def test_configured_api_key_does_not_trigger_error(self):
        """When the key is set, no parse_error should come from the key check."""
        client = _make_client(_slot_json())
        output = extract_slots("filter amount > 1000", client=client)
        assert output.parse_error is None
