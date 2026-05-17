"""Analyst flow planner for bounded multi-step analytical workflows.

Produces a deterministic, ordered sequence of analytical step suggestions
(AnalystFlowPlan) based on the dataset schema and current observation signals.
Does not call any LLM — all logic is rule-based and fully testable.

Design constraints (Task 9):
- Maximum 3 steps per plan (inspect / profile → summarize → compare).
- Each suggestion carries rationale and evidence so the caller can present
  a meaningful confirmation prompt to the user before executing.
- Two predefined demo paths are supported:
    "explore"  — profile → summarize → compare (numeric + categorical data)
    "quality"  — profile → inspect_unique_values  (data quality issues present)
- next_suggestion() drives the step-by-step confirmation flow.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.observation.models import ObservationSummary
from app.models.dataset import DatasetProfile


# Maximum number of analytical steps in a single analyst flow.
_MAX_FLOW_STEPS = 3

AnalystDemoPath = Literal["explore", "quality", "minimal"]


class AnalystStepSuggestion(BaseModel):
    """A single step in an analyst flow plan, with rationale and evidence.

    Parameters contain the recommended arguments for the suggested tool type.
    confirmation_question is the prompt shown to the user before execution.
    is_destructive marks steps that modify the dataset (require extra care).
    """

    tool_type: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    confirmation_question: str
    is_destructive: bool = False


class AnalystFlowPlan(BaseModel):
    """Ordered, bounded list of analyst step suggestions for one session.

    suggestions are ordered by recommended execution sequence.
    max_steps caps how many steps the flow may advance before stopping.
    """

    demo_path: AnalystDemoPath
    suggestions: list[AnalystStepSuggestion] = Field(default_factory=list)
    max_steps: int = Field(default=_MAX_FLOW_STEPS, ge=1)
    rationale: str


def plan_analyst_flow(
    dataset_profile: DatasetProfile,
    observation: ObservationSummary | None = None,
) -> AnalystFlowPlan:
    """Build a bounded analyst flow plan from dataset schema and observation.

    Selects a demo path based on:
    - Observation signals (quality-related signals → quality path).
    - Dataset composition (numeric + categorical columns → explore path).
    - Falls back to the minimal path (suggest_analysis_steps only).

    The returned plan is deterministic and does not call any LLM.
    """
    numeric_cols = _numeric_columns(dataset_profile)
    cat_cols = _categorical_columns(dataset_profile)
    missing_cols = _missing_columns(dataset_profile)
    obs_signals = list((observation.signals if observation else []))

    quality_signals = {
        "data_quality_issue",
        "suspected_wrong_value",
        "suspected_wrong_column",
        "needs_inspection",
    }
    is_quality = bool(obs_signals and quality_signals.intersection(obs_signals))
    is_explore = bool(numeric_cols and cat_cols)

    if is_quality:
        return _quality_plan(numeric_cols, cat_cols, missing_cols, obs_signals)
    if is_explore:
        return _explore_plan(numeric_cols, cat_cols, obs_signals)
    return _minimal_plan(numeric_cols, cat_cols)


def next_suggestion(
    plan: AnalystFlowPlan,
    completed_step_types: list[str],
) -> AnalystStepSuggestion | None:
    """Return the first uncompleted suggestion from the plan, or None.

    A suggestion is considered completed when its tool_type appears anywhere
    in completed_step_types.  Only the first occurrence matters — the flow
    advances one step at a time.
    """
    done = set(completed_step_types)
    for suggestion in plan.suggestions[: plan.max_steps]:
        if suggestion.tool_type not in done:
            return suggestion
    return None


# ---------------------------------------------------------------------------
# Path builders
# ---------------------------------------------------------------------------


def _explore_plan(
    numeric_cols: list[str],
    cat_cols: list[str],
    obs_signals: list[str],
) -> AnalystFlowPlan:
    num = numeric_cols[0]
    cat = cat_cols[0]
    evidence_base = [f"dataset has numeric column '{num}'", f"dataset has categorical column '{cat}'"]
    if obs_signals:
        evidence_base += [f"observation signal: {s}" for s in obs_signals[:2]]

    suggestions = [
        AnalystStepSuggestion(
            tool_type="profile_column",
            rationale=(
                f"Profiling '{num}' reveals its distribution shape, "
                "missing values, and outliers before deeper analysis."
            ),
            evidence=evidence_base[:],
            parameters={"column": num},
            confirmation_question=f"Profile column '{num}' to inspect its distribution?",
        ),
        AnalystStepSuggestion(
            tool_type="summarize_numeric_column",
            rationale=(
                f"Numeric summary of '{num}' provides mean, median, std, "
                "and percentiles for statistical context."
            ),
            evidence=[f"profile_column completed for '{num}'", *evidence_base[:1]],
            parameters={"column": num},
            confirmation_question=f"Summarize numeric column '{num}' (mean, median, std, percentiles)?",
        ),
        AnalystStepSuggestion(
            tool_type="compare_groups",
            rationale=(
                f"Comparing '{num}' across '{cat}' groups reveals "
                "whether values differ meaningfully between categories."
            ),
            evidence=[
                f"summarize_numeric_column completed for '{num}'",
                f"categorical column '{cat}' available for grouping",
            ],
            parameters={"group_column": cat, "value_column": num, "aggregation": "mean"},
            confirmation_question=(
                f"Compare mean '{num}' across '{cat}' groups?"
            ),
        ),
    ]
    return AnalystFlowPlan(
        demo_path="explore",
        suggestions=suggestions,
        max_steps=_MAX_FLOW_STEPS,
        rationale=(
            f"Dataset has numeric column '{num}' and categorical column '{cat}'. "
            "Recommended path: profile → summarize → compare groups."
        ),
    )


def _quality_plan(
    numeric_cols: list[str],
    cat_cols: list[str],
    missing_cols: list[str],
    obs_signals: list[str],
) -> AnalystFlowPlan:
    focus_col = missing_cols[0] if missing_cols else (numeric_cols[0] if numeric_cols else None)
    inspect_col = next((c for c in cat_cols if c in missing_cols), cat_cols[0] if cat_cols else focus_col)
    evidence_base = [f"observation signal: {s}" for s in obs_signals[:3]]
    if missing_cols:
        evidence_base.append(f"columns with missing values: {missing_cols[:3]}")

    suggestions: list[AnalystStepSuggestion] = []
    if focus_col:
        suggestions.append(
            AnalystStepSuggestion(
                tool_type="profile_column",
                rationale=(
                    f"Profiling '{focus_col}' identifies missing value patterns "
                    "and anomalies before deciding on a cleaning strategy."
                ),
                evidence=evidence_base[:],
                parameters={"column": focus_col},
                confirmation_question=f"Profile column '{focus_col}' to identify data quality issues?",
            )
        )
    if inspect_col:
        suggestions.append(
            AnalystStepSuggestion(
                tool_type="inspect_unique_values",
                rationale=(
                    f"Inspecting unique values of '{inspect_col}' exposes "
                    "unexpected nulls, typos, and category distribution."
                ),
                evidence=[*(["profile_column completed"] if focus_col else []), *evidence_base[:2]],
                parameters={"column": inspect_col},
                confirmation_question=f"Inspect unique values of '{inspect_col}' to find anomalies?",
            )
        )
    suggestions.append(
        AnalystStepSuggestion(
            tool_type="suggest_analysis_steps",
            rationale=(
                "After reviewing data quality, suggest next analytical steps "
                "based on the current dataset state."
            ),
            evidence=["quality inspection completed"],
            parameters={},
            confirmation_question="Generate next-step analysis suggestions based on current data?",
        )
    )
    return AnalystFlowPlan(
        demo_path="quality",
        suggestions=suggestions,
        max_steps=_MAX_FLOW_STEPS,
        rationale=(
            "Observation signals indicate data quality issues. "
            "Recommended path: profile → inspect unique values → suggest analysis steps."
        ),
    )


def _minimal_plan(
    numeric_cols: list[str],
    cat_cols: list[str],
) -> AnalystFlowPlan:
    suggestions: list[AnalystStepSuggestion] = [
        AnalystStepSuggestion(
            tool_type="suggest_analysis_steps",
            rationale=(
                "Dataset schema does not clearly indicate an explore or quality path. "
                "Generating general analysis suggestions to guide the next action."
            ),
            evidence=["no dominant quality signals", "no numeric+categorical column pair found"],
            parameters={},
            confirmation_question="Generate analysis suggestions for this dataset?",
        )
    ]
    if numeric_cols:
        suggestions.append(
            AnalystStepSuggestion(
                tool_type="profile_column",
                rationale=f"Profile the first numeric column '{numeric_cols[0]}' to understand its distribution.",
                evidence=[f"numeric column '{numeric_cols[0]}' is available"],
                parameters={"column": numeric_cols[0]},
                confirmation_question=f"Profile column '{numeric_cols[0]}'?",
            )
        )
    return AnalystFlowPlan(
        demo_path="minimal",
        suggestions=suggestions,
        max_steps=_MAX_FLOW_STEPS,
        rationale="Minimal path: suggest analysis steps, then optionally profile numeric columns.",
    )


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

_NUMERIC_DTYPES = {
    "int8", "int16", "int32", "int64",
    "uint8", "uint16", "uint32", "uint64",
    "float16", "float32", "float64",
    "number", "int", "float",
}
_CAT_DTYPES = {"object", "string", "category", "bool", "boolean"}


def _numeric_columns(profile: DatasetProfile) -> list[str]:
    return [
        col.name
        for col in profile.columns
        if col.dtype.lower() in _NUMERIC_DTYPES
    ]


def _categorical_columns(profile: DatasetProfile) -> list[str]:
    return [
        col.name
        for col in profile.columns
        if col.dtype.lower() in _CAT_DTYPES or col.dtype.lower() == "object"
    ]


def _missing_columns(profile: DatasetProfile) -> list[str]:
    return [col.name for col in profile.columns if col.missing_count > 0]
