"""LLM-based slot extractor for the workflow NLU layer."""
import json
import logging
from dataclasses import dataclass

from openai import OpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.workflow.nlu.slot_models import ExtractedSlots, SlotExtractionResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlotExtractorOutput:
    result: SlotExtractionResult
    raw_llm_output: str
    parse_error: str | None = None


_SYSTEM_PROMPT = """\
You are the Slot Extractor for DataCopilot.

Parse a user's natural-language data query into structured slots.
Output ONLY valid JSON. Do NOT include explanations or markdown fences.

Output schema:
{
  "intent": "filter" | "sort" | "group_aggregate" | "limit" | "inspect" | "clean" | "unknown",
  "slots": {
    "column": string or null,
    "operator": "eq"|"ne"|"gt"|"gte"|"lt"|"lte"|"contains"|"not_contains"|"starts_with"|"ends_with"|"is_null"|"is_not_null" or null,
    "value": string or null,
    "target_column": string or null,
    "aggregation": "sum"|"mean"|"count"|"min"|"max"|"median" or null,
    "sort_direction": "asc"|"desc" or null,
    "limit": integer or null
  },
  "confidence": float 0.0-1.0,
  "missing_slots": list of required slot names that are absent,
  "ambiguities": list of free-text ambiguity descriptions,
  "query_locale": "en" | "zh" | "mixed"
}

Chinese operator mapping:
  大于 / 高于 -> "gt"
  大于等于 -> "gte"
  小于 / 低于 -> "lt"
  小于等于 -> "lte"
  等于 / 是 -> "eq"
  不等于 / 不是 -> "ne"
  包含 -> "contains"
  不包含 -> "not_contains"

Rules:
- Preserve column names exactly as written in the query; do not translate or infer.
- For filter intent: column and operator are required. value is required for
  comparison operators, but must be null for is_null / is_not_null.
- For sort intent: column and sort_direction are required.
- For group_aggregate intent: column is the group-by column, target_column is the numeric column, aggregation is required.
- For limit intent: limit is required.
- If the query is structurally ambiguous, set intent to "unknown" and explain in ambiguities.
- Use confidence 0.9+ for clear queries, 0.5-0.9 for partial extraction, below 0.5 for guesses.

Examples:

Query: "filter rows where amount > 1000"
{"intent":"filter","slots":{"column":"amount","operator":"gt","value":"1000","target_column":null,"aggregation":null,"sort_direction":null,"limit":null},"confidence":0.95,"missing_slots":[],"ambiguities":[],"query_locale":"en"}

Query: "find rows where amount is missing"
{"intent":"filter","slots":{"column":"amount","operator":"is_null","value":null,"target_column":null,"aggregation":null,"sort_direction":null,"limit":null},"confidence":0.95,"missing_slots":[],"ambiguities":[],"query_locale":"en"}

Query: "筛选 amount 大于 1000 的行"
{"intent":"filter","slots":{"column":"amount","operator":"gt","value":"1000","target_column":null,"aggregation":null,"sort_direction":null,"limit":null},"confidence":0.93,"missing_slots":[],"ambiguities":[],"query_locale":"zh"}

Query: "sort by date descending"
{"intent":"sort","slots":{"column":"date","operator":null,"value":null,"target_column":null,"aggregation":null,"sort_direction":"desc","limit":null},"confidence":0.95,"missing_slots":[],"ambiguities":[],"query_locale":"en"}

Query: "按 date 降序排列"
{"intent":"sort","slots":{"column":"date","operator":null,"value":null,"target_column":null,"aggregation":null,"sort_direction":"desc","limit":null},"confidence":0.93,"missing_slots":[],"ambiguities":[],"query_locale":"zh"}

Query: "total sales by region"
{"intent":"group_aggregate","slots":{"column":"region","operator":null,"value":null,"target_column":"sales","aggregation":"sum","sort_direction":null,"limit":null},"confidence":0.88,"missing_slots":[],"ambiguities":[],"query_locale":"en"}

Query: "按 region 分组求 sales 的总和"
{"intent":"group_aggregate","slots":{"column":"region","operator":null,"value":null,"target_column":"sales","aggregation":"sum","sort_direction":null,"limit":null},"confidence":0.92,"missing_slots":[],"ambiguities":[],"query_locale":"zh"}

Query: "show top 5 rows"
{"intent":"limit","slots":{"column":null,"operator":null,"value":null,"target_column":null,"aggregation":null,"sort_direction":null,"limit":5},"confidence":0.98,"missing_slots":[],"ambiguities":[],"query_locale":"en"}
"""

_USER_PROMPT = "User query: {query}\n\nExtract slots as JSON."


def _empty_result(query: str) -> SlotExtractionResult:
    return SlotExtractionResult(raw_query=query, intent="unknown", confidence=0.0)


def _parse_llm_output(raw: str, query: str) -> tuple[SlotExtractionResult, str | None]:
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


def extract_slots(query: str, *, client: OpenAI | None = None) -> SlotExtractorOutput:
    """Extract structured slots from a raw user query via a few-shot LLM call."""
    if client is None:
        if not settings.llm_api_key:
            return SlotExtractorOutput(
                result=_empty_result(query),
                raw_llm_output="",
                parse_error="LLM API key is not configured. Set LLM_API_KEY in your .env file.",
            )
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
