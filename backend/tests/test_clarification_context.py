"""Tests for run-local clarification context contracts."""

from app.models.clarification_context import (
    new_pending_context,
    next_iteration_input,
    planner_query_with_context,
    resolve_context,
    validate_scope,
)


def test_pending_context_records_question_and_scope():
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
        affected_step={"type": "filter_rows", "column": "revenue"},
    )

    assert context.status == "pending"
    assert context.question == "Which column should I use?"
    assert context.affected_step == {"type": "filter_rows", "column": "revenue"}
    assert validate_scope(context, dataset_id="dataset-1", original_query="filter revenue")


def test_resolve_context_records_user_answer_and_parameter():
    pending = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
    )
    answered = pending.model_copy(update={"user_answer": "sales"})

    resolved = resolve_context(
        answered,
        dataset_id="dataset-1",
        original_query="filter revenue",
    )

    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.user_answer == "sales"
    assert resolved.resolved_parameter == "sales"


def test_resolve_context_normalizes_conflicting_answer_fields():
    malformed = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
    ).model_copy(update={"user_answer": "sales", "resolved_parameter": "amount"})

    resolved = resolve_context(
        malformed,
        dataset_id="dataset-1",
        original_query="filter revenue",
    )

    assert resolved is not None
    assert resolved.user_answer == "sales"
    assert resolved.resolved_parameter == "sales"
    assert resolved.status == "resolved"


def test_resolve_context_drops_whitespace_only_user_answer():
    pending = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
    )
    answered = pending.model_copy(update={"user_answer": "  \t "})

    resolved = resolve_context(
        answered,
        dataset_id="dataset-1",
        original_query="filter revenue",
    )

    assert resolved is not None
    assert resolved.user_answer is None
    assert resolved.resolved_parameter is None
    assert resolved.status == "pending"
    assert planner_query_with_context("filter revenue", resolved) == "filter revenue"


def test_planner_query_rewrites_affected_column_with_resolved_answer():
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="Filter rows where revenue > 1000",
        question="Which column should I use?",
        affected_step={"type": "filter_rows", "column": "revenue"},
    ).model_copy(update={"user_answer": "amount"})
    resolved = resolve_context(
        context,
        dataset_id="dataset-1",
        original_query="Filter rows where revenue > 1000",
    )

    assert resolved is not None
    assert planner_query_with_context("Filter rows where revenue > 1000", resolved) == (
        "Filter rows where amount > 1000"
    )


def test_string_clarification_context_is_supported_for_current_ui():
    resolved = resolve_context(
        "sales",
        dataset_id="dataset-1",
        original_query="filter revenue",
    )

    assert resolved is not None
    assert resolved.status == "resolved"
    assert resolved.question is None
    assert resolved.user_answer == "sales"


def test_context_scope_prevents_cross_dataset_reuse():
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
    )

    assert not validate_scope(context, dataset_id="dataset-2", original_query="filter revenue")
    assert not validate_scope(context, dataset_id="dataset-1", original_query="filter amount")


def test_clarification_answer_builds_next_iteration_input():
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter revenue",
        question="Which column should I use?",
        affected_step={"type": "filter_rows", "column": "revenue"},
    ).model_copy(update={"user_answer": "sales", "resolved_parameter": "sales", "status": "resolved"})

    iteration_input = next_iteration_input(context)

    assert iteration_input["original_query"] == "filter revenue"
    assert iteration_input["question"] == "Which column should I use?"
    assert iteration_input["user_answer"] == "sales"
    assert iteration_input["resolved_parameter"] == "sales"
    assert iteration_input["affected_step"]["column"] == "revenue"
