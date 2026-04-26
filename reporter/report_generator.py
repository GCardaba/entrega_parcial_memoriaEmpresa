# reporter/report_generator.py
class ReportGenerator:
  def create_report(self, state: SystemState) -> OptimizationReport:
      winner = state.winner
      
      return OptimizationReport(
          summary=self._create_executive_summary(state),
          winner_analysis=self._analyze_winner(winner),
          optimization_explanations=self._format_explanations(
              winner.proposal.explanations
          ),
          comparison_table=self._build_comparison_table(state.evaluations),
          query_diff=self._highlight_differences(
              state.original_query, 
              winner.proposal.optimized_query
          ),
          execution_plans=self._format_plans(state.evaluations),
          master_agent_scores=self._format_scores(winner.master_agent_scores),
          charts=self._generate_performance_charts(state.evaluations)
      )
      
  def _format_explanations(self, explanations: List[OptimizationExplanation]) -> str:
      """Format optimization explanations in a user-friendly way"""
      formatted = []
      
      for i, exp in enumerate(explanations, 1):
          formatted.append(f"### Optimization {i}: {exp.technique}\n")
          formatted.append(f"**Why**: {exp.reason}\n")
          formatted.append(f"**Benefit**: {exp.expected_benefit}\n")
          
          if exp.risk_factor:
              formatted.append(f"**Risk Level**: {exp.risk_factor}/10\n")
              
          if exp.limitations:
              formatted.append("**Limitations**:\n")
              for limit in exp.limitations:
                  formatted.append(f"- {limit}\n")
          
          formatted.append("\n")
          
      return "".join(formatted)