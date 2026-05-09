"""Workflow evaluation script for DataCopilot.

Runs a fixed set of annotated queries end-to-end against the demo dataset
(sample_data/orders.csv) and reports per-phase success rates:

  - retrieval_ok    : RAG retrieved at least one relevant doc
  - planner_ok      : LLM produced valid workflow steps (no PlannerError)
  - clarification   : LLM requested clarification instead of steps
  - validation_ok   : steps passed the validator
  - execution_ok    : executor completed without error
  - step_types_ok   : actual step types match expected_step_types
  - shape_ok        : output row/column count matches expected_output

Failure cases are classified by the earliest failing phase:
  retrieval → planning → validation → execution → shape

Usage (from the backend/ directory):

    # Keyword retrieval (no database required; LLM_API_KEY is still needed)
    python scripts/eval_workflow.py

    # pgvector retrieval (requires DATABASE_URL + LLM_API_KEY)
    python scripts/eval_workflow.py --method pgvector

    # Save JSON report
    python scripts/eval_workflow.py --output report.json

    # Inside the Docker api container (sample_data is mounted at /app/sample_data)
    docker exec datacopilot-api python scripts/eval_workflow.py
    docker exec datacopilot-api python scripts/eval_workflow.py --method pgvector
    docker exec datacopilot-api python scripts/eval_workflow.py --output /tmp/report.json

Environment variables (read from .env or shell):
    LLM_API_KEY     required
    LLM_BASE_URL    optional; defaults to https://api.openai.com/v1
    LLM_MODEL       optional; defaults to settings value
    DATABASE_URL    required only for --method pgvector
    RETRIEVAL_METHOD overridden by --method flag when provided
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Bootstrap: add backend root to sys.path so app.* imports work when the
# script is run from any working directory.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
_REPO_DIR = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.core.exceptions import (  # noqa: E402
    ClarificationNeeded,
    ExecutionError,
    PlannerError,
    WorkflowValidationError,
)
from app.models.workflow import WorkflowStep  # noqa: E402
from app.services import executor as executor_service  # noqa: E402
from app.services import rag_service  # noqa: E402
from app.services import validator as validator_service  # noqa: E402
from app.services import workflow_planner  # noqa: E402
from app.services.profiler import profile  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("eval_workflow")

_QUERIES_FILE = _SCRIPTS_DIR / "eval_workflow_queries.json"
# Default dataset path works both locally (repo root / sample_data) and inside
# the Docker api container where sample_data is mounted at /app/sample_data.
_DEFAULT_DATASET = _BACKEND_DIR / "sample_data" / "orders.csv"
if not _DEFAULT_DATASET.exists():
    _DEFAULT_DATASET = _REPO_DIR / "sample_data" / "orders.csv"

ExpectedOutcome = Literal["success", "validation_error", "clarification"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    retrieval_ok: bool = False
    planner_ok: bool = False
    clarification: bool = False      # LLM asked for clarification (expected or not)
    validation_ok: bool = False
    execution_ok: bool = False
    step_types_ok: bool = False
    shape_ok: bool = False
    actual_step_types: list[str] = field(default_factory=list)
    actual_row_count: int | None = None
    actual_col_count: int | None = None
    failure_phase: str | None = None  # retrieval | planning | validation | execution | shape
    failure_message: str = ""
    elapsed_ms: float = 0.0


@dataclass
class QueryResult:
    query_id: str
    demo_case: str
    query: str
    expected_step_types: list[str]
    expected_outcome: ExpectedOutcome
    expected_row_count: int | None
    expected_col_count: int | None
    phases: PhaseResult
    overall_ok: bool


@dataclass
class EvalReport:
    method: str
    dataset: str
    total_queries: int
    results: list[QueryResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "planner_ok": sum(1 for r in self.results if r.phases.planner_ok),
            "validation_ok": sum(1 for r in self.results if r.phases.validation_ok),
            "execution_ok": sum(1 for r in self.results if r.phases.execution_ok),
            "step_types_ok": sum(1 for r in self.results if r.phases.step_types_ok),
            "shape_ok": sum(1 for r in self.results if r.phases.shape_ok),
            "overall_ok": sum(1 for r in self.results if r.overall_ok),
        }

    @property
    def failures(self) -> list[QueryResult]:
        return [r for r in self.results if not r.overall_ok]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_queries() -> list[dict]:
    try:
        return json.loads(_QUERIES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Eval queries file not found: %s", _QUERIES_FILE)
        sys.exit(1)


def _load_dataset(path: Path) -> bytes:
    if not path.exists():
        logger.error("Demo dataset not found: %s", path)
        sys.exit(1)
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Per-query evaluation
# ---------------------------------------------------------------------------

async def _eval_query(
    query_spec: dict,
    dataset_bytes: bytes,
    method: str,
    docs: list[dict] | None,
) -> QueryResult:
    q_id: str = query_spec["id"]
    demo_case: str = query_spec.get("demo_case", "")
    query: str = query_spec["query"]
    expected_step_types: list[str] = query_spec.get("expected_step_types", [])
    expected_outcome: ExpectedOutcome = query_spec.get("expected_outcome", "success")
    expected_output: dict | None = query_spec.get("expected_output")
    expected_row_count: int | None = expected_output.get("row_count") if expected_output else None
    expected_col_count: int | None = expected_output.get("column_count") if expected_output else None

    phases = PhaseResult()
    t0 = time.monotonic()

    # --- Phase 0: profile dataset ---
    dataset_profile = profile(dataset_bytes, "orders.csv")
    column_names = [c.name for c in dataset_profile.columns]

    # --- Phase 1: RAG retrieval ---
    try:
        rag_ctx = await rag_service.build_context(
            query=query,
            dataset_profile=dataset_profile,
            top_k=3,
            docs=docs,
        )
        phases.retrieval_ok = bool(rag_ctx.retrieved_docs)
    except Exception as exc:
        phases.failure_phase = "retrieval"
        phases.failure_message = str(exc)
        phases.elapsed_ms = (time.monotonic() - t0) * 1000
        return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                              expected_row_count, expected_col_count, phases)

    # --- Phase 2: planning ---
    planned_steps: list[WorkflowStep] = []
    try:
        planned_steps = workflow_planner.plan(query, rag_ctx)
        phases.planner_ok = True
        phases.actual_step_types = [s.type for s in planned_steps]
    except ClarificationNeeded as exc:
        phases.clarification = True
        phases.failure_phase = "planning"
        phases.failure_message = f"clarification: {exc}"
        phases.elapsed_ms = (time.monotonic() - t0) * 1000
        return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                              expected_row_count, expected_col_count, phases)
    except PlannerError as exc:
        phases.failure_phase = "planning"
        phases.failure_message = str(exc)
        phases.elapsed_ms = (time.monotonic() - t0) * 1000
        return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                              expected_row_count, expected_col_count, phases)

    # --- Phase 3: validation ---
    try:
        validator_service.validate(planned_steps, column_names)
        phases.validation_ok = True
    except WorkflowValidationError as exc:
        # For w09-style cases, a validation error is the expected outcome.
        phases.failure_phase = "validation"
        phases.failure_message = str(exc)
        phases.elapsed_ms = (time.monotonic() - t0) * 1000
        return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                              expected_row_count, expected_col_count, phases)

    # --- Phase 4: execution ---
    try:
        exec_result = executor_service.execute(planned_steps, dataset_bytes)
        phases.execution_ok = True
        phases.actual_row_count = exec_result.row_count
        phases.actual_col_count = exec_result.column_count
    except ExecutionError as exc:
        phases.failure_phase = "execution"
        phases.failure_message = str(exc)
        phases.elapsed_ms = (time.monotonic() - t0) * 1000
        return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                              expected_row_count, expected_col_count, phases)

    # --- Phase 5: shape check ---
    if expected_row_count is not None and phases.actual_row_count != expected_row_count:
        phases.failure_phase = "shape"
        phases.failure_message = (
            f"row count mismatch: expected {expected_row_count}, got {phases.actual_row_count}"
        )
    elif expected_col_count is not None and phases.actual_col_count != expected_col_count:
        phases.failure_phase = "shape"
        phases.failure_message = (
            f"column count mismatch: expected {expected_col_count}, got {phases.actual_col_count}"
        )
    else:
        phases.shape_ok = True

    # --- Step type check ---
    phases.step_types_ok = phases.actual_step_types == expected_step_types

    phases.elapsed_ms = (time.monotonic() - t0) * 1000
    return _build_result(q_id, demo_case, query, expected_step_types, expected_outcome,
                          expected_row_count, expected_col_count, phases)


def _build_result(
    q_id: str,
    demo_case: str,
    query: str,
    expected_step_types: list[str],
    expected_outcome: ExpectedOutcome,
    expected_row_count: int | None,
    expected_col_count: int | None,
    phases: PhaseResult,
) -> QueryResult:
    overall_ok = _is_overall_ok(expected_outcome, phases)
    return QueryResult(
        query_id=q_id,
        demo_case=demo_case,
        query=query,
        expected_step_types=expected_step_types,
        expected_outcome=expected_outcome,
        expected_row_count=expected_row_count,
        expected_col_count=expected_col_count,
        phases=phases,
        overall_ok=overall_ok,
    )


def _is_overall_ok(expected_outcome: ExpectedOutcome, phases: PhaseResult) -> bool:
    """Decide if a query passed based on the expected outcome type.

    - success: all phases must pass (retrieval, planner, validation, execution, shape)
    - validation_error: planner must succeed and validator must reject (validation_ok=False)
    - clarification: planner must return clarification (clarification=True)
    """
    if expected_outcome == "validation_error":
        # Planner should have generated steps that fail validation.
        # If planner itself fails, that is also acceptable (e.g. column-not-found hint).
        return phases.failure_phase in ("validation", "planning") and not phases.validation_ok
    if expected_outcome == "clarification":
        return phases.clarification
    # Default: success
    return (
        phases.retrieval_ok
        and phases.planner_ok
        and phases.validation_ok
        and phases.execution_ok
        and phases.shape_ok
        and phases.step_types_ok
    )


# ---------------------------------------------------------------------------
# Eval runner
# ---------------------------------------------------------------------------

async def run_eval(method: str, dataset_path: Path) -> EvalReport:
    queries = _load_queries()
    dataset_bytes = _load_dataset(dataset_path)

    # For keyword retrieval, pre-load docs so each query doesn't reload from disk.
    docs: list[dict] | None = None
    if method == "keyword":
        docs = rag_service.load_docs()

    if method == "pgvector":
        from app.core import database  # noqa: PLC0415
        await database.connect()

    results: list[QueryResult] = []
    try:
        for q in queries:
            print(f"  [{q['id']}] {q['query'][:60]}...")
            result = await _eval_query(q, dataset_bytes, method, docs)
            icon = "OK" if result.overall_ok else "FAIL"
            print(f"         → {icon}  (phase failure: {result.phases.failure_phase or '—'})")
            results.append(result)
    finally:
        if method == "pgvector":
            from app.core import database  # noqa: PLC0415
            await database.disconnect()

    return EvalReport(
        method=method,
        dataset=str(dataset_path),
        total_queries=len(results),
        results=results,
    )


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

def _print_report(report: EvalReport) -> None:
    sep = "─" * 68
    c = report.counts
    n = report.total_queries

    print(f"\n{sep}")
    print(f"  Workflow Eval — method: {report.method}  dataset: {report.dataset}")
    print(sep)
    print(f"  {'Metric':<30} {'Pass':>6} / {'Total':>5}   {'Rate':>7}")
    print(f"  {'-'*30} {'-'*6}   {'-'*5}   {'-'*7}")

    def _row(label: str, val: int) -> None:
        print(f"  {label:<30} {val:>6} / {n:>5}   {val/n:>7.2%}")

    _row("planner_ok", c["planner_ok"])
    _row("validation_ok", c["validation_ok"])
    _row("execution_ok", c["execution_ok"])
    _row("step_types_ok", c["step_types_ok"])
    _row("shape_ok", c["shape_ok"])
    print(f"  {sep}")
    _row("overall_ok", c["overall_ok"])
    print(sep)

    failures = report.failures
    if not failures:
        print("  All queries passed. [OK]")
    else:
        print(f"\n  Failure cases ({len(failures)}):")
        for r in failures:
            print(f"\n  [{r.query_id}/{r.demo_case}] {r.query}")
            print(f"    expected outcome : {r.expected_outcome}")
            print(f"    failure phase    : {r.phases.failure_phase or '—'}")
            print(f"    failure message  : {r.phases.failure_message or '—'}")
            print(f"    expected steps   : {r.expected_step_types}")
            print(f"    actual steps     : {r.phases.actual_step_types}")
            if r.expected_row_count is not None:
                print(f"    expected rows    : {r.expected_row_count}  actual: {r.phases.actual_row_count}")
            if r.expected_col_count is not None:
                print(f"    expected cols    : {r.expected_col_count}  actual: {r.phases.actual_col_count}")
            print(f"    elapsed_ms       : {r.phases.elapsed_ms:.0f}")
    print(sep)


def _build_json_output(report: EvalReport) -> dict:
    c = report.counts
    n = report.total_queries

    def _phase_dict(p: PhaseResult) -> dict:
        return {
            "retrieval_ok": p.retrieval_ok,
            "planner_ok": p.planner_ok,
            "clarification": p.clarification,
            "validation_ok": p.validation_ok,
            "execution_ok": p.execution_ok,
            "step_types_ok": p.step_types_ok,
            "shape_ok": p.shape_ok,
            "actual_step_types": p.actual_step_types,
            "actual_row_count": p.actual_row_count,
            "actual_col_count": p.actual_col_count,
            "failure_phase": p.failure_phase,
            "failure_message": p.failure_message,
            "elapsed_ms": round(p.elapsed_ms),
        }

    return {
        "method": report.method,
        "dataset": report.dataset,
        "total_queries": n,
        "summary": {
            "planner_ok": f"{c['planner_ok']}/{n}",
            "validation_ok": f"{c['validation_ok']}/{n}",
            "execution_ok": f"{c['execution_ok']}/{n}",
            "step_types_ok": f"{c['step_types_ok']}/{n}",
            "shape_ok": f"{c['shape_ok']}/{n}",
            "overall_ok": f"{c['overall_ok']}/{n}",
        },
        "failures": [
            {
                "query_id": r.query_id,
                "demo_case": r.demo_case,
                "query": r.query,
                "failure_phase": r.phases.failure_phase,
                "failure_message": r.phases.failure_message,
                "expected_step_types": r.expected_step_types,
                "actual_step_types": r.phases.actual_step_types,
            }
            for r in report.failures
        ],
        "results": [
            {
                "query_id": r.query_id,
                "demo_case": r.demo_case,
                "query": r.query,
                "expected_outcome": r.expected_outcome,
                "overall_ok": r.overall_ok,
                "phases": _phase_dict(r.phases),
            }
            for r in report.results
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(method: str, dataset: str, output: str | None) -> None:
    dataset_path = Path(dataset)
    print(f"Running workflow eval (method={method}, dataset={dataset_path})...")
    report = await run_eval(method, dataset_path)
    _print_report(report)

    if output:
        out_path = Path(output)
        out_path.write_text(
            json.dumps(_build_json_output(report), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nJSON report saved to: {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate full workflow pipeline quality against the demo dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--method",
        choices=["keyword", "pgvector"],
        default="keyword",
        help="RAG retrieval method to use (default: keyword).",
    )
    parser.add_argument(
        "--dataset",
        default=str(_DEFAULT_DATASET),
        help=(
            "Path to the demo CSV dataset "
            f"(default: {_DEFAULT_DATASET})."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write a JSON report file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.method, args.dataset, args.output))
