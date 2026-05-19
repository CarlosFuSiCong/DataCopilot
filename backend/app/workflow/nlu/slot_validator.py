"""Deterministic slot validator for workflow NLU."""
import difflib
from typing import Literal

from pydantic import BaseModel, Field

from app.models.dataset import DatasetProfile
from app.workflow.nlu.slot_models import SlotExtractionResult

_REQUIRED_SLOTS: dict[str, list[str]] = {
    "filter": ["column", "operator"],
    "sort": ["column", "sort_direction"],
    "group_aggregate": ["column", "aggregation"],
    "limit": ["limit"],
    "inspect": [],
    "clean": [],
}

_UNSUPPORTED_INTENTS: frozenset[str] = frozenset({"unknown"})
_NUMERIC_DTYPES = {"int64", "float64", "int32", "float32", "uint64", "uint32", "Int64", "Float64"}
_MAX_CANDIDATES = 3
_NULL_OPERATORS = {"is_null", "is_not_null"}

SlotValidationStatus = Literal[
    "valid",
    "missing_required_slot",
    "missing_column",
    "ambiguous_column",
    "invalid_type",
    "unsupported_intent",
]


class SlotValidationOutcome(BaseModel):
    status: SlotValidationStatus
    is_valid: bool
    needs_clarification: bool
    blocked: bool = False
    clarification_question: str | None = None
    candidate_columns: list[str] = Field(default_factory=list)
    details: str | None = None


def _schema_column_names(profile: DatasetProfile) -> list[str]:
    return [c.name for c in profile.columns]


def _find_column(name: str, schema_columns: list[str]) -> str | None:
    for col in schema_columns:
        if col.lower() == name.lower():
            return col
    return None


def _fuzzy_candidates(name: str, schema_columns: list[str]) -> list[str]:
    return difflib.get_close_matches(
        name.lower(),
        [c.lower() for c in schema_columns],
        n=_MAX_CANDIDATES,
        cutoff=0.6,
    )


def _resolve_candidates(fuzzy_lower: list[str], schema_columns: list[str]) -> list[str]:
    lower_to_orig = {c.lower(): c for c in schema_columns}
    return [lower_to_orig[f] for f in fuzzy_lower if f in lower_to_orig]


def _is_numeric_column(dtype: str) -> bool:
    return dtype in _NUMERIC_DTYPES


def _value_compatible(value: str, dtype: str) -> bool:
    if _is_numeric_column(dtype):
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    return True


def _get_column_dtype(name: str, profile: DatasetProfile) -> str | None:
    for col in profile.columns:
        if col.name.lower() == name.lower():
            return col.dtype
    return None


def _valid() -> SlotValidationOutcome:
    return SlotValidationOutcome(status="valid", is_valid=True, needs_clarification=False)


def _blocked(intent: str) -> SlotValidationOutcome:
    return SlotValidationOutcome(
        status="unsupported_intent",
        is_valid=False,
        needs_clarification=False,
        blocked=True,
        details=f"Intent '{intent}' is not supported.",
    )


def _missing_slot(slot_names: list[str], intent: str) -> SlotValidationOutcome:
    joined = ", ".join(slot_names)
    return SlotValidationOutcome(
        status="missing_required_slot",
        is_valid=False,
        needs_clarification=True,
        clarification_question=(
            f"To {intent.replace('_', ' ')} the data, I need: {joined}. "
            "Could you provide the missing information?"
        ),
        details=f"Missing required slots for intent '{intent}': {joined}",
    )


def _missing_column(column: str, schema_columns: list[str]) -> SlotValidationOutcome:
    available = ", ".join(schema_columns)
    return SlotValidationOutcome(
        status="missing_column",
        is_valid=False,
        needs_clarification=True,
        clarification_question=(
            f"Column '{column}' does not exist in the dataset. "
            f"Available columns are: {available}. Which column did you mean?"
        ),
        details=f"Column '{column}' not found in schema.",
    )


def _ambiguous_column(column: str, candidates: list[str]) -> SlotValidationOutcome:
    suggestions = ", ".join(f"'{c}'" for c in candidates)
    return SlotValidationOutcome(
        status="ambiguous_column",
        is_valid=False,
        needs_clarification=True,
        clarification_question=f"Column '{column}' is ambiguous. Did you mean one of: {suggestions}?",
        candidate_columns=candidates,
        details=f"Ambiguous column '{column}'; candidates: {candidates}",
    )


def _invalid_type(column: str, value: str, dtype: str) -> SlotValidationOutcome:
    return SlotValidationOutcome(
        status="invalid_type",
        is_valid=False,
        needs_clarification=True,
        clarification_question=(
            f"The value '{value}' cannot be used with column '{column}' "
            f"(type: {dtype}). Please provide a numeric value."
        ),
        details=f"Value '{value}' incompatible with dtype '{dtype}' for column '{column}'.",
    )


def validate_slots(
    extraction: SlotExtractionResult,
    profile: DatasetProfile,
) -> SlotValidationOutcome:
    """Validate extracted slots against the active dataset schema."""
    intent = extraction.intent
    slots = extraction.slots
    schema_columns = _schema_column_names(profile)

    if intent in _UNSUPPORTED_INTENTS:
        return _blocked(intent)

    required = _REQUIRED_SLOTS.get(intent, [])
    slot_dict = slots.model_dump()
    missing = [r for r in required if slot_dict.get(r) is None]
    if intent == "filter" and slots.operator not in _NULL_OPERATORS and slots.value is None:
        missing.append("value")
    if missing:
        return _missing_slot(missing, intent)

    column = slots.column
    if column:
        exact = _find_column(column, schema_columns)
        if exact is None:
            candidates = _resolve_candidates(_fuzzy_candidates(column, schema_columns), schema_columns)
            if candidates:
                return _ambiguous_column(column, candidates)
            return _missing_column(column, schema_columns)

        if intent == "filter" and slots.value is not None:
            dtype = _get_column_dtype(exact, profile) or ""
            if _is_numeric_column(dtype) and not _value_compatible(slots.value, dtype):
                return _invalid_type(exact, slots.value, dtype)

    return _valid()
