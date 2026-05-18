"""LLM-based query type classifier with deterministic fallback.

Primary path: calls a lightweight LLM (same model as the planner) with a
structured JSON prompt to classify the query into a QueryType and derive a
RouteDecision.  The LLM is language-agnostic — Chinese, English, or any
other language works without adding keyword lists.

Fallback path: if the LLM API key is absent, the LLM call fails, or the
response cannot be parsed, `classify_deterministic()` is used instead.  That
function uses regex keyword tables and is kept for offline tests and CI.

Route derivation is always deterministic regardless of which classification
path ran, and is based on query_type + confidence thresholds:
  confidence >= 0.8 → deterministic_tool or ask_mode
  0.5 <= confidence < 0.8 → llm_planner (or clarification for broad/ambiguous)
  confidence < 0.5 → clarification
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Sequence

from openai import OpenAI

from app.core.config import settings
from app.workflow.planning.route_decision import QueryType, Route, RouteDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM_PROMPT = """\
You are a query type classifier for a data workflow assistant called DataCopilot.

Classify the user's query into exactly ONE of these query types:

  ask                  - Read-only question about the dataset (schema, column types, row count, sample data, previous result explanation).
  profiling            - Profile or summarize a column (distribution, unique values, statistics, histogram).
  diagnosis            - Detect data quality issues (missing values, duplicates, null check, data quality overview).
  comparison           - Compare groups or categories (compare X by Y, difference between groups, ranking).
  aggregation          - Aggregate or group data (group by, sum, count, average, pivot table, rollup).
  filtering            - Filter rows by a condition (where clause, keep rows matching criteria, exclude rows).
  sorting              - Sort or order rows (sort by column, top N, ascending/descending).
  cleaning             - Mutate the dataset to fix quality issues (remove missing, drop duplicates, fill null, trim, impute).
  broad_analysis_request - Vague high-level request without a specific operation (analyse this data, find insights, explore).
  visual_analysis      - Request to plot or chart data (bar chart, histogram, scatter plot, visualize).
  unsupported_request  - Request that is outside the tool's scope (predict, forecast, machine learning, clustering, regression).
  ambiguous_request    - Cannot be classified into any of the above with confidence.

Rules:
- Pick the single most specific type that matches the intent.
- cleaning beats diagnosis when the user wants to MODIFY data (remove/drop/fill).
- comparison beats aggregation when the query uses "compare" or asks about differences between groups.
- If the query is vague but not clearly broad_analysis, prefer ambiguous_request.

Output valid JSON only, no extra text:
{
  "query_type": "<one of the types above>",
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence explaining the classification>",
  "evidence": ["<keyword or phrase from the query that drove the decision>"]
}
"""

# ---------------------------------------------------------------------------
# Tool / route tables
# ---------------------------------------------------------------------------

_TYPE_TO_DEFAULT_TOOL: dict[str, str] = {
    "profiling": "profile_column",
    "diagnosis": "detect_missing_values",
    "comparison": "compare_groups",
}

_DUPLICATE_TOOL_PATTERN = re.compile(r"duplicate|重复", re.IGNORECASE)
_DISTRIBUTION_TOOL_PATTERN = re.compile(
    r"distribution|histogram|spread|range|分布",
    re.IGNORECASE,
)
_UNIQUE_TOOL_PATTERN = re.compile(
    r"unique\s+values?|value\s+counts?|inspect\s+unique|取值",
    re.IGNORECASE,
)
_CORRELATION_TOOL_PATTERN = re.compile(r"correlat(e|ion)|相关", re.IGNORECASE)


def _selected_tool(query_type: str, query_lower: str) -> str | None:
    if _CORRELATION_TOOL_PATTERN.search(query_lower):
        return "correlation_summary"
    if query_type == "profiling":
        if _UNIQUE_TOOL_PATTERN.search(query_lower):
            return "inspect_unique_values"
        if _DISTRIBUTION_TOOL_PATTERN.search(query_lower):
            return "distribution_summary"
        return "profile_column"
    if query_type == "diagnosis":
        return "detect_duplicates" if _DUPLICATE_TOOL_PATTERN.search(query_lower) else "detect_missing_values"
    return _TYPE_TO_DEFAULT_TOOL.get(query_type)


def _derive_route(query_type: str, confidence: float) -> Route:
    """Deterministically derive the processing route from type and confidence."""
    if query_type == "ask":
        return "ask_mode"
    if query_type in ("unsupported_request", "visual_analysis"):
        return "unsupported"
    if query_type in ("broad_analysis_request", "ambiguous_request"):
        return "clarification"
    if confidence >= 0.8 and query_type in ("profiling", "diagnosis", "comparison"):
        return "deterministic_tool"
    if confidence >= 0.5:
        return "llm_planner"
    return "clarification"


# ---------------------------------------------------------------------------
# LLM classification
# ---------------------------------------------------------------------------

_VALID_QUERY_TYPES: set[str] = {
    "ask", "profiling", "diagnosis", "comparison", "aggregation",
    "filtering", "sorting", "cleaning", "broad_analysis_request",
    "visual_analysis", "unsupported_request", "ambiguous_request",
}


def _call_llm(query: str, client: OpenAI) -> dict[str, Any]:
    """Call the LLM classifier and return the parsed JSON dict."""
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=200,
        temperature=0,
    )
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


def _build_route_decision(
    data: dict[str, Any],
    query_lower: str,
    col_evidence: list[str],
) -> RouteDecision:
    """Convert a parsed LLM response dict into a RouteDecision."""
    raw_type = str(data.get("query_type", "ambiguous_request")).strip()
    query_type: QueryType = raw_type if raw_type in _VALID_QUERY_TYPES else "ambiguous_request"  # type: ignore[assignment]
    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))
    reason = str(data.get("reason", ""))
    evidence: list[str] = list(data.get("evidence", []))
    if col_evidence:
        evidence = list(dict.fromkeys(evidence + col_evidence))

    route = _derive_route(query_type, confidence)
    tool = _selected_tool(query_type, query_lower) if route in ("deterministic_tool", "ask_mode") else None

    return RouteDecision(
        route=route,
        query_type=query_type,
        confidence=round(confidence, 2),
        reason=reason,
        evidence=evidence,
        extracted_slots={"candidate_columns": col_evidence},
        selected_tool=tool,
        fallback_route="llm_planner" if route not in ("ask_mode", "unsupported") else None,
    )


# ---------------------------------------------------------------------------
# Deterministic fallback (regex-based)
# ---------------------------------------------------------------------------

_ASK_PATTERNS = [
    r"\bwhat\s+columns?\b", r"\bwhich\s+columns?\b", r"\bhow\s+many\s+rows?\b",
    r"\bhow\s+many\s+columns?\b", r"\bshow\s+me\s+the\s+(schema|columns?|fields?|structure)\b",
    r"\blist\s+(the\s+)?(columns?|fields?)\b", r"\bwhat('s|\s+is)\s+(in\s+)?this\s+dataset\b",
    r"\bdescribe\s+(the\s+)?(dataset|data|table)\b", r"\bwhat\s+does\s+\w+\s+column\b",
    r"\btell\s+me\s+about\s+(this\s+)?(dataset|data)\b",
    r"\bexplain\s+(the\s+)?(previous\s+)?(result|column|dataset)\b",
    r"\bwhat\s+(are\s+)?(the\s+)?(data\s+)?types?\b", r"\bshow\s+(me\s+)?sample\b",
    r"\bdata\s+overview\b", r"\boverview\s+of\s+(the\s+)?data\b",
    r"这个数据有哪些字段", r"有哪些列", r"有多少行", r"这个数据是什么",
]
_PROFILING_PATTERNS = [
    r"\bprofile\b", r"\bdistribution\s+(of\s+|summary\b|for\b)?", r"\binspect\s+unique\b",
    r"\bunique\s+values?\b", r"\bvalue\s+counts?\b", r"\bsummariz(e|ation)\b",
    r"\bhistogram\b", r"\bspread\s+of\b", r"\brange\s+of\b", r"\bmin\b.*\bmax\b",
    r"\bstats?\s+(for|of|on)\b", r"\bstatistics\b", r"看看.+的分布", r"分布情况", r"取值情况",
    r"分析.+分布", r"分布",
]
_DIAGNOSIS_PATTERNS = [
    r"\bdetect\s+(missing|duplicates?|null|nulls|outlier)\b",
    r"\bcheck\s+(for\s+)?(missing|duplicates?|null|outlier|data\s+quality)\b",
    r"\bmissing\s+values?\b", r"\bduplicate\s+(rows?|records?|values?|entries?)?\b",
    r"\bnull\s+values?\b", r"\bdata\s+quality\b", r"\bdata\s+issues?\b",
    r"\bwhat('s|\s+is)\s+wrong\s+(with|in)\b", r"\bfind\s+(all\s+)?(missing|duplicate|null)\b",
    r"有哪些问题", r"缺失值", r"重复值", r"数据质量", r"帮我看看这个数据有什么问题",
]
_COMPARISON_PATTERNS = [
    r"\bcompare\b", r"\bgroup\s+comparison\b", r"\bdifference\s+between\b",
    r"\bcorrelation\b", r"\bcorrelate\b", r"\bcorrelations?\s+between\b",
    r"\brank\s+(by|groups?)\b", r"按.+比较", r"各.+的.+(均值|总量|数量)", r"不同.+的.+对比",
]
_AGGREGATION_PATTERNS = [
    r"\bgroup\s+by\b", r"\bsum\s+(of\s+|the\s+)?\w+\b", r"\btotal\s+(of\s+|the\s+)?\w+\b",
    r"\bcount\s+(of\s+|the\s+)?\w+\b", r"\baverage\s+(of\s+|the\s+)?\w+\b", r"\baggregate\b",
    r"\bpivot\s+table\b", r"\brollup\b",
    r"\b(average|mean|sum|total|count)\s+\w+\s+by\s+\w+\b",
    r"按.+分组", r"汇总", r"求和", r"统计",
]
_FILTERING_PATTERNS = [
    r"\bfilter\b", r"\bwhere\b", r"\bonly\s+(rows?|records?|entries?)\s+where\b",
    r"\brows?\s+where\b", r"\bkeep\s+(only\s+)?(rows?|records?)\b", r"\bsubset\b",
    r"\bshow\s+(me\s+)?(rows?|records?)\s+where\b", r"\bexclude\s+(rows?|records?)\b",
    r"筛选", r"过滤", r"只保留",
]
_SORTING_PATTERNS = [
    r"\bsort\b", r"\border\s+by\b", r"\btop\s+\d+\b", r"\bbottom\s+\d+\b",
    r"\bascending\b", r"\bdescending\b", r"排序", r"按.+排列", r"最高", r"最低",
]
_CLEANING_PATTERNS = [
    r"\bremove\s+(missing|null|duplicate|duplicates?)\b",
    r"\bremove\s+all\s+rows?\s+with\s+(missing|null)\s+values?\b",
    r"\bdrop\s+(missing|null|duplicate|duplicates?|column)\b",
    r"\brename\s+column\b",
    r"\bfill\s+(missing|null)\b", r"\bclean\b", r"\bimpute\b", r"\bdeduplicate\b",
    r"\bstrip\s+(whitespace|spaces?)\b", r"\btrim\b", r"\bdelete\s+(rows?|column)\b",
    r"\bextract\b", r"\bcalculate\s+days\s+between\b", r"\bdays\s+between\b",
    r"\badd\s+a\s+column\b", r"\bcreate\s+\w+\s+bands?\b", r"\bbins?\b",
    r"\breplace\b", r"\bcast\b", r"\bnormalize\b",
    r"删除重复", r"删除缺失", r"填充缺失", r"填充.+缺失", r"清洗", r"归一化", r"标准化",
]
_VISUAL_PATTERNS = [
    r"\bplot\b", r"\bchart\b", r"\bgraph\b", r"\bvisuali[sz]e?\b",
    r"\bbar\s+chart\b", r"\bline\s+chart\b", r"\bscatter\s+plot\b", r"画图", r"绘制",
]
_UNSUPPORTED_PATTERNS = [
    r"\bpredict\b", r"\bforecast\b", r"\bmachine\s+learning\b", r"\bml\s+model\b",
    r"\btrain\s+(a\s+)?model\b", r"\bclassif(y|ication)\b", r"\bregression\b",
    r"\bcluster(ing)?\b", r"\bneural\s+network\b", r"\bdeep\s+learning\b",
    r"\bfeature\s+engineering\b", r"\bautoml\b", r"预测", r"机器学习", r"训练模型",
]
_BROAD_PATTERNS = [
    r"\banalyze\b", r"\banalysis\b", r"\bexplore\b", r"\bexploration\b", r"\binsights?\b",
    r"\bwhat('s|\s+is)\s+interesting\b", r"\bwhat\s+can\s+(you|I)\s+(tell|find|see)\b",
    r"\bgive\s+me\s+an?\s+overview\b", r"帮我分析", r"分析一下", r"看看有什么有趣", r"全面分析",
]

_DETERMINISTIC_CHECKS: list[tuple[list[str], str, float]] = [
    (_UNSUPPORTED_PATTERNS, "unsupported_request", 0.95),
    (_VISUAL_PATTERNS,      "visual_analysis",     0.90),
    (_ASK_PATTERNS,         "ask",                 0.85),
    (_CLEANING_PATTERNS,    "cleaning",            0.75),
    (_PROFILING_PATTERNS,   "profiling",           0.80),
    (_DIAGNOSIS_PATTERNS,   "diagnosis",           0.80),
    (_COMPARISON_PATTERNS,  "comparison",          0.80),
    (_AGGREGATION_PATTERNS, "aggregation",         0.70),
    (_FILTERING_PATTERNS,   "filtering",           0.70),
    (_SORTING_PATTERNS,     "sorting",             0.39),
    (_BROAD_PATTERNS,       "broad_analysis_request", 0.55),
]


def _regex_matches(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            hits.append(m.group(0))
    return hits


def _col_evidence(query_lower: str, column_names: Sequence[str]) -> list[str]:
    return [
        col for col in column_names
        if re.search(r"\b" + re.escape(col.lower()) + r"\b", query_lower)
    ]


def classify_deterministic(
    query: str,
    column_names: Sequence[str] | None = None,
) -> RouteDecision:
    """Regex-based classifier.  No LLM calls — used as fallback and in tests."""
    cols = list(column_names or [])
    q = query.lower()
    col_ev = _col_evidence(q, cols)

    for patterns, qtype, base_conf in _DETERMINISTIC_CHECKS:
        hits = _regex_matches(q, patterns)
        if not hits:
            continue
        conf = base_conf
        if len(hits) >= 2:
            conf = min(conf + 0.1, 1.0)
        if col_ev:
            conf = min(conf + 0.1, 1.0)
        conf = round(conf, 2)
        route = _derive_route(qtype, conf)
        tool = _selected_tool(qtype, q) if route in ("deterministic_tool", "ask_mode") else None
        return RouteDecision(
            route=route,
            query_type=qtype,  # type: ignore[arg-type]
            confidence=conf,
            reason=f"Deterministic match on patterns: {hits[:3]}",
            evidence=hits[:5],
            extracted_slots={"candidate_columns": col_ev},
            selected_tool=tool,
            fallback_route="llm_planner" if route not in ("ask_mode", "unsupported") else None,
        )

    return RouteDecision(
        route="clarification",
        query_type="ambiguous_request",
        confidence=0.3,
        reason="No keyword pattern matched. Requesting clarification.",
        evidence=[],
        extracted_slots={"candidate_columns": col_ev},
        fallback_route="llm_planner",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(
    query: str,
    column_names: Sequence[str] | None = None,
    _client: OpenAI | None = None,
) -> RouteDecision:
    """Classify a user query and return a RouteDecision.

    Uses the LLM for language-agnostic classification.  Falls back to the
    deterministic regex classifier when the API key is absent or the call fails.

    Parameters
    ----------
    query:
        Raw user query in any language.
    column_names:
        Active dataset column names used to extract slot evidence.
    _client:
        Optional pre-built OpenAI client (primarily for testing).
    """
    cols = list(column_names or [])
    col_ev = _col_evidence(query.lower(), cols)

    if not settings.llm_api_key:
        logger.debug("LLM API key not set — using deterministic classifier.")
        return classify_deterministic(query, column_names)

    try:
        client = _client or OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
        data = _call_llm(query, client)
        rd = _build_route_decision(data, query.lower(), col_ev)
        logger.info(
            "LLM classifier: type=%s route=%s confidence=%.2f reason=%r",
            rd.query_type, rd.route, rd.confidence, rd.reason,
        )
        return rd
    except Exception as exc:
        logger.warning("LLM classifier failed (%s) — falling back to deterministic.", exc)
        return classify_deterministic(query, column_names)
