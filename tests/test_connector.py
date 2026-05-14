"""
Integration tests for PostgreSQLConnector.
These tests require a live PostgreSQL 16 instance with the TPC-H schema loaded.
"""
import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_query_returns_rows(db):
    rows = await db.execute_query("SELECT 1 AS n")
    assert len(rows) == 1
    assert rows[0]["n"] == 1


@pytest.mark.asyncio
async def test_tpch_tables_have_data(db):
    rows = await db.execute_query("SELECT count(*) FROM tpch.orders")
    assert rows[0]["count"] == 150_000


@pytest.mark.asyncio
async def test_lineitem_row_count(db):
    rows = await db.execute_query("SELECT count(*) FROM tpch.lineitem")
    assert rows[0]["count"] == 600_572


# ---------------------------------------------------------------------------
# execute_explain (syntax validation without running the query)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_explain_valid_query(db, simple_query):
    plan = await db.execute_explain(simple_query)
    assert isinstance(plan, list)
    assert "Plan" in plan[0]


@pytest.mark.asyncio
async def test_execute_explain_returns_parsed_dict(db, simple_query):
    """Result must be a Python list, not a raw JSON string."""
    plan = await db.execute_explain(simple_query)
    assert isinstance(plan[0]["Plan"], dict)


@pytest.mark.asyncio
async def test_execute_explain_invalid_query_raises(db, invalid_query):
    with pytest.raises(Exception):
        await db.execute_explain(invalid_query)


# ---------------------------------------------------------------------------
# execute_explain_analyze
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_explain_analyze_returns_execution_time(db, simple_query):
    plan = await db.execute_explain_analyze(simple_query)
    assert "Execution Time" in plan[0]
    assert plan[0]["Execution Time"] > 0


@pytest.mark.asyncio
async def test_execute_explain_analyze_has_buffers(db, simple_query):
    plan = await db.execute_explain_analyze(simple_query)
    root = plan[0]["Plan"]
    assert "Shared Hit Blocks" in root


@pytest.mark.asyncio
async def test_explain_analyze_parsed_not_string(db, simple_query):
    plan = await db.execute_explain_analyze(simple_query)
    assert isinstance(plan, list)
    assert isinstance(plan[0], dict)


# ---------------------------------------------------------------------------
# get_schema_info
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_schema_info_returns_all_tpch_tables(db):
    schema = await db.get_schema_info("tpch")
    expected_tables = {"customer", "lineitem", "nation", "orders", "part", "partsupp", "region", "supplier"}
    assert expected_tables == set(schema.keys())


@pytest.mark.asyncio
async def test_schema_info_has_columns(db):
    schema = await db.get_schema_info("tpch")
    customer_cols = [c["name"] for c in schema["customer"]["columns"]]
    assert "c_custkey" in customer_cols
    assert "c_mktsegment" in customer_cols


@pytest.mark.asyncio
async def test_schema_info_has_indexes(db):
    schema = await db.get_schema_info("tpch")
    customer_idx_names = [i["name"] for i in schema["customer"]["indexes"]]
    assert "idx_customer_mktsegment" in customer_idx_names


@pytest.mark.asyncio
async def test_schema_info_has_primary_key(db):
    schema = await db.get_schema_info("tpch")
    assert schema["customer"]["primary_key"] == "c_custkey"


# ---------------------------------------------------------------------------
# get_table_statistics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_table_statistics_returns_estimated_rows(db):
    stats = await db.get_table_statistics("orders")
    assert "estimated_rows" in stats
    # After ANALYZE, planner estimate should be close to real count
    assert stats["estimated_rows"] > 100_000
