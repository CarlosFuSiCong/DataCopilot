"""Observation tools for agent-ready dataset inspection.

These tools are intentionally separate from workflow JSON transformations:
they inspect a DataFrame and return structured observations or recommended
workflow steps, but they never mutate data directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd


ObservationType = Literal[
    "detect_missing_values",
    "detect_duplicates",
    "detect_outliers",
    "suggest_cleaning_steps",
]


@dataclass(frozen=True)
class ObservationSpec:
    type: ObservationType
    description: str
    output_schema: dict[str, Any]
    enters_workflow_json: bool = False
    suggested_workflow_types: list[str] = field(default_factory=list)


def observation_tools() -> list[ObservationSpec]:
    return [
        ObservationSpec(
            type="detect_missing_values",
            description="Detect columns with missing values and missing percentages.",
            output_schema={
                "columns": [{"column": "string", "missing_count": "int", "missing_pct": "float"}]
            },
            suggested_workflow_types=["fill_missing_values", "remove_missing_values"],
        ),
        ObservationSpec(
            type="detect_duplicates",
            description="Detect duplicate rows across all columns or a subset.",
            output_schema={"duplicate_count": "int", "duplicate_pct": "float", "subset": "list[string] | null"},
            suggested_workflow_types=["deduplicate_rows"],
        ),
        ObservationSpec(
            type="detect_outliers",
            description="Detect numeric outliers using the IQR rule.",
            output_schema={
                "columns": [{"column": "string", "outlier_count": "int", "lower_bound": "float", "upper_bound": "float"}]
            },
            suggested_workflow_types=["filter_rows", "bin_column"],
        ),
        ObservationSpec(
            type="suggest_cleaning_steps",
            description="Suggest deterministic cleaning workflow steps from observations.",
            output_schema={"suggestions": [{"reason": "string", "step": "workflow_step"}]},
            suggested_workflow_types=["fill_missing_values", "deduplicate_rows", "cast_column"],
        ),
    ]


def detect_missing_values(df: pd.DataFrame) -> dict[str, Any]:
    columns = []
    total = len(df)
    for column in df.columns:
        missing = int(df[column].isna().sum())
        if missing:
            columns.append({
                "column": column,
                "missing_count": missing,
                "missing_pct": round((missing / total) * 100, 2) if total else 0.0,
            })
    return {"type": "detect_missing_values", "columns": columns}


def detect_duplicates(df: pd.DataFrame, subset: list[str] | None = None) -> dict[str, Any]:
    duplicate_count = int(df.duplicated(subset=subset).sum())
    total = len(df)
    return {
        "type": "detect_duplicates",
        "duplicate_count": duplicate_count,
        "duplicate_pct": round((duplicate_count / total) * 100, 2) if total else 0.0,
        "subset": subset,
    }


def detect_outliers(df: pd.DataFrame) -> dict[str, Any]:
    columns = []
    numeric = df.select_dtypes(include="number")
    for column in numeric.columns:
        q1 = numeric[column].quantile(0.25)
        q3 = numeric[column].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mask = (numeric[column] < lower) | (numeric[column] > upper)
        count = int(mask.sum())
        if count:
            columns.append({
                "column": column,
                "outlier_count": count,
                "lower_bound": float(lower),
                "upper_bound": float(upper),
            })
    return {"type": "detect_outliers", "columns": columns}


def suggest_cleaning_steps(df: pd.DataFrame) -> dict[str, Any]:
    suggestions: list[dict[str, Any]] = []
    missing = detect_missing_values(df)["columns"]
    for item in missing:
        column = item["column"]
        if pd.api.types.is_numeric_dtype(df[column]):
            step = {"type": "fill_missing_values", "column": column, "strategy": "mean"}
        else:
            step = {"type": "fill_missing_values", "column": column, "strategy": "mode"}
        suggestions.append({
            "reason": f"Column '{column}' has {item['missing_count']} missing value(s).",
            "step": step,
        })

    duplicates = detect_duplicates(df)
    if duplicates["duplicate_count"]:
        suggestions.append({
            "reason": f"Dataset has {duplicates['duplicate_count']} duplicate row(s).",
            "step": {"type": "deduplicate_rows", "columns": [], "keep": "first"},
        })

    return {"type": "suggest_cleaning_steps", "suggestions": suggestions}
