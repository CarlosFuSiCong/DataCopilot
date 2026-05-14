"""Workflow step contracts."""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


class RemoveMissingValuesStep(BaseModel):
    type: Literal["remove_missing_values"]


class SelectColumnsStep(BaseModel):
    type: Literal["select_columns"]
    columns: list[str]


_OPERATOR_ALIASES: dict[str, str] = {
    "==": "=",
    "<>": "!=",
    "equals": "=",
    "eq": "=",
    "equal": "=",
    "not_equal": "!=",
    "neq": "!=",
    "ne": "!=",
    "not_equals": "!=",
    "greater_than": ">",
    "gt": ">",
    "greater_than_or_equal": ">=",
    "gte": ">=",
    "ge": ">=",
    "less_than": "<",
    "lt": "<",
    "less_than_or_equal": "<=",
    "lte": "<=",
    "le": "<=",
}


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
    columns: list[str] = []
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


class LimitRowsStep(BaseModel):
    type: Literal["limit_rows"]
    n: int


_DERIVE_OPS = Literal["+", "-", "*", "/"]
_DERIVE_OP_ALIASES: dict[str, str] = {"add": "+", "sub": "-", "mul": "*", "div": "/"}


class DeriveColumnStep(BaseModel):
    type: Literal["derive_column"]
    new_column: str
    column: str
    operator: _DERIVE_OPS
    value: float | None = None
    other_column: str = ""

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_derive_op(cls, v: str) -> str:
        return _DERIVE_OP_ALIASES.get(v, v)


class DateExtractStep(BaseModel):
    type: Literal["date_extract"]
    column: str
    part: Literal["year", "month", "quarter", "day", "weekday"]
    new_column: str


class DropColumnsStep(BaseModel):
    type: Literal["drop_columns"]
    columns: list[str]


class FillMissingValuesStep(BaseModel):
    type: Literal["fill_missing_values"]
    column: str
    strategy: Literal["constant", "mean", "median", "mode", "ffill", "bfill"]
    value: Union[float, str, None] = None


class DeduplicateRowsStep(BaseModel):
    type: Literal["deduplicate_rows"]
    columns: list[str] = []
    keep: Literal["first", "last"] = "first"


class ReplaceValuesStep(BaseModel):
    type: Literal["replace_values"]
    column: str
    mapping: dict[Union[int, float, str, bool], Union[int, float, str, bool, None]]


class CastColumnStep(BaseModel):
    type: Literal["cast_column"]
    column: str
    target_type: Literal["string", "int", "float", "boolean", "datetime"]
    errors: Literal["raise", "coerce"] = "raise"


class ConditionalColumnStep(BaseModel):
    type: Literal["conditional_column"]
    new_column: str
    condition_column: str
    operator: Literal["=", "!=", ">", ">=", "<", "<="]
    value: Union[int, float, str]
    true_value: Union[int, float, str, bool, None]
    false_value: Union[int, float, str, bool, None]

    @field_validator("operator", mode="before")
    @classmethod
    def normalize_operator(cls, v: str) -> str:
        return _OPERATOR_ALIASES.get(v, v)


class BinColumnStep(BaseModel):
    type: Literal["bin_column"]
    column: str
    new_column: str
    bins: list[float]
    labels: list[str] = []
    include_lowest: bool = True


class PivotTableStep(BaseModel):
    type: Literal["pivot_table"]
    index: list[str]
    columns: str | None = None
    values: str
    agg: Literal["sum", "mean", "count", "min", "max"]


class TrimTextStep(BaseModel):
    type: Literal["trim_text"]
    column: str
    collapse_whitespace: bool = False


class NormalizeTextStep(BaseModel):
    type: Literal["normalize_text"]
    column: str
    case: Literal["lower", "upper", "title"]


class ExtractTextStep(BaseModel):
    type: Literal["extract_text"]
    column: str
    pattern: str
    new_column: str
    group: int = 1
    no_match: str | None = None


class DateDiffStep(BaseModel):
    type: Literal["date_diff"]
    start_column: str
    end_column: str
    new_column: str
    unit: Literal["days"] = "days"
    errors: Literal["raise", "coerce"] = "raise"


WorkflowStep = Annotated[
    Union[
        RemoveMissingValuesStep,
        SelectColumnsStep,
        FilterRowsStep,
        GroupByStep,
        SortValuesStep,
        RenameColumnsStep,
        GenerateSummaryStep,
        LimitRowsStep,
        DeriveColumnStep,
        DateExtractStep,
        DropColumnsStep,
        FillMissingValuesStep,
        DeduplicateRowsStep,
        ReplaceValuesStep,
        CastColumnStep,
        ConditionalColumnStep,
        BinColumnStep,
        PivotTableStep,
        TrimTextStep,
        NormalizeTextStep,
        ExtractTextStep,
        DateDiffStep,
    ],
    Field(discriminator="type"),
]
