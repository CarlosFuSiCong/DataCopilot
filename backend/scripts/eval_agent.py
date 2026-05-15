"""MVP5 Agent loop evaluation script.

Validates the controlled Agent loop decision logic against scenario contracts
defined in eval_contract_mvp5.json. All scenarios are deterministic — no LLM
calls are made. The script constructs AgentLoopContext from each scenario's
input state, calls decide_next_action, and checks the result against expected
fields.

Usage:
    python scripts/eval_agent.py
    python scripts/eval_agent.py --contract scripts/eval_contract_mvp5.json
    python scripts/eval_agent.py --output reports/eval_agent.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.agent.evaluation.evaluator import EvaluationDecision  # noqa: E402
from app.agent.loop.agent_models import AgentValidationSummary  # noqa: E402
from app.agent.loop.controlled_loop import (  # noqa: E402
    AgentLoopConfig,
    AgentLoopContext,
    AgentLoopState,
    decide_next_action,
    map_evaluation_to_action,
)
from app.agent.observation.models import ObservationSummary  # noqa: E402
from app.agent.policy.models import ActionPolicyResult  # noqa: E402

_DEFAULT_CONTRACT = _SCRIPTS_DIR / "eval_contract_mvp5.json"
_DEFAULT_OUTPUT = _SCRIPTS_DIR / "eval_agent_report.json"


# ---------------------------------------------------------------------------
# Report data classes
# ---------------------------------------------------------------------------


@dataclass
class EvalCheck:
    field: str
    expected: object
    actual: object
    ok: bool


@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_description: str
    overall_ok: bool
    checks: list[EvalCheck]
    iteration_count: int
    stop_reason: str | None
    policy_decision: str | None
    observation_signals: list[str]
    elapsed_ms: float


@dataclass
class EvalReport:
    contract_version: str
    total_scenarios: int
    passed: int
    failed: int
    generated_at: str
    elapsed_ms: float
    results: list[ScenarioResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Contract loading
# ---------------------------------------------------------------------------


def _load_contract(path: Path) -> dict:
    if not path.exists():
        print(f"[error] contract file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate_contract_structure(data: dict) -> None:
    if "version" not in data:
        print("[error] contract is missing required field 'version'", file=sys.stderr)
        sys.exit(1)
    if "scenarios" not in data or not isinstance(data["scenarios"], list):
        print("[error] contract is missing required field 'scenarios'", file=sys.stderr)
        sys.exit(1)
    for scenario in data["scenarios"]:
        for required in ("id", "description", "input", "expected"):
            if required not in scenario:
                print(
                    f"[error] scenario '{scenario.get('id', '?')}' is missing required field '{required}'",
                    file=sys.stderr,
                )
                sys.exit(1)


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------


def _build_observation(input_data: dict) -> ObservationSummary:
    return ObservationSummary(
        status=input_data.get("observation_status", "ok"),
        signals=input_data.get("observation_signals", []),
        message=input_data.get("observation_message"),
        recommended_next_action=input_data.get("observation_recommended_next_action"),
    )


def _build_validation(input_data: dict) -> AgentValidationSummary:
    return AgentValidationSummary(
        status=input_data.get("validation_status", "not_run"),
        error=input_data.get("validation_error"),
    )


def _build_policy(input_data: dict) -> ActionPolicyResult | None:
    decision = input_data.get("policy_decision")
    if decision is None:
        return None
    return ActionPolicyResult(
        action="plan_workflow",
        decision=decision,
        reason=input_data.get("policy_reason", "Policy decision from eval contract."),
        can_execute=decision == "auto_executable",
        requires_confirmation=decision == "requires_confirmation",
    )


def run_scenario(scenario: dict) -> ScenarioResult:
    input_data = scenario["input"]
    expected = scenario["expected"]

    observation = _build_observation(input_data)
    validation = _build_validation(input_data)
    policy = _build_policy(input_data)

    context = AgentLoopContext(
        task=input_data.get("task", ""),
        plan=input_data.get("plan", []),
        observation=observation,
        validation=validation,
        policy=policy,
    )
    config = AgentLoopConfig(
        max_iterations=3,
        max_retries=input_data.get("max_retries", 1),
    )
    state = AgentLoopState(
        iteration_count=0,
        retry_count=input_data.get("retry_count", 0),
    )

    start = time.monotonic()
    dec, action, evaluation = decide_next_action(context, config=config, state=state)
    elapsed_ms = (time.monotonic() - start) * 1000

    checks: list[EvalCheck] = []

    def _check(field_name: str, actual: object, exp_value: object) -> None:
        checks.append(EvalCheck(field=field_name, expected=exp_value, actual=actual, ok=actual == exp_value))

    if "next_action" in expected:
        _check("next_action", evaluation.next_action, expected["next_action"])

    if "agent_action_type" in expected:
        _check("agent_action_type", action.type, expected["agent_action_type"])

    if "result_status" in expected:
        _check("result_status", evaluation.result_status, expected["result_status"])

    if expected.get("stop_reason_not_null"):
        checks.append(
            EvalCheck(
                field="stop_reason_not_null",
                expected=True,
                actual=bool(dec.rationale),
                ok=bool(dec.rationale),
            )
        )

    for signal in expected.get("observation_signals_include", []):
        checks.append(
            EvalCheck(
                field=f"observation_signals_include[{signal}]",
                expected=signal,
                actual=signal if signal in observation.signals else None,
                ok=signal in observation.signals,
            )
        )

    overall_ok = all(c.ok for c in checks)

    return ScenarioResult(
        scenario_id=scenario["id"],
        scenario_description=scenario.get("description", ""),
        overall_ok=overall_ok,
        checks=checks,
        iteration_count=1,
        stop_reason=dec.rationale,
        policy_decision=policy.decision if policy else None,
        observation_signals=list(observation.signals),
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------


def _build_report(
    contract_version: str,
    results: list[ScenarioResult],
    elapsed_ms: float,
) -> EvalReport:
    passed = sum(1 for r in results if r.overall_ok)
    return EvalReport(
        contract_version=contract_version,
        total_scenarios=len(results),
        passed=passed,
        failed=len(results) - passed,
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        elapsed_ms=round(elapsed_ms, 2),
        results=results,
    )


def _print_summary(report: EvalReport) -> None:
    status = "PASSED" if report.failed == 0 else "FAILED"
    print(f"\n[{status}] {report.passed}/{report.total_scenarios} scenarios passed ({report.elapsed_ms:.1f} ms)\n")
    for result in report.results:
        mark = "✓" if result.overall_ok else "✗"
        print(f"  {mark} {result.scenario_id}")
        if not result.overall_ok:
            for check in result.checks:
                if not check.ok:
                    print(f"      FAIL [{check.field}]: expected={check.expected!r}  actual={check.actual!r}")


def _serialize_report(report: EvalReport) -> dict:
    def _to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _to_dict(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [_to_dict(item) for item in obj]
        return obj

    return _to_dict(report)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="MVP5 Agent loop eval runner")
    parser.add_argument(
        "--contract",
        type=Path,
        default=_DEFAULT_CONTRACT,
        help="Path to the MVP5 eval contract JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write the JSON report. Omit to skip file output.",
    )
    args = parser.parse_args()

    data = _load_contract(args.contract)
    _validate_contract_structure(data)

    print(f"Running {len(data['scenarios'])} scenarios from {args.contract.name} …")
    start = time.monotonic()
    results = [run_scenario(scenario) for scenario in data["scenarios"]]
    elapsed_ms = (time.monotonic() - start) * 1000

    report = _build_report(
        contract_version=data.get("version", "unknown"),
        results=results,
        elapsed_ms=elapsed_ms,
    )

    _print_summary(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(_serialize_report(report), f, indent=2, ensure_ascii=False)
        print(f"Report written to {args.output}")

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
