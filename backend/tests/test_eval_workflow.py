"""Tests for workflow eval contract parsing."""
import json
from pathlib import Path

import pytest

from scripts.eval_workflow import (
    DatasetReport,
    EvalReport,
    PhaseResult,
    QueryResult,
    _build_json_output,
    _load_contracts,
)

MVP4_CONTRACT = Path(__file__).parents[1] / "scripts" / "eval_contract_mvp4.json"


def test_load_contracts_missing_dataset_path_raises_clear_error(tmp_path: Path):
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps({"datasets": [{"id": "broken", "queries": []}]}),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="missing required field 'path'"):
        _load_contracts(contract, tmp_path / "unused.csv", tmp_path / "unused.json")


def test_build_json_output_uses_query_regression_candidate_field():
    report = EvalReport(
        method="keyword",
        mode="strict",
        llm_model="test-model",
        git_commit_sha="abc123",
        generated_at="2026-01-01T00:00:00+00:00",
        datasets=[
            DatasetReport(
                dataset_id="demo",
                dataset="demo.csv",
                dataset_hash="hash",
                total_queries=1,
                results=[
                    QueryResult(
                        dataset_id="demo",
                        query_id="q1",
                        demo_case="D01",
                        query="bad query",
                        expected_step_types=["filter_rows"],
                        expected_outcome="success",
                        expected_row_count=1,
                        expected_col_count=2,
                        phases=PhaseResult(
                            failure_phase="shape",
                            failure_message="shape mismatch",
                            actual_step_types=["filter_rows"],
                        ),
                        overall_ok=False,
                        regression_candidate=False,
                    )
                ],
            )
        ],
    )

    output = _build_json_output(report)

    assert output["failures"][0]["regression_candidate"] is False


def test_mvp4_eval_contract_defines_required_datasets():
    data = json.loads(MVP4_CONTRACT.read_text(encoding="utf-8"))
    dataset_ids = {dataset["id"] for dataset in data["datasets"]}

    assert {
        "orders",
        "sales",
        "messy_customers",
        "time_series",
        "wide_table",
    }.issubset(dataset_ids)


def test_mvp4_eval_contract_documents_schema_and_expected_outputs():
    data = json.loads(MVP4_CONTRACT.read_text(encoding="utf-8"))

    for dataset in data["datasets"]:
        schema = dataset["schema"]
        assert schema["row_count"] > 0
        assert schema["columns"]
        assert "missing_values" in schema
        assert dataset["demo_prompts"]

        queries = dataset.get("queries")
        if queries is None:
            continue
        for query in queries:
            assert "expected_step_types" in query
            assert "expected_outcome" in query
            assert "expected_output" in query
            assert "expected_warning" in query
