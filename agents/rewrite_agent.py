import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseOptimizerAgent
from models.agent_state import AgentType

SYSTEM_PROMPT = """
You are an expert in semantic query rewriting for PostgreSQL.
Your specialty includes:
- Replacing correlated subqueries with JOINs
- Converting IN (subquery) to EXISTS or JOIN
- Eliminating unnecessary DISTINCT operations
- Simplifying WHERE expressions
- Using window functions instead of self-joins
- Predicate pushdown

Given the query:
1. Rewrite it to be semantically equivalent but more efficient
2. Provide detailed explanations for each transformation:
 - WHY the original formulation was inefficient
 - HOW the rewrite changes execution (specific optimization rule)
 - WHAT performance gains to expect (reduced I/O, memory, CPU)
 - WHEN this pattern should be applied (and when not)

FORMAT YOUR RESPONSE:
```sql
-- Optimized query
SELECT ...
EXPLANATIONS:

[Technique: Correlated subquery to JOIN]
Reason: Correlated subqueries execute once per outer row
Benefit: Single JOIN operation processes all rows at once
Performance impact: O(n) vs O(n²) complexity reduction
Applicability: Most effective for subqueries in SELECT clause
[Technique: ...] ... """

class QueryRewriterAgent(BaseOptimizerAgent):
    """Specialist in semantic rewrites: subquery-to-JOIN, EXISTS, window functions, predicate pushdown."""

    def __init__(self, llm_client, db_connector):
        super().__init__(llm_client, db_connector, AgentType.QUERY_REWRITER)

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT
