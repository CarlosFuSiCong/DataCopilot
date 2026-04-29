import math
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Individual step models — discriminated by the "type" literal field
# ---------------------------------------------------------------------------

class RemoveMissingValuesStep(BaseModel):
    type: Literal["remove_missing_values"]


class SelectColumnsStep(BaseModel):
    type: Literal["select_columns"]
    columns: list[str]


_OPERATOR_ALIASES: dict[str, str] = {"==": "=", "<>": "!="}


class FilterRowsStep(BaseModel):
    type: Literal["filter_rows"]
    column: str
    operator: Literal["=", "!=", ">", ">=", "<", "<="]
    value: Union[int, float, str]

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_operator(cls, v: str) -> str:
        return _OPERATOR_ALIASES.get(v, v)


class GroupByStep(BaseModel):
    type: Literal["group_by"]
    column: str
    target: str
    agg: Literal["sum", "mean", "count", "min", "max"]


class SortValuesStep(BaseModel):
    type: Literal["sort_values"]
    column: str
    ascending: bool = True


class RenameColumnsStep(BaseModel):
    type: Literal["rename_columns"]
    mapping: dict[str, str]


class GenerateSummaryStep(BaseModel):
    type: Literal["generate_summary"]


# Discriminated union — Pydantic resolves the correct subtype from "type"
WorkflowStep = Annotated[
    Union[
        RemoveMissingValuesStep,
        SelectColumnsStep,
        FilterRowsStep,
        GroupByStep,
        SortValuesStep,
        RenameColumnsStep,
        GenerateSummaryStep,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class WorkflowRequest(BaseModel):
    dataset_id: str
    steps: list[WorkflowStep]


class StepLog(BaseModel):
    step_index: int
    step_type: str
    rows_before: int
    rows_after: int
    message: str


class ExecutionResult(BaseModel):
    row_count: int
    column_count: int
    columns: list[str]
    preview: list[dict]
    logs: list[StepLog]
    # True when the workflow includes a generate_summary step (Task 5 will use this)
    has_summary: bool
