# agents/master_agents/base_master_agent.py
class BaseMasterAgent:
  def __init__(self, llm_client, db_connector, agent_id: str):
      self.llm = llm_client
      self.db = db_connector
      self.agent_id = agent_id
      self.system_prompt = self._build_system_prompt()
  
  def _build_system_prompt(self) -> str:
      """Base system prompt for master agents"""
      return """
      You are a PostgreSQL query optimization expert tasked with:
      1. Analyzing multiple optimization proposals
      2. Combining compatible optimizations into a coherent solution
      3. Evaluating the quality of optimized queries
      
      You must carefully consider trade-offs between different optimization techniques.
      Produce a final optimized query that integrates compatible optimizations.
      """
  
  async def combine_optimizations(
      self, 
      original_query: str,
      proposals: List[QueryProposal],
      schema_context: dict
  ) -> QueryProposal:
      """Combine compatible optimizations from different proposals"""
      # Implementation to combine optimizations
      
  async def score_proposal(
      self,
      proposal: QueryProposal,
      metrics: EvaluationMetrics,
      original_metrics: EvaluationMetrics
  ) -> MasterAgentScore:
      """Score a proposal based on metrics and optimization quality"""
      # Implementation to score a proposal