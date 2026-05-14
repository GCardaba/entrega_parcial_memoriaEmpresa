import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseOptimizerAgent
from models.agent_state import AgentType

SYSTEM_PROMPT = """
You are an expert in PostgreSQL index optimization.
Your responsibility is to analyze SQL queries and identify:
- Columns suitable for B-tree, Hash, GIN, GiST indexes
- Partial indexes for data subsets
- Composite indexes for multi-column queries
- Covering indexes to eliminate heap fetches

Given the schema and table statistics:
1. Propose necessary CREATE INDEX statements
2. Rewrite the query if applicable (e.g., using covering index)
3. Provide detailed explanations for each optimization:
 - WHY this index helps (selectivity, cardinality)
 - HOW it improves performance (reduced I/O, faster lookups)
 - WHAT specific operation benefits (filter, join, sort)
 - POTENTIAL DRAWBACKS (maintenance cost, storage)

FORMAT YOUR RESPONSE:
```sql
-- Optimized query
SELECT ...
EXPLANATIONS:

[Technique: B-tree index on column X]
Reason: High selectivity (only 2% of rows match typical predicates)
Benefit: Reduces scan from sequential to index-only
Trade-off: Adds 20MB storage and affects INSERT performance
[Technique: ...] ... """


class IndexOptimizerAgent(BaseOptimizerAgent):
    """Specialist in B-tree, Hash, GIN, GiST, partial, and covering indexes."""

    def __init__(self, llm_client, db_connector):
        super().__init__(llm_client, db_connector, AgentType.INDEX_OPTIMIZER)

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT