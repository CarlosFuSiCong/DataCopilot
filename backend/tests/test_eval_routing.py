"""Unit tests for eval_routing script and golden query contract."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval_routing import (
    RouteResult,
    RoutingMetrics,
    RoutingReport,
    _accumulate_metrics,
    _build_json_output,
    _build_markdown_report,
    run_routing_eval,
)

_GOLDEN_FILE = Path(__file__).parents[1] / "scripts" / "eval_route_decision.json"


# ---------------------------------------------------------------------------
# Golden file contract
# ---------------------------------------------------------------------------


def test_golden_file_exists():
    assert _GOLDEN_FILE.exists(), f"Golden query file not found: {_GOLDEN_FILE}"


def test_golden_file_is_valid_json_array():
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) > 0


def test_golden_file_required_fields():
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    required = {"id", "query", "expected_route", "expected_query_type"}
    for item in data:
        missing = required - item.keys()
        assert not missing, f"Query {item.get('id')} missing fields: {missing}"


def test_golden_file_valid_routes():
    valid_routes = {"ask_mode", "deterministic_tool", "llm_planner", "clarification", "unsupported"}
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    for item in data:
        assert item["expected_route"] in valid_routes, (
            f"Query {item['id']} has invalid route: {item['expected_route']}"
        )


def test_golden_file_unique_ids():
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    ids = [item["id"] for item in data]
    assert len(ids) == len(set(ids)), "Duplicate IDs found in golden query file."


def test_golden_file_has_all_route_types():
    """Golden set must cover all 5 route types for meaningful evaluation."""
    data = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    routes = {item["expected_route"] for item in data}
    expected_routes = {"ask_mode", "deterministic_tool", "llm_planner", "clarification", "unsupported"}
    missing = expected_routes - routes
    assert not missing, f"Golden set is missing examples for routes: {missing}"


# ---------------------------------------------------------------------------
# RoutingMetrics accumulation
# ---------------------------------------------------------------------------


def _make_result(
    *,
    route_ok: bool = True,
    query_type_ok: bool = True,
    tool_ok: bool = True,
    actual_route: str = "deterministic_tool",
    expected_query_type: str = "profiling",
    used_llm: bool = False,
    expected_tool: str | None = "profile_column",
    elapsed_ms: float = 10.0,
) -> RouteResult:
    return RouteResult(
        query_id="t01",
        query="test query",
        expected_route="deterministic_tool",
        expected_query_type=expected_query_type,
        expected_tool=expected_tool,
        actual_route=actual_route,
        actual_query_type=expected_query_type,
        actual_tool=expected_tool,
        actual_confidence=0.9,
        actual_evidence=[],
        route_ok=route_ok,
        query_type_ok=query_type_ok,
        tool_ok=tool_ok,
        used_llm=used_llm,
        elapsed_ms=elapsed_ms,
    )


def test_accumulate_metrics_correct_result():
    metrics = RoutingMetrics()
    result = _make_result(route_ok=True, query_type_ok=True, tool_ok=True, actual_route="deterministic_tool")
    _accumulate_metrics(metrics, result, has_expected_tool=True)
    assert metrics.total == 1
    assert metrics.route_correct == 1
    assert metrics.query_type_correct == 1
    assert metrics.tool_correct == 1
    assert metrics.deterministic_tool_count == 1
    assert metrics.llm_call_count == 0


def test_accumulate_metrics_wrong_route():
    metrics = RoutingMetrics()
    result = _make_result(route_ok=False, actual_route="llm_planner")
    _accumulate_metrics(metrics, result, has_expected_tool=False)
    assert metrics.route_correct == 0
    assert metrics.llm_planner_count == 1


def test_accumulate_metrics_llm_call_tracked():
    metrics = RoutingMetrics()
    result = _make_result(used_llm=True, actual_route="llm_planner")
    _accumulate_metrics(metrics, result, has_expected_tool=False)
    assert metrics.llm_call_count == 1


def test_route_accuracy_zero_when_no_queries():
    metrics = RoutingMetrics()
    assert metrics.route_accuracy == 0.0


def test_route_accuracy_calculation():
    metrics = RoutingMetrics()
    metrics.total = 10
    metrics.route_correct = 8
    assert abs(metrics.route_accuracy - 0.8) < 1e-6


def test_tool_selection_accuracy_uses_tool_eval_count_not_total():
    metrics = RoutingMetrics()
    metrics.total = 10
    metrics.tool_eval_count = 5
    metrics.tool_correct = 4
    assert abs(metrics.tool_selection_accuracy - 0.8) < 1e-6


def test_tool_selection_accuracy_zero_when_no_tool_queries():
    metrics = RoutingMetrics()
    metrics.total = 5
    metrics.tool_eval_count = 0
    assert metrics.tool_selection_accuracy == 0.0


# ---------------------------------------------------------------------------
# run_routing_eval (deterministic mode — no LLM needed)
# ---------------------------------------------------------------------------


def test_run_routing_eval_deterministic_returns_report():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    report = run_routing_eval(golden_queries, use_deterministic=True)
    assert isinstance(report, RoutingReport)
    assert report.metrics.total == len(golden_queries)
    assert len(report.results) == len(golden_queries)


def test_run_routing_eval_method_is_deterministic():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    report = run_routing_eval(golden_queries, use_deterministic=True)
    assert report.method == "deterministic"


def test_run_routing_eval_all_route_types_covered():
    """Eval runs without error for all 5 route types in the golden set."""
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))
    report = run_routing_eval(golden_queries, use_deterministic=True)
    actual_routes = {r.actual_route for r in report.results}
    # At minimum deterministic classifier should produce multiple routes
    assert len(actual_routes) >= 2


def test_run_routing_eval_latency_tracked():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))[:3]
    report = run_routing_eval(golden_queries, use_deterministic=True)
    assert all(r.elapsed_ms >= 0 for r in report.results)


# ---------------------------------------------------------------------------
# JSON / Markdown output
# ---------------------------------------------------------------------------


def test_build_json_output_structure():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))[:5]
    report = run_routing_eval(golden_queries, use_deterministic=True)
    output = _build_json_output(report)
    assert "metrics" in output
    assert "query_type_breakdown" in output
    assert "failures" in output
    assert "results" in output
    assert output["total_queries"] == 5


def test_build_json_output_metrics_fields():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))[:5]
    report = run_routing_eval(golden_queries, use_deterministic=True)
    output = _build_json_output(report)
    required_metrics = {
        "route_accuracy",
        "query_type_accuracy",
        "deterministic_route_rate",
        "ask_mode_rate",
        "llm_planner_rate",
        "clarification_rate",
        "unsupported_rate",
        "llm_call_rate",
        "average_latency_ms",
    }
    assert required_metrics.issubset(output["metrics"].keys())


def test_build_markdown_report_contains_key_sections():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))[:5]
    report = run_routing_eval(golden_queries, use_deterministic=True)
    md = _build_markdown_report(report)
    assert "# Routing Eval Report" in md
    assert "## Accuracy" in md
    assert "## Route Distribution" in md
    assert "## Per Query-Type Breakdown" in md


def test_json_output_is_serializable():
    golden_queries = json.loads(_GOLDEN_FILE.read_text(encoding="utf-8"))[:5]
    report = run_routing_eval(golden_queries, use_deterministic=True)
    output = _build_json_output(report)
    serialized = json.dumps(output, ensure_ascii=False)
    assert len(serialized) > 0
