"""Workflow evaluation script for DataCopilot.

Evaluates the RAG → planner → validator → executor pipeline against one or
more dataset contracts. Reports include retrieval method, LLM model, dataset
hash, git commit sha, strict/tolerant mode, and regression candidates.

Usage:
    python scripts/eval_workflow.py
    python scripts/eval_workflow.py --method pgvector
    python scripts/eval_workflow.py --mode tolerant
    python scripts/eval_workflow.py --contract scripts/eval_contract.json
    python scripts/eval_workflow.py --output reports/eval.json
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

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
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("eval_workflow")

_DEFAULT_QUERIES_FILE = _SCRIPTS_DIR / "eval_workflow_queries.json"
_DEFAULT_DATASET = _BACKEND_DIR / "sample_data" / "orders.csv"
if not _DEFAULT_DATASET.exists():
    _DEFAULT_DATASET = _REPO_DIR / "sample_data" / "orders.csv"

ExpectedOutcome = Literal["success", "validation_error", "clarification"]
EvalMode = Literal["strict", "tolerant"]


@dataclass
class DatasetContract:
    id: str
    path: Path
    queries: list[dict]


@dataclass
class PhaseResult:
    retrieval_ok: bool = False
    planner_ok: bool = False
    clarification: bool = False
    validation_ok: bool = False
    execution_ok: bool = False
    step_types_ok: bool = False
    shape_ok: bool = False
    actual_step_types: list[str] = field(default_factory=list)
    actual_row_count: int | None = None
    actual_col_count: int | None = None
    failure_phase: str | None = None
    failure_message: str = ""
    elapsed_ms: float = 0.0


@dataclass
class QueryResult:
    dataset_id: str
    query_id: str
    demo_case: str
    query: str
    expected_step_types: list[str]
    expected_outcome: ExpectedOutcome
    expected_row_count: int | None
    expected_col_count: int | None
    phases: PhaseResult
    overall_ok: bool
    regression_candidate: bool


@dataclass
class DatasetReport:
    dataset_id: str
    dataset: str
    dataset_hash: str
    total_queries: int
    results: list[QueryResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "retrieval_ok": sum(1 for r in self.results if r.phases.retrieval_ok),
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


@dataclass
class EvalReport:
    method: str
    mode: EvalMode
    llm_model: str
    git_commit_sha: str
    generated_at: str
    datasets: list[DatasetReport] = field(default_factory=list)

    @property
    def total_queries(self) -> int:
        return sum(d.total_queries for d in self.datasets)

    @property
    def counts(self) -> dict[str, int]:
        keys = [
            "retrieval_ok",
            "planner_ok",
            "validation_ok",
            "execution_ok",
            "step_types_ok",
            "shape_ok",
            "overall_ok",
        ]
        return {
            key: sum(dataset.counts[key] for dataset in self.datasets)
            for key in keys
        }

    @property
    def failures(self) -> list[QueryResult]:
        return [result for dataset in self.datasets for result in dataset.failures]


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("File not found: %s", path)
        sys.exit(1)


def _load_queries(path: Path) -> list[dict]:
    data = _load_json(path)
    if not isinstance(data, list):
        raise SystemExit(f"Query file must be a JSON array: {path}")
    return data


def _load_contracts(contract_path: Path | None, dataset_path: Path, queries_path: Path) -> list[DatasetContract]:
    if contract_path is None:
        return [
            DatasetContract(
                id=dataset_path.stem,
                path=dataset_path,
                queries=_load_queries(queries_path),
            )
        ]

    data = _load_json(contract_path)
    if not isinstance(data, dict) or not isinstance(data.get("datasets"), list):
        raise SystemExit("Contract must be an object with a 'datasets' array.")

    contracts: list[DatasetContract] = []
    for idx, item in enumerate(data["datasets"]):
        if not isinstance(item, dict):
            raise SystemExit(f"Dataset contract item #{idx} must be an object.")
        if "path" not in item:
            raise SystemExit(f"Dataset contract item #{idx} is missing required field 'path'.")

        base = contract_path.parent
        path = Path(item["path"])
        if not path.is_absolute():
            path = base / path

        if "queries" in item:
            queries = item["queries"]
        elif "queries_path" in item:
            q_path = Path(item["queries_path"])
            if not q_path.is_absolute():
                q_path = base / q_path
            queries = _load_queries(q_path)
        else:
            raise SystemExit(f"Dataset contract '{item.get('id', path.stem)}' lacks queries or queries_path.")

        contracts.append(DatasetContract(
            id=item.get("id", path.stem),
            path=path,
            queries=queries,
        ))

    return contracts


def _load_dataset(path: Path) -> bytes:
    if not path.exists():
        logger.error("Dataset not found: %s", path)
        sys.exit(1)
    return path.read_bytes()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


async def _eval_query(
    *,
    dataset_id: str,
    dataset_filename: str,
    query_spec: dict,
    dataset_bytes: bytes,
    method: str,
    mode: EvalMode,
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

    dataset_profile = profile(dataset_bytes, dataset_filename)
    column_names = [c.name for c in dataset_profile.columns]

    try:
        rag_ctx = await rag_service.build_context(
            query=query,
            dataset_profile=dataset_profile,
            top_k=query_spec.get("rag_top_k", 3),
            docs=docs,
        )
        phases.retrieval_ok = bool(rag_ctx.retrieved_docs)
    except Exception as exc:
        phases.failure_phase = "retrieval"
        phases.failure_message = str(exc)
        return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                             expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)

    planned_steps: list[WorkflowStep] = []
    try:
        planned_steps = workflow_planner.plan(query, rag_ctx)
        phases.planner_ok = True
        phases.actual_step_types = [s.type for s in planned_steps]
    except ClarificationNeeded as exc:
        phases.clarification = True
        phases.failure_phase = "planning"
        phases.failure_message = f"clarification: {exc}"
        return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                             expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)
    except PlannerError as exc:
        phases.failure_phase = "planning"
        phases.failure_message = str(exc)
        return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                             expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)

    try:
        validator_service.validate(planned_steps, column_names)
        phases.validation_ok = True
    except WorkflowValidationError as exc:
        phases.failure_phase = "validation"
        phases.failure_message = str(exc)
        return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                             expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)

    try:
        exec_result = executor_service.execute(planned_steps, dataset_bytes)
        phases.execution_ok = True
        phases.actual_row_count = exec_result.row_count
        phases.actual_col_count = exec_result.column_count
    except ExecutionError as exc:
        phases.failure_phase = "execution"
        phases.failure_message = str(exc)
        return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                             expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)

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

    phases.step_types_ok = phases.actual_step_types == expected_step_types
    return _build_result(dataset_id, q_id, demo_case, query, expected_step_types,
                         expected_outcome, expected_row_count, expected_col_count, phases, mode, t0)


def _build_result(
    dataset_id: str,
    q_id: str,
    demo_case: str,
    query: str,
    expected_step_types: list[str],
    expected_outcome: ExpectedOutcome,
    expected_row_count: int | None,
    expected_col_count: int | None,
    phases: PhaseResult,
    mode: EvalMode,
    t0: float,
) -> QueryResult:
    phases.elapsed_ms = (time.monotonic() - t0) * 1000
    overall_ok = _is_overall_ok(expected_outcome, phases, mode)
    return QueryResult(
        dataset_id=dataset_id,
        query_id=q_id,
        demo_case=demo_case,
        query=query,
        expected_step_types=expected_step_types,
        expected_outcome=expected_outcome,
        expected_row_count=expected_row_count,
        expected_col_count=expected_col_count,
        phases=phases,
        overall_ok=overall_ok,
        regression_candidate=not overall_ok,
    )


def _is_overall_ok(expected_outcome: ExpectedOutcome, phases: PhaseResult, mode: EvalMode) -> bool:
    if expected_outcome == "validation_error":
        return phases.failure_phase in ("validation", "planning") and not phases.validation_ok
    if expected_outcome == "clarification":
        return phases.clarification

    required = (
        phases.retrieval_ok
        and phases.planner_ok
        and phases.validation_ok
        and phases.execution_ok
        and phases.shape_ok
    )
    if mode == "strict":
        return required and phases.step_types_ok
    return required


async def run_eval(
    *,
    method: str,
    mode: EvalMode,
    contracts: list[DatasetContract],
) -> EvalReport:
    docs: list[dict] | None = rag_service.load_docs() if method == "keyword" else None

    if method == "pgvector":
        from app.core import database  # noqa: PLC0415
        await database.connect()

    dataset_reports: list[DatasetReport] = []
    try:
        for contract in contracts:
            dataset_bytes = _load_dataset(contract.path)
            print(f"\nDataset [{contract.id}] {contract.path}")
            results: list[QueryResult] = []
            for q in contract.queries:
                print(f"  [{q['id']}] {q['query'][:60]}...")
                result = await _eval_query(
                    dataset_id=contract.id,
                    dataset_filename=contract.path.name,
                    query_spec=q,
                    dataset_bytes=dataset_bytes,
                    method=method,
                    mode=mode,
                    docs=docs,
                )
                icon = "OK" if result.overall_ok else "FAIL"
                print(f"         -> {icon}  (phase failure: {result.phases.failure_phase or '-'})")
                results.append(result)

            dataset_reports.append(DatasetReport(
                dataset_id=contract.id,
                dataset=str(contract.path),
                dataset_hash=_sha256(dataset_bytes),
                total_queries=len(results),
                results=results,
            ))
    finally:
        if method == "pgvector":
            from app.core import database  # noqa: PLC0415
            await database.disconnect()

    return EvalReport(
        method=method,
        mode=mode,
        llm_model=settings.llm_model,
        git_commit_sha=_git_commit_sha(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        datasets=dataset_reports,
    )


def _print_report(report: EvalReport) -> None:
    sep = "-" * 76
    c = report.counts
    n = report.total_queries
    print(f"\n{sep}")
    print(
        f"Workflow Eval - method: {report.method}  mode: {report.mode}  "
        f"model: {report.llm_model}"
    )
    print(f"git: {report.git_commit_sha}")
    print(sep)

    def _row(label: str, val: int) -> None:
        rate = val / n if n else 0
        print(f"  {label:<30} {val:>6} / {n:>5}   {rate:>7.2%}")

    for key in ("retrieval_ok", "planner_ok", "validation_ok", "execution_ok", "step_types_ok", "shape_ok"):
        _row(key, c[key])
    print(f"  {sep}")
    _row("overall_ok", c["overall_ok"])

    if report.failures:
        print(f"\nFailure cases / regression candidates ({len(report.failures)}):")
        for r in report.failures:
            print(f"\n  [{r.dataset_id}/{r.query_id}/{r.demo_case}] {r.query}")
            print(f"    expected outcome : {r.expected_outcome}")
            print(f"    failure phase    : {r.phases.failure_phase or '-'}")
            print(f"    failure message  : {r.phases.failure_message or '-'}")
            print(f"    expected steps   : {r.expected_step_types}")
            print(f"    actual steps     : {r.phases.actual_step_types}")
    else:
        print("\nAll queries passed. [OK]")
    print(sep)


def _build_json_output(report: EvalReport) -> dict:
    output = asdict(report)
    output["total_queries"] = report.total_queries
    output["summary"] = {
        key: f"{value}/{report.total_queries}"
        for key, value in report.counts.items()
    }
    output["failures"] = [
        {
            "dataset_id": r.dataset_id,
            "query_id": r.query_id,
            "demo_case": r.demo_case,
            "query": r.query,
            "failure_phase": r.phases.failure_phase,
            "failure_message": r.phases.failure_message,
            "expected_step_types": r.expected_step_types,
            "actual_step_types": r.phases.actual_step_types,
            "regression_candidate": r.regression_candidate,
        }
        for r in report.failures
    ]
    return output


def _default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _REPO_DIR / "reports" / f"workflow_eval_{stamp}.json"


async def main(args: argparse.Namespace) -> None:
    contracts = _load_contracts(args.contract, Path(args.dataset), Path(args.queries))
    print(f"Running workflow eval (method={args.method}, mode={args.mode}, datasets={len(contracts)})...")
    report = await run_eval(method=args.method, mode=args.mode, contracts=contracts)
    _print_report(report)

    out_path = Path(args.output) if args.output else _default_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_build_json_output(report), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON report saved to: {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate workflow pipeline quality against dataset contracts.",
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
        "--mode",
        choices=["strict", "tolerant"],
        default="strict",
        help="strict checks exact step types; tolerant checks validation/execution/output shape.",
    )
    parser.add_argument(
        "--dataset",
        default=str(_DEFAULT_DATASET),
        help=f"CSV path for legacy single-dataset mode (default: {_DEFAULT_DATASET}).",
    )
    parser.add_argument(
        "--queries",
        default=str(_DEFAULT_QUERIES_FILE),
        help=f"Query JSON path for legacy single-dataset mode (default: {_DEFAULT_QUERIES_FILE}).",
    )
    parser.add_argument(
        "--contract",
        default=None,
        type=Path,
        help="Optional multi-dataset contract JSON path.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional report path. Defaults to reports/workflow_eval_<timestamp>.json.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_parse_args()))
