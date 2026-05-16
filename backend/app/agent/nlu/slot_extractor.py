"""LLM-based slot extractor for the NLU layer.

Converts a raw user query into a SlotExtractionResult using a few-shot
LLM call with JSON-mode output. Keeps raw_llm_output alongside the
parsed result so callers can log or inspect both sides.

Error handling:
- Empty LLM output → returns a result with intent="unknown", confidence=0.
- Invalid JSON → returns a result with parse_error set.
- Pydantic ValidationError → returns a result with parse_error set.

This module does NOT validate slots against the dataset schema.
Schema validation is the responsibility of slot_validator.py.
"""
import json
import logging
from dataclasses import dataclass, field

from openai import OpenAI
from pydantic import ValidationError

from app.agent.nlu.slot_models import ExtractedSlots, SlotExtractionResult
from app.core.config import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Output container
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SlotExtractorOutput:
    """Paired raw + parsed output from one extraction call."""
    result: SlotExtractionResult
    raw_llm_output: str
    parse_error: str | None = None


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """\
You are the Slot Extractor for DataCopilot.

Your job is to parse a user's natural-language data query into structured slots.
Output ONLY valid JSON. Do NOT include explanations or markdown fences.

Output schema (all fields required):
{
  "intent":        one of: "filter" | "sort" | "group_aggregate" | "limit" | "inspect" | "clean" | "unknown",
  "slots": {
    "column":        string or null,
    "operator":      one of: "eq"|"ne"|"gt"|"gte"|"lt"|"lte"|"contains"|"not_contains"|"starts_with"|"ends_with"|"is_null"|"is_not_null" or null,
    "value":         string or null,
    "target_column": string or null,
    "aggregation":   one of: "sum"|"mean"|"count"|"min"|"max"|"median" or null,
    "sort_direction": one of: "asc"|"desc" or null,
    "limit":         integer or null
  },
  "confidence":    float 0.0–1.0,
  "missing_slots": list of slot names that are required for the intent but not found,
  "ambiguities":   list of free-text descriptions of ambiguous parts,
  "query_locale":  one of: "en" | "zh" | "mixed"
}

Operator mapping for Chinese queries:
  大于 / 高于       → "gt"
  大于等于          → "gte"
  小于 / 低于       → "lt"
  小于等于          → "lte"
  等于 / 是         → "eq"
  不等于 / 不是     → "ne"
  包含              → "contains"
  不包含            → "not_contains"

Rules:
- Preserve column names exactly as written in the query; do not translate or infer.
- For filter intent: column, operator, value are all required. List any missing ones in missing_slots.
- For sort intent: column and sort_direction are required.
- For group_aggregate intent: column (group-by column) and aggregation are required; target_column is the numeric column.
- For limit intent: limit (integer) is required.
- For inspect / clean intent: all slot fields may be null.
- If the query is ambiguous, set intent to "unknown" and describe the ambiguity in ambiguities.
- Set confidence to reflect how certain you are: 0.9+ for clear queries, 0.5–0.9 for partial, below 0.5 for guesses.

--- EXAMPLES ---

Query: "filter rows where amount > 1000"
{
  "intent": "filter",
  "slots": {"column": "amount", "operator": "gt", "value": "1000", "target_column": null, "aggregation": null, "sort_direction": null, "limit": null},
  "confidence": 0.95, "missing_slots": [], "ambiguities": [], "query_locale": "en"
}

Query: "筛选 amount 大于 1000 的行"
{
  "intent": "filter",
  "slots": {"column": "amount", "operator": "gt", "value": "1000", "target_column": null, "aggregation": null, "sort_direction": null, "limit": null},
  "confidence": 0.93, "missing_slots": [], "ambiguities": [], "query_locale": "zh"
}

Query: "filter amount 大于 1000"
{
  "intent": "filter",
  "slots": {"column": "amount", "operator": "gt", "value": "1000", "target_column": null, "aggregation": null, "sort_direction": null, "limit": null},
  "confidence": 0.90, "missing_slots": [], "ambiguities": [], "query_locale": "mixed"
}

Query: "sort by date descending"
{
  "intent": "sort",
  "slots": {"column": "date", "operator": null, "value": null, "target_column": null, "aggregation": null, "sort_direction": "desc", "limit": null},
  "confidence": 0.95, "missing_slots": [], "ambiguities": [], "query_locale": "en"
}

Query: "按 date 降序排列"
{
  "intent": "sort",
  "slots": {"column": "date", "operator": null, "value": null, "target_column": null, "aggregation": null, "sort_direction": "desc", "limit": null},
  "confidence": 0.93, "missing_slots": [], "ambiguities": [], "query_locale": "zh"
}

Query: "total sales by region"
{
  "intent": "group_aggregate",
  "slots": {"column": "region", "operator": null, "value": null, "target_column": "sales", "aggregation": "sum", "sort_direction": null, "limit": null},
  "confidence": 0.88, "missing_slots": [], "ambiguities": [], "query_locale": "en"
}

Query: "按 region 分组求 sales 的总和"
{
  "intent": "group_aggregate",
  "slots": {"column": "region", "operator": null, "value": null, "target_column": "sales", "aggregation": "sum", "sort_direction": null, "limit": null},
  "confidence": 0.92, "missing_slots": [], "ambiguities": [], "query_locale": "zh"
}

Query: "show top 5 rows"
{
  "intent": "limit",
  "slots": {"column": null, "operator": null, "value": null, "target_column": null, "aggregation": null, "sort_direction": null, "limit": 5},
  "confidence": 0.98, "missing_slots": [], "ambiguities": [], "query_locale": "en"
}

Query: "filter rows where amount"
{
  "intent": "filter",
  "slots": {"column": "amount", "operator": null, "value": null, "target_column": null, "aggregation": null, "sort_direction": null, "limit": null},
  "confidence": 0.60, "missing_slots": ["operator", "value"], "ambiguities": [], "query_locale": "en"
}

Query: "inspect the dataset"
{
  "intent": "inspect",
  "slots": {"column": null, "operator": null, "value": null, "target_column": null, "aggregation": null, "sort_direction": null, "limit": null},
  "confidence": 0.85, "missing_slots": [], "ambiguities": [], "query_locale": "en"
}
"""

_USER_PROMPT = "User query: {query}\n\nExtract slots as JSON."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _empty_result(query: str) -> SlotExtractionResult:
    return SlotExtractionResult(raw_query=query, intent="unknown", confidence=0.0)


def _parse_llm_output(raw: str, query: str) -> tuple[SlotExtractionResult, str | None]:
    """Parse raw LLM JSON into SlotExtractionResult.

    Returns (result, parse_error). parse_error is None on success.
    """
    if not raw or not raw.strip():
        return _empty_result(query), "LLM returned empty output"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _empty_result(query), f"Invalid JSON from LLM: {exc}"

    if not isinstance(data, dict):
        return _empty_result(query), "LLM response is not a JSON object"

    slots_data = data.get("slots") or {}
    try:
        slots = ExtractedSlots(**{k: v for k, v in slots_data.items() if v is not None})
    except (ValidationError, TypeError) as exc:
        return _empty_result(query), f"Slot field type error: {exc}"

    try:
        result = SlotExtractionResult(
            raw_query=query,
            intent=data.get("intent", "unknown"),
            slots=slots,
            confidence=float(data.get("confidence", 0.0)),
            missing_slots=data.get("missing_slots") or [],
            ambiguities=data.get("ambiguities") or [],
            query_locale=data.get("query_locale", "en"),
        )
    except (ValidationError, TypeError) as exc:
        return _empty_result(query), f"SlotExtractionResult validation error: {exc}"

    return result, None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def extract_slots(query: str, *, client: OpenAI | None = None) -> SlotExtractorOutput:
    """Extract structured slots from a raw user query via a few-shot LLM call.

    Args:
        query:  Raw user input.
        client: Optional pre-built OpenAI client; a default client is created
                from settings if not provided (useful for testing via injection).

    Returns:
        SlotExtractorOutput with .result, .raw_llm_output, and optional .parse_error.
        Never raises; all errors are captured in .parse_error.
    """
    if client is None:
        client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _USER_PROMPT.format(query=query)},
    ]

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=512,
            temperature=0,
        )
        raw_output = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("Slot extractor LLM call failed: %s", exc)
        raw_output = ""

    result, parse_error = _parse_llm_output(raw_output, query)

    if parse_error:
        logger.warning("Slot extractor parse error for query %r: %s", query, parse_error)

    return SlotExtractorOutput(
        result=result,
        raw_llm_output=raw_output,
        parse_error=parse_error,
    )
