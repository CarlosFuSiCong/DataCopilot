"""Tool selector — deterministic layer that ranks candidate tools from retrieved docs.

Derives intent from the composition of retrieved doc types, then uses that
derived intent to apply a scoring bonus. No LLM calls, no separate keyword list.

Observation-driven bonuses (Task 8): observation signals from a previous preview
can boost tools that are relevant to the diagnosed problem, making them appear
higher in candidate_tools even when not retrieved via RAG.
"""
from app.agent.observation.models import ObservationSummary
from app.agent.planning.pipeline_models import ObservationToolSuggestion, ToolSelectionResult
from app.agent.task_intake.intent import ParsedTaskIntent, TaskIntentType
from app.models.rag import RetrievedDoc

_INSPECT_TOOLS = {
    "generate_summary", "select_columns", "limit_rows",
    "profile_column", "inspect_unique_values", "summarize_numeric_column",
    "compare_groups", "correlation_summary", "distribution_summary",
    "suggest_analysis_steps",
}
_TRANSFORM_TOOLS = {
    "filter_rows", "group_by", "sort_values", "rename_columns",
    "remove_missing_values", "fill_missing_values", "drop_columns",
    "derive_column", "date_extract", "date_diff", "bin_column",
    "cast_column", "deduplicate_rows", "replace_values", "pivot_table",
    "normalize_text", "trim_text", "extract_text", "conditional_column",
}

_INTENT_BONUS = 0.5
# Observation signal bonus — enough to surface suggested tools above neutral RAG noise
# but below a strong RAG hit, so domain-matched tools still win.
_OBS_BONUS = 0.6

# Maps each observation signal to an ordered list of (tool_type, reason) pairs.
# Tools earlier in the list receive the full _OBS_BONUS; later entries also receive
# the bonus but appear lower when their RAG score is lower.
_SIGNAL_TOOL_MAP: dict[str, list[tuple[str, str]]] = {
    "empty_result": [
        (
            "inspect_unique_values",
            "Empty result may indicate a value mismatch; inspect actual column values.",
        ),
        (
            "profile_column",
            "Profile the filtered column to understand available values and missing rate.",
        ),
    ],
    "suspected_wrong_value": [
        (
            "inspect_unique_values",
            "Suspected wrong filter value; inspect column to find the correct value.",
        ),
        (
            "profile_column",
            "Profile column to verify available values and distribution.",
        ),
    ],
    "suspected_wrong_column": [
        (
            "profile_column",
            "Suspected wrong column reference; profile candidate columns to identify the correct one.",
        ),
        (
            "inspect_unique_values",
            "Inspect values of the suspected column to confirm or rule out a name mismatch.",
        ),
    ],
    "data_quality_issue": [
        (
            "remove_missing_values",
            "Missing values detected; remove rows with nulls before analysis.",
        ),
        (
            "fill_missing_values",
            "Fill missing values to prevent gaps in aggregations or filters.",
        ),
        (
            "distribution_summary",
            "Distribution may be skewed by missing or extreme values; inspect before deciding.",
        ),
    ],
    "large_row_removal": [
        (
            "distribution_summary",
            "Large fraction of rows removed; check if the filter threshold is appropriate.",
        ),
        (
            "summarize_numeric_column",
            "Summarize the filtered column to verify that the threshold makes sense.",
        ),
    ],
    "high_warning_rate": [
        (
            "distribution_summary",
            "High warning rate may indicate data quality issues in the source data.",
        ),
        (
            "suggest_analysis_steps",
            "Multiple warnings detected; suggest structured next steps.",
        ),
    ],
    "needs_inspection": [
        (
            "suggest_analysis_steps",
            "Multiple signals detected; suggest an analysis plan before further transformation.",
        ),
        (
            "profile_column",
            "Profile key columns to gather evidence before deciding on the next step.",
        ),
    ],
}


def suggest_tools_from_observation(
    observation: ObservationSummary,
) -> list[ObservationToolSuggestion]:
    """Return tool suggestions derived from observation signals.

    Each signal maps to one or more tool recommendations. Duplicate tool types
    are de-duplicated (first signal that triggered a tool type wins).
    """
    seen: set[str] = set()
    suggestions: list[ObservationToolSuggestion] = []
    for signal in observation.signals:
        for tool_type, reason in _SIGNAL_TOOL_MAP.get(signal, []):
            if tool_type not in seen:
                suggestions.append(
                    ObservationToolSuggestion(
                        tool_type=tool_type,
                        signal=signal,
                        reason=reason,
                    )
                )
                seen.add(tool_type)
    return suggestions


def select_tools(
    intent: ParsedTaskIntent,
    retrieved_docs: list[RetrievedDoc],
    *,
    observation: ObservationSummary | None = None,
) -> ToolSelectionResult:
    """Derive intent from retrieved doc types, then rank candidate tools.

    Intent is determined by which category (transform vs inspect) appears more
    frequently in the top-k docs. The derived intent is used to apply a scoring
    bonus to matching tools. Raw scores are preserved for downstream inspection.

    When an observation is provided, additional tools are suggested based on
    observation signals and receive a scoring bonus (_OBS_BONUS). These tools
    appear in candidate_tools even when not retrieved via RAG.

    The ParsedTaskIntent argument carries candidate_columns and constraints from
    the query; its intent field is intentionally ignored here.
    """
    derived_intent = _derive_intent_from_docs(retrieved_docs)
    obs_suggestions = suggest_tools_from_observation(observation) if observation else []
    scores = _score_tools(derived_intent, retrieved_docs, obs_suggestions)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    candidate_tools = [tool for tool, _ in ordered]

    return ToolSelectionResult(
        intent=derived_intent,
        candidate_tools=candidate_tools,
        selected_tool=candidate_tools[0] if candidate_tools else None,
        scores={tool: round(score, 4) for tool, score in scores.items()},
        observation_suggestions=obs_suggestions,
    )


def _derive_intent_from_docs(docs: list[RetrievedDoc]) -> TaskIntentType:
    """Count transform vs inspect tools in retrieved docs to vote on intent.

    On a tie, transform_dataset wins because most user queries are data
    transformation requests. Returns 'unknown' only when no relevant docs exist.
    """
    transform_count = 0
    inspect_count = 0
    for doc in docs:
        if doc.doc_type != "transformation" or not doc.type:
            continue
        if doc.type in _TRANSFORM_TOOLS:
            transform_count += 1
        elif doc.type in _INSPECT_TOOLS:
            inspect_count += 1

    if transform_count == 0 and inspect_count == 0:
        return "unknown"
    if inspect_count > transform_count:
        return "inspect_dataset"
    return "transform_dataset"


def _score_tools(
    derived_intent: TaskIntentType,
    retrieved_docs: list[RetrievedDoc],
    obs_suggestions: list[ObservationToolSuggestion],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for doc in retrieved_docs:
        if doc.doc_type != "transformation" or not doc.type:
            continue
        tool_type = doc.type
        candidate = float(doc.score) + _intent_bonus(derived_intent, tool_type)
        # Keep the highest score when multiple docs reference the same tool type.
        if candidate > scores.get(tool_type, 0.0):
            scores[tool_type] = candidate
    # Apply observation signal bonuses — add to existing score or start from _OBS_BONUS.
    for suggestion in obs_suggestions:
        tool_type = suggestion.tool_type
        scores[tool_type] = scores.get(tool_type, 0.0) + _OBS_BONUS
    return scores


def _intent_bonus(derived_intent: TaskIntentType, tool_type: str) -> float:
    if derived_intent == "inspect_dataset" and tool_type in _INSPECT_TOOLS:
        return _INTENT_BONUS
    if derived_intent == "transform_dataset" and tool_type in _TRANSFORM_TOOLS:
        return _INTENT_BONUS
    return 0.0
