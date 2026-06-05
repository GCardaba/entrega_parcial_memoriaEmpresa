"""
Shared pytest fixtures used across the test suite.
The mock LLM avoids real API calls; the DB connector hits real TPC-H PostgreSQL.
"""
import json
import os
import sys
import types
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.agent_state import (
    AgentType,
    EvaluationMetrics,
    EvaluationResult,
    MasterAgentScore,
    OptimizationExplanation,
    QueryProposal,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_NAME", "optimizer_db")
os.environ.setdefault("DB_USER", "optimizer_admin")
os.environ.setdefault("DB_PASSWORD", "practicas")


@pytest_asyncio.fixture
async def db():
    from database.connector import PostgreSQLConnector
    return PostgreSQLConnector()


# ---------------------------------------------------------------------------
# Sample TPC-H queries
# ---------------------------------------------------------------------------

SIMPLE_QUERY = """
SELECT c.c_name, SUM(o.o_totalprice)
FROM tpch.customer c
JOIN tpch.orders o ON c.c_custkey = o.o_custkey
WHERE c.c_mktsegment = 'BUILDING'
GROUP BY c.c_name
LIMIT 10
"""

CORRELATED_QUERY = """
SELECT p.p_name, p.p_retailprice
FROM tpch.part p
WHERE p.p_retailprice > (
    SELECT AVG(p2.p_retailprice)
    FROM tpch.part p2
    WHERE p2.p_type = p.p_type
)
"""

INVALID_QUERY = "SELECT * FROM nonexistent_table_xyz WHERE foo = bar"


@pytest.fixture
def simple_query():
    return SIMPLE_QUERY.strip()


@pytest.fixture
def correlated_query():
    return CORRELATED_QUERY.strip()


@pytest.fixture
def invalid_query():
    return INVALID_QUERY.strip()


# ---------------------------------------------------------------------------
# Real EXPLAIN ANALYZE JSON fixture (captured from live PostgreSQL 16 + TPC-H)
# Used in parser unit tests — no DB connection needed.
# ---------------------------------------------------------------------------

EXPLAIN_FIXTURE = [
    {
        "Plan": {
            "Node Type": "Limit",
            "Startup Cost": 5176.58,
            "Total Cost": 5176.71,
            "Plan Rows": 10,
            "Plan Width": 51,
            "Actual Startup Time": 61.985,
            "Actual Total Time": 61.990,
            "Actual Rows": 10,
            "Actual Loops": 1,
            "Shared Hit Blocks": 3013,
            "Shared Read Blocks": 0,
            "Plans": [
                {
                    "Node Type": "Aggregate",
                    "Startup Cost": 5176.58,
                    "Total Cost": 5215.47,
                    "Actual Rows": 10,
                    "Shared Hit Blocks": 3013,
                    "Shared Read Blocks": 0,
                    "Plans": [
                        {
                            "Node Type": "Hash Join",
                            "Startup Cost": 479.17,
                            "Total Cost": 5021.03,
                            "Actual Rows": 31264,
                            "Shared Hit Blocks": 3013,
                            "Shared Read Blocks": 0,
                            "Plans": [
                                {
                                    "Node Type": "Seq Scan",
                                    "Relation Name": "orders",
                                    "Startup Cost": 0.00,
                                    "Total Cost": 4148.00,
                                    "Actual Rows": 150000,
                                    "Shared Hit Blocks": 2648,
                                    "Shared Read Blocks": 0,
                                },
                                {
                                    "Node Type": "Hash",
                                    "Startup Cost": 440.28,
                                    "Total Cost": 440.28,
                                    "Actual Rows": 3111,
                                    "Shared Hit Blocks": 365,
                                    "Shared Read Blocks": 0,
                                    "Plans": [
                                        {
                                            "Node Type": "Bitmap Heap Scan",
                                            "Relation Name": "customer",
                                            "Startup Cost": 40.40,
                                            "Total Cost": 440.28,
                                            "Actual Rows": 3111,
                                            "Shared Hit Blocks": 365,
                                            "Shared Read Blocks": 0,
                                            "Plans": [
                                                {
                                                    "Node Type": "Bitmap Index Scan",
                                                    "Index Name": "idx_customer_mktsegment",
                                                    "Startup Cost": 0.00,
                                                    "Total Cost": 39.62,
                                                    "Actual Rows": 3111,
                                                    "Shared Hit Blocks": 5,
                                                    "Shared Read Blocks": 0,
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        },
        "Planning Time": 17.979,
        "Execution Time": 62.443,
    }
]


@pytest.fixture
def explain_fixture():
    return EXPLAIN_FIXTURE


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

def make_optimizer_response(query: str = None) -> str:
    return json.dumps({
        "optimized_query": query or SIMPLE_QUERY.strip(),
        "optimization_strategy": "Covering index on c_mktsegment to avoid heap fetch",
        "optimizations": [
            {
                "technique": "Covering index on customer(c_mktsegment, c_custkey, c_name)",
                "reason": "Seq Scan on customer reads all 15k rows to filter by c_mktsegment",
                "expected_benefit": "Eliminates Seq Scan, reduces rows read by ~85%",
                "risk_factor": 0.1,
                "limitations": ["Index maintenance cost on INSERT/UPDATE"],
            }
        ],
        "confidence_score": 0.82,
    })


def make_score_response(score: float = 7.5) -> str:
    return json.dumps({
        "score": score,
        "reasoning": "Good execution time improvement with low risk optimizations applied.",
    })


class MockMessages:
    def __init__(self, score: float = 7.5):
        self._score = score

    async def create(self, messages, **kwargs):
        user_content = messages[-1]["content"] if messages else ""
        content = (
            make_score_response(self._score)
            if "Score this query" in user_content
            else make_optimizer_response()
        )

        return types.SimpleNamespace(
            content=[types.SimpleNamespace(text=content)]
        )


class MockLLM:
    def __init__(self, score: float = 7.5):
        self.messages = MockMessages(score)


@pytest.fixture
def mock_llm():
    return MockLLM()


# ---------------------------------------------------------------------------
# Pre-built model instances
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_explanation():
    return OptimizationExplanation(
        technique="Covering index",
        reason="Avoids heap fetch for filtered rows",
        expected_benefit="Reduces I/O by 80%",
        risk_factor=0.1,
        limitations=["Extra write overhead"],
    )


@pytest.fixture
def sample_proposal(simple_query, sample_explanation):
    return QueryProposal(
        agent_id="index_optimizer",
        agent_type=AgentType.INDEX_OPTIMIZER,
        original_query=simple_query,
        optimized_query=simple_query,
        optimization_strategy="Covering index",
        explanations=[sample_explanation],
        expected_improvements=["Reduces I/O by 80%"],
        confidence_score=0.82,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_metrics():
    return EvaluationMetrics(
        total_cost=5176.71,
        actual_time_ms=62.443,
        rows_processed=10,
        buffer_hits=3013,
        seq_scans=1,
        index_scans=1,
        plan_json=EXPLAIN_FIXTURE,
    )


@pytest.fixture
def better_metrics():
    """Metrics representing a meaningfully faster query."""
    return EvaluationMetrics(
        total_cost=1200.0,
        actual_time_ms=15.0,
        rows_processed=10,
        buffer_hits=5000,
        seq_scans=0,
        index_scans=2,
        plan_json=EXPLAIN_FIXTURE,
    )


@pytest.fixture
def sample_evaluation(sample_proposal, sample_metrics):
    return EvaluationResult(
        proposal=sample_proposal,
        metrics=sample_metrics,
        improvement_vs_original={"actual_time_ms": 30.0, "total_cost": 20.0},
        master_agent_scores=[
            MasterAgentScore(master_agent_id="master_1", score=8.0, reasoning="Good"),
            MasterAgentScore(master_agent_id="master_2", score=6.0, reasoning="Decent"),
            MasterAgentScore(master_agent_id="master_3", score=7.0, reasoning="OK"),
            MasterAgentScore(master_agent_id="master_4", score=9.0, reasoning="Excellent"),
            MasterAgentScore(master_agent_id="master_5", score=5.0, reasoning="Conservative"),
        ],
        final_score=7.0,
    )
