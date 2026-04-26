# agents/master_agents/scoring_system.py
class MasterAgentsScoring:
  """
  Manages the scoring process by all master agents
  """
  def __init__(self, master_agents: List[BaseMasterAgent], db_connector):
      self.master_agents = master_agents
      self.db = db_connector
  
  async def calculate_final_score(
      self,
      proposal: QueryProposal,
      metrics: EvaluationMetrics,
      original_metrics: EvaluationMetrics
  ) -> float:
      """
      Get scores from all master agents, discard highest and lowest,
      then calculate the average of remaining scores
      """
      scores = []
      for agent in self.master_agents:
          score = await agent.score_proposal(proposal, metrics, original_metrics)
          scores.append(score)
      
      # Sort by score value
      scores.sort(key=lambda s: s.score)
      
      # Remove highest and lowest
      if len(scores) > 2:
          scores = scores[1:-1]
      
      # Calculate average of remaining scores
      if scores:
          return sum(s.score for s in scores) / len(scores)
      return 0.0