"""Unit tests for app.agent.context.rag_service and app.agent.context.retriever."""
import pytest

from app.agent.context.rag_service import build_context, load_docs, retrieve
from app.agent.context.retriever import KeywordRetriever, get_retriever
from app.models.dataset import ColumnProfile, DatasetProfile

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_DOCS = [
    {
        "type": "group_by",
        "description": "Group rows by a column and aggregate a numeric target.",
        "keywords": ["group", "aggregate", "sum", "mean", "count", "分组", "汇总"],
        "parameters": [
            {"name": "column", "type": "str", "required": True, "description": "Group column."},
            {"name": "target", "type": "str", "required": True, "description": "Numeric column."},
            {"name": "agg", "type": "str", "required": True, "description": "Aggregation function."},
        ],
        "example": {"type": "group_by", "column": "region", "target": "sales", "agg": "sum"},
    },
    {
        "type": "filter_rows",
        "description": "Keep only rows satisfying a condition on a column.",
        "keywords": ["filter", "where", "condition", "greater", "less", "过滤", "筛选"],
        "parameters": [
            {"name": "column", "type": "str", "required": True, "description": "Column to filter."},
            {"name": "operator", "type": "str", "required": True, "description": "Comparison operator."},
            {"name": "value", "type": "int | float | str", "required": True, "description": "Compare value."},
        ],
        "example": {"type": "filter_rows", "column": "sales", "operator": ">", "value": 1000},
    },
    {
        "type": "sort_values",
        "description": "Sort rows by a column ascending or descending.",
        "keywords": ["sort", "order", "rank", "ascending", "descending", "排序", "排列"],
        "parameters": [
            {"name": "column", "type": "str", "required": True, "description": "Column to sort by."},
            {"name": "ascending", "type": "bool", "required": False, "description": "Sort direction."},
        ],
        "example": {"type": "sort_values", "column": "sales", "ascending": False},
    },
]

SAMPLE_PROFILE = DatasetProfile(
    filename="sales.csv",
    row_count=100,
    column_count=3,
    columns=[
        ColumnProfile(name="region", dtype="object", missing_count=0, missing_pct=0.0),
        ColumnProfile(name="sales", dtype="float64", missing_count=2, missing_pct=2.0),
        ColumnProfile(name="month", dtype="object", missing_count=0, missing_pct=0.0),
    ],
    preview=[],
)


# ---------------------------------------------------------------------------
# load_docs — filesystem smoke test
# ---------------------------------------------------------------------------

def test_load_docs_returns_all_transformation_files():
    docs = load_docs()
    step_types = {d["step_type"] for d in docs if d.get("step_type")}
    assert "group_by" in step_types
    assert "filter_rows" in step_types
    assert "sort_values" in step_types
    assert "remove_missing_values" in step_types
    assert "select_columns" in step_types
    assert "rename_columns" in step_types
    assert "generate_summary" in step_types


def test_load_docs_includes_failure_and_example_docs():
    docs = load_docs()
    doc_types = {d["doc_type"] for d in docs}
    assert "transformation" in doc_types
    assert "failure_case" in doc_types
    assert "correction_case" in doc_types
    assert "workflow_example" in doc_types


def test_load_docs_each_has_required_keys():
    # All corpus docs must have the unified metadata fields defined in Task 4.
    for doc in load_docs():
        assert "doc_type" in doc, f"Missing 'doc_type' in {doc.get('source_path', '?')}"
        assert "source_path" in doc, f"Missing 'source_path' in {doc.get('title', '?')}"
        assert "description" in doc
        assert "keywords" in doc


# ---------------------------------------------------------------------------
# retrieve — keyword matching
# ---------------------------------------------------------------------------

def test_retrieve_group_by_for_aggregation_query():
    retrieved, debug = retrieve("按地区统计销售额 sum", SAMPLE_DOCS, top_k=1)
    assert retrieved[0].type == "group_by"
    assert retrieved[0].score > 0


def test_retrieve_filter_rows_for_filter_query():
    retrieved, debug = retrieve("filter rows where sales greater than 1000", SAMPLE_DOCS, top_k=1)
    assert retrieved[0].type == "filter_rows"


def test_retrieve_sort_for_rank_query():
    retrieved, debug = retrieve("sort order rank descending", SAMPLE_DOCS, top_k=1)
    assert retrieved[0].type == "sort_values"


def test_retrieve_returns_top_k():
    retrieved, _ = retrieve("group filter sort", SAMPLE_DOCS, top_k=2)
    assert len(retrieved) == 2


def test_retrieve_debug_contains_all_doc_types():
    _, debug = retrieve("anything", SAMPLE_DOCS, top_k=3)
    assert set(debug.all_scores.keys()) == {"group_by", "filter_rows", "sort_values"}


def test_retrieve_debug_method_is_keyword_matching():
    _, debug = retrieve("test", SAMPLE_DOCS, top_k=1)
    assert debug.method == "keyword_matching"


def test_retrieve_query_tokens_are_lowercase():
    _, debug = retrieve("Group Aggregate", SAMPLE_DOCS, top_k=1)
    assert all(t == t.lower() for t in debug.query_tokens)


def test_retrieve_zero_score_when_no_match():
    # "hello world" doesn't match any keyword in the sample docs.
    retrieved, debug = retrieve("hello world", SAMPLE_DOCS, top_k=3)
    assert all(r.score == 0 for r in retrieved)


# ---------------------------------------------------------------------------
# build_context (async — docs param forces KeywordRetriever, no DB/OpenAI calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_build_context_includes_query():
    ctx = await build_context("按地区汇总销售", SAMPLE_PROFILE, top_k=2, docs=SAMPLE_DOCS)
    assert ctx.query == "按地区汇总销售"


@pytest.mark.asyncio
async def test_build_context_dataset_summary_matches_profile():
    ctx = await build_context("group by region", SAMPLE_PROFILE, top_k=2, docs=SAMPLE_DOCS)
    assert ctx.dataset_summary.filename == "sales.csv"
    assert ctx.dataset_summary.row_count == 100
    assert ctx.dataset_summary.column_count == 3
    assert len(ctx.dataset_summary.columns) == 3


@pytest.mark.asyncio
async def test_build_context_returns_requested_top_k():
    ctx = await build_context("filter sort group", SAMPLE_PROFILE, top_k=2, docs=SAMPLE_DOCS)
    assert len(ctx.retrieved_docs) == 2


@pytest.mark.asyncio
async def test_build_context_debug_included():
    ctx = await build_context("sort ascending", SAMPLE_PROFILE, top_k=1, docs=SAMPLE_DOCS)
    assert ctx.debug.method == "keyword_matching"
    assert len(ctx.debug.all_scores) == len(SAMPLE_DOCS)


# ---------------------------------------------------------------------------
# get_retriever factory
# ---------------------------------------------------------------------------

def test_get_retriever_with_docs_returns_keyword():
    r = get_retriever(docs=SAMPLE_DOCS)
    assert isinstance(r, KeywordRetriever)


def test_get_retriever_keyword_method_returns_keyword():
    r = get_retriever(method="keyword")
    assert isinstance(r, KeywordRetriever)


@pytest.mark.asyncio
async def test_keyword_retriever_retrieve_returns_correct_type():
    r = KeywordRetriever(docs=SAMPLE_DOCS)
    retrieved, debug = await r.retrieve("filter rows condition", top_k=1)
    assert len(retrieved) == 1
    assert retrieved[0].type == "filter_rows"
    assert debug.method == "keyword_matching"
    assert debug.embedding_model is None


@pytest.mark.asyncio
async def test_keyword_retriever_scores_are_float():
    r = KeywordRetriever(docs=SAMPLE_DOCS)
    retrieved, debug = await r.retrieve("group aggregate sum", top_k=1)
    assert isinstance(retrieved[0].score, float)
    assert all(isinstance(v, float) for v in debug.all_scores.values())
