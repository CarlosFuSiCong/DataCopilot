"""Unit tests for Task 4: Planner Integration — slot context injection.

Covers:
- _format_slot_hints: hint formatting for various intents and edge cases.
- workflow_planner.plan() passes slot hints to _build_messages.
- orchestrator._run_slot_extraction: fallback conditions, clarification signal.
- Chat-router integration: slot validation triggers clarification; valid slot
  context reaches the planner; LLM extraction failures fall back gracefully.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.workflow.nlu.slot_models import ExtractedSlots, SlotExtractionResult
from app.workflow.planning.workflow_planner import (
    _SLOT_HINT_MIN_CONFIDENCE,
    _format_slot_hints,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _result(
    intent: str = "filter",
    confidence: float = 0.9,
    column: str | None = "amount",
    operator: str | None = "gt",
    value: str | None = "1000",
    target_column: str | None = None,
    aggregation: str | None = None,
    sort_direction: str | None = None,
    limit: int | None = None,
) -> SlotExtractionResult:
    return SlotExtractionResult(
        raw_query="test",
        intent=intent,
        slots=ExtractedSlots(
            column=column,
            operator=operator,
            value=value,
            target_column=target_column,
            aggregation=aggregation,
            sort_direction=sort_direction,
            limit=limit,
        ),
        confidence=confidence,
        query_locale="en",
    )


# --------------------------------------------------------------------------- #
# _format_slot_hints
# --------------------------------------------------------------------------- #

class TestFormatSlotHints:
    def test_unknown_intent_returns_empty(self):
        assert _format_slot_hints(_result(intent="unknown")) == ""

    def test_low_confidence_returns_empty(self):
        assert _format_slot_hints(_result(confidence=_SLOT_HINT_MIN_CONFIDENCE - 0.01)) == ""

    def test_filter_hint_includes_column_operator_value(self):
        hint = _format_slot_hints(_result(intent="filter", column="amount", operator="gt", value="1000"))
        assert "column: amount" in hint
        assert "operator: >" in hint
        assert "value: 1000" in hint

    def test_filter_hint_maps_gte_operator(self):
        hint = _format_slot_hints(_result(operator="gte"))
        assert "operator: >=" in hint

    def test_filter_hint_maps_eq_operator(self):
        hint = _format_slot_hints(_result(operator="eq"))
        assert "operator: =" in hint

    def test_filter_hint_maps_ne_operator(self):
        hint = _format_slot_hints(_result(operator="ne"))
        assert "operator: !=" in hint

    def test_unmapped_operator_omitted(self):
        # "contains" has no planner mapping — operator line should be absent.
        hint = _format_slot_hints(_result(operator="contains"))
        assert "operator:" not in hint

    def test_sort_hint_includes_ascending_flag(self):
        hint = _format_slot_hints(_result(intent="sort", column="date", operator=None, value=None, sort_direction="desc"))
        assert "ascending: false" in hint
        assert "column: date" in hint

    def test_sort_asc_maps_to_true(self):
        hint = _format_slot_hints(_result(intent="sort", column="date", operator=None, value=None, sort_direction="asc"))
        assert "ascending: true" in hint

    def test_group_aggregate_hint_includes_aggregation_and_target(self):
        hint = _format_slot_hints(_result(
            intent="group_aggregate",
            column="region",
            operator=None,
            value=None,
            target_column="sales",
            aggregation="sum",
        ))
        assert "column: region" in hint
        assert "aggregation: sum" in hint
        assert "target_column: sales" in hint

    def test_limit_hint_includes_limit_value(self):
        hint = _format_slot_hints(_result(intent="limit", column=None, operator=None, value=None, limit=10))
        assert "limit: 10" in hint

    def test_hint_contains_intent_line(self):
        hint = _format_slot_hints(_result(intent="filter"))
        assert "intent: filter" in hint

    def test_hint_contains_preamble(self):
        hint = _format_slot_hints(_result(intent="filter"))
        assert "Pre-validated slot extraction" in hint

    def test_no_concrete_slots_returns_empty(self):
        # Only intent, no slot values — nothing useful to inject.
        hint = _format_slot_hints(_result(
            intent="filter",
            column=None,
            operator=None,
            value=None,
        ))
        assert hint == ""

    def test_confidence_just_below_threshold_returns_empty(self):
        # Bug 1 regression: confidence < _SLOT_HINT_MIN_CONFIDENCE must not produce hints.
        hint = _format_slot_hints(_result(confidence=_SLOT_HINT_MIN_CONFIDENCE - 0.01))
        assert hint == ""

    def test_confidence_at_threshold_produces_hints(self):
        # Bug 1 regression: exactly at threshold must produce hints.
        hint = _format_slot_hints(_result(confidence=_SLOT_HINT_MIN_CONFIDENCE))
        assert hint != ""


# --------------------------------------------------------------------------- #
# Bug 1 regression: orchestrator threshold must equal the planner hint threshold
# --------------------------------------------------------------------------- #

class TestConfidenceThresholdAlignment:
    def test_orchestrator_and_planner_thresholds_are_equal(self):
        """_SLOT_MIN_CONFIDENCE in orchestrator must equal _SLOT_HINT_MIN_CONFIDENCE
        in workflow_planner.  If they diverge, slots in the gap are validated
        and returned but then silently discarded by _format_slot_hints.
        """
        from app.workflow.service_nlu import _SLOT_MIN_CONFIDENCE
        from app.workflow.planning.workflow_planner import _SLOT_HINT_MIN_CONFIDENCE
        assert _SLOT_MIN_CONFIDENCE == _SLOT_HINT_MIN_CONFIDENCE, (
            f"Threshold mismatch: orchestrator uses {_SLOT_MIN_CONFIDENCE}, "
            f"planner uses {_SLOT_HINT_MIN_CONFIDENCE}. "
            "Slots in the gap would be validated but silently discarded."
        )


# --------------------------------------------------------------------------- #
# _run_slot_extraction (unit)
# --------------------------------------------------------------------------- #

class TestRunSlotExtraction:
    def _call(self, query="filter amount > 1000", clarification=None, *, mock_extract=None, mock_validate=None):
        from app.workflow.service_nlu import _run_slot_extraction
        from app.services.profiler import profile

        dummy_profile = profile(
            b"amount,region\n100,North\n200,South\n",
            filename="test.csv",
        )
        with patch("app.workflow.service_nlu.extract_slots", mock_extract or MagicMock(
            return_value=MagicMock(
                parse_error=None,
                result=_result(),
            )
        )):
            with patch("app.workflow.service_nlu.validate_slots", mock_validate or MagicMock(
                return_value=MagicMock(is_valid=True, needs_clarification=False, blocked=False)
            )):
                return _run_slot_extraction(query, dummy_profile, clarification)

    def test_returns_slot_result_when_valid(self):
        from app.workflow.nlu.slot_models import SlotExtractionResult
        result = self._call()
        assert isinstance(result, SlotExtractionResult)

    def test_skips_when_clarification_has_user_answer(self):
        from app.models.clarification_context import ClarificationContext, make_scope_key
        clarification = ClarificationContext(
            dataset_id="d1",
            original_query="q",
            user_answer="amount",
            status="resolved",
            scope_key=make_scope_key(dataset_id="d1", original_query="q"),
        )
        result = self._call(clarification=clarification)
        assert result is None

    def test_falls_back_on_parse_error(self):
        result = self._call(mock_extract=MagicMock(
            return_value=MagicMock(parse_error="bad JSON", result=_result(confidence=0.0, intent="unknown"))
        ))
        assert result is None

    def test_falls_back_on_unknown_intent(self):
        result = self._call(mock_extract=MagicMock(
            return_value=MagicMock(parse_error=None, result=_result(intent="unknown"))
        ))
        assert result is None

    def test_falls_back_on_low_confidence(self):
        result = self._call(mock_extract=MagicMock(
            return_value=MagicMock(
                parse_error=None,
                result=_result(confidence=0.3),
            )
        ))
        assert result is None

    def test_falls_back_when_validation_blocked(self):
        result = self._call(mock_validate=MagicMock(
            return_value=MagicMock(is_valid=False, needs_clarification=False, blocked=True)
        ))
        assert result is None

    def test_returns_clarification_signal_when_needs_clarification(self):
        from app.workflow.service_nlu import _SlotClarificationSignal
        result = self._call(mock_validate=MagicMock(
            return_value=MagicMock(
                is_valid=False,
                needs_clarification=True,
                blocked=False,
                clarification_question="Which column?",
            )
        ))
        assert isinstance(result, _SlotClarificationSignal)
        assert result.question == "Which column?"

    def test_falls_back_on_extract_exception(self):
        result = self._call(mock_extract=MagicMock(side_effect=RuntimeError("network error")))
        assert result is None

    def test_clarification_signal_affected_step_filter_intent(self):
        """Bug regression: affected_step.type must be 'filter_rows' for filter intent."""
        from app.workflow.service_nlu import _SlotClarificationSignal
        result = self._call(
            mock_extract=MagicMock(
                return_value=MagicMock(
                    parse_error=None,
                    result=_result(intent="filter", column="amount"),
                )
            ),
            mock_validate=MagicMock(
                return_value=MagicMock(
                    is_valid=False, needs_clarification=True, blocked=False,
                    clarification_question="Did you mean 'revenue'?",
                )
            ),
        )
        assert isinstance(result, _SlotClarificationSignal)
        assert result.affected_step is not None
        assert result.affected_step["type"] == "filter_rows"

    def test_clarification_signal_affected_step_sort_intent(self):
        """Bug regression: affected_step.type must be 'sort_values' for sort intent."""
        from app.workflow.service_nlu import _SlotClarificationSignal
        result = self._call(
            mock_extract=MagicMock(
                return_value=MagicMock(
                    parse_error=None,
                    result=_result(intent="sort", column="date", operator=None, value=None, sort_direction="desc"),
                )
            ),
            mock_validate=MagicMock(
                return_value=MagicMock(
                    is_valid=False, needs_clarification=True, blocked=False,
                    clarification_question="Did you mean 'created_at'?",
                )
            ),
        )
        assert isinstance(result, _SlotClarificationSignal)
        assert result.affected_step is not None
        assert result.affected_step["type"] == "sort_values"

    def test_clarification_signal_affected_step_group_aggregate_intent(self):
        """Bug regression: affected_step.type must be 'group_by' for group_aggregate intent."""
        from app.workflow.service_nlu import _SlotClarificationSignal
        result = self._call(
            mock_extract=MagicMock(
                return_value=MagicMock(
                    parse_error=None,
                    result=_result(intent="group_aggregate", column="region", operator=None, value=None, aggregation="sum"),
                )
            ),
            mock_validate=MagicMock(
                return_value=MagicMock(
                    is_valid=False, needs_clarification=True, blocked=False,
                    clarification_question="Did you mean 'territory'?",
                )
            ),
        )
        assert isinstance(result, _SlotClarificationSignal)
        assert result.affected_step is not None
        assert result.affected_step["type"] == "group_by"

    def test_clarification_signal_affected_step_none_for_limit_intent(self):
        """Limit intent has no column; affected_step should be None."""
        from app.workflow.service_nlu import _SlotClarificationSignal
        result = self._call(
            mock_extract=MagicMock(
                return_value=MagicMock(
                    parse_error=None,
                    result=_result(intent="limit", column=None, operator=None, value=None, limit=10),
                )
            ),
            mock_validate=MagicMock(
                return_value=MagicMock(
                    is_valid=False, needs_clarification=True, blocked=False,
                    clarification_question="How many rows?",
                )
            ),
        )
        assert isinstance(result, _SlotClarificationSignal)
        assert result.affected_step is None


# --------------------------------------------------------------------------- #
# Chat router integration
# --------------------------------------------------------------------------- #

import io
from fastapi.testclient import TestClient
from app.main import app

_http = TestClient(app)

_BASE_CSV = (
    b"amount,region\n"
    b"1200,North\n"
    b"850,South\n"
)

_MOCK_STEPS = __import__(
    "app.models.workflow",
    fromlist=["FilterRowsStep"],
).FilterRowsStep(type="filter_rows", column="amount", operator=">", value=800)


def _upload(csv_bytes: bytes = _BASE_CSV) -> str:
    resp = _http.post(
        "/api/datasets/upload",
        files={"file": ("data.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert resp.status_code == 200
    return resp.json()["dataset_id"]


class TestChatRouterSlotIntegration:
    """Integration tests verifying slot extraction hooks into the chat API."""

    def _mock_valid_extraction(self, intent="filter", confidence=0.9):
        extraction = _result(intent=intent, confidence=confidence)
        output = MagicMock(parse_error=None, result=extraction)
        return output

    def test_slot_clarification_returned_when_column_missing(self):
        """When slot validation finds a missing column, API returns clarification state."""
        did = _upload()
        missing_result = _result(intent="filter", column="revenue", confidence=0.85)
        output = MagicMock(parse_error=None, result=missing_result)
        with patch("app.workflow.service_nlu.extract_slots", return_value=output):
            with patch("app.workflow.service_nlu.validate_slots") as mock_val:
                mock_val.return_value = MagicMock(
                    is_valid=False,
                    needs_clarification=True,
                    blocked=False,
                    clarification_question="Column 'revenue' not found. Did you mean 'amount'?",
                )
                with patch("app.api.chat.result_explainer.explain", return_value=""):
                    resp = _http.post(
                        "/api/chat",
                        json={"dataset_id": did, "query": "filter revenue > 1000"},
                    )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "needs_clarification"
        assert "clarification_question" in data or data.get("needs_clarification") is True

    def test_fallback_path_used_when_extraction_fails(self):
        """When extract_slots raises, the planner-only path still returns a result."""
        did = _upload()
        mock_steps = [_MOCK_STEPS]
        with patch("app.workflow.service_nlu.extract_slots", side_effect=RuntimeError("no LLM")):
            with patch("app.api.chat.workflow_planner.plan", return_value=mock_steps):
                with patch("app.api.chat.result_explainer.explain", return_value="ok"):
                    resp = _http.post(
                        "/api/chat",
                        json={"dataset_id": did, "query": "filter amount > 800"},
                    )
        assert resp.status_code == 200
        assert resp.json()["state"] in {"completed", "preview_ready", "warning_review"}

    def test_valid_slot_context_passed_to_planner(self):
        """When slot extraction and validation succeed, planner receives slot_context."""
        did = _upload()
        captured = {}

        def fake_plan(query, ctx, client=None, slot_context=None):
            captured["slot_context"] = slot_context
            return [_MOCK_STEPS]

        extraction = _result(intent="filter", confidence=0.9)
        output = MagicMock(parse_error=None, result=extraction)
        with patch("app.workflow.service_nlu.extract_slots", return_value=output):
            with patch("app.workflow.service_nlu.validate_slots") as mock_val:
                mock_val.return_value = MagicMock(
                    is_valid=True, needs_clarification=False, blocked=False
                )
                with patch("app.api.chat.workflow_planner.plan", side_effect=fake_plan):
                    with patch("app.api.chat.result_explainer.explain", return_value="ok"):
                        resp = _http.post(
                            "/api/chat",
                            json={"dataset_id": did, "query": "filter amount > 1000"},
                        )
        assert resp.status_code == 200
        assert captured.get("slot_context") is not None
        assert captured["slot_context"].intent == "filter"

    def test_low_confidence_slot_bypasses_validation_and_uses_planner(self):
        """Low-confidence slot extraction should not trigger validation or clarification."""
        did = _upload()
        extraction = _result(intent="filter", confidence=0.3)
        output = MagicMock(parse_error=None, result=extraction)
        mock_steps = [_MOCK_STEPS]
        with patch("app.workflow.service_nlu.extract_slots", return_value=output):
            with patch("app.workflow.service_nlu.validate_slots") as mock_val:
                with patch("app.api.chat.workflow_planner.plan", return_value=mock_steps):
                    with patch("app.api.chat.result_explainer.explain", return_value="ok"):
                        resp = _http.post(
                            "/api/chat",
                            json={"dataset_id": did, "query": "filter amount > 1000"},
                        )
                mock_val.assert_not_called()
        assert resp.status_code == 200
