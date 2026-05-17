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


def test_planner_query_does_not_replace_partial_word_match():
    # Bug regression: "amount" must NOT match inside "amount_total".
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter amount_total > 500",
        question="Which column?",
        affected_step={"type": "filter_rows", "column": "amount"},
    ).model_copy(update={"user_answer": "revenue"})
    resolved = resolve_context(
        context,
        dataset_id="dataset-1",
        original_query="filter amount_total > 500",
    )

    result = planner_query_with_context("filter amount_total > 500", resolved)
    assert "amount_total" in result, "partial word must not be replaced"
    assert "revenue_total" not in result, "partial replacement must not occur"


def test_planner_query_does_not_replace_column_embedded_in_another_word():
    # Bug regression: "amount" must NOT match inside "unamount".
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="filter unamount > 0",
        question="Which column?",
        affected_step={"type": "filter_rows", "column": "amount"},
    ).model_copy(update={"user_answer": "sales"})
    resolved = resolve_context(
        context,
        dataset_id="dataset-1",
        original_query="filter unamount > 0",
    )

    result = planner_query_with_context("filter unamount > 0", resolved)
    assert "unamount" in result, "prefix-embedded column must not be replaced"
    assert "unsales" not in result, "prefix-embedded replacement must not occur"


def test_planner_query_falls_back_to_appended_clarification_when_no_word_boundary():
    # When the affected column is not found with word boundaries, the context
    # must NOT use str.replace; instead append as a clarification note.
    context = new_pending_context(
        dataset_id="dataset-1",
        original_query="show me data",
        question="Which column?",
        affected_step={"type": "filter_rows", "column": "revenue"},
    ).model_copy(update={"user_answer": "amount"})
    resolved = resolve_context(
        context,
        dataset_id="dataset-1",
        original_query="show me data",
    )

    result = planner_query_with_context("show me data", resolved)
    # Column "revenue" is absent → no in-place substitution; answer appended.
    assert "amount" in result
    assert "show me data" in result


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
