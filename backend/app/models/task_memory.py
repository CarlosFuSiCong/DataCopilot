"""Task memory boundary for a single dataset session.

TaskMemory records the minimal state needed for a bounded analytical session:
  - goal        : the original user intent
  - confirmed choices : step types the user has explicitly confirmed
  - clarification answers : Q&A pairs from clarification rounds

Design constraints (Task 10):
  - Strictly scoped to one dataset_id; cross-dataset reuse raises an error.
  - No long-term user profiling; no fields outside the current session.
  - Storage is bounded by max_clarifications and max_confirmed_steps to prevent
    unbounded growth across a long session.
  - Memory is auditable (all fields are public Pydantic model fields).
  - Memory is clearable (clear_memory() returns a fresh session copy).
  - Memory is compressible (compress_memory() returns a short prompt string).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ClarificationRecord(BaseModel):
    """One Q&A pair recorded during a clarification round."""

    question: str
    answer: str
    step_type: str | None = None


class TaskMemory(BaseModel):
    """Minimal, bounded session memory for one dataset analytical task.

    Fields outside goal / confirmed_step_types / clarification_answers are
    intentionally absent to prevent accidental long-term user profiling.
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    dataset_id: str
    goal: str
    confirmed_step_types: list[str] = Field(default_factory=list)
    clarification_answers: list[ClarificationRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Hard caps prevent unbounded memory growth during long sessions.
    max_clarifications: int = Field(default=10, ge=1)
    max_confirmed_steps: int = Field(default=20, ge=1)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def new_task_memory(
    dataset_id: str,
    goal: str,
    *,
    session_id: str | None = None,
    max_clarifications: int = 10,
    max_confirmed_steps: int = 20,
) -> TaskMemory:
    """Create a fresh TaskMemory for a new dataset session."""
    return TaskMemory(
        session_id=session_id or str(uuid.uuid4()),
        dataset_id=dataset_id,
        goal=goal,
        max_clarifications=max_clarifications,
        max_confirmed_steps=max_confirmed_steps,
    )


# ---------------------------------------------------------------------------
# Scope validation
# ---------------------------------------------------------------------------


class TaskMemoryScopeError(Exception):
    """Raised when memory is used outside its declared dataset scope."""


def validate_memory_scope(memory: TaskMemory, dataset_id: str) -> bool:
    """Return True if memory belongs to dataset_id, False otherwise."""
    return memory.dataset_id == dataset_id


def assert_memory_scope(memory: TaskMemory, dataset_id: str) -> None:
    """Raise TaskMemoryScopeError if memory does not belong to dataset_id."""
    if not validate_memory_scope(memory, dataset_id):
        raise TaskMemoryScopeError(
            f"TaskMemory is scoped to dataset '{memory.dataset_id}' "
            f"and cannot be reused for dataset '{dataset_id}'."
        )


# ---------------------------------------------------------------------------
# Immutable update helpers (return new TaskMemory copies)
# ---------------------------------------------------------------------------


def record_clarification(
    memory: TaskMemory,
    question: str,
    answer: str,
    step_type: str | None = None,
) -> TaskMemory:
    """Return a new TaskMemory with the clarification appended (bounded).

    When the cap is reached the oldest record is dropped to make room,
    keeping only the most recent max_clarifications answers.
    """
    new_record = ClarificationRecord(question=question, answer=answer, step_type=step_type)
    current = list(memory.clarification_answers)
    current.append(new_record)
    if len(current) > memory.max_clarifications:
        current = current[-memory.max_clarifications :]
    return memory.model_copy(update={"clarification_answers": current})


def record_confirmed_step(memory: TaskMemory, step_type: str) -> TaskMemory:
    """Return a new TaskMemory with step_type appended to confirmed_step_types (bounded).

    When the cap is reached the oldest entries are dropped to keep only the
    most recent max_confirmed_steps step types.
    """
    current = list(memory.confirmed_step_types)
    current.append(step_type)
    if len(current) > memory.max_confirmed_steps:
        current = current[-memory.max_confirmed_steps :]
    return memory.model_copy(update={"confirmed_step_types": current})


def clear_memory(memory: TaskMemory) -> TaskMemory:
    """Return a cleared TaskMemory preserving scope (dataset_id, goal, session_id).

    Confirmed steps and clarification answers are wiped. The same session_id
    is kept so callers can track that a clear operation happened on the same
    logical session.
    """
    return memory.model_copy(
        update={
            "confirmed_step_types": [],
            "clarification_answers": [],
        }
    )


# ---------------------------------------------------------------------------
# Compression (prompt injection)
# ---------------------------------------------------------------------------

_MAX_COMPRESSED_GOAL_LEN = 120
_MAX_COMPRESSED_STEPS = 10
_MAX_COMPRESSED_CLARIFICATIONS = 5


def compress_memory(memory: TaskMemory) -> str:
    """Return a short, LLM-readable summary of the task memory.

    The output is deterministic and bounded in length. It is safe to inject
    directly into a planner or explainer prompt without risking prompt overflow.
    Only the most recent confirmed steps and clarifications are included.

    Example output:
        Goal: filter orders where status is active
        Confirmed steps: filter_rows, sort_values
        Clarifications: "Which status?" → "active"; "Sort direction?" → "descending"
    """
    parts: list[str] = []

    goal = memory.goal[:_MAX_COMPRESSED_GOAL_LEN]
    if len(memory.goal) > _MAX_COMPRESSED_GOAL_LEN:
        goal += "…"
    parts.append(f"Goal: {goal}")

    recent_steps = memory.confirmed_step_types[-_MAX_COMPRESSED_STEPS:]
    if recent_steps:
        parts.append(f"Confirmed steps: {', '.join(recent_steps)}")
    else:
        parts.append("Confirmed steps: none")

    recent_clarifications = memory.clarification_answers[-_MAX_COMPRESSED_CLARIFICATIONS:]
    if recent_clarifications:
        pairs = "; ".join(
            f'"{r.question}" → "{r.answer}"' for r in recent_clarifications
        )
        parts.append(f"Clarifications: {pairs}")
    else:
        parts.append("Clarifications: none")

    return "\n".join(parts)
