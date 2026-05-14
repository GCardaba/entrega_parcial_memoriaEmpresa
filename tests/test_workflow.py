"""
Integration test for the full LangGraph optimization workflow.
Uses MockLLM + real TPC-H PostgreSQL.
Verifies the entire pipeline from initial state to final report.
"""
import uuid
import pytest


INITIAL_STATE = {
    "session_id": "",
    "original_query": """
        SELECT c.c_name, SUM(o.o_totalprice)
        FROM tpch.customer c
        JOIN tpch.orders o ON c.c_custkey = o.o_custkey
        WHERE c.c_mktsegment = 'BUILDING'
        GROUP BY c.c_name
        LIMIT 10
    """,
    "schema_context": {},
    "baseline_metrics": None,
    "proposals": [],
    "combined_proposals": [],
    "evaluations": [],
    "winner": None,
    "report": None,
    "status": "pending",
}


@pytest.mark.asyncio
async def test_workflow_completes_successfully(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    workflow = build_optimization_workflow(mock_llm, db)
    final = await workflow.ainvoke(state)
    assert final["status"] == "done"


@pytest.mark.asyncio
async def test_workflow_produces_five_optimizer_proposals(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    assert len(final["proposals"]) == 5


@pytest.mark.asyncio
async def test_workflow_produces_five_combined_proposals(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    assert len(final["combined_proposals"]) == 5


@pytest.mark.asyncio
async def test_each_evaluation_has_five_master_scores(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    for ev in final["evaluations"]:
        assert len(ev["master_agent_scores"]) == 5


@pytest.mark.asyncio
async def test_winner_has_highest_or_tied_score(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    winner_score = final["winner"]["final_score"]
    all_scores = [ev["final_score"] for ev in final["evaluations"]]
    assert winner_score == max(all_scores)


@pytest.mark.asyncio
async def test_report_has_required_keys(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    report = final["report"]
    for key in ("summary", "winner", "explanations", "comparison_table", "original_query", "query_diff"):
        assert key in report, f"Missing key in report: {key}"


@pytest.mark.asyncio
async def test_comparison_table_has_five_rows(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    assert len(final["report"]["comparison_table"]) == 5


@pytest.mark.asyncio
async def test_comparison_table_ranked_descending(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    scores = [row["final_score"] for row in final["report"]["comparison_table"]]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_baseline_metrics_populated(db, mock_llm):
    from orchestrator.workflow import build_optimization_workflow

    state = {**INITIAL_STATE, "session_id": str(uuid.uuid4())}
    final = await build_optimization_workflow(mock_llm, db).ainvoke(state)
    bm = final["baseline_metrics"]
    assert bm is not None
    assert bm["actual_time_ms"] > 0
    assert bm["total_cost"] > 0
