# models/agent_state.py
from pydantic import BaseModel
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime


class AgentType(Enum):
    INDEX_OPTIMIZER = "index_optimizer"
    JOIN_OPTIMIZER = "join_optimizer"
    QUERY_REWRITER = "query_rewriter"
    CTE_OPTIMIZER = "cte_optimizer"
    CACHE_OPTIMIZER = "cache_optimizer"
    MASTER_AGENT = "master_agent"


class OptimizationExplanation(BaseModel):
    """Detailed explanation of a single optimization applied by an agent."""
    technique: str
    reason: str
    expected_benefit: str
    risk_factor: Optional[float] = None
    limitations: Optional[List[str]] = None


class QueryProposal(BaseModel):
    agent_id: str
    agent_type: AgentType
    original_query: str
    optimized_query: str
    optimization_strategy: str
    explanations: List[OptimizationExplanation]
    expected_improvements: List[str]
    confidence_score: float
    timestamp: datetime


class EvaluationMetrics(BaseModel):
    total_cost: float
    actual_time_ms: float
    rows_processed: int
    buffer_hits: int
    seq_scans: int
    index_scans: int
    plan_json: List  # PostgreSQL EXPLAIN FORMAT JSON returns a list at the top level


class MasterAgentScore(BaseModel):
    master_agent_id: str
    score: float
    reasoning: str


class EvaluationResult(BaseModel):
    proposal: QueryProposal
    metrics: EvaluationMetrics
    improvement_vs_original: Dict[str, float]
    master_agent_scores: List[MasterAgentScore]
    final_score: float  # Trimmed mean after dropping highest and lowest MA scores


class SystemState(BaseModel):
    session_id: str
    original_query: str
    schema_context: dict
    baseline_metrics: Optional[EvaluationMetrics] = None
    proposals: List[QueryProposal] = []          # From optimizer agents
    combined_proposals: List[QueryProposal] = [] # From master agents
    evaluations: List[EvaluationResult] = []
    winner: Optional[EvaluationResult] = None
    report: Optional[Dict[str, Any]] = None
    status: str = "pending"
