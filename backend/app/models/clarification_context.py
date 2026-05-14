"""Run-local clarification context contracts."""
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field


ClarificationStatus = Literal["pending", "resolved"]


class ClarificationContext(BaseModel):
    """Structured clarification state scoped to one dataset and query."""

    dataset_id: str
    original_query: str
    question: str | None = None
    user_answer: str | None = None
    resolved_parameter: str | None = None
    affected_step: dict[str, Any] | None = None
    status: ClarificationStatus = "pending"
    scope_key: str


def make_scope_key(*, dataset_id: str, original_query: str) -> str:
    """Return a stable run-local scope key without storing raw data."""
    digest = hashlib.sha256(f"{dataset_id}:{original_query}".encode("utf-8")).hexdigest()
    return digest[:16]


def new_pending_context(
    *,
    dataset_id: str,
    original_query: str,
    question: str,
    affected_step: dict[str, Any] | None = None,
) -> ClarificationContext:
    """Create a pending clarification request for the current run/query."""
    return ClarificationContext(
        dataset_id=dataset_id,
        original_query=original_query,
        question=question,
        affected_step=affected_step,
        status="pending",
        scope_key=make_scope_key(dataset_id=dataset_id, original_query=original_query),
    )


def resolve_context(
    clarification_context: str | ClarificationContext | None,
    *,
    dataset_id: str,
    original_query: str,
) -> ClarificationContext | None:
    """Return a resolved context after checking dataset/query scope.

    A plain string is accepted for backward compatibility with the current UI.
    Structured contexts are rejected by the caller if their dataset or query
    scope does not match the active request.
    """
    if clarification_context is None:
        return None

    if isinstance(clarification_context, str):
        answer = clarification_context.strip()
        if not answer:
            return None
        return ClarificationContext(
            dataset_id=dataset_id,
            original_query=original_query,
            user_answer=answer,
            resolved_parameter=answer,
            status="resolved",
            scope_key=make_scope_key(dataset_id=dataset_id, original_query=original_query),
        )

    answer = (clarification_context.user_answer or clarification_context.resolved_parameter or "").strip()
    return clarification_context.model_copy(
        update={
            "user_answer": answer or None,
            "resolved_parameter": answer or None,
            "status": "resolved" if answer else clarification_context.status,
        }
    )


def validate_scope(
    context: ClarificationContext,
    *,
    dataset_id: str,
    original_query: str,
) -> bool:
    """Return whether a clarification context belongs to this request scope."""
    return (
        context.dataset_id == dataset_id
        and context.original_query == original_query
        and context.scope_key == make_scope_key(dataset_id=dataset_id, original_query=original_query)
    )


def planner_query_with_context(query: str, context: ClarificationContext | None) -> str:
    """Append the resolved clarification answer for planner consumption."""
    if not context or not context.user_answer:
        return query
    return f"{query}\nUser clarification: {context.user_answer}"


def next_iteration_input(context: ClarificationContext) -> dict[str, Any]:
    """Compact input for the Agent iteration after a clarification answer."""
    return {
        "original_query": context.original_query,
        "question": context.question,
        "user_answer": context.user_answer,
        "resolved_parameter": context.resolved_parameter,
        "affected_step": context.affected_step,
        "scope_key": context.scope_key,
    }
