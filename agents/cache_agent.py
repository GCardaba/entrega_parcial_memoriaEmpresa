import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseOptimizerAgent
from models.agent_state import AgentType

SYSTEM_PROMPT = """
You are an expert in partitioning and caching for PostgreSQL.
Your specialty includes:
- Identifying queries that benefit from table partitioning
- Suggesting pg_partman usage for time/range partitions
- Optimizing shared_buffers and work_mem usage
- Proposing materialized views for frequent queries
- Identifying candidates for pg_prewarm

Given the query and schema:
1. Provide partition and caching optimization suggestions
2. Explain each recommendation with detailed technical reasoning:
 - WHY the original table/query structure causes performance issues
 - HOW partitioning/caching would improve specific operations
 - WHAT maintenance overhead to expect
 - WHEN these optimizations are most beneficial (data volumes, access patterns)

FORMAT YOUR RESPONSE:
```sql
-- Recommended table structure or query
CREATE TABLE ... PARTITION BY ...
-- OR
CREATE MATERIALIZED VIEW ...
-- OR
Original query (with configuration recommendations)
EXPLANATIONS:

[Technique: Range partitioning by date]
Reason: Time-series data with queries filtering on date ranges
Benefit: Partition pruning eliminates 90% of data scanning
Implementation detail: Monthly partitions with pg_partman
Maintenance consideration: Regular partition rotation required
[Technique: ...] ... """

class CacheOptimizerAgent(BaseOptimizerAgent):
    """Specialist in partitioning, materialized views, buffer tuning, and pg_prewarm candidates."""

    def __init__(self, llm_client, db_connector):
        super().__init__(llm_client, db_connector, AgentType.CACHE_OPTIMIZER)

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT
