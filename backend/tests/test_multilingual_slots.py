"""Task 5 – Multilingual slot extraction tests.

Covers the end-to-end slot extraction pipeline for Chinese and mixed-language
queries.  All LLM calls are mocked; no real API key is needed.

Test groups
-----------
TestChineseFilterSlots      – 中文 filter 查询的 slot 提取
TestChineseSortSlots        – 中文 sort 查询的 slot 提取
TestChineseGroupAggSlots    – 中文 group_aggregate 查询的 slot 提取
TestMixedLanguageSlots      – 中英混合语言查询
TestColumnNamePreservation  – 列名必须原样保留，不被翻译
TestOperatorMapping         – 中文 operator 映射（大于/小于/等于…）
TestPromptMultilingualContent – system prompt 内容覆盖检查
"""
import json
from unittest.mock import MagicMock

import pytest

from app.workflow.nlu.slot_extractor import (
    SlotExtractorOutput,
    _SYSTEM_PROMPT,
    extract_slots,
    _parse_llm_output,
)
from app.workflow.nlu.slot_models import SlotExtractionResult


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_client(content: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def _slot_json(
    intent: str = "filter",
    column: str | None = "amount",
    operator: str | None = "gt",
    value: str | None = "1000",
    target_column: str | None = None,
    aggregation: str | None = None,
    sort_direction: str | None = None,
    limit: int | None = None,
    confidence: float = 0.93,
    missing_slots: list | None = None,
    ambiguities: list | None = None,
    query_locale: str = "zh",
) -> str:
    return json.dumps({
        "intent": intent,
        "slots": {
            "column": column,
            "operator": operator,
            "value": value,
            "target_column": target_column,
            "aggregation": aggregation,
            "sort_direction": sort_direction,
            "limit": limit,
        },
        "confidence": confidence,
        "missing_slots": missing_slots or [],
        "ambiguities": ambiguities or [],
        "query_locale": query_locale,
    })


# --------------------------------------------------------------------------- #
# Chinese filter queries
# --------------------------------------------------------------------------- #

class TestChineseFilterSlots:
    def test_chinese_filter_extracts_column(self):
        client = _make_client(_slot_json())
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert output.result.slots.column == "amount"

    def test_chinese_filter_extracts_gt_operator(self):
        client = _make_client(_slot_json(operator="gt"))
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert output.result.slots.operator == "gt"

    def test_chinese_filter_extracts_value(self):
        client = _make_client(_slot_json(value="1000"))
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert output.result.slots.value == "1000"

    def test_chinese_filter_locale_is_zh(self):
        client = _make_client(_slot_json(query_locale="zh"))
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert output.result.query_locale == "zh"

    def test_chinese_filter_lt_operator(self):
        client = _make_client(_slot_json(operator="lt", value="500", query_locale="zh"))
        output = extract_slots("筛选 amount 小于 500 的行", client=client)
        assert output.result.slots.operator == "lt"

    def test_chinese_filter_lte_operator(self):
        client = _make_client(_slot_json(operator="lte", value="500", query_locale="zh"))
        output = extract_slots("amount 小于等于 500", client=client)
        assert output.result.slots.operator == "lte"

    def test_chinese_filter_gte_operator(self):
        client = _make_client(_slot_json(operator="gte", value="100", query_locale="zh"))
        output = extract_slots("amount 大于等于 100", client=client)
        assert output.result.slots.operator == "gte"

    def test_chinese_filter_eq_operator(self):
        client = _make_client(_slot_json(operator="eq", value="Asia", query_locale="zh"))
        output = extract_slots("region 等于 Asia", client=client)
        assert output.result.slots.operator == "eq"

    def test_chinese_filter_ne_operator(self):
        client = _make_client(_slot_json(operator="ne", value="0", query_locale="zh"))
        output = extract_slots("amount 不等于 0", client=client)
        assert output.result.slots.operator == "ne"

    def test_chinese_filter_gaoyú_maps_to_gt(self):
        """高于 (higher than) is an alias for gt in the operator mapping."""
        client = _make_client(_slot_json(operator="gt", value="1000", query_locale="zh"))
        output = extract_slots("筛选 sales 高于 1000 的行", client=client)
        assert output.result.slots.operator == "gt"

    def test_chinese_filter_diyú_maps_to_lt(self):
        """低于 (lower than) is an alias for lt in the operator mapping."""
        client = _make_client(_slot_json(operator="lt", value="500", query_locale="zh"))
        output = extract_slots("筛选 sales 低于 500 的行", client=client)
        assert output.result.slots.operator == "lt"

    def test_chinese_filter_no_parse_error(self):
        client = _make_client(_slot_json())
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert output.parse_error is None

    def test_chinese_filter_confidence_in_range(self):
        client = _make_client(_slot_json(confidence=0.93))
        output = extract_slots("筛选 amount 大于 1000 的行", client=client)
        assert 0.0 <= output.result.confidence <= 1.0


# --------------------------------------------------------------------------- #
# Chinese sort queries
# --------------------------------------------------------------------------- #

class TestChineseSortSlots:
    def test_chinese_sort_desc_direction(self):
        payload = _slot_json(
            intent="sort", column="date", operator=None, value=None,
            sort_direction="desc", confidence=0.93, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 date 降序排列", client=client)
        assert output.result.intent == "sort"
        assert output.result.slots.sort_direction == "desc"

    def test_chinese_sort_asc_direction(self):
        payload = _slot_json(
            intent="sort", column="amount", operator=None, value=None,
            sort_direction="asc", confidence=0.93, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 amount 升序排列", client=client)
        assert output.result.slots.sort_direction == "asc"

    def test_chinese_sort_locale(self):
        payload = _slot_json(
            intent="sort", column="date", operator=None, value=None,
            sort_direction="desc", confidence=0.93, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 date 降序排列", client=client)
        assert output.result.query_locale == "zh"


# --------------------------------------------------------------------------- #
# Chinese group_aggregate queries
# --------------------------------------------------------------------------- #

class TestChineseGroupAggSlots:
    def test_chinese_group_agg_intent(self):
        payload = _slot_json(
            intent="group_aggregate", column="region", operator=None, value=None,
            target_column="sales", aggregation="sum", confidence=0.92, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 region 分组求 sales 的总和", client=client)
        assert output.result.intent == "group_aggregate"

    def test_chinese_group_agg_column(self):
        payload = _slot_json(
            intent="group_aggregate", column="region", operator=None, value=None,
            target_column="sales", aggregation="sum", confidence=0.92, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 region 分组求 sales 的总和", client=client)
        assert output.result.slots.column == "region"

    def test_chinese_group_agg_target_column(self):
        payload = _slot_json(
            intent="group_aggregate", column="region", operator=None, value=None,
            target_column="sales", aggregation="sum", confidence=0.92, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 region 分组求 sales 的总和", client=client)
        assert output.result.slots.target_column == "sales"

    def test_chinese_group_agg_aggregation(self):
        payload = _slot_json(
            intent="group_aggregate", column="region", operator=None, value=None,
            target_column="sales", aggregation="sum", confidence=0.92, query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 region 分组求 sales 的总和", client=client)
        assert output.result.slots.aggregation == "sum"


# --------------------------------------------------------------------------- #
# Mixed-language queries
# --------------------------------------------------------------------------- #

class TestMixedLanguageSlots:
    def test_mixed_filter_locale(self):
        payload = _slot_json(
            operator="gt", value="1000", confidence=0.90, query_locale="mixed",
        )
        client = _make_client(payload)
        output = extract_slots("filter amount 大于 1000", client=client)
        assert output.result.query_locale == "mixed"

    def test_mixed_filter_operator(self):
        payload = _slot_json(
            operator="gt", value="1000", confidence=0.90, query_locale="mixed",
        )
        client = _make_client(payload)
        output = extract_slots("filter amount 大于 1000", client=client)
        assert output.result.slots.operator == "gt"

    def test_mixed_filter_column(self):
        payload = _slot_json(
            column="amount", operator="gt", value="1000",
            confidence=0.90, query_locale="mixed",
        )
        client = _make_client(payload)
        output = extract_slots("filter amount 大于 1000", client=client)
        assert output.result.slots.column == "amount"

    def test_mixed_sort_query(self):
        payload = _slot_json(
            intent="sort", column="sales", operator=None, value=None,
            sort_direction="desc", confidence=0.88, query_locale="mixed",
        )
        client = _make_client(payload)
        output = extract_slots("sort sales 降序", client=client)
        assert output.result.intent == "sort"
        assert output.result.query_locale == "mixed"

    def test_mixed_no_parse_error(self):
        payload = _slot_json(
            operator="lt", value="200", confidence=0.88, query_locale="mixed",
        )
        client = _make_client(payload)
        output = extract_slots("filter price 低于 200", client=client)
        assert output.parse_error is None


# --------------------------------------------------------------------------- #
# Column name preservation
# --------------------------------------------------------------------------- #

class TestColumnNamePreservation:
    def test_chinese_query_preserves_english_column_name(self):
        """Column names from the dataset must not be translated."""
        payload = _slot_json(column="order_amount", operator="gt", value="500", query_locale="zh")
        client = _make_client(payload)
        output = extract_slots("筛选 order_amount 大于 500 的行", client=client)
        assert output.result.slots.column == "order_amount"

    def test_mixed_query_preserves_column_name_as_written(self):
        payload = _slot_json(column="CustomerID", operator="eq", value="42", query_locale="mixed")
        client = _make_client(payload)
        output = extract_slots("filter CustomerID 等于 42", client=client)
        assert output.result.slots.column == "CustomerID"

    def test_column_with_underscores_preserved(self):
        payload = _slot_json(column="sales_amount", operator="gte", value="1000", query_locale="zh")
        client = _make_client(payload)
        output = extract_slots("sales_amount 大于等于 1000", client=client)
        assert output.result.slots.column == "sales_amount"

    def test_target_column_preserved_in_group_by(self):
        payload = _slot_json(
            intent="group_aggregate", column="region", operator=None, value=None,
            target_column="revenue_usd", aggregation="sum", query_locale="zh",
        )
        client = _make_client(payload)
        output = extract_slots("按 region 分组求 revenue_usd 总和", client=client)
        assert output.result.slots.target_column == "revenue_usd"


# --------------------------------------------------------------------------- #
# Chinese operator mapping in system prompt
# --------------------------------------------------------------------------- #

class TestOperatorMapping:
    def test_prompt_contains_dayu_mapping(self):
        """大于 → gt must be in the system prompt."""
        assert "大于" in _SYSTEM_PROMPT
        assert '"gt"' in _SYSTEM_PROMPT

    def test_prompt_contains_xiaoyu_mapping(self):
        assert "小于" in _SYSTEM_PROMPT
        assert '"lt"' in _SYSTEM_PROMPT

    def test_prompt_contains_dengyu_mapping(self):
        assert "等于" in _SYSTEM_PROMPT
        assert '"eq"' in _SYSTEM_PROMPT

    def test_prompt_contains_budengyu_mapping(self):
        assert "不等于" in _SYSTEM_PROMPT
        assert '"ne"' in _SYSTEM_PROMPT

    def test_prompt_contains_gaoyú_alias(self):
        """高于 is an alias for gt."""
        assert "高于" in _SYSTEM_PROMPT

    def test_prompt_contains_diyú_alias(self):
        """低于 is an alias for lt."""
        assert "低于" in _SYSTEM_PROMPT

    def test_prompt_contains_dayudengyu(self):
        assert "大于等于" in _SYSTEM_PROMPT
        assert '"gte"' in _SYSTEM_PROMPT

    def test_prompt_contains_xiaoyudengyu(self):
        assert "小于等于" in _SYSTEM_PROMPT
        assert '"lte"' in _SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# System prompt multilingual coverage check
# --------------------------------------------------------------------------- #

class TestPromptMultilingualContent:
    def test_prompt_has_chinese_filter_example(self):
        assert "筛选" in _SYSTEM_PROMPT

    def test_prompt_has_chinese_sort_example(self):
        assert "降序" in _SYSTEM_PROMPT

    def test_prompt_has_chinese_group_example(self):
        assert "分组" in _SYSTEM_PROMPT

    def test_prompt_has_mixed_locale_example(self):
        assert "mixed" in _SYSTEM_PROMPT

    def test_prompt_has_query_locale_field(self):
        assert "query_locale" in _SYSTEM_PROMPT

    def test_prompt_specifies_column_name_preservation(self):
        """The prompt must tell the LLM not to translate column names."""
        assert "Preserve column names" in _SYSTEM_PROMPT or "do not translate" in _SYSTEM_PROMPT.lower()

    def test_parse_chinese_locale_roundtrip(self):
        """_parse_llm_output must correctly parse query_locale=zh."""
        raw = _slot_json(query_locale="zh")
        result, error = _parse_llm_output(raw, "筛选 amount 大于 1000 的行")
        assert error is None
        assert result.query_locale == "zh"

    def test_parse_mixed_locale_roundtrip(self):
        raw = _slot_json(query_locale="mixed")
        result, error = _parse_llm_output(raw, "filter amount 大于 1000")
        assert error is None
        assert result.query_locale == "mixed"
