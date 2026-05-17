"""Focused tests for Task 10: Session / Task Memory Boundary.

Coverage:
- ClarificationRecord model contract (3 tests)
- TaskMemory model contract (6 tests)
- new_task_memory factory (5 tests)
- validate_memory_scope (5 tests)
- assert_memory_scope (3 tests)
- record_clarification: behavior + bounds (7 tests)
- record_confirmed_step: behavior + bounds (7 tests)
- clear_memory (5 tests)
- compress_memory: formatting + edge cases (10 tests)
"""
import pytest

from app.models.task_memory import (
    ClarificationRecord,
    TaskMemory,
    TaskMemoryScopeError,
    assert_memory_scope,
    clear_memory,
    compress_memory,
    new_task_memory,
    record_clarification,
    record_confirmed_step,
    validate_memory_scope,
)


# ---------------------------------------------------------------------------
# 1. ClarificationRecord model contract
# ---------------------------------------------------------------------------


class TestClarificationRecord:
    def test_required_fields(self):
        r = ClarificationRecord(question="Which column?", answer="amount")
        assert r.question == "Which column?"
        assert r.answer == "amount"

    def test_step_type_defaults_none(self):
        r = ClarificationRecord(question="q", answer="a")
        assert r.step_type is None

    def test_step_type_can_be_set(self):
        r = ClarificationRecord(question="q", answer="a", step_type="filter_rows")
        assert r.step_type == "filter_rows"


# ---------------------------------------------------------------------------
# 2. TaskMemory model contract
# ---------------------------------------------------------------------------


class TestTaskMemoryModel:
    def test_required_fields(self):
        m = TaskMemory(dataset_id="ds-1", goal="filter orders")
        assert m.dataset_id == "ds-1"
        assert m.goal == "filter orders"

    def test_default_empty_lists(self):
        m = TaskMemory(dataset_id="ds-1", goal="g")
        assert m.confirmed_step_types == []
        assert m.clarification_answers == []

    def test_session_id_auto_generated(self):
        m1 = TaskMemory(dataset_id="ds-1", goal="g")
        m2 = TaskMemory(dataset_id="ds-1", goal="g")
        assert m1.session_id != m2.session_id

    def test_created_at_is_set(self):
        m = TaskMemory(dataset_id="ds-1", goal="g")
        assert m.created_at is not None

    def test_default_caps(self):
        m = TaskMemory(dataset_id="ds-1", goal="g")
        assert m.max_clarifications == 10
        assert m.max_confirmed_steps == 20

    def test_max_clarifications_lower_bound(self):
        with pytest.raises(Exception):
            TaskMemory(dataset_id="ds-1", goal="g", max_clarifications=0)


# ---------------------------------------------------------------------------
# 3. new_task_memory factory
# ---------------------------------------------------------------------------


class TestNewTaskMemory:
    def test_creates_with_dataset_and_goal(self):
        m = new_task_memory("ds-abc", "find top customers")
        assert m.dataset_id == "ds-abc"
        assert m.goal == "find top customers"

    def test_starts_empty(self):
        m = new_task_memory("ds-1", "g")
        assert m.confirmed_step_types == []
        assert m.clarification_answers == []

    def test_custom_session_id(self):
        m = new_task_memory("ds-1", "g", session_id="my-session-123")
        assert m.session_id == "my-session-123"

    def test_auto_session_id_is_uuid_format(self):
        import re
        m = new_task_memory("ds-1", "g")
        assert re.match(r"[0-9a-f-]{36}", m.session_id)

    def test_custom_caps(self):
        m = new_task_memory("ds-1", "g", max_clarifications=3, max_confirmed_steps=5)
        assert m.max_clarifications == 3
        assert m.max_confirmed_steps == 5


# ---------------------------------------------------------------------------
# 4. validate_memory_scope
# ---------------------------------------------------------------------------


class TestValidateMemoryScope:
    def test_matching_dataset_returns_true(self):
        m = new_task_memory("ds-abc", "g")
        assert validate_memory_scope(m, "ds-abc") is True

    def test_different_dataset_returns_false(self):
        m = new_task_memory("ds-abc", "g")
        assert validate_memory_scope(m, "ds-xyz") is False

    def test_empty_dataset_id_mismatch(self):
        m = new_task_memory("ds-1", "g")
        assert validate_memory_scope(m, "") is False

    def test_case_sensitive_match(self):
        m = new_task_memory("DS-1", "g")
        assert validate_memory_scope(m, "ds-1") is False

    def test_same_instance_matches_itself(self):
        m = new_task_memory("ds-1", "g")
        assert validate_memory_scope(m, m.dataset_id) is True


# ---------------------------------------------------------------------------
# 5. assert_memory_scope
# ---------------------------------------------------------------------------


class TestAssertMemoryScope:
    def test_same_dataset_does_not_raise(self):
        m = new_task_memory("ds-1", "g")
        assert_memory_scope(m, "ds-1")  # should not raise

    def test_different_dataset_raises(self):
        m = new_task_memory("ds-1", "g")
        with pytest.raises(TaskMemoryScopeError) as exc_info:
            assert_memory_scope(m, "ds-2")
        assert "ds-1" in str(exc_info.value)
        assert "ds-2" in str(exc_info.value)

    def test_error_message_mentions_both_datasets(self):
        m = new_task_memory("original-dataset", "g")
        with pytest.raises(TaskMemoryScopeError) as exc_info:
            assert_memory_scope(m, "intruder-dataset")
        msg = str(exc_info.value)
        assert "original-dataset" in msg
        assert "intruder-dataset" in msg


# ---------------------------------------------------------------------------
# 6. record_clarification
# ---------------------------------------------------------------------------


class TestRecordClarification:
    def test_adds_record(self):
        m = new_task_memory("ds-1", "g")
        m2 = record_clarification(m, "Which column?", "amount")
        assert len(m2.clarification_answers) == 1
        assert m2.clarification_answers[0].answer == "amount"

    def test_immutable_original(self):
        m = new_task_memory("ds-1", "g")
        record_clarification(m, "q", "a")
        assert len(m.clarification_answers) == 0  # original unchanged

    def test_step_type_recorded(self):
        m = new_task_memory("ds-1", "g")
        m2 = record_clarification(m, "q", "a", step_type="filter_rows")
        assert m2.clarification_answers[0].step_type == "filter_rows"

    def test_multiple_records_ordered(self):
        m = new_task_memory("ds-1", "g")
        m = record_clarification(m, "q1", "a1")
        m = record_clarification(m, "q2", "a2")
        assert m.clarification_answers[0].question == "q1"
        assert m.clarification_answers[1].question == "q2"

    def test_bounded_at_max_drops_oldest(self):
        m = new_task_memory("ds-1", "g", max_clarifications=3)
        for i in range(4):
            m = record_clarification(m, f"q{i}", f"a{i}")
        assert len(m.clarification_answers) == 3
        # oldest (q0) was dropped, q1..q3 remain
        assert m.clarification_answers[0].question == "q1"

    def test_bounded_exact_at_max_no_drop(self):
        m = new_task_memory("ds-1", "g", max_clarifications=3)
        for i in range(3):
            m = record_clarification(m, f"q{i}", f"a{i}")
        assert len(m.clarification_answers) == 3

    def test_dataset_id_preserved(self):
        m = new_task_memory("ds-1", "g")
        m2 = record_clarification(m, "q", "a")
        assert m2.dataset_id == "ds-1"


# ---------------------------------------------------------------------------
# 7. record_confirmed_step
# ---------------------------------------------------------------------------


class TestRecordConfirmedStep:
    def test_adds_step(self):
        m = new_task_memory("ds-1", "g")
        m2 = record_confirmed_step(m, "filter_rows")
        assert m2.confirmed_step_types == ["filter_rows"]

    def test_immutable_original(self):
        m = new_task_memory("ds-1", "g")
        record_confirmed_step(m, "filter_rows")
        assert m.confirmed_step_types == []

    def test_multiple_steps_ordered(self):
        m = new_task_memory("ds-1", "g")
        m = record_confirmed_step(m, "filter_rows")
        m = record_confirmed_step(m, "sort_values")
        assert m.confirmed_step_types == ["filter_rows", "sort_values"]

    def test_duplicate_steps_allowed(self):
        m = new_task_memory("ds-1", "g")
        m = record_confirmed_step(m, "filter_rows")
        m = record_confirmed_step(m, "filter_rows")
        assert len(m.confirmed_step_types) == 2

    def test_bounded_at_max_drops_oldest(self):
        m = new_task_memory("ds-1", "g", max_confirmed_steps=3)
        for i in range(4):
            m = record_confirmed_step(m, f"step_{i}")
        assert len(m.confirmed_step_types) == 3
        assert m.confirmed_step_types[0] == "step_1"  # step_0 dropped

    def test_bounded_exact_at_max_no_drop(self):
        m = new_task_memory("ds-1", "g", max_confirmed_steps=3)
        for i in range(3):
            m = record_confirmed_step(m, f"step_{i}")
        assert len(m.confirmed_step_types) == 3

    def test_dataset_id_preserved(self):
        m = new_task_memory("ds-1", "g")
        m2 = record_confirmed_step(m, "filter_rows")
        assert m2.dataset_id == "ds-1"


# ---------------------------------------------------------------------------
# 8. clear_memory
# ---------------------------------------------------------------------------


class TestClearMemory:
    def test_wipes_confirmed_steps(self):
        m = new_task_memory("ds-1", "g")
        m = record_confirmed_step(m, "filter_rows")
        m = clear_memory(m)
        assert m.confirmed_step_types == []

    def test_wipes_clarifications(self):
        m = new_task_memory("ds-1", "g")
        m = record_clarification(m, "q", "a")
        m = clear_memory(m)
        assert m.clarification_answers == []

    def test_preserves_goal(self):
        m = new_task_memory("ds-1", "filter orders")
        m = clear_memory(m)
        assert m.goal == "filter orders"

    def test_preserves_dataset_id(self):
        m = new_task_memory("ds-42", "g")
        m = clear_memory(m)
        assert m.dataset_id == "ds-42"

    def test_preserves_session_id(self):
        m = new_task_memory("ds-1", "g", session_id="fixed-id")
        m = clear_memory(m)
        assert m.session_id == "fixed-id"


# ---------------------------------------------------------------------------
# 9. compress_memory
# ---------------------------------------------------------------------------


class TestCompressMemory:
    def test_includes_goal(self):
        m = new_task_memory("ds-1", "filter orders by status")
        result = compress_memory(m)
        assert "filter orders by status" in result

    def test_empty_steps_says_none(self):
        m = new_task_memory("ds-1", "g")
        result = compress_memory(m)
        assert "Confirmed steps: none" in result

    def test_steps_listed(self):
        m = new_task_memory("ds-1", "g")
        m = record_confirmed_step(m, "filter_rows")
        m = record_confirmed_step(m, "sort_values")
        result = compress_memory(m)
        assert "filter_rows" in result
        assert "sort_values" in result

    def test_empty_clarifications_says_none(self):
        m = new_task_memory("ds-1", "g")
        result = compress_memory(m)
        assert "Clarifications: none" in result

    def test_clarifications_listed(self):
        m = new_task_memory("ds-1", "g")
        m = record_clarification(m, "Which column?", "amount")
        result = compress_memory(m)
        assert "Which column?" in result
        assert "amount" in result

    def test_clarification_uses_arrow_format(self):
        m = new_task_memory("ds-1", "g")
        m = record_clarification(m, "q", "a")
        result = compress_memory(m)
        assert "→" in result

    def test_long_goal_is_truncated(self):
        long_goal = "x" * 200
        m = new_task_memory("ds-1", long_goal)
        result = compress_memory(m)
        goal_line = [l for l in result.splitlines() if l.startswith("Goal:")][0]
        assert len(goal_line) < 160  # well below 200

    def test_result_is_multiline(self):
        m = new_task_memory("ds-1", "g")
        result = compress_memory(m)
        assert "\n" in result

    def test_result_has_three_sections(self):
        m = new_task_memory("ds-1", "g")
        lines = compress_memory(m).splitlines()
        assert any(l.startswith("Goal:") for l in lines)
        assert any(l.startswith("Confirmed steps:") for l in lines)
        assert any(l.startswith("Clarifications:") for l in lines)

    def test_only_recent_clarifications_appear(self):
        """compress_memory caps output to the 5 most recent clarifications."""
        m = new_task_memory("ds-1", "g")
        for i in range(7):
            m = record_clarification(m, f"q{i}", f"a{i}")
        result = compress_memory(m)
        # q0, q1 should NOT appear (only 5 most recent: q2..q6)
        assert "q0" not in result
        assert "q2" in result
        assert "q6" in result
