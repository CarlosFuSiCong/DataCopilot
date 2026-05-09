"""Live API smoke harness for DataCopilot.

This script exercises a running backend over HTTP. It is intended for the
Docker-backed MVP4 harness path, for example:

    python backend/scripts/smoke_api.py --dataset path/to/orders.csv --profile deep

    docker exec datacopilot-api \
      python scripts/smoke_api.py --dataset /app/sample_data/orders.csv --profile deep

The script prints a machine-readable JSON report and exits non-zero when any
selected check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import httpx


ProfileName = Literal["mvp3", "deep"]


@dataclass
class SmokeCheck:
    name: str
    ok: bool
    elapsed_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class SmokeFailure(AssertionError):
    """Raised when a smoke check does not satisfy its expected contract."""


class SmokeRunner:
    def __init__(
        self,
        *,
        base_url: str,
        dataset_path: Path,
        profile: ProfileName,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset_path = dataset_path
        self.profile = profile
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.checks: list[SmokeCheck] = []

        self.dataset_id: str | None = None
        self.filename = dataset_path.name
        self.columns: list[str] = []
        self.row_count = 0
        self.success_steps: list[dict[str, Any]] = []
        self.warning_steps: list[dict[str, Any]] = []
        self.confirmed_run_id: str | None = None

    def close(self) -> None:
        self.client.close()

    def run(self) -> dict[str, Any]:
        selected = [
            self.check_health,
            self.check_upload_and_profile,
            self.check_rows_pagination,
            self.check_original_download,
            self.check_chat_success_auto_confirm,
            self.check_warning_preview,
            self.check_manual_confirm,
            self.check_run_history_and_detail,
            self.check_result_download,
            self.check_execute_rows_pagination,
            self.check_export_result_csv,
            self.check_missing_column_error,
            self.check_rerun_preview,
            self.check_clarification_request_and_answer,
        ]
        if self.profile == "deep":
            selected.append(self.check_diff_rows)

        for check in selected:
            self._run_check(check)

        passed = sum(1 for check in self.checks if check.ok)
        failed = len(self.checks) - passed
        return {
            "tool": "smoke_api",
            "profile": self.profile,
            "base_url": self.base_url,
            "dataset": str(self.dataset_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": len(self.checks),
                "passed": passed,
                "failed": failed,
                "ok": failed == 0,
            },
            "checks": [check.__dict__ for check in self.checks],
        }

    def _run_check(self, check: Callable[[], dict[str, Any] | None]) -> None:
        start = time.monotonic()
        try:
            details = check() or {}
            self.checks.append(SmokeCheck(
                name=check.__name__.removeprefix("check_"),
                ok=True,
                elapsed_ms=round((time.monotonic() - start) * 1000, 2),
                details=details,
            ))
        except Exception as exc:
            self.checks.append(SmokeCheck(
                name=check.__name__.removeprefix("check_"),
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
        response = self.client.request(method, path, **kwargs)
        if response.status_code != expected_status:
            raise SmokeFailure(
                f"{method} {path} returned {response.status_code}, "
                f"expected {expected_status}: {response.text[:500]}"
            )
        return response

    def _dataset_id(self) -> str:
        if not self.dataset_id:
            raise SmokeFailure("dataset_id is not available; upload check did not pass.")
        return self.dataset_id

    def _confirmed_run_id(self) -> str:
        if not self.confirmed_run_id:
            raise SmokeFailure("run_id is not available; confirm check did not pass.")
        return self.confirmed_run_id

    def _simple_columns(self, max_count: int = 2) -> list[str]:
        simple = [
            col for col in self.columns
            if col.replace("_", "").isalnum() and " " not in col
        ]
        return (simple or self.columns)[:max_count]

    def check_health(self) -> dict[str, Any]:
        response = self._request("GET", "/health")
        payload = response.json()
        if payload.get("status") != "ok":
            raise SmokeFailure(f"unexpected health payload: {payload}")
        return payload

    def check_upload_and_profile(self) -> dict[str, Any]:
        if not self.dataset_path.exists():
            raise SmokeFailure(f"dataset file does not exist: {self.dataset_path}")

        with self.dataset_path.open("rb") as file_obj:
            response = self._request(
                "POST",
                "/api/datasets/upload",
                files={"file": (self.dataset_path.name, file_obj, "text/csv")},
            )
        payload = response.json()
        profile = payload.get("profile") or {}
        self.dataset_id = payload.get("dataset_id")
        self.columns = [col["name"] for col in profile.get("columns", [])]
        self.row_count = int(profile.get("row_count") or 0)

        if not self.dataset_id:
            raise SmokeFailure(f"upload response missing dataset_id: {payload}")
        if not self.columns:
            raise SmokeFailure(f"upload response missing columns: {payload}")
        if self.row_count <= 0:
            raise SmokeFailure(f"upload response has invalid row_count: {payload}")

        return {
            "dataset_id": self.dataset_id,
            "filename": profile.get("filename"),
            "row_count": self.row_count,
            "column_count": profile.get("column_count"),
            "columns": self.columns,
        }

    def check_rows_pagination(self) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/api/datasets/{self._dataset_id()}/rows",
            params={"offset": 0, "limit": 5},
        )
        payload = response.json()
        rows = payload.get("rows", [])
        if not rows:
            raise SmokeFailure("rows endpoint returned no rows")
        if payload.get("total_rows") != self.row_count:
            raise SmokeFailure(f"rows total mismatch: {payload}")
        return {"returned_rows": len(rows), "total_rows": payload.get("total_rows")}

    def check_original_download(self) -> dict[str, Any]:
        response = self._request("GET", f"/api/datasets/{self._dataset_id()}/download")
        if len(response.content) == 0:
            raise SmokeFailure("original CSV download returned an empty body")
        return {
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type"),
        }

    def check_chat_success_auto_confirm(self) -> dict[str, Any]:
        selected = self._simple_columns()
        query = f"Select columns {', '.join(selected)}"
        response = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "auto_confirm": True,
            },
        )
        payload = response.json()
        if payload.get("needs_clarification"):
            raise SmokeFailure(f"expected auto-confirm, got clarification: {payload}")
        if payload.get("execution_result") is None:
            raise SmokeFailure(f"chat success did not auto-confirm: {payload}")
        if payload.get("has_errors"):
            raise SmokeFailure(f"chat success returned errors: {payload}")

        self.success_steps = payload.get("planned_steps") or []
        return {
            "query": query,
            "step_types": [step.get("type") for step in self.success_steps],
            "run_id": payload.get("run_id"),
        }

    def check_warning_preview(self) -> dict[str, Any]:
        filter_column = self._simple_columns(1)[0]
        self.warning_steps = [{
            "type": "filter_rows",
            "column": filter_column,
            "operator": "=",
            "value": "__datacopilot_smoke_no_match__",
        }]
        response = self._request(
            "POST",
            "/api/workflows/preview",
            json={"dataset_id": self._dataset_id(), "steps": self.warning_steps},
        )
        payload = response.json()
        if not payload.get("has_warnings"):
            raise SmokeFailure(f"preview should have warning: {payload}")
        if payload.get("has_errors"):
            raise SmokeFailure(f"preview should not have errors: {payload}")
        return {
            "step_results": payload.get("step_results", []),
            "blocked_at_step": payload.get("blocked_at_step"),
        }

    def check_manual_confirm(self) -> dict[str, Any]:
        if not self.warning_steps:
            raise SmokeFailure("warning_steps not available; preview check did not pass.")
        response = self._request(
            "POST",
            "/api/workflows/confirm",
            json={
                "dataset_id": self._dataset_id(),
                "steps": self.warning_steps,
                "query": "Smoke confirm warning preview workflow",
            },
        )
        payload = response.json()
        self.confirmed_run_id = payload.get("run_id")
        if not self.confirmed_run_id:
            raise SmokeFailure(f"confirm response missing run_id: {payload}")
        if payload.get("execution_result") is None:
            raise SmokeFailure(f"confirm response missing execution_result: {payload}")
        return {
            "run_id": self.confirmed_run_id,
            "row_count": payload["execution_result"].get("row_count"),
        }

    def check_run_history_and_detail(self) -> dict[str, Any]:
        list_response = self._request(
            "GET",
            "/api/runs",
            params={"dataset_id": self._dataset_id(), "limit": 10},
        )
        list_payload = list_response.json()
        runs = list_payload.get("runs", [])
        if not any(run.get("run_id") == self._confirmed_run_id() for run in runs):
            raise SmokeFailure(f"confirmed run missing from history: {list_payload}")

        detail_response = self._request("GET", f"/api/runs/{self._confirmed_run_id()}")
        detail_payload = detail_response.json()
        if detail_payload.get("run_id") != self._confirmed_run_id():
            raise SmokeFailure(f"run detail returned wrong run: {detail_payload}")
        if not detail_payload.get("planned_steps"):
            raise SmokeFailure(f"run detail missing planned_steps: {detail_payload}")

        return {"total": list_payload.get("total"), "run_id": detail_payload.get("run_id")}

    def check_rerun_preview(self) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/api/runs/{self._confirmed_run_id()}/rerun",
            json={
                "dataset_id": self._dataset_id(),
                "steps": self.warning_steps,
                "query": "Smoke rerun warning workflow",
            },
        )
        payload = response.json()
        if not payload.get("has_warnings"):
            raise SmokeFailure(f"rerun preview should preserve warning: {payload}")
        return {"step_results": payload.get("step_results", [])}

    def check_result_download(self) -> dict[str, Any]:
        response = self._request("GET", f"/api/runs/{self._confirmed_run_id()}/download")
        if len(response.content) == 0:
            raise SmokeFailure("result CSV download returned an empty body")
        return {
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type"),
        }

    def check_execute_rows_pagination(self) -> dict[str, Any]:
        steps = self.success_steps or [{"type": "select_columns", "columns": self._simple_columns()}]
        response = self._request(
            "POST",
            f"/api/datasets/{self._dataset_id()}/execute-rows",
            json={"steps": steps, "offset": 0, "limit": 5},
        )
        payload = response.json()
        if "rows" not in payload or "total_rows" not in payload:
            raise SmokeFailure(f"execute-rows returned invalid payload: {payload}")
        return {"returned_rows": len(payload["rows"]), "total_rows": payload["total_rows"]}

    def check_diff_rows(self) -> dict[str, Any]:
        steps = self.success_steps or [{"type": "select_columns", "columns": self._simple_columns()}]
        response = self._request(
            "POST",
            f"/api/datasets/{self._dataset_id()}/execute-diff",
            json={"steps": steps, "offset": 0, "limit": 5},
        )
        payload = response.json()
        rows = payload.get("rows", [])
        if not rows:
            raise SmokeFailure(f"execute-diff returned no rows: {payload}")
        if "_kept" not in rows[0]:
            raise SmokeFailure(f"execute-diff rows missing _kept flag: {payload}")
        return {
            "returned_rows": len(rows),
            "total_original": payload.get("total_original"),
            "total_result": payload.get("total_result"),
        }

    def check_export_result_csv(self) -> dict[str, Any]:
        steps = self.success_steps or [{"type": "select_columns", "columns": self._simple_columns()}]
        response = self._request(
            "POST",
            f"/api/datasets/{self._dataset_id()}/export",
            json={"steps": steps, "filename": self.filename},
        )
        if len(response.content) == 0:
            raise SmokeFailure("export result CSV returned an empty body")
        return {
            "bytes": len(response.content),
            "content_type": response.headers.get("content-type"),
        }

    def check_missing_column_error(self) -> dict[str, Any]:
        response = self._request(
            "POST",
            "/api/chat",
            expected_status=400,
            json={
                "dataset_id": self._dataset_id(),
                "query": "Filter rows where __missing_smoke_column__ > 1",
            },
        )
        payload = response.json()
        if payload.get("error_code") != "missing_column":
            raise SmokeFailure(f"expected missing_column error: {payload}")
        context = payload.get("context") or {}
        if not context.get("available_columns"):
            raise SmokeFailure(f"missing_column response lacks available_columns: {payload}")
        return {"error_code": payload.get("error_code"), "context": context}

    def check_clarification_request_and_answer(self) -> dict[str, Any]:
        query = "Analyze this dataset"
        first_response = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "auto_confirm": False,
            },
        )
        first_payload = first_response.json()
        if not first_payload.get("needs_clarification"):
            raise SmokeFailure(f"expected clarification request: {first_payload}")

        selected = self._simple_columns()
        second_response = self._request(
            "POST",
            "/api/chat",
            json={
                "dataset_id": self._dataset_id(),
                "query": query,
                "clarification_context": f"Select columns {', '.join(selected)}",
                "auto_confirm": False,
            },
        )
        second_payload = second_response.json()
        if second_payload.get("needs_clarification"):
            raise SmokeFailure(f"clarification answer did not resolve request: {second_payload}")
        if not second_payload.get("planned_steps"):
            raise SmokeFailure(f"clarification answer produced no workflow: {second_payload}")

        return {
            "question": first_payload.get("clarification_question"),
            "resolved_step_types": [step.get("type") for step in second_payload.get("planned_steps", [])],
        }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live DataCopilot API smoke checks.")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL for the running API container. Default: http://localhost:8000",
    )
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="CSV file to upload for the smoke run.",
    )
    parser.add_argument(
        "--profile",
        choices=["mvp3", "deep"],
        default="mvp3",
        help="Smoke profile to run. 'deep' includes an additional diff rows check.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for each API call.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the JSON report.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    runner = SmokeRunner(
        base_url=args.base_url,
        dataset_path=args.dataset,
        profile=args.profile,
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

    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
