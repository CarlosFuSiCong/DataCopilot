"""Consistency tests for the central tool registry."""
import json
from pathlib import Path

from app.tools import registry


BACKEND_DIR = Path(__file__).resolve().parents[1]
TRANSFORMATIONS_DIR = BACKEND_DIR / "app" / "transformations"
EVAL_QUERIES_FILE = BACKEND_DIR / "scripts" / "eval_workflow_queries.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_rag_transformation_docs_exist_in_registry():
    doc_types = {
        _load_json(path)["type"]
        for path in TRANSFORMATIONS_DIR.glob("*.json")
    }
    assert doc_types
    assert doc_types <= registry.step_types()


def test_all_eval_expected_step_types_exist_in_registry():
    queries = _load_json(EVAL_QUERIES_FILE)
    expected_types = {
        step_type
        for query in queries
        for step_type in query.get("expected_step_types", [])
    }
    assert expected_types
    assert expected_types <= registry.step_types()


def test_registry_exposes_required_metadata_surfaces():
    tools = registry.all_tools()
    assert tools
    for spec in tools:
        assert spec.type
        assert spec.description
        assert spec.input_schema
        assert callable(spec.validate)
        assert callable(spec.execute)
        assert isinstance(spec.examples, list)
        assert isinstance(spec.risk_profile, dict)

    prompt = registry.supported_tools_prompt()
    assert "filter_rows" in prompt
    assert "group_by" in prompt

    rag_metadata = registry.rag_metadata()
    assert {tool["type"] for tool in rag_metadata} == registry.step_types()

    editor_metadata = registry.workflow_editor_metadata()
    assert {tool["type"] for tool in editor_metadata} == registry.step_types()
