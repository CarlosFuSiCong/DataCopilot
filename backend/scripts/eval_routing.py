"""Routing eval script for DataCopilot.

Evaluates the query classifier (RouteDecision) against a golden query set.
Reports route accuracy, query-type accuracy, tool selection accuracy, and a
per-query-type breakdown of deterministic vs LLM-planner routes.

Usage:
    python scripts/eval_routing.py
    python scripts/eval_routing.py --queries scripts/eval_route_decision.json
    python scripts/eval_routing.py --output reports/routing_eval.json
    python scripts/eval_routing.py --deterministic
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
_REPO_DIR = _BACKEND_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.workflow.planning.query_classifier import classify, classify_deterministic  # noqa: E402
from app.workflow.planning.route_decision import Route, QueryType  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("eval_routing")

_DEFAULT_GOLDEN_FILE = _SCRIPTS_DIR / "eval_route_decision.json"


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class RouteResult:
    query_id: str
    query: str
    expected_route: str
    expected_query_type: str
    expected_tool: str | None
    actual_route: str
    actual_query_type: str
    actual_tool: str | None
    actual_confidence: float
    actual_evidence: list[str]
    route_ok: bool
    query_type_ok: bool
    tool_ok: bool
    used_llm: bool
    elapsed_ms: float
    notes: str = ""


@dataclass
class RoutingMetrics:
    total: int = 0
    route_correct: int = 0
    query_type_correct: int = 0
    tool_correct: int = 0
    tool_eval_count: int = 0  # queries that had an expected_tool value
    # Route distribution
    deterministic_tool_count: int = 0
    ask_mode_count: int = 0
    llm_planner_count: int = 0
    clarification_count: int = 0
    unsupported_count: int = 0
    # LLM usage
    llm_call_count: int = 0
    # Latency
    total_elapsed_ms: float = 0.0
    # Per query-type counts: query_type -> {total, route_correct}
    query_type_stats: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def route_accuracy(self) -> float:
        return self.route_correct / self.total if self.total else 0.0

    @property
    def query_type_accuracy(self) -> float:
        return self.query_type_correct / self.total if self.total else 0.0

    @property
    def tool_selection_accuracy(self) -> float:
        return self.tool_correct / self.tool_eval_count if self.tool_eval_count else 0.0

    @property
    def deterministic_route_rate(self) -> float:
        return self.deterministic_tool_count / self.total if self.total else 0.0

    @property
    def ask_mode_rate(self) -> float:
        return self.ask_mode_count / self.total if self.total else 0.0

    @property
    def llm_planner_rate(self) -> float:
        return self.llm_planner_count / self.total if self.total else 0.0

    @property
    def clarification_rate(self) -> float:
        return self.clarification_count / self.total if self.total else 0.0

    @property
    def unsupported_rate(self) -> float:
        return self.unsupported_count / self.total if self.total else 0.0

    @property
    def llm_call_rate(self) -> float:
        return self.llm_call_count / self.total if self.total else 0.0

    @property
    def average_latency_ms(self) -> float:
        return self.total_elapsed_ms / self.total if self.total else 0.0


@dataclass
class RoutingReport:
    method: str
    llm_model: str
    git_commit_sha: str
    generated_at: str
    metrics: RoutingMetrics = field(default_factory=RoutingMetrics)
    results: list[RouteResult] = field(default_factory=list)

    @property
    def failures(self) -> list[RouteResult]:
        return [r for r in self.results if not r.route_ok]


# ---------------------------------------------------------------------------
# Core eval logic
# ---------------------------------------------------------------------------


def _eval_query(query_spec: dict, *, use_deterministic: bool) -> RouteResult:
    q_id: str = query_spec["id"]
    query: str = query_spec["query"]
    expected_route: str = query_spec["expected_route"]
    expected_query_type: str = query_spec["expected_query_type"]
    expected_tool: str | None = query_spec.get("expected_tool")

    t0 = time.monotonic()
    if use_deterministic:
        rd = classify_deterministic(query)
        used_llm = False
    else:
        rd = classify(query)
        used_llm = bool(settings.llm_api_key)
    elapsed_ms = (time.monotonic() - t0) * 1000

    route_ok = rd.route == expected_route
    query_type_ok = rd.query_type == expected_query_type
    tool_ok = (
        rd.selected_tool == expected_tool
        if expected_tool is not None
        else True
    )

    return RouteResult(
        query_id=q_id,
        query=query,
        expected_route=expected_route,
        expected_query_type=expected_query_type,
        expected_tool=expected_tool,
        actual_route=rd.route,
        actual_query_type=rd.query_type,
        actual_tool=rd.selected_tool,
        actual_confidence=rd.confidence,
        actual_evidence=rd.evidence,
        route_ok=route_ok,
        query_type_ok=query_type_ok,
        tool_ok=tool_ok,
        used_llm=used_llm,
        elapsed_ms=elapsed_ms,
        notes=query_spec.get("notes", ""),
    )


def _accumulate_metrics(metrics: RoutingMetrics, result: RouteResult, has_expected_tool: bool) -> None:
    metrics.total += 1
    if result.route_ok:
        metrics.route_correct += 1
    if result.query_type_ok:
        metrics.query_type_correct += 1
    if has_expected_tool:
        metrics.tool_eval_count += 1
        if result.tool_ok:
            metrics.tool_correct += 1

    route = result.actual_route
    if route == "deterministic_tool":
        metrics.deterministic_tool_count += 1
    elif route == "ask_mode":
        metrics.ask_mode_count += 1
    elif route == "llm_planner":
        metrics.llm_planner_count += 1
    elif route == "clarification":
        metrics.clarification_count += 1
    elif route == "unsupported":
        metrics.unsupported_count += 1

    if result.used_llm:
        metrics.llm_call_count += 1
    metrics.total_elapsed_ms += result.elapsed_ms

    qt = result.expected_query_type
    if qt not in metrics.query_type_stats:
        metrics.query_type_stats[qt] = {"total": 0, "route_correct": 0, "query_type_correct": 0}
    metrics.query_type_stats[qt]["total"] += 1
    if result.route_ok:
        metrics.query_type_stats[qt]["route_correct"] += 1
    if result.query_type_ok:
        metrics.query_type_stats[qt]["query_type_correct"] += 1


def run_routing_eval(
    golden_queries: list[dict],
    *,
    use_deterministic: bool = False,
) -> RoutingReport:
    method = "deterministic" if use_deterministic else ("llm" if settings.llm_api_key else "deterministic_fallback")
    metrics = RoutingMetrics()
    results: list[RouteResult] = []

    for q in golden_queries:
        has_expected_tool = q.get("expected_tool") is not None
        result = _eval_query(q, use_deterministic=use_deterministic)
        _accumulate_metrics(metrics, result, has_expected_tool)
        results.append(result)

    return RoutingReport(
        method=method,
        llm_model=settings.llm_model,
        git_commit_sha=_git_commit_sha(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        metrics=metrics,
        results=results,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(report: RoutingReport) -> None:
    sep = "-" * 76
    m = report.metrics
    n = m.total
    print(f"\n{sep}")
    print(f"Routing Eval - method: {report.method}  model: {report.llm_model}")
    print(f"git: {report.git_commit_sha}  queries: {n}")
    print(sep)

    def _row(label: str, val: float | int, *, is_rate: bool = True) -> None:
        if is_rate:
            print(f"  {label:<40} {val:>7.2%}")
        else:
            print(f"  {label:<40} {val:>7.1f} ms")

    print("\nAccuracy:")
    _row("route_accuracy", m.route_accuracy)
    _row("query_type_accuracy", m.query_type_accuracy)
    _row("tool_selection_accuracy (expected-tool cases)", m.tool_selection_accuracy)

    print("\nRoute distribution (actual):")
    _row("deterministic_route_rate", m.deterministic_route_rate)
    _row("ask_mode_rate", m.ask_mode_rate)
    _row("llm_planner_rate", m.llm_planner_rate)
    _row("clarification_rate", m.clarification_rate)
    _row("unsupported_rate", m.unsupported_rate)
    _row("llm_call_rate", m.llm_call_rate)

    print("\nLatency:")
    _row("average_latency_ms (all queries)", m.average_latency_ms, is_rate=False)

    print("\nPer query-type breakdown:")
    header = f"  {'query_type':<28}  total  route_ok  type_ok"
    print(header)
    for qt, stats in sorted(m.query_type_stats.items()):
        t = stats["total"]
        r = stats["route_correct"]
        ty = stats["query_type_correct"]
        print(f"  {qt:<28}  {t:>5}  {r:>7}  {ty:>7}")

    if report.failures:
        print(f"\nRoute mismatches ({len(report.failures)}):")
        for r in report.failures:
            print(f"\n  [{r.query_id}] {r.query}")
            print(f"    expected route     : {r.expected_route}")
            print(f"    actual route       : {r.actual_route}")
            print(f"    expected type      : {r.expected_query_type}")
            print(f"    actual type        : {r.actual_query_type}")
            print(f"    confidence         : {r.actual_confidence:.2f}")
            print(f"    evidence           : {r.actual_evidence}")
    else:
        print("\nAll routing decisions matched. [OK]")
    print(sep)


def _build_json_output(report: RoutingReport) -> dict:
    m = report.metrics
    tool_count = m.tool_eval_count

    return {
        "method": report.method,
        "llm_model": report.llm_model,
        "git_commit_sha": report.git_commit_sha,
        "generated_at": report.generated_at,
        "total_queries": m.total,
        "summary": {
            "route_accuracy": f"{m.route_correct}/{m.total}",
            "query_type_accuracy": f"{m.query_type_correct}/{m.total}",
            "tool_selection_accuracy": (
                f"{m.tool_correct}/{tool_count}" if tool_count else "n/a"
            ),
        },
        "metrics": {
            "route_accuracy": round(m.route_accuracy, 4),
            "query_type_accuracy": round(m.query_type_accuracy, 4),
            "tool_selection_accuracy": round(m.tool_selection_accuracy, 4) if tool_count else None,
            "deterministic_route_rate": round(m.deterministic_route_rate, 4),
            "ask_mode_rate": round(m.ask_mode_rate, 4),
            "llm_planner_rate": round(m.llm_planner_rate, 4),
            "clarification_rate": round(m.clarification_rate, 4),
            "unsupported_rate": round(m.unsupported_rate, 4),
            "llm_call_rate": round(m.llm_call_rate, 4),
            "average_latency_ms": round(m.average_latency_ms, 2),
        },
        "query_type_breakdown": {
            qt: {
                "total": s["total"],
                "route_accuracy": round(s["route_correct"] / s["total"], 4),
                "query_type_accuracy": round(s["query_type_correct"] / s["total"], 4),
            }
            for qt, s in sorted(m.query_type_stats.items())
        },
        "failures": [
            {
                "query_id": r.query_id,
                "query": r.query,
                "expected_route": r.expected_route,
                "actual_route": r.actual_route,
                "expected_query_type": r.expected_query_type,
                "actual_query_type": r.actual_query_type,
                "expected_tool": r.expected_tool,
                "actual_tool": r.actual_tool,
                "confidence": r.actual_confidence,
                "evidence": r.actual_evidence,
            }
            for r in report.failures
        ],
        "results": [asdict(r) for r in report.results],
    }


def _build_markdown_report(report: RoutingReport) -> str:
    m = report.metrics
    n = m.total
    tool_count = m.tool_eval_count

    lines = [
        "# Routing Eval Report",
        "",
        f"- **method**: {report.method}",
        f"- **model**: {report.llm_model}",
        f"- **git**: `{report.git_commit_sha}`",
        f"- **generated**: {report.generated_at}",
        f"- **total queries**: {n}",
        "",
        "## Accuracy",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| route_accuracy | {m.route_accuracy:.2%} ({m.route_correct}/{n}) |",
        f"| query_type_accuracy | {m.query_type_accuracy:.2%} ({m.query_type_correct}/{n}) |",
        f"| tool_selection_accuracy | {f'{m.tool_selection_accuracy:.2%} ({m.tool_correct}/{tool_count})' if tool_count else 'n/a'} |",
        "",
        "## Route Distribution",
        "",
        f"| Route | Count | Rate |",
        f"|-------|-------|------|",
        f"| deterministic_tool | {m.deterministic_tool_count} | {m.deterministic_route_rate:.2%} |",
        f"| ask_mode | {m.ask_mode_count} | {m.ask_mode_rate:.2%} |",
        f"| llm_planner | {m.llm_planner_count} | {m.llm_planner_rate:.2%} |",
        f"| clarification | {m.clarification_count} | {m.clarification_rate:.2%} |",
        f"| unsupported | {m.unsupported_count} | {m.unsupported_rate:.2%} |",
        f"| llm_call_rate | {m.llm_call_count} | {m.llm_call_rate:.2%} |",
        "",
        "## Latency",
        "",
        f"- average_latency_ms: {m.average_latency_ms:.1f} ms",
        "",
        "## Per Query-Type Breakdown",
        "",
        "| query_type | total | route_accuracy | type_accuracy |",
        "|------------|-------|---------------|---------------|",
    ]
    for qt, s in sorted(m.query_type_stats.items()):
        t = s["total"]
        r_acc = s["route_correct"] / t if t else 0
        t_acc = s["query_type_correct"] / t if t else 0
        lines.append(f"| {qt} | {t} | {r_acc:.2%} | {t_acc:.2%} |")

    if report.failures:
        lines += [
            "",
            f"## Route Mismatches ({len(report.failures)})",
            "",
        ]
        for r in report.failures:
            lines += [
                f"### [{r.query_id}] {r.query}",
                f"- expected route: `{r.expected_route}` / actual: `{r.actual_route}`",
                f"- expected type: `{r.expected_query_type}` / actual: `{r.actual_query_type}`",
                f"- confidence: {r.actual_confidence:.2f}",
                f"- evidence: {r.actual_evidence}",
                "",
            ]
    else:
        lines += ["", "## Result", "", "All routing decisions matched. ✓", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _load_golden_queries(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Error: golden query file not found: {path}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, list):
        print("Error: golden query file must be a JSON array.", file=sys.stderr)
        sys.exit(1)
    return data


def _default_json_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return _REPO_DIR / "reports" / f"routing_eval_{stamp}.json"


def _default_md_output_path(json_path: Path) -> Path:
    return json_path.with_suffix(".md")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> None:
    golden_queries = _load_golden_queries(Path(args.queries))
    print(
        f"Running routing eval (method={'deterministic' if args.deterministic else 'auto'}, "
        f"queries={len(golden_queries)})..."
    )

    report = run_routing_eval(golden_queries, use_deterministic=args.deterministic)
    _print_report(report)

    out_path = Path(args.output) if args.output else _default_json_output_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(_build_json_output(report), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nJSON report saved to: {out_path}")

    if not args.no_markdown:
        md_path = _default_md_output_path(out_path)
        md_path.write_text(_build_markdown_report(report), encoding="utf-8")
        print(f"Markdown report saved to: {md_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate RouteDecision accuracy against a golden query set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--queries",
        default=str(_DEFAULT_GOLDEN_FILE),
        help=f"Golden query file (default: {_DEFAULT_GOLDEN_FILE}).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON report path. Defaults to reports/routing_eval_<timestamp>.json.",
    )
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Force deterministic classifier even when an LLM API key is present.",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip Markdown report generation.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main(_parse_args()))
