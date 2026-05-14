import sys
import os
from abc import ABC, abstractmethod
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models.agent_state import (
    QueryProposal,
    EvaluationMetrics,
    MasterAgentScore,
    AgentType,
    OptimizationExplanation,
)
from datetime import datetime, timezone


class BaseMasterAgent(ABC):
    def __init__(self, llm_client, db_connector, agent_id: str):
        self.llm = llm_client
        self.db = db_connector
        self.agent_id = agent_id
        self.system_prompt = self._build_system_prompt()

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Each master agent defines its combination and scoring strategy."""

    async def combine_optimizations(
        self,
        original_query: str,
        proposals: List[QueryProposal],
        schema_context: dict,
    ) -> QueryProposal:
        """
        Receive the 5 optimizer proposals and produce one pre-final combined query.
        Each master agent applies its own strategy to select and merge optimizations.
        """
        proposals_text = self._format_proposals(proposals)
        schema_text = self._format_schema(schema_context)

        user_message = f"""
Original query:
```sql
{original_query}
```

Schema context:
{schema_text}

Optimization proposals from specialist agents:
{proposals_text}

Combine the compatible optimizations according to your strategy and produce a single
pre-final optimized query with consolidated explanations.

Respond ONLY with valid JSON in this exact format:
{{
  "optimized_query": "<complete SQL query here>",
  "optimization_strategy": "<one sentence describing your combination strategy>",
  "optimizations": [
    {{
      "technique": "<name of technique>",
      "reason": "<why this technique applies to this query>",
      "expected_benefit": "<what specific metric improves and by how much>",
      "risk_factor": <float 0.0-1.0>,
      "limitations": ["<limitation 1>", "<limitation 2>"]
    }}
  ],
  "confidence_score": <float 0.0-1.0>
}}
"""
        response = await self.llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

        import json
        data = json.loads(response.choices[0].message.content)

        explanations = [
            OptimizationExplanation(
                technique=opt["technique"],
                reason=opt["reason"],
                expected_benefit=opt["expected_benefit"],
                risk_factor=opt.get("risk_factor"),
                limitations=opt.get("limitations", []),
            )
            for opt in data.get("optimizations", [])
        ]

        return QueryProposal(
            agent_id=self.agent_id,
            agent_type=AgentType.MASTER_AGENT,
            original_query=original_query,
            optimized_query=data["optimized_query"],
            optimization_strategy=data.get("optimization_strategy", ""),
            explanations=explanations,
            expected_improvements=[e.expected_benefit for e in explanations],
            confidence_score=data.get("confidence_score", 0.5),
            timestamp=datetime.now(timezone.utc),
        )

    async def score_proposal(
        self,
        proposal: QueryProposal,
        metrics: EvaluationMetrics,
        original_metrics: EvaluationMetrics,
    ) -> MasterAgentScore:
        """
        Score a pre-final proposal from 0 to 10 using this agent's scoring strategy.
        """
        time_improvement = (
            (original_metrics.actual_time_ms - metrics.actual_time_ms)
            / original_metrics.actual_time_ms
            * 100
            if original_metrics.actual_time_ms > 0
            else 0.0
        )
        cost_improvement = (
            (original_metrics.total_cost - metrics.total_cost)
            / original_metrics.total_cost
            * 100
            if original_metrics.total_cost > 0
            else 0.0
        )

        user_message = f"""
You are scoring a pre-final optimized SQL query.

Original metrics:
- Execution time: {original_metrics.actual_time_ms:.2f} ms
- Planner cost: {original_metrics.total_cost:.2f}
- Seq scans: {original_metrics.seq_scans}
- Index scans: {original_metrics.index_scans}
- Buffer hits: {original_metrics.buffer_hits}

Pre-final query metrics after EXPLAIN ANALYZE:
- Execution time: {metrics.actual_time_ms:.2f} ms  ({time_improvement:+.1f}% vs original)
- Planner cost: {metrics.total_cost:.2f}  ({cost_improvement:+.1f}% vs original)
- Seq scans: {metrics.seq_scans}
- Index scans: {metrics.index_scans}
- Buffer hits: {metrics.buffer_hits}

Applied optimizations:
{self._format_explanations(proposal.explanations)}

Pre-final query:
```sql
{proposal.optimized_query}
```

Score this query from 0 to 10 based on your evaluation strategy.
Consider: performance gain, plan efficiency, semantic correctness, optimization quality, and risk.

Respond ONLY with valid JSON:
{{"score": <float 0-10>, "reasoning": "<2-3 sentence explanation of the score>"}}
"""
        response = await self.llm.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        import json
        data = json.loads(response.choices[0].message.content)

        return MasterAgentScore(
            master_agent_id=self.agent_id,
            score=float(data["score"]),
            reasoning=data["reasoning"],
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _format_proposals(self, proposals: List[QueryProposal]) -> str:
        parts = []
        for i, p in enumerate(proposals, 1):
            explanations = "\n".join(
                f"  - [{e.technique}] {e.reason} → {e.expected_benefit}"
                for e in p.explanations
            )
            parts.append(
                f"--- Proposal {i} ({p.agent_type.value}, confidence={p.confidence_score:.2f}) ---\n"
                f"Strategy: {p.optimization_strategy}\n"
                f"Optimized query:\n```sql\n{p.optimized_query}\n```\n"
                f"Explanations:\n{explanations}"
            )
        return "\n\n".join(parts)

    def _format_schema(self, schema_context: dict) -> str:
        lines = []
        for table, info in schema_context.items():
            cols = ", ".join(
                f"{c['name']} ({c['type']})" for c in info.get("columns", [])
            )
            indexes = ", ".join(i["name"] for i in info.get("indexes", []))
            lines.append(f"Table {table}: [{cols}]  Indexes: [{indexes}]")
        return "\n".join(lines)

    def _format_explanations(self, explanations: List[OptimizationExplanation]) -> str:
        return "\n".join(
            f"- [{e.technique}] {e.reason} → {e.expected_benefit} (risk={e.risk_factor})"
            for e in explanations
        )
