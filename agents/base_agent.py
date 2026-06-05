import sys
import os
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.agent_state import QueryProposal, AgentType, OptimizationExplanation


# Expected JSON schema that every optimizer agent must return.
# Written in English so the LLM produces consistent, parseable output.
RESPONSE_FORMAT_INSTRUCTIONS = """
You MUST respond with a single valid JSON object. No markdown, no prose outside the JSON.

{
  "optimized_query": "<complete, executable SQL query>",
  "optimization_strategy": "<one sentence describing the main approach taken>",
  "optimizations": [
    {
      "technique": "<short name of the technique, e.g. 'Covering index on orders.o_custkey'>",
      "reason": "<why the original query needed this, referencing schema or cardinality>",
      "expected_benefit": "<concrete metric expected to improve, e.g. 'Eliminates Seq Scan on orders (~150k rows)'>",
      "risk_factor": <float between 0.0 (no risk) and 1.0 (high risk)>,
      "limitations": ["<caveat 1>", "<caveat 2>"]
    }
  ],
  "confidence_score": <float between 0.0 and 1.0>
}

Rules:
- optimized_query must be valid PostgreSQL 16 SQL.
- If no improvement is possible, return the original query unchanged and explain why.
- List every distinct optimization as a separate object in the optimizations array.
- Do not include DDL (CREATE INDEX, ALTER TABLE) inside optimized_query unless it is a
  CREATE MATERIALIZED VIEW that replaces the query. Suggest DDL in the explanation instead.
"""


class BaseOptimizerAgent(ABC):
    def __init__(self, llm_client, db_connector, agent_type: AgentType):
        self.llm = llm_client
        self.db = db_connector
        self.agent_type = agent_type
        self.system_prompt = self._build_system_prompt()

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """Each subclass returns its specialization prompt (in English)."""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def optimize(self, query: str, schema_context: dict) -> QueryProposal:
        """
        Full optimization pipeline:
        1. Build context from query + schema.
        2. Call the LLM.
        3. Parse the structured response.
        4. Validate SQL syntax via EXPLAIN (no ANALYZE).
        5. Return a QueryProposal.
        """
        user_message = self._prepare_context(query, schema_context)
        raw_response = await self._call_llm(user_message)
        data = self._parse_llm_response(raw_response)

        optimized_query = data.get("optimized_query", query).strip()
        explanations = self._extract_explanations(data)

        # Validate SQL — if invalid, attempt one self-correction round.
        validated_query = await self._validate_syntax(optimized_query, query)

        return self._build_proposal(
            original_query=query,
            optimized_query=validated_query,
            strategy=data.get("optimization_strategy", ""),
            explanations=explanations,
            confidence_score=float(data.get("confidence_score", 0.5)),
        )

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, user_message: str) -> str:
        response = await self.llm.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=self.system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.2,
        )
        return response.content[0].text

    # ------------------------------------------------------------------
    # Context preparation
    # ------------------------------------------------------------------

    def _prepare_context(self, query: str, schema_context: dict) -> str:
        schema_text = self._format_schema(schema_context)
        return f"""
Analyze the following PostgreSQL query and apply your specialized optimizations.

QUERY TO OPTIMIZE:
```sql
{query}
```

SCHEMA CONTEXT:
{schema_text}

{RESPONSE_FORMAT_INSTRUCTIONS}
"""

    def _format_schema(self, schema_context: dict) -> str:
        lines = []
        for table, info in schema_context.items():
            cols = ", ".join(
                f"{c['name']} {c['type'].upper()}{'(nullable)' if c['nullable'] else ''}"
                for c in info.get("columns", [])
            )
            pk = info.get("primary_key")
            pk_str = f"  PK: {pk}" if pk else ""
            indexes = info.get("indexes", [])
            idx_str = (
                "\n  Indexes: " + ", ".join(i["name"] for i in indexes)
                if indexes
                else ""
            )
            lines.append(f"Table {table}:\n  Columns: {cols}{pk_str}{idx_str}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_llm_response(self, raw: str) -> dict:
        """
        Parse the LLM JSON response. Falls back gracefully if the model
        wraps the JSON in a markdown code block despite our instructions.
        """
        # Strip markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Last resort: try to extract the first {...} block
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
            return {}

    def _extract_explanations(self, data: dict) -> List[OptimizationExplanation]:
        result = []
        for opt in data.get("optimizations", []):
            result.append(
                OptimizationExplanation(
                    technique=opt.get("technique", ""),
                    reason=opt.get("reason", ""),
                    expected_benefit=opt.get("expected_benefit", ""),
                    risk_factor=float(opt.get("risk_factor", 0.0)),
                    limitations=opt.get("limitations", []),
                )
            )
        return result

    # ------------------------------------------------------------------
    # SQL validation and self-correction
    # ------------------------------------------------------------------

    async def _validate_syntax(self, optimized_query: str, original_query: str) -> str:
        """
        Run EXPLAIN (no ANALYZE) to catch syntax errors before proposing.
        On failure, ask the LLM to fix the issue once.
        On second failure, fall back to the original query.
        """
        try:
            await self.db.execute_explain(optimized_query)
            return optimized_query
        except Exception as first_error:
            fixed = await self._fix_syntax(optimized_query, str(first_error))
            try:
                await self.db.execute_explain(fixed)
                return fixed
            except Exception:
                # Safety fallback: return the original unchanged query.
                return original_query

    async def _fix_syntax(self, bad_query: str, error_message: str) -> str:
        """Ask the LLM to repair a query that failed EXPLAIN."""
        fix_prompt = f"""
The following PostgreSQL query contains a syntax or semantic error.
Fix it so it becomes valid PostgreSQL 16 SQL.

INVALID QUERY:
```sql
{bad_query}
```

ERROR FROM POSTGRESQL:
{error_message}

Respond with a single JSON object:
{{"fixed_query": "<corrected SQL query>"}}
"""
        response = await self.llm.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system="You are a PostgreSQL SQL syntax expert.",
            messages=[{"role": "user", "content": fix_prompt}],
            temperature=0.0,
        )
        data = json.loads(response.content[0].text)
        return data.get("fixed_query", bad_query)

    # ------------------------------------------------------------------
    # Proposal builder
    # ------------------------------------------------------------------

    def _build_proposal(
        self,
        original_query: str,
        optimized_query: str,
        strategy: str,
        explanations: List[OptimizationExplanation],
        confidence_score: float,
    ) -> QueryProposal:
        return QueryProposal(
            agent_id=self.agent_type.value,
            agent_type=self.agent_type,
            original_query=original_query,
            optimized_query=optimized_query,
            optimization_strategy=strategy,
            explanations=explanations,
            expected_improvements=[e.expected_benefit for e in explanations],
            confidence_score=max(0.0, min(1.0, confidence_score)),
            timestamp=datetime.now(timezone.utc),
        )
