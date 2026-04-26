# agents/master_agents/master_agent_1.py
class MasterAgent1(BaseMasterAgent):
  def _build_system_prompt(self) -> str:
      base_prompt = super()._build_system_prompt()
      ##TODO: keep itearting this prompt is not enough for a master agent
      specialized_prompt = """
      Your specialty is evaluating index and JOIN optimizations together.
      
      FOCUS AREAS:
      - How index choices affect JOIN method selection
      - Balance between index creation cost and query performance gain
      - Identifying when JOIN reordering conflicts with index usage
      - Prioritizing optimizations with the largest performance impact
      
      You are more concerned with consistent performance than occasional peaks.
      """
      return f"{base_prompt}\n\n{specialized_prompt}"