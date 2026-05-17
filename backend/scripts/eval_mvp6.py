"""MVP6 evaluation script.

Validates the MVP6 pipeline components against scenario contracts defined in
eval_contract_mvp6.json.  All scenarios are deterministic — no LLM calls are
made.  Four component types are supported:

  slot_validation          — validate_slots from NLU
  observation_tool_suggestion — suggest_tools_from_observation from tool_selector
  analyst_flow             — plan_analyst_flow from analyst.flow_planner
  agent_loop               — decide_next_action from controlled_loop (MVP5 path)

Usage:
    python scripts/eval_mvp6.py
    python scripts/eval_mvp6.py --contract scripts/eval_contract_mvp6.json
    python scripts/eval_mvp6.py --output reports/eval_mvp6.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.agent.analyst.flow_planner import plan_analyst_flow  # noqa: E402
from app.agent.loop.agent_models import AgentValidationSummary  # noqa: E402
from app.agent.loop.controlled_loop import (  # noqa: E402
    AgentLoopConfig,
    AgentLoopContext,
    AgentLoopState,
    decide_next_action,
)
from app.agent.nlu.slot_models import ExtractedSlots, SlotExtractionResult  # noqa: E402
from app.agent.nlu.slot_validator import validate_slots  # noqa: E402
from app.agent.observation.models import ObservationSummary  # noqa: E402
from app.agent.planning.tool_selector import suggest_tools_from_observation  # noqa: E402
from app.agent.policy.models import ActionPolicyResult  # noqa: E402
from app.models.dataset import ColumnProfile, DatasetProfile  # noqa: E402

_DEFAULT_CONTRACT = _SCRIPTS_DIR / "eval_contract_mvp6.json"
_DEFAULT_OUTPUT = _SCRIPTS_DIR / "eval_mvp6_report.json"


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
    component: str
    overall_ok: bool
    checks: list[EvalCheck]
    # MVP6-specific report fields
    slot_result: str | None
    validation_status: str | None
    selected_tools: list[str]
    observation_signals: list[str]
    demo_path: str | None
    iteration_count: int
    stop_reason: str | None
    policy_decision: str | None
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
# Component: slot_validation
# ---------------------------------------------------------------------------


def _build_slot_extraction_result(input_data: dict) -> SlotExtractionResult:
    slots_dict = input_data.get("slots", {})
    slots = ExtractedSlots(
        column=slots_dict.get("column"),
        operator=slots_dict.get("operator"),
        value=slots_dict.get("value"),
        target_column=slots_dict.get("target_column"),
        aggregation=slots_dict.get("aggregation"),
        sort_direction=slots_dict.get("sort_direction"),
        limit=slots_dict.get("limit"),
    )
    return SlotExtractionResult(
        raw_query=input_data.get("raw_query", "eval query"),
        intent=input_data.get("intent", "unknown"),
        slots=slots,
        confidence=input_data.get("confidence", 0.0),
        query_locale=input_data.get("query_locale", "en"),
    )


def _build_dataset_profile_from_columns(column_names: list[str]) -> DatasetProfile:
    columns = [ColumnProfile(name=c, dtype="object", missing_count=0, missing_pct=0.0) for c in column_names]
    return DatasetProfile.model_construct(
        filename="eval.csv",
        row_count=100,
        column_count=len(columns),
        columns=columns,
        preview=[],
    )


def run_slot_validation_scenario(scenario: dict) -> ScenarioResult:
    input_data = scenario["input"]
    expected = scenario["expected"]
    start = time.monotonic()

    extraction = _build_slot_extraction_result(input_data)
    profile = _build_dataset_profile_from_columns(input_data.get("schema_columns", []))
    outcome = validate_slots(extraction, profile)

    elapsed_ms = (time.monotonic() - start) * 1000

    checks: list[EvalCheck] = []

    def _check(fname: str, actual: object, exp: object) -> None:
        checks.append(EvalCheck(field=fname, expected=exp, actual=actual, ok=actual == exp))

    if "is_valid" in expected:
        _check("is_valid", outcome.is_valid, expected["is_valid"])
    if "needs_clarification" in expected:
        _check("needs_clarification", outcome.needs_clarification, expected["needs_clarification"])
    if "status" in expected:
        _check("status", outcome.status, expected["status"])
    if "blocked" in expected:
        _check("blocked", outcome.blocked, expected["blocked"])
    if expected.get("clarification_question_not_empty"):
        checks.append(
            EvalCheck(
                field="clarification_question_not_empty",
                expected=True,
                actual=bool(outcome.clarification_question),
                ok=bool(outcome.clarification_question),
            )
        )
    if expected.get("has_candidate_columns"):
        checks.append(
            EvalCheck(
                field="has_candidate_columns",
                expected=True,
                actual=bool(outcome.candidate_columns),
                ok=bool(outcome.candidate_columns),
            )
        )

    return ScenarioResult(
        scenario_id=scenario["id"],
        scenario_description=scenario.get("description", ""),
        component="slot_validation",
        overall_ok=all(c.ok for c in checks),
        checks=checks,
        slot_result=outcome.status,
        validation_status="valid" if outcome.is_valid else outcome.status,
        selected_tools=[],
        observation_signals=[],
        demo_path=None,
        iteration_count=0,
        stop_reason=outcome.clarification_question,
        policy_decision=None,
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# Component: observation_tool_suggestion
# ---------------------------------------------------------------------------


def run_observation_tool_suggestion_scenario(scenario: dict) -> ScenarioResult:
    input_data = scenario["input"]
    expected = scenario["expected"]
    start = time.monotonic()

    signals = input_data.get("observation_signals", [])
    observation = ObservationSummary(status="warning", signals=signals)
    suggestions = suggest_tools_from_observation(observation)
    suggested_tool_types = [s.tool_type for s in suggestions]

    elapsed_ms = (time.monotonic() - start) * 1000
    checks: list[EvalCheck] = []

    if "suggestion_count_min" in expected:
        actual_count = len(suggestions)
        exp_min = expected["suggestion_count_min"]
        checks.append(
            EvalCheck(
                field="suggestion_count_min",
                expected=f">= {exp_min}",
                actual=actual_count,
                ok=actual_count >= exp_min,
            )
        )
    for tool_type in expected.get("suggestion_tool_types_include", []):
        checks.append(
            EvalCheck(
                field=f"suggestion_tool_types_include[{tool_type}]",
                expected=tool_type,
                actual=tool_type if tool_type in suggested_tool_types else None,
                ok=tool_type in suggested_tool_types,
            )
        )

    return ScenarioResult(
        scenario_id=scenario["id"],
        scenario_description=scenario.get("description", ""),
        component="observation_tool_suggestion",
        overall_ok=all(c.ok for c in checks),
        checks=checks,
        slot_result=None,
        validation_status=None,
        selected_tools=suggested_tool_types,
        observation_signals=signals,
        demo_path=None,
        iteration_count=0,
        stop_reason=None,
        policy_decision=None,
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# Component: analyst_flow
# ---------------------------------------------------------------------------


def _build_dataset_profile_from_scenario(input_data: dict) -> DatasetProfile:
    raw_columns = input_data.get("columns", [])
    columns = [
        ColumnProfile(
            name=c["name"],
            dtype=c.get("dtype", "object"),
            missing_count=c.get("missing_count", 0),
            missing_pct=0.0,
        )
        for c in raw_columns
    ]
    return DatasetProfile.model_construct(
        filename="eval.csv",
        row_count=100,
        column_count=len(columns),
        columns=columns,
        preview=[],
    )


def run_analyst_flow_scenario(scenario: dict) -> ScenarioResult:
    input_data = scenario["input"]
    expected = scenario["expected"]
    start = time.monotonic()

    profile = _build_dataset_profile_from_scenario(input_data)
    signals = input_data.get("observation_signals", [])
    observation = ObservationSummary(status="warning" if signals else "ok", signals=signals) if signals else None
    plan = plan_analyst_flow(profile, observation)

    elapsed_ms = (time.monotonic() - start) * 1000
    checks: list[EvalCheck] = []

    def _check(fname: str, actual: object, exp: object) -> None:
        checks.append(EvalCheck(field=fname, expected=exp, actual=actual, ok=actual == exp))

    if "demo_path" in expected:
        _check("demo_path", plan.demo_path, expected["demo_path"])
    if "first_tool_type" in expected:
        first = plan.suggestions[0].tool_type if plan.suggestions else None
        _check("first_tool_type", first, expected["first_tool_type"])
    if "suggestion_count_min" in expected:
        actual_count = len(plan.suggestions)
        exp_min = expected["suggestion_count_min"]
        checks.append(
            EvalCheck(
                field="suggestion_count_min",
                expected=f">= {exp_min}",
                actual=actual_count,
                ok=actual_count >= exp_min,
            )
        )

    return ScenarioResult(
        scenario_id=scenario["id"],
        scenario_description=scenario.get("description", ""),
        component="analyst_flow",
        overall_ok=all(c.ok for c in checks),
        checks=checks,
        slot_result=None,
        validation_status=None,
        selected_tools=[s.tool_type for s in plan.suggestions],
        observation_signals=signals,
        demo_path=plan.demo_path,
        iteration_count=0,
        stop_reason=None,
        policy_decision=None,
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# Component: agent_loop  (reuses the MVP5 controlled_loop logic)
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


def run_agent_loop_scenario(scenario: dict) -> ScenarioResult:
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
    config = AgentLoopConfig(max_iterations=3, max_retries=input_data.get("max_retries", 1))
    state = AgentLoopState(iteration_count=0, retry_count=input_data.get("retry_count", 0))

    start = time.monotonic()
    dec, action, evaluation = decide_next_action(context, config=config, state=state)
    elapsed_ms = (time.monotonic() - start) * 1000

    checks: list[EvalCheck] = []

    def _check(fname: str, actual: object, exp: object) -> None:
        checks.append(EvalCheck(field=fname, expected=exp, actual=actual, ok=actual == exp))

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

    return ScenarioResult(
        scenario_id=scenario["id"],
        scenario_description=scenario.get("description", ""),
        component="agent_loop",
        overall_ok=all(c.ok for c in checks),
        checks=checks,
        slot_result=None,
        validation_status=input_data.get("validation_status"),
        selected_tools=[],
        observation_signals=list(observation.signals),
        demo_path=None,
        iteration_count=1,
        stop_reason=dec.rationale,
        policy_decision=policy.decision if policy else None,
        elapsed_ms=round(elapsed_ms, 2),
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_RUNNERS = {
    "slot_validation": run_slot_validation_scenario,
    "observation_tool_suggestion": run_observation_tool_suggestion_scenario,
    "analyst_flow": run_analyst_flow_scenario,
    "agent_loop": run_agent_loop_scenario,
}


def run_scenario(scenario: dict) -> ScenarioResult:
    component = scenario.get("component", "agent_loop")
    runner = _RUNNERS.get(component)
    if runner is None:
        print(f"[error] unknown component '{component}' in scenario '{scenario.get('id')}'", file=sys.stderr)
        sys.exit(1)
    return runner(scenario)


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
        print(f"  {mark} [{result.component}] {result.scenario_id}")
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
    parser = argparse.ArgumentParser(description="MVP6 eval runner")
    parser.add_argument("--contract", type=Path, default=_DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=None)
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
