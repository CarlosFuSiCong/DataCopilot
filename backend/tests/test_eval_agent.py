"""Tests for the MVP5 Agent eval contract and runner."""
import json
from pathlib import Path

import pytest

from scripts.eval_agent import (
    EvalCheck,
    EvalReport,
    ScenarioResult,
    _build_report,
    _load_contract,
    _validate_contract_structure,
    run_scenario,
)

MVP5_CONTRACT = Path(__file__).parents[1] / "scripts" / "eval_contract_mvp5.json"


# ---------------------------------------------------------------------------
# Contract structure tests
# ---------------------------------------------------------------------------


def test_mvp5_contract_file_exists():
    assert MVP5_CONTRACT.exists(), f"eval_contract_mvp5.json not found at {MVP5_CONTRACT}"


def test_mvp5_contract_has_required_top_level_fields():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    assert "version" in data
    assert "scenarios" in data
    assert isinstance(data["scenarios"], list)
    assert len(data["scenarios"]) > 0


def test_mvp5_contract_all_scenarios_have_required_fields():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        sid = scenario.get("id", "<unknown>")
        assert "id" in scenario, f"scenario missing 'id'"
        assert "description" in scenario, f"scenario '{sid}' missing 'description'"
        assert "input" in scenario, f"scenario '{sid}' missing 'input'"
        assert "expected" in scenario, f"scenario '{sid}' missing 'expected'"


def test_mvp5_contract_covers_all_required_scenario_ids():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    ids = {s["id"] for s in data["scenarios"]}
    required = {
        "simple_success",
        "two_step_analysis",
        "empty_result_clarification",
        "missing_required_field_clarification",
        "warning_requires_confirmation",
        "blocked_action",
    }
    assert required.issubset(ids), f"Missing scenario IDs: {required - ids}"


def test_mvp5_contract_all_scenarios_have_expected_fields():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    for scenario in data["scenarios"]:
        sid = scenario["id"]
        expected = scenario["expected"]
        assert "next_action" in expected, f"scenario '{sid}' expected missing 'next_action'"
        assert "agent_action_type" in expected, f"scenario '{sid}' expected missing 'agent_action_type'"
        assert "result_status" in expected, f"scenario '{sid}' expected missing 'result_status'"


def test_load_contract_missing_file_exits(tmp_path: Path):
    with pytest.raises(SystemExit):
        _load_contract(tmp_path / "nonexistent.json")


def test_validate_contract_structure_rejects_missing_version(tmp_path: Path):
    bad_contract = tmp_path / "contract.json"
    bad_contract.write_text(json.dumps({"scenarios": []}), encoding="utf-8")
    data = json.loads(bad_contract.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit):
        _validate_contract_structure(data)


def test_validate_contract_structure_rejects_missing_scenarios(tmp_path: Path):
    bad_contract = tmp_path / "contract.json"
    bad_contract.write_text(json.dumps({"version": "mvp5"}), encoding="utf-8")
    data = json.loads(bad_contract.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit):
        _validate_contract_structure(data)


def test_validate_contract_structure_rejects_scenario_missing_required_field(tmp_path: Path):
    bad_contract = tmp_path / "contract.json"
    bad_contract.write_text(
        json.dumps({"version": "mvp5", "scenarios": [{"id": "s1"}]}),
        encoding="utf-8",
    )
    data = json.loads(bad_contract.read_text(encoding="utf-8"))
    with pytest.raises(SystemExit):
        _validate_contract_structure(data)


# ---------------------------------------------------------------------------
# Scenario execution: success scenarios
# ---------------------------------------------------------------------------


def test_simple_success_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "simple_success")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


def test_two_step_analysis_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "two_step_analysis")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


def test_empty_result_clarification_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "empty_result_clarification")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


def test_missing_required_field_clarification_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "missing_required_field_clarification")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


def test_warning_requires_confirmation_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "warning_requires_confirmation")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


def test_blocked_action_scenario_passes():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "blocked_action")
    result = run_scenario(scenario)
    assert result.overall_ok, _format_failures(result)


# ---------------------------------------------------------------------------
# Report fields: iteration_count, stop_reason, policy_decision, observation_signals
# ---------------------------------------------------------------------------


def test_report_records_iteration_count():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "simple_success")
    result = run_scenario(scenario)
    assert result.iteration_count == 1


def test_report_records_stop_reason():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "simple_success")
    result = run_scenario(scenario)
    assert result.stop_reason is not None
    assert len(result.stop_reason) > 0


def test_report_records_policy_decision_none_when_no_policy():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "simple_success")
    result = run_scenario(scenario)
    assert result.policy_decision is None


def test_report_records_policy_decision_for_blocked_action():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "blocked_action")
    result = run_scenario(scenario)
    assert result.policy_decision == "blocked"


def test_report_records_policy_decision_for_confirmation():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "warning_requires_confirmation")
    result = run_scenario(scenario)
    assert result.policy_decision == "requires_confirmation"


def test_report_records_observation_signals_empty_for_success():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "simple_success")
    result = run_scenario(scenario)
    assert result.observation_signals == []


def test_report_records_observation_signals_for_empty_result():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "empty_result_clarification")
    result = run_scenario(scenario)
    assert "empty_result" in result.observation_signals


def test_report_records_observation_signals_for_large_row_removal():
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    scenario = next(s for s in data["scenarios"] if s["id"] == "warning_requires_confirmation")
    result = run_scenario(scenario)
    assert "large_row_removal" in result.observation_signals


# ---------------------------------------------------------------------------
# Full report aggregation
# ---------------------------------------------------------------------------


def test_build_report_counts_passed_and_failed():
    results = [
        ScenarioResult(
            scenario_id="s1",
            scenario_description="passes",
            overall_ok=True,
            checks=[EvalCheck(field="f", expected="a", actual="a", ok=True)],
            iteration_count=1,
            stop_reason="done",
            policy_decision=None,
            observation_signals=[],
            elapsed_ms=1.0,
        ),
        ScenarioResult(
            scenario_id="s2",
            scenario_description="fails",
            overall_ok=False,
            checks=[EvalCheck(field="f", expected="a", actual="b", ok=False)],
            iteration_count=1,
            stop_reason="done",
            policy_decision=None,
            observation_signals=[],
            elapsed_ms=2.0,
        ),
    ]
    report = _build_report("mvp5", results, elapsed_ms=10.0)
    assert report.total_scenarios == 2
    assert report.passed == 1
    assert report.failed == 1


def test_all_mvp5_contract_scenarios_pass():
    """Integration smoke test: run the entire MVP5 contract and expect all scenarios to pass."""
    data = json.loads(MVP5_CONTRACT.read_text(encoding="utf-8"))
    failures = []
    for scenario in data["scenarios"]:
        result = run_scenario(scenario)
        if not result.overall_ok:
            failures.append(f"{result.scenario_id}: {_format_failures(result)}")
    assert not failures, "Some MVP5 scenarios failed:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_failures(result: ScenarioResult) -> str:
    lines = []
    for check in result.checks:
        if not check.ok:
            lines.append(f"[{check.field}] expected={check.expected!r} actual={check.actual!r}")
    return "; ".join(lines) if lines else "unknown failure"
