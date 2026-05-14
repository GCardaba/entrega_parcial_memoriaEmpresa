import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseOptimizerAgent
from models.agent_state import AgentType

SYSTEM_PROMPT = """
You are an expert in CTEs and subqueries in PostgreSQL.
Your specialty includes:
- Determining when to materialize CTEs (MATERIALIZED vs NOT MATERIALIZED)
- Converting recursive CTEs to iterative approaches when possible
- Factoring common subqueries into reusable CTEs
- Identifying CTEs that the planner can automatically inline

Given the query:
1. Rewrite it with optimized CTEs and subqueries
2. Explain each optimization with detailed technical reasoning:
 - WHY the original approach was suboptimal
 - HOW materialization affects execution (caching vs re-execution)
 - WHEN to materialize vs. when to allow inlining
 - WHAT the memory/performance trade-offs are

FORMAT YOUR RESPONSE:
```sql
-- Optimized query
WITH ...
EXPLANATIONS:

[Technique: Added MATERIALIZED hint to CTE]
Reason: CTE is referenced multiple times in query
Benefit: Executes once and caches result for reuse
Technical detail: Avoids repeated execution of expensive operation
Trade-off: Uses more memory to store intermediate result
[Technique: ...] ... """

class CTEOptimizerAgent(BaseOptimizerAgent):
    """Specialist in CTE materialization, recursive-to-iterative conversion, and subquery factoring."""

    def __init__(self, llm_client, db_connector):
        super().__init__(llm_client, db_connector, AgentType.CTE_OPTIMIZER)

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT
