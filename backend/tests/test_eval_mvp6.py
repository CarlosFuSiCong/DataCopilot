"""Tests for the MVP6 eval contract and runner.

Coverage:
- Contract file existence and structure (5 tests)
- Required scenario IDs present (1 test)
- Each scenario has correct fields (1 test)
- run_scenario for each component type (12 tests)
- Report fields: slot_result, validation_status, selected_tools, demo_path (8 tests)
- Full contract all-scenarios smoke (1 test)
- _build_report aggregation (1 test)
- _load_contract / _validate_contract_structure error paths (3 tests)
- E2E demo script gate (2 tests)
"""
import json
import os
from pathlib import Path

import pytest

from scripts.eval_mvp6 import (
    EvalCheck,
    EvalReport,
    ScenarioResult,
    _build_report,
    _load_contract,
    _validate_contract_structure,
    run_scenario,
)

MVP6_CONTRACT = Path(__file__).parents[1] / "scripts" / "eval_contract_mvp6.json"


# ---------------------------------------------------------------------------
# Contract structure
# ---------------------------------------------------------------------------


def test_mvp6_contract_file_exists():
    assert MVP6_CONTRACT.exists(), f"eval_contract_mvp6.json not found at {MVP6_CONTRACT}"


def test_mvp6_contract_has_required_top_level_fields():
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    assert "version" in data
    assert data["version"] == "mvp6"
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) > 0


def test_mvp6_contract_all_scenarios_have_required_fields():
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        sid = scenario.get("id", "<unknown>")
        assert "id" in scenario, f"scenario missing 'id'"
        assert "description" in scenario, f"scenario '{sid}' missing 'description'"
        assert "input" in scenario, f"scenario '{sid}' missing 'input'"
        assert "expected" in scenario, f"scenario '{sid}' missing 'expected'"


def test_mvp6_contract_covers_required_scenario_ids():
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    ids = {s["id"] for s in data["scenarios"]}
    required = {
        "slot_extraction_success",
        "missing_slot_clarification",
        "ambiguous_column_clarification",
        "multilingual_query",
        "observation_driven_inspect_tool",
        "analyst_flow_explore_path",
        "analyst_flow_quality_path",
        "analyst_flow_minimal_path",
        "agent_loop_slot_success_finalizes",
    }
    assert required.issubset(ids), f"Missing scenario IDs: {required - ids}"


def test_mvp6_contract_all_scenarios_declare_component():
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    valid_components = {"slot_validation", "observation_tool_suggestion", "analyst_flow", "agent_loop"}
    for scenario in data["scenarios"]:
        sid = scenario["id"]
        assert "component" in scenario, f"scenario '{sid}' missing 'component'"
        assert scenario["component"] in valid_components, (
            f"scenario '{sid}' has unknown component '{scenario['component']}'"
        )


# ---------------------------------------------------------------------------
# Contract loading error paths
# ---------------------------------------------------------------------------


def test_load_contract_missing_file_exits(tmp_path: Path):
    with pytest.raises(SystemExit):
        _load_contract(tmp_path / "nonexistent.json")


def test_validate_contract_structure_rejects_missing_version(tmp_path: Path):
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _validate_contract_structure(json.loads(bad.read_text()))


def test_validate_contract_structure_rejects_scenario_missing_required_field(tmp_path: Path):
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"version": "mvp6", "scenarios": [{"id": "s1"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _validate_contract_structure(json.loads(bad.read_text()))


# ---------------------------------------------------------------------------
# Slot validation scenarios
# ---------------------------------------------------------------------------


def _get_scenario(scenario_id: str) -> dict:
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    return next(s for s in data["scenarios"] if s["id"] == scenario_id)


def test_slot_extraction_success_passes():
    result = run_scenario(_get_scenario("slot_extraction_success"))
    assert result.overall_ok, _format_failures(result)


def test_slot_extraction_success_reports_valid_status():
    result = run_scenario(_get_scenario("slot_extraction_success"))
    assert result.slot_result == "valid"
    assert result.validation_status == "valid"


def test_missing_slot_clarification_passes():
    result = run_scenario(_get_scenario("missing_slot_clarification"))
    assert result.overall_ok, _format_failures(result)


def test_missing_slot_clarification_reports_status():
    result = run_scenario(_get_scenario("missing_slot_clarification"))
    assert result.slot_result == "missing_required_slot"


def test_ambiguous_column_clarification_passes():
    result = run_scenario(_get_scenario("ambiguous_column_clarification"))
    assert result.overall_ok, _format_failures(result)


def test_ambiguous_column_clarification_reports_status():
    result = run_scenario(_get_scenario("ambiguous_column_clarification"))
    assert result.slot_result == "ambiguous_column"


def test_multilingual_query_passes():
    result = run_scenario(_get_scenario("multilingual_query"))
    assert result.overall_ok, _format_failures(result)


def test_unsupported_intent_blocked_passes():
    result = run_scenario(_get_scenario("unsupported_intent_blocked"))
    assert result.overall_ok, _format_failures(result)


# ---------------------------------------------------------------------------
# Observation tool suggestion scenarios
# ---------------------------------------------------------------------------


def test_observation_driven_inspect_tool_passes():
    result = run_scenario(_get_scenario("observation_driven_inspect_tool"))
    assert result.overall_ok, _format_failures(result)


def test_observation_driven_inspect_tool_reports_selected_tools():
    result = run_scenario(_get_scenario("observation_driven_inspect_tool"))
    assert "inspect_unique_values" in result.selected_tools or "profile_column" in result.selected_tools
    assert result.observation_signals == ["empty_result"]


# ---------------------------------------------------------------------------
# Analyst flow scenarios
# ---------------------------------------------------------------------------


def test_analyst_flow_explore_path_passes():
    result = run_scenario(_get_scenario("analyst_flow_explore_path"))
    assert result.overall_ok, _format_failures(result)


def test_analyst_flow_explore_path_reports_demo_path():
    result = run_scenario(_get_scenario("analyst_flow_explore_path"))
    assert result.demo_path == "explore"


def test_analyst_flow_quality_path_passes():
    result = run_scenario(_get_scenario("analyst_flow_quality_path"))
    assert result.overall_ok, _format_failures(result)


def test_analyst_flow_quality_path_reports_demo_path():
    result = run_scenario(_get_scenario("analyst_flow_quality_path"))
    assert result.demo_path == "quality"
    assert "data_quality_issue" in result.observation_signals


def test_analyst_flow_minimal_path_passes():
    result = run_scenario(_get_scenario("analyst_flow_minimal_path"))
    assert result.overall_ok, _format_failures(result)


def test_analyst_flow_minimal_path_reports_demo_path():
    result = run_scenario(_get_scenario("analyst_flow_minimal_path"))
    assert result.demo_path == "minimal"


# ---------------------------------------------------------------------------
# Agent loop scenarios
# ---------------------------------------------------------------------------


def test_agent_loop_slot_success_finalizes_passes():
    result = run_scenario(_get_scenario("agent_loop_slot_success_finalizes"))
    assert result.overall_ok, _format_failures(result)


def test_agent_loop_slot_success_reports_iteration_count():
    result = run_scenario(_get_scenario("agent_loop_slot_success_finalizes"))
    assert result.iteration_count == 1
    assert result.stop_reason is not None


def test_agent_loop_quality_observation_clarify_passes():
    result = run_scenario(_get_scenario("agent_loop_quality_observation_clarify"))
    assert result.overall_ok, _format_failures(result)


def test_agent_loop_quality_observation_reports_signals():
    result = run_scenario(_get_scenario("agent_loop_quality_observation_clarify"))
    assert "data_quality_issue" in result.observation_signals


def test_agent_loop_inspect_tool_step_finalizes_passes():
    result = run_scenario(_get_scenario("agent_loop_inspect_tool_step_finalizes"))
    assert result.overall_ok, _format_failures(result)


# ---------------------------------------------------------------------------
# Report aggregation
# ---------------------------------------------------------------------------


def test_build_report_counts_passed_and_failed():
    results = [
        ScenarioResult(
            scenario_id="s1",
            scenario_description="passes",
            component="slot_validation",
            overall_ok=True,
            checks=[EvalCheck(field="f", expected="a", actual="a", ok=True)],
            slot_result="valid",
            validation_status="valid",
            selected_tools=[],
            observation_signals=[],
            demo_path=None,
            iteration_count=0,
            stop_reason=None,
            policy_decision=None,
            elapsed_ms=1.0,
        ),
        ScenarioResult(
            scenario_id="s2",
            scenario_description="fails",
            component="analyst_flow",
            overall_ok=False,
            checks=[EvalCheck(field="f", expected="a", actual="b", ok=False)],
            slot_result=None,
            validation_status=None,
            selected_tools=[],
            observation_signals=[],
            demo_path="explore",
            iteration_count=0,
            stop_reason=None,
            policy_decision=None,
            elapsed_ms=2.0,
        ),
    ]
    report = _build_report("mvp6", results, elapsed_ms=10.0)
    assert report.total_scenarios == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.contract_version == "mvp6"


# ---------------------------------------------------------------------------
# Full contract smoke
# ---------------------------------------------------------------------------


def test_all_mvp6_contract_scenarios_pass():
    """Integration smoke: run the entire MVP6 contract and expect all scenarios to pass."""
    data = json.loads(MVP6_CONTRACT.read_text(encoding="utf-8"))
    failures = []
    for scenario in data["scenarios"]:
        result = run_scenario(scenario)
        if not result.overall_ok:
            failures.append(f"{result.scenario_id}: {_format_failures(result)}")
    assert not failures, "Some MVP6 scenarios failed:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# E2E demo script gate tests (no live backend required)
# ---------------------------------------------------------------------------


def test_e2e_demo_skips_without_env_var(monkeypatch, capsys):
    monkeypatch.delenv("RUN_REAL_E2E", raising=False)
    import importlib
    import scripts.e2e_demo as e2e_mod
    importlib.reload(e2e_mod)
    exit_code = e2e_mod.main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "RUN_REAL_E2E" in captured.err or "RUN_REAL_E2E" in captured.out


def test_e2e_demo_fixture_csv_exists():
    fixture = Path(__file__).parents[1] / "scripts" / "e2e_demo_fixture.csv"
    assert fixture.exists(), f"e2e_demo_fixture.csv not found at {fixture}"


def test_e2e_demo_fixture_has_expected_columns():
    fixture = Path(__file__).parents[1] / "scripts" / "e2e_demo_fixture.csv"
    first_line = fixture.read_text(encoding="utf-8").splitlines()[0]
    columns = [c.strip() for c in first_line.split(",")]
    assert "amount" in columns
    assert "status" in columns
    assert "region" in columns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_failures(result: ScenarioResult) -> str:
    lines = [
        f"[{c.field}] expected={c.expected!r} actual={c.actual!r}"
        for c in result.checks
        if not c.ok
    ]
    return "; ".join(lines) if lines else "unknown failure"
