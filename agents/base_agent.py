# agents/base_agent.py
from abc import ABC, abstractmethod
from typing import List
from models.agent_state import QueryProposal, AgentType, OptimizationExplanation

class BaseOptimizerAgent(ABC):
  def __init__(self, llm_client, db_connector, agent_type: AgentType):
      self.llm = llm_client
      self.db = db_connector
      self.agent_type = agent_type
      self.system_prompt = self._build_system_prompt()
  
  @abstractmethod
  def _build_system_prompt(self) -> str:
      """Each agent defines its specialization"""
  
  async def optimize(self, query: str, schema_context: dict) -> QueryProposal:
      context = self._prepare_context(query, schema_context)
      optimization_result = await self._call_llm(context)
      
      # Extract optimized query and explanations
      optimized_query = self._extract_optimized_query(optimization_result)
      explanations = self._extract_explanations(optimization_result)
      
      # Validate syntax before proposing
      validated_query = await self._validate_syntax(optimized_query)
      
      return self._build_proposal(query, validated_query, explanations)
  
  async def _validate_syntax(self, query: str) -> str:
      """Validate with EXPLAIN (without ANALYZE) before proposing"""
      try:
          await self.db.execute_explain(query)
          return query
      except Exception as e:
          return await self._fix_syntax(query, str(e))
  
  def _extract_optimized_query(self, llm_response: str) -> str:
      """Extract the optimized query from LLM response"""
      # Implementation to extract SQL query from response
      
  def _extract_explanations(self, llm_response: str) -> List[OptimizationExplanation]:
      """Extract optimization explanations from LLM response"""
      # Implementation to parse explanations