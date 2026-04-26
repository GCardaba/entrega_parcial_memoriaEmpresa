# orchestrator/workflow.py
from langgraph.graph import StateGraph, END

def build_optimization_workflow():
  workflow = StateGraph(SystemState)
  
  # Graph nodes
  workflow.add_node("parse_query", parse_and_extract_schema)
  workflow.add_node("run_optimizer_agents", run_all_optimizer_agents)
  workflow.add_node("combine_optimizations", run_master_agents_combination)
  workflow.add_node("evaluate_proposals", evaluate_all_proposals)
  workflow.add_node("score_proposals", score_all_proposals)
  workflow.add_node("select_winner", select_best_proposal)
  workflow.add_node("generate_report", report_generator.create_report)
  
  # Edges
  workflow.set_entry_point("parse_query")
  workflow.add_edge("parse_query", "run_optimizer_agents")
  workflow.add_edge("run_optimizer_agents", "combine_optimizations")
  workflow.add_edge("combine_optimizations", "evaluate_proposals")
  workflow.add_edge("evaluate_proposals", "score_proposals")
  workflow.add_edge("score_proposals", "select_winner")
  workflow.add_edge("select_winner", "generate_report")
  workflow.add_edge("generate_report", END)
  
  return workflow.compile()

# Run optimizer agents in parallel
async def run_all_optimizer_agents(state: SystemState) -> SystemState:
  agents = [
      IndexOptimizerAgent(),
      JoinOptimizerAgent(),
      QueryRewriterAgent(),
      CTEOptimizerAgent(),
      CacheOptimizerAgent()
  ]
  
  # Execute all in parallel
  proposals = await asyncio.gather(*[
      agent.optimize(state.original_query, state.schema_context)
      for agent in agents
  ])
  
  state.proposals = list(proposals)
  return state

# Master agents combine optimizations
async def run_master_agents_combination(state: SystemState) -> SystemState:
  master_agents = [
      MasterAgent1(),
      MasterAgent2(),
      MasterAgent3(),
      MasterAgent4(),
      MasterAgent5()
  ]
  
  # Each master agent combines optimizations
  combined_proposals = await asyncio.gather(*[
      agent.combine_optimizations(
          state.original_query,
          state.proposals,
          state.schema_context
      )
      for agent in master_agents
  ])
  
  state.combined_proposals = list(combined_proposals)
  return state