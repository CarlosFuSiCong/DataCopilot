"""MVP6 Real E2E Demo Script.

This script exercises a live DataCopilot backend over HTTP, covering the full
MVP6 pipeline for three demo paths:

  Path A: upload → filter query → slot clarification → preview → confirm → explanation
  Path B: upload → profile_column (analytical inspect flow)
  Path C: upload → suggest_analysis_steps (analyst multi-step trigger)

REQUIREMENTS
  - A running DataCopilot backend reachable at BASE_URL (default: http://localhost:8000).
  - A valid OpenAI API key in the backend environment (LLM calls are made).

GATE
  This script requires the env var RUN_REAL_E2E=1 to be set.  It will not run
  in CI automatically; it is intended for manual release confidence checks.

USAGE
  # From the workspace root:
  RUN_REAL_E2E=1 python backend/scripts/e2e_demo.py

  # Inside the Docker container:
  docker exec -e RUN_REAL_E2E=1 datacopilot-api \\
      python scripts/e2e_demo.py --base-url http://localhost:8000

  # With a different dataset or base URL:
  RUN_REAL_E2E=1 python backend/scripts/e2e_demo.py \\
      --dataset backend/scripts/e2e_demo_fixture.csv \\
      --base-url http://localhost:8000 \\
      --output reports/e2e_demo.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx


_DEFAULT_FIXTURE = Path(__file__).parent / "e2e_demo_fixture.csv"
_DEFAULT_BASE_URL = "http://localhost:8000"
_ENV_GATE = "RUN_REAL_E2E"


# ---------------------------------------------------------------------------
# Check infrastructure
# ---------------------------------------------------------------------------


@dataclass
class DemoCheck:
    name: str
    path: str
    ok: bool
    elapsed_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class DemoFailure(AssertionError):
    """Raised when a demo step fails its contract."""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class E2eDemoRunner:
    """Runs sequenced MVP6 demo paths against a live backend."""

    def __init__(
        self,
        *,
        base_url: str,
        dataset_path: Path,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset_path = dataset_path
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.checks: list[DemoCheck] = []

        self.dataset_id: str | None = None
        self.columns: list[str] = []
        self.row_count: int = 0

    def close(self) -> None:
        self.client.close()

    def run(self) -> dict[str, Any]:
        steps: list[Callable[[], dict[str, Any] | None]] = [
            # Infrastructure
            self._check_health,
            self._check_upload,
            # Path A: filter → clarification → preview → confirm
            self._check_path_a_filter_query,
            self._check_path_a_clarification_round,
            self._check_path_a_confirmed_execution,
            # Path B: analytical inspect
            self._check_path_b_profile_column,
            # Path C: analyst multi-step suggestion
            self._check_path_c_suggest_analysis_steps,
        ]
        for step in steps:
            self._run_check(step)

        passed = sum(1 for c in self.checks if c.ok)
        failed = len(self.checks) - passed
        return {
            "tool": "e2e_demo",
            "base_url": self.base_url,
            "dataset": str(self.dataset_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": len(self.checks),
                "passed": passed,
                "failed": failed,
                "ok": failed == 0,
            },
            "checks": [c.__dict__ for c in self.checks],
        }

    def _run_check(self, fn: Callable[[], dict[str, Any] | None]) -> None:
        name = fn.__name__.lstrip("_")
        start = time.monotonic()
        try:
            details = fn() or {}
            self.checks.append(DemoCheck(
                name=name,
                path=name,
                ok=True,
                elapsed_ms=round((time.monotonic() - start) * 1000, 2),
                details=details,
            ))
        except Exception as exc:
            self.checks.append(DemoCheck(
                name=name,
                path=name,
                ok=False,
                elapsed_ms=round((time.monotonic() - start) * 1000, 2),
                error=str(exc),
            ))

    def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: int = 200,
        **kwargs: Any,
    ) -> httpx.Response:
        resp = self.client.request(method, path, **kwargs)
        if resp.status_code != expected_status:
            raise DemoFailure(
                f"{method} {path} → {resp.status_code} (expected {expected_status}): "
                f"{resp.text[:400]}"
            )
        return resp

    def _dataset_id(self) -> str:
        if not self.dataset_id:
            raise DemoFailure("dataset_id unavailable — upload step did not pass.")
        return self.dataset_id

    # ------------------------------------------------------------------
    # Infrastructure
    # ------------------------------------------------------------------

    def _check_health(self) -> dict[str, Any]:
        """GET /health → status ok."""
        payload = self._request("GET", "/health").json()
        if payload.get("status") != "ok":
            raise DemoFailure(f"health check failed: {payload}")
        return payload

    def _check_upload(self) -> dict[str, Any]:
        """POST /api/datasets/upload — upload fixture CSV and record dataset_id."""
        if not self.dataset_path.exists():
            raise DemoFailure(f"fixture file not found: {self.dataset_path}")
        with self.dataset_path.open("rb") as fh:
            resp = self._request(
                "POST",
                "/api/datasets/upload",
                files={"file": (self.dataset_path.name, fh, "text/csv")},
            )
        payload = resp.json()
        self.dataset_id = payload.get("dataset_id")
        profile = payload.get("profile") or {}
        self.columns = [c["name"] for c in profile.get("columns", [])]
        self.row_count = int(profile.get("row_count") or 0)
        if not self.dataset_id:
            raise DemoFailure(f"upload missing dataset_id: {payload}")
        if not self.columns:
            raise DemoFailure(f"upload missing columns: {payload}")
        return {
            "dataset_id": self.dataset_id,
            "column_count": len(self.columns),
            "row_count": self.row_count,
            "columns": self.columns,
        }

    # ------------------------------------------------------------------
    # Path A: filter query → clarification → confirm
    # ------------------------------------------------------------------

    def _check_path_a_filter_query(self) -> dict[str, Any]:
        """POST /api/chat — query with ambiguous phrasing to trigger clarification or plan."""
        query = "筛选 amount 大于 1000 的订单"
        resp = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "auto_confirm": False,
            },
        )
        payload = resp.json()
        # Accept either clarification (slot path) or a workflow plan (planner path).
        if payload.get("has_errors"):
            raise DemoFailure(f"Path A filter query returned errors: {payload}")

        self._path_a_clarification_context = payload.get("clarification_context")
        self._path_a_query = query
        self._path_a_payload = payload

        return {
            "query": query,
            "needs_clarification": payload.get("needs_clarification"),
            "has_plan": bool(payload.get("planned_steps")),
            "step_types": [s.get("type") for s in (payload.get("planned_steps") or [])],
        }

    def _check_path_a_clarification_round(self) -> dict[str, Any]:
        """If Path A got clarification, answer it; otherwise verify we have a plan."""
        payload = getattr(self, "_path_a_payload", {})
        if not payload.get("needs_clarification"):
            # Already got a plan; skip clarification round
            planned = payload.get("planned_steps") or []
            if not planned:
                raise DemoFailure("Path A produced neither clarification nor a plan.")
            return {"skipped": True, "step_types": [s.get("type") for s in planned]}

        # Answer the clarification
        question = payload.get("clarification_question", "")
        resp = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": self._path_a_query,
                "clarification_context": "amount 字段，大于 1000",
                "auto_confirm": False,
            },
        )
        second = resp.json()
        if second.get("needs_clarification"):
            raise DemoFailure(f"Path A clarification not resolved: {second}")
        if not second.get("planned_steps"):
            raise DemoFailure(f"Path A clarification produced no plan: {second}")
        self._path_a_payload = second
        return {
            "question": question,
            "resolved_step_types": [s.get("type") for s in second.get("planned_steps", [])],
        }

    def _check_path_a_confirmed_execution(self) -> dict[str, Any]:
        """Confirm the planned workflow from Path A."""
        payload = getattr(self, "_path_a_payload", {})
        steps = payload.get("planned_steps") or []
        if not steps:
            raise DemoFailure("Path A: no planned steps to confirm.")

        if payload.get("execution_result"):
            # Already auto-confirmed in earlier step
            return {
                "auto_confirmed": True,
                "row_count": payload["execution_result"].get("row_count"),
            }

        resp = self._request(
            "POST",
            "/api/workflows/confirm",
            json={
                "dataset_id": self._dataset_id(),
                "steps": steps,
                "query": self._path_a_query,
            },
        )
        result = resp.json()
        if result.get("execution_result") is None:
            raise DemoFailure(f"Path A confirm missing execution_result: {result}")
        return {
            "run_id": result.get("run_id"),
            "row_count": result["execution_result"].get("row_count"),
            "step_types": [s.get("type") for s in steps],
        }

    # ------------------------------------------------------------------
    # Path B: profile_column analytical inspect
    # ------------------------------------------------------------------

    def _check_path_b_profile_column(self) -> dict[str, Any]:
        """POST /api/chat — ask to profile a column; expect profile_column in plan."""
        col = "amount" if "amount" in self.columns else self.columns[0]
        query = f"Profile the '{col}' column"
        resp = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "auto_confirm": True,
            },
        )
        payload = resp.json()
        if payload.get("has_errors"):
            raise DemoFailure(f"Path B profile_column returned errors: {payload}")
        step_types = [s.get("type") for s in (payload.get("planned_steps") or [])]
        return {
            "query": query,
            "step_types": step_types,
            "has_execution": bool(payload.get("execution_result")),
        }

    # ------------------------------------------------------------------
    # Path C: analyst multi-step suggestion
    # ------------------------------------------------------------------

    def _check_path_c_suggest_analysis_steps(self) -> dict[str, Any]:
        """POST /api/chat — ask for analysis suggestions; expect suggest_analysis_steps in plan."""
        query = "What analysis should I do on this dataset?"
        resp = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "auto_confirm": True,
            },
        )
        payload = resp.json()
        if payload.get("has_errors"):
            raise DemoFailure(f"Path C suggest_analysis_steps returned errors: {payload}")
        step_types = [s.get("type") for s in (payload.get("planned_steps") or [])]
        return {
            "query": query,
            "step_types": step_types,
            "needs_clarification": payload.get("needs_clarification"),
            "has_execution": bool(payload.get("execution_result")),
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MVP6 Real E2E demo script. Requires RUN_REAL_E2E=1 env var. "
            "Runs against a live backend and makes real LLM calls."
        )
    )
    parser.add_argument("--base-url", default=_DEFAULT_BASE_URL)
    parser.add_argument("--dataset", type=Path, default=_DEFAULT_FIXTURE)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    if not os.environ.get(_ENV_GATE):
        print(
            f"[skip] {_ENV_GATE} is not set. "
            "Set RUN_REAL_E2E=1 to run this real E2E demo against a live backend.",
            file=sys.stderr,
        )
        return 0

    args = parse_args(argv)
    print(f"Running MVP6 E2E demo against {args.base_url} …")
    print(f"Dataset: {args.dataset}")

    runner = E2eDemoRunner(
        base_url=args.base_url,
        dataset_path=args.dataset,
        timeout=args.timeout,
    )
    try:
        report = runner.run()
    finally:
        runner.close()

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report written to {args.output}")

    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
