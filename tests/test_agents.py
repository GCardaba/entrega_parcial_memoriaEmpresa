"""
Unit tests for the optimizer agent pipeline.
Uses MockLLM so no OpenAI API key is needed.
The DB connector is real (validates SQL via EXPLAIN).
"""
import pytest
from models.agent_state import AgentType, QueryProposal, OptimizationExplanation


# ---------------------------------------------------------------------------
# BaseOptimizerAgent internals
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_index_agent_returns_query_proposal(db, mock_llm, simple_query):
    from agents.index_agent import IndexOptimizerAgent
    schema = await db.get_schema_info("tpch")
    agent = IndexOptimizerAgent(mock_llm, db)
    proposal = await agent.optimize(simple_query, schema)
    assert isinstance(proposal, QueryProposal)


@pytest.mark.asyncio
async def test_proposal_has_required_fields(db, mock_llm, simple_query):
    from agents.index_agent import IndexOptimizerAgent
    schema = await db.get_schema_info("tpch")
    proposal = await IndexOptimizerAgent(mock_llm, db).optimize(simple_query, schema)

    assert proposal.agent_id == AgentType.INDEX_OPTIMIZER.value
    assert proposal.agent_type == AgentType.INDEX_OPTIMIZER
    assert proposal.original_query == simple_query
    assert proposal.optimized_query.strip() != ""
    assert 0.0 <= proposal.confidence_score <= 1.0
    assert isinstance(proposal.explanations, list)


@pytest.mark.asyncio
async def test_proposal_explanations_are_well_formed(db, mock_llm, simple_query):
    from agents.join_agent import JoinOptimizerAgent
    schema = await db.get_schema_info("tpch")
    proposal = await JoinOptimizerAgent(mock_llm, db).optimize(simple_query, schema)

    for exp in proposal.explanations:
        assert isinstance(exp, OptimizationExplanation)
        assert exp.technique != ""
        assert exp.reason != ""
        assert exp.expected_benefit != ""


@pytest.mark.asyncio
async def test_optimized_query_passes_explain(db, mock_llm, simple_query):
    """The optimized query must be valid SQL — EXPLAIN should not raise."""
    from agents.rewrite_agent import QueryRewriterAgent
    schema = await db.get_schema_info("tpch")
    proposal = await QueryRewriterAgent(mock_llm, db).optimize(simple_query, schema)
    # If query is invalid, execute_explain raises; this line would fail the test
    plan = await db.execute_explain(proposal.optimized_query)
    assert isinstance(plan, list)


@pytest.mark.asyncio
async def test_all_five_agents_run_in_parallel(db, mock_llm, simple_query):
    """asyncio.gather over all 5 agents must complete without error."""
    import asyncio
    from agents.index_agent import IndexOptimizerAgent
    from agents.join_agent import JoinOptimizerAgent
    from agents.rewrite_agent import QueryRewriterAgent
    from agents.cte_agent import CTEOptimizerAgent
    from agents.cache_agent import CacheOptimizerAgent

    schema = await db.get_schema_info("tpch")
    proposals = await asyncio.gather(*[
        IndexOptimizerAgent(mock_llm, db).optimize(simple_query, schema),
        JoinOptimizerAgent(mock_llm, db).optimize(simple_query, schema),
        QueryRewriterAgent(mock_llm, db).optimize(simple_query, schema),
        CTEOptimizerAgent(mock_llm, db).optimize(simple_query, schema),
        CacheOptimizerAgent(mock_llm, db).optimize(simple_query, schema),
    ])
    assert len(proposals) == 5
    agent_types = {p.agent_type for p in proposals}
    assert agent_types == {
        AgentType.INDEX_OPTIMIZER,
        AgentType.JOIN_OPTIMIZER,
        AgentType.QUERY_REWRITER,
        AgentType.CTE_OPTIMIZER,
        AgentType.CACHE_OPTIMIZER,
    }


# ---------------------------------------------------------------------------
# Syntax validation fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_llm_output_falls_back_to_original(db, simple_query):
    """When the LLM returns invalid SQL and the fix also fails, the original query is returned."""
    import json, types

    bad_sql = "THIS IS NOT VALID SQL AT ALL !!!"
    fix_response = json.dumps({"fixed_query": bad_sql})  # fix also invalid

    class BrokenMessages:
        async def create(self, messages, **kwargs):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text=fix_response)]
            )

    class BrokenLLM:
        def __init__(self):
            self.messages = BrokenMessages()

    # Patch _call_llm to return garbage JSON
    from agents.index_agent import IndexOptimizerAgent
    schema = await db.get_schema_info("tpch")
    agent = IndexOptimizerAgent(BrokenLLM(), db)

    # Monkeypatch _call_llm to return a response with bad SQL
    import json as _json
    async def bad_call_llm(user_message):
        return _json.dumps({
            "optimized_query": bad_sql,
            "optimization_strategy": "broken",
            "optimizations": [],
            "confidence_score": 0.1,
        })
    agent._call_llm = bad_call_llm

    proposal = await agent.optimize(simple_query, {})
    # Should fall back to the original query
    assert proposal.optimized_query.strip() == simple_query.strip()
