"""Retrieval evaluation script for DataCopilot RAG.

Runs keyword and/or pgvector retrieval against a fixed set of annotated
evaluation queries and reports:
  - top_1_accuracy  : fraction of queries where the top-1 result matches an expected doc
  - recall_at_k     : fraction of queries where any expected doc appears in top-k results
  - failure cases   : queries where retrieval missed all expected docs

Usage (from the backend/ directory):

    # Keyword only (no database required)
    python scripts/eval_retrieval.py --method keyword

    # pgvector only (requires DATABASE_URL + LLM_API_KEY)
    python scripts/eval_retrieval.py --method pgvector

    # Both methods side-by-side comparison
    python scripts/eval_retrieval.py --method both

    # Control how many results are retrieved per query (default: 3)
    python scripts/eval_retrieval.py --method both --top-k 5

    # Save JSON report to file
    python scripts/eval_retrieval.py --method both --output report.json

Environment variables (read from .env or shell):
    DATABASE_URL    required for pgvector method
    LLM_API_KEY     required for pgvector method (OpenAI embedding calls)
    LLM_BASE_URL    optional; defaults to https://api.openai.com/v1
    EMBEDDING_MODEL optional; defaults to text-embedding-3-small
"""
import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add backend root to sys.path so app.* imports work when the
# script is run directly from any working directory.
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.rag_service import load_docs  # noqa: E402
from app.services.retriever import KeywordRetriever, PgvectorRetriever  # noqa: E402

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("eval_retrieval")

_QUERIES_FILE = _SCRIPTS_DIR / "eval_retrieval_queries.json"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    query_id: str
    query: str
    expected: list[str]
    retrieved: list[str]  # source_paths in rank order
    scores: dict[str, float]
    top_1_hit: bool
    recall_hit: bool  # any expected doc in top-k


@dataclass
class EvalReport:
    method: str
    top_k: int
    total_queries: int
    top_1_hits: int
    recall_hits: int
    top_1_accuracy: float
    recall_at_k: float
    results: list[QueryResult] = field(default_factory=list)

    @property
    def failures(self) -> list[QueryResult]:
        return [r for r in self.results if not r.recall_hit]


# ---------------------------------------------------------------------------
# Evaluation runner
# ---------------------------------------------------------------------------

def _load_queries() -> list[dict]:
    try:
        return json.loads(_QUERIES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Evaluation queries file not found: %s", _QUERIES_FILE)
        sys.exit(1)


async def run_eval(method: str, top_k: int) -> EvalReport:
    queries = _load_queries()

    if method not in ("keyword", "pgvector"):
        raise ValueError(f"Unknown method: {method!r}")

    results: list[QueryResult] = []

    try:
        if method == "keyword":
            docs = load_docs()
            retriever: KeywordRetriever | PgvectorRetriever = KeywordRetriever(docs=docs)
        else:
            from app.core import database  # noqa: PLC0415
            await database.connect()
            retriever = PgvectorRetriever()

        for q in queries:
            query_text: str = q["query"]
            expected: list[str] = q.get("expected_source_paths", [])

            retrieved_docs, debug = await retriever.retrieve(query_text, top_k=top_k)
            retrieved_paths = [doc.source_path for doc in retrieved_docs]
            scores = {doc.source_path: doc.score for doc in retrieved_docs}

            top_1_hit = bool(retrieved_paths) and retrieved_paths[0] in expected
            recall_hit = any(p in expected for p in retrieved_paths)

            results.append(QueryResult(
                query_id=q["id"],
                query=query_text,
                expected=expected,
                retrieved=retrieved_paths,
                scores=scores,
                top_1_hit=top_1_hit,
                recall_hit=recall_hit,
            ))
    finally:
        if method == "pgvector":
            from app.core import database  # noqa: PLC0415
            await database.disconnect()

    total = len(results)
    top_1_hits = sum(1 for r in results if r.top_1_hit)
    recall_hits = sum(1 for r in results if r.recall_hit)

    return EvalReport(
        method=method,
        top_k=top_k,
        total_queries=total,
        top_1_hits=top_1_hits,
        recall_hits=recall_hits,
        top_1_accuracy=round(top_1_hits / total, 4) if total else 0.0,
        recall_at_k=round(recall_hits / total, 4) if total else 0.0,
        results=results,
    )


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

def _print_report(report: EvalReport) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  Method : {report.method}")
    print(f"  top_k  : {report.top_k}")
    print(f"  Queries: {report.total_queries}")
    print(sep)
    print(f"  top_1_accuracy  : {report.top_1_hits}/{report.total_queries} = {report.top_1_accuracy:.2%}")
    print(f"  recall_at_{report.top_k}    : {report.recall_hits}/{report.total_queries} = {report.recall_at_k:.2%}")
    print(sep)

    failures = report.failures
    if not failures:
        print("  All queries retrieved at least one expected doc. [OK]")
    else:
        print(f"  Failure cases ({len(failures)} queries missed all expected docs):")
        for f in failures:
            print(f"\n  [{f.query_id}] {f.query}")
            print(f"    expected : {f.expected}")
            print(f"    retrieved: {f.retrieved}")
            score_str = ", ".join(f"{p}={s:.4f}" for p, s in f.scores.items())
            print(f"    scores   : {score_str}")
    print(sep)


def _print_comparison(kw: EvalReport, pg: EvalReport) -> None:
    sep = "═" * 60
    print(f"\n{sep}")
    print("  Comparison: keyword vs pgvector")
    print(sep)
    print(f"  {'Metric':<25} {'keyword':>10} {'pgvector':>10}")
    print(f"  {'-'*25} {'-'*10} {'-'*10}")
    print(f"  {'top_1_accuracy':<25} {kw.top_1_accuracy:>10.2%} {pg.top_1_accuracy:>10.2%}")
    print(f"  {'recall_at_' + str(kw.top_k):<25} {kw.recall_at_k:>10.2%} {pg.recall_at_k:>10.2%}")
    print(f"  {'queries total':<25} {kw.total_queries:>10} {pg.total_queries:>10}")
    print(f"  {'failures':<25} {len(kw.failures):>10} {len(pg.failures):>10}")
    print(sep)

    # Per-query diff: highlight where both methods produced results but disagree.
    # Default to r.recall_hit so queries with no matching pgvector result are
    # excluded rather than spuriously flagged.
    diffs = [
        r for r in kw.results
        if r.recall_hit != next((p.recall_hit for p in pg.results if p.query_id == r.query_id), r.recall_hit)
    ]
    if diffs:
        print("\n  Per-query disagreements (recall_at_k differs between methods):")
        for kw_r in diffs:
            pg_r = next((p for p in pg.results if p.query_id == kw_r.query_id), None)
            if pg_r is None:
                continue
            kw_icon = "[Y]" if kw_r.recall_hit else "[N]"
            pg_icon = "[Y]" if pg_r.recall_hit else "[N]"
            print(f"\n  [{kw_r.query_id}] {kw_r.query}")
            print(f"    expected  : {kw_r.expected}")
            print(f"    keyword   : {kw_icon} {kw_r.retrieved}")
            print(f"    pgvector  : {pg_icon} {pg_r.retrieved}")
        print(sep)


def _build_json_output(reports: list[EvalReport]) -> dict:
    def _report_dict(r: EvalReport) -> dict:
        return {
            "method": r.method,
            "top_k": r.top_k,
            "total_queries": r.total_queries,
            "top_1_accuracy": r.top_1_accuracy,
            f"recall_at_{r.top_k}": r.recall_at_k,
            "top_1_hits": r.top_1_hits,
            "recall_hits": r.recall_hits,
            "failures": [
                {
                    "query_id": f.query_id,
                    "query": f.query,
                    "expected": f.expected,
                    "retrieved": f.retrieved,
                    "scores": f.scores,
                }
                for f in r.failures
            ],
            "results": [
                {
                    "query_id": res.query_id,
                    "query": res.query,
                    "expected": res.expected,
                    "retrieved": res.retrieved,
                    "scores": res.scores,
                    "top_1_hit": res.top_1_hit,
                    "recall_hit": res.recall_hit,
                }
                for res in r.results
            ],
        }

    return {"reports": [_report_dict(r) for r in reports]}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(method: str, top_k: int, output: str | None) -> None:
    reports: list[EvalReport] = []

    if method in ("keyword", "both"):
        print(f"Running keyword retrieval eval (top_k={top_k})...")
        kw_report = await run_eval("keyword", top_k)
        reports.append(kw_report)
        _print_report(kw_report)

    if method in ("pgvector", "both"):
        print(f"Running pgvector retrieval eval (top_k={top_k})...")
        pg_report = await run_eval("pgvector", top_k)
        reports.append(pg_report)
        _print_report(pg_report)

    if method == "both" and len(reports) == 2:
        _print_comparison(reports[0], reports[1])

    if output:
        out_path = Path(output)
        out_path.write_text(json.dumps(_build_json_output(reports), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nJSON report saved to: {out_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate keyword vs pgvector retrieval quality.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--method",
        choices=["keyword", "pgvector", "both"],
        default="keyword",
        help="Retrieval method(s) to evaluate (default: keyword).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of docs to retrieve per query (default: 3).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write a JSON report file.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.method, args.top_k, args.output))
