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


_OPERATOR_ALIASES: dict[str, str] = {
    # symbol variants
    "==": "=",
    "<>": "!=",
    # english words the LLM commonly generates
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
    # Multi-column grouping: when non-empty, used instead of the single `column`.
    # Kept optional so existing single-column workflows remain valid.
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
    # Exactly one of value or other_column must be provided.
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
    # Required when strategy is "constant"; ignored otherwise.
    value: Union[float, str, None] = None


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
        LimitRowsStep,
        DeriveColumnStep,
        DateExtractStep,
        DropColumnsStep,
        FillMissingValuesStep,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class WorkflowRequest(BaseModel):
    dataset_id: str
    steps: list[WorkflowStep]


class StepIssue(BaseModel):
    severity: Literal["warning", "error"]
    code: str
    message: str


class StepResult(BaseModel):
    step_index: int
    step_type: str
    status: Literal["success", "warning", "error"] = "success"
    issues: list[StepIssue] = Field(default_factory=list)
    input_row_count: int
    output_row_count: int
    input_column_count: int
    output_column_count: int
    # Absolute number of rows removed or added by this step.
    affected_rows: int = 0
    match_rate: float | None = None
    affected_rate: float | None = None
    preview: list[dict] = Field(default_factory=list)
    message: str


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
    step_results: list[StepResult]
    # Backward-compatible log shape for MVP1 frontend/tests.
    logs: list[StepLog]
    # True when the workflow includes a generate_summary step (Task 5 will use this)
    has_summary: bool


class PreviewResponse(BaseModel):
    """Response for the preview-only execution endpoint.

    The workflow runs through the validator and executor (with risk checks)
    but the result explainer is never called.  Errors are captured instead of
    raised so the client can inspect the full partial result.
    """

    planned_steps: list[dict]
    step_results: list[StepResult]
    has_warnings: bool
    has_errors: bool
    # Index of the step that caused a blocking error and stopped execution.
    blocked_at_step: int | None = None


class ConfirmRequest(BaseModel):
    """Request to execute a pre-reviewed workflow and generate an explanation.

    The client sends this after showing the user the preview result and
    receiving explicit confirmation that the workflow should proceed.
    """

    dataset_id: str
    steps: list[WorkflowStep]
    # Original user query — used by the result explainer for language detection
    # and grounding the explanation in the user's intent.
    query: str


class ConfirmResponse(BaseModel):
    """Response from the confirm execution endpoint.

    Contains the full execution result plus an LLM-generated explanation.
    Unlike ChatResponse there is no rag_context because the confirm flow
    receives an already-planned workflow from the client.
    """

    query: str
    planned_steps: list[dict]
    execution_result: ExecutionResult
    explanation: str
    # UUID of the persisted result run; used by the frontend to download the
    # full result CSV via GET /api/runs/{run_id}/download.
    run_id: str | None = None
