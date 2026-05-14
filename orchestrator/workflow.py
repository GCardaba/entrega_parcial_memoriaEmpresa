import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langgraph.graph import StateGraph, END

from models.agent_state import SystemState, EvaluationResult
from database.connector import PostgreSQLConnector
from database.explain_parser import ExplainAnalyzeParser
from agents.index_agent import IndexOptimizerAgent
from agents.join_agent import JoinOptimizerAgent
from agents.rewrite_agent import QueryRewriterAgent
from agents.cte_agent import CTEOptimizerAgent
from agents.cache_agent import CacheOptimizerAgent
from agents.master_agents.master_agent_1 import MasterAgent1
from agents.master_agents.master_agent_2 import MasterAgent2
from agents.master_agents.master_agent_3 import MasterAgent3
from agents.master_agents.master_agent_4 import MasterAgent4
from agents.master_agents.master_agent_5 import MasterAgent5
from agents.master_agents.scoring_system import MasterAgentsScoring
from reporter.report_generator import ReportGenerator


# ---------------------------------------------------------------------------
# Node functions
# Each receives the full SystemState dict and returns a partial update dict.
# LangGraph merges the returned dict into the state automatically.
# ---------------------------------------------------------------------------

async def parse_query(state: dict, db: PostgreSQLConnector, parser: ExplainAnalyzeParser) -> dict:
    """Fetch schema and run baseline EXPLAIN ANALYZE. Returns full state."""
    schema_context = await db.get_schema_info("tpch")
    baseline_plan = await db.execute_explain_analyze(state["original_query"])
    baseline_metrics = parser.parse(baseline_plan)
    return {**state, "schema_context": schema_context,
            "baseline_metrics": baseline_metrics.model_dump(), "status": "parsed"}


async def run_optimizer_agents(state: dict, llm, db: PostgreSQLConnector) -> dict:
    """Run the 5 specialist optimizer agents in parallel. Returns full state."""
    agents = [
        IndexOptimizerAgent(llm, db),
        JoinOptimizerAgent(llm, db),
        QueryRewriterAgent(llm, db),
        CTEOptimizerAgent(llm, db),
        CacheOptimizerAgent(llm, db),
    ]
    proposals = await asyncio.gather(*[
        agent.optimize(state["original_query"], state["schema_context"])
        for agent in agents
    ])
    return {**state, "proposals": [p.model_dump() for p in proposals], "status": "optimized"}


async def combine_optimizations(state: dict, llm, db: PostgreSQLConnector) -> dict:
    """Each master agent combines optimizer proposals into one pre-final query. Returns full state."""
    from models.agent_state import QueryProposal

    proposals = [QueryProposal(**p) for p in state["proposals"]]
    master_agents = [
        MasterAgent1(llm, db, "master_1"),
        MasterAgent2(llm, db, "master_2"),
        MasterAgent3(llm, db, "master_3"),
        MasterAgent4(llm, db, "master_4"),
        MasterAgent5(llm, db, "master_5"),
    ]
    combined = await asyncio.gather(*[
        agent.combine_optimizations(state["original_query"], proposals, state["schema_context"])
        for agent in master_agents
    ])
    return {**state, "combined_proposals": [p.model_dump() for p in combined], "status": "combined"}


async def evaluate_proposals(state: dict, db: PostgreSQLConnector, parser: ExplainAnalyzeParser) -> dict:
    """EXPLAIN ANALYZE each combined proposal (3 runs, averaged). Returns full state."""
    from models.agent_state import QueryProposal, EvaluationMetrics

    combined = [QueryProposal(**p) for p in state["combined_proposals"]]
    baseline = EvaluationMetrics(**state["baseline_metrics"])

    async def evaluate_one(proposal: QueryProposal):
        try:
            await db.execute_query(proposal.optimized_query)  # warm-up
        except Exception:
            pass

        plans = []
        for _ in range(3):
            try:
                plan = await db.execute_explain_analyze(proposal.optimized_query)
                plans.append(parser.parse(plan))
            except Exception:
                pass

        metrics = _average_metrics(plans) if plans else baseline
        return EvaluationResult(
            proposal=proposal,
            metrics=metrics,
            improvement_vs_original=_calc_improvements(metrics, baseline),
            master_agent_scores=[],
            final_score=0.0,
        )

    evaluations = await asyncio.gather(*[evaluate_one(p) for p in combined])
    return {**state, "evaluations": [e.model_dump() for e in evaluations], "status": "evaluated"}


async def score_proposals(state: dict, llm, db: PostgreSQLConnector) -> dict:
    """All 5 master agents score all 5 proposals; trim mean → final_score. Returns full state."""
    from models.agent_state import EvaluationMetrics, EvaluationResult

    master_agents = [
        MasterAgent1(llm, db, "master_1"),
        MasterAgent2(llm, db, "master_2"),
        MasterAgent3(llm, db, "master_3"),
        MasterAgent4(llm, db, "master_4"),
        MasterAgent5(llm, db, "master_5"),
    ]
    scoring = MasterAgentsScoring(master_agents, db)
    evaluations = [EvaluationResult(**e) for e in state["evaluations"]]
    baseline = EvaluationMetrics(**state["baseline_metrics"])

    async def score_one(ev: EvaluationResult) -> EvaluationResult:
        scores = await asyncio.gather(*[
            agent.score_proposal(ev.proposal, ev.metrics, baseline)
            for agent in master_agents
        ])
        ev.master_agent_scores = list(scores)
        # Trim mean: drop highest and lowest, average the rest
        sorted_scores = sorted(scores, key=lambda s: s.score)
        trimmed = sorted_scores[1:-1] if len(sorted_scores) > 2 else sorted_scores
        ev.final_score = sum(s.score for s in trimmed) / len(trimmed) if trimmed else 0.0
        return ev

    scored = await asyncio.gather(*[score_one(ev) for ev in evaluations])
    return {**state, "evaluations": [e.model_dump() for e in scored], "status": "scored"}


async def select_winner(state: dict) -> dict:
    """Pick the combined proposal with the highest final_score. Returns full state."""
    from models.agent_state import EvaluationResult

    evaluations = [EvaluationResult(**e) for e in state["evaluations"]]
    winner = max(evaluations, key=lambda e: e.final_score)
    return {**state, "winner": winner.model_dump(), "status": "winner_selected"}


async def generate_report(state: dict) -> dict:
    """Build the final report dict from the completed state. Returns full state."""
    from models.agent_state import SystemState as SS

    full_state = SS(**{k: v for k, v in state.items() if k in SS.model_fields})
    generator = ReportGenerator()
    report = generator.create_report(full_state)
    return {**state, "report": report, "status": "done"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _average_metrics(metrics_list):
    from models.agent_state import EvaluationMetrics

    n = len(metrics_list)
    return EvaluationMetrics(
        total_cost=sum(m.total_cost for m in metrics_list) / n,
        actual_time_ms=sum(m.actual_time_ms for m in metrics_list) / n,
        rows_processed=int(sum(m.rows_processed for m in metrics_list) / n),
        buffer_hits=int(sum(m.buffer_hits for m in metrics_list) / n),
        seq_scans=int(sum(m.seq_scans for m in metrics_list) / n),
        index_scans=int(sum(m.index_scans for m in metrics_list) / n),
        plan_json=metrics_list[-1].plan_json,
    )


def _calc_improvements(metrics, baseline) -> dict:
    def pct(new, old):
        return round((old - new) / old * 100, 2) if old > 0 else 0.0

    return {
        "actual_time_ms": pct(metrics.actual_time_ms, baseline.actual_time_ms),
        "total_cost": pct(metrics.total_cost, baseline.total_cost),
        "buffer_hits": pct(baseline.buffer_hits, metrics.buffer_hits),  # more hits = better
        "seq_scans": pct(metrics.seq_scans, baseline.seq_scans),
        "index_scans": pct(baseline.index_scans, metrics.index_scans),  # more = better
    }


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_optimization_workflow(llm, db: PostgreSQLConnector):
    """
    Compile the LangGraph workflow with injected dependencies.
    Returns a callable that accepts an initial state dict.
    """
    parser = ExplainAnalyzeParser()

    # Bind dependencies into each node via closures
    async def _parse(state):        return await parse_query(state, db, parser)
    async def _optimize(state):     return await run_optimizer_agents(state, llm, db)
    async def _combine(state):      return await combine_optimizations(state, llm, db)
    async def _evaluate(state):     return await evaluate_proposals(state, db, parser)
    async def _score(state):        return await score_proposals(state, llm, db)
    async def _select(state):       return await select_winner(state)
    async def _report(state):       return await generate_report(state)

    workflow = StateGraph(dict)
    workflow.add_node("parse_query",          _parse)
    workflow.add_node("run_optimizer_agents", _optimize)
    workflow.add_node("combine_optimizations",_combine)
    workflow.add_node("evaluate_proposals",   _evaluate)
    workflow.add_node("score_proposals",      _score)
    workflow.add_node("select_winner",        _select)
    workflow.add_node("generate_report",      _report)

    workflow.set_entry_point("parse_query")
    workflow.add_edge("parse_query",           "run_optimizer_agents")
    workflow.add_edge("run_optimizer_agents",  "combine_optimizations")
    workflow.add_edge("combine_optimizations", "evaluate_proposals")
    workflow.add_edge("evaluate_proposals",    "score_proposals")
    workflow.add_edge("score_proposals",       "select_winner")
    workflow.add_edge("select_winner",         "generate_report")
    workflow.add_edge("generate_report",       END)

    return workflow.compile()
