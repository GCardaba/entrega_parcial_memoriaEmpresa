# agents/judge_agent.py
# agents/judge_agent.py
class JudgeAgent:
  """
  Evalúa propuestas usando métricas reales de PostgreSQL.
  Combina métricas objetivas + análisis LLM del plan de ejecución.
  """
  
  SCORING_WEIGHTS = {
      "actual_time_ms": 0.40,      # Tiempo real → máxima prioridad
      "total_cost": 0.25,           # Costo del planner
      "buffer_hits_ratio": 0.20,    # Eficiencia de caché
      "seq_scan_penalty": 0.10,     # Penalizar Seq Scans evitables
      "plan_complexity": 0.05       # Simplicidad del plan
  }
  
  async def evaluate_all(
      self, 
      proposals: list[QueryProposal],
      original_metrics: EvaluationMetrics
  ) -> list[EvaluationResult]:
      
      results = []
      for proposal in proposals:
          # 1. Ejecutar EXPLAIN ANALYZE real
          metrics = await self._run_explain_analyze(proposal.optimized_query)
          
          # 2. Calcular mejora porcentual vs original
          improvements = self._calculate_improvements(metrics, original_metrics)
          
          # 3. Score compuesto
          score = self._calculate_composite_score(improvements)
          
          # 4. LLM analiza el plan de ejecución
          reasoning = await self._analyze_plan_with_llm(
              proposal, metrics, improvements
          )
          
          results.append(EvaluationResult(
              proposal=proposal,
              metrics=metrics,
              improvement_vs_original=improvements,
              final_score=score,
              judge_reasoning=reasoning
          ))
      
      return sorted(results, key=lambda x: x.final_score, reverse=True)
  
  def _calculate_composite_score(self, improvements: dict) -> float:
      score = 0.0
      for metric, weight in self.SCORING_WEIGHTS.items():
          improvement = improvements.get(metric, 0.0)
          score += weight * max(improvement, -100)  # Cap penalizaciones
      return score

async def _run_explain_analyze_stable( self, query: str, runs: int = 3) -> EvaluationMetrics:
    """
    Ejecuta N veces y promedia para reducir varianza
    de tiempos por I/O y caché fría
    """
    # Primera ejecución: calentar caché
    await self.db.execute_query(query)
    
    # Ejecutar N veces y promediar
    metrics_list = []
    for _ in range(runs):
        metrics = await self.db.execute_explain_analyze(query)
        metrics_list.append(metrics)
    
    return self._average_metrics(metrics_list)