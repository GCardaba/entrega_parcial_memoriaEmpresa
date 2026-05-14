import sys
import os
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.agent_state import SystemState, EvaluationResult, OptimizationExplanation


class ReportGenerator:
    def create_report(self, state: SystemState) -> dict:
        """
        Build a structured report dict from the completed SystemState.
        Returns plain Python dict so it serialises cleanly through FastAPI.
        """
        winner = state.winner
        evaluations = state.evaluations

        return {
            "summary": self._create_executive_summary(state),
            "winner": {
                "agent_id": winner.proposal.agent_id,
                "optimized_query": winner.proposal.optimized_query,
                "optimization_strategy": winner.proposal.optimization_strategy,
                "confidence_score": winner.proposal.confidence_score,
                "final_score": winner.final_score,
                "metrics": self._format_metrics(winner),
                "master_agent_scores": self._format_scores(winner.master_agent_scores),
            },
            "explanations": self._format_explanations(winner.proposal.explanations),
            "comparison_table": self._build_comparison_table(evaluations),
            "original_query": state.original_query,
            "query_diff": self._highlight_differences(
                state.original_query, winner.proposal.optimized_query
            ),
        }

    # ------------------------------------------------------------------

    def _create_executive_summary(self, state: SystemState) -> str:
        winner = state.winner
        time_imp = winner.improvement_vs_original.get("actual_time_ms", 0)
        cost_imp = winner.improvement_vs_original.get("total_cost", 0)
        n_opts = len(winner.proposal.explanations)
        return (
            f"The winning query (from {winner.proposal.agent_id}) achieves a "
            f"{time_imp:+.1f}% execution time change and {cost_imp:+.1f}% planner cost change "
            f"over the original, applying {n_opts} optimization(s). "
            f"Final score: {winner.final_score:.2f}/10."
        )

    def _format_metrics(self, ev: EvaluationResult) -> dict:
        return {
            "actual_time_ms": round(ev.metrics.actual_time_ms, 3),
            "total_cost": round(ev.metrics.total_cost, 2),
            "rows_processed": ev.metrics.rows_processed,
            "buffer_hits": ev.metrics.buffer_hits,
            "seq_scans": ev.metrics.seq_scans,
            "index_scans": ev.metrics.index_scans,
            "improvement_vs_original": {
                k: f"{v:+.1f}%" for k, v in ev.improvement_vs_original.items()
            },
        }

    def _format_explanations(self, explanations: List[OptimizationExplanation]) -> list:
        result = []
        for i, exp in enumerate(explanations, 1):
            entry = {
                "number": i,
                "technique": exp.technique,
                "reason": exp.reason,
                "expected_benefit": exp.expected_benefit,
                "risk_factor": exp.risk_factor,
                "limitations": exp.limitations or [],
            }
            result.append(entry)
        return result

    def _format_scores(self, scores: list) -> list:
        return [
            {
                "master_agent_id": s.master_agent_id,
                "score": round(s.score, 2),
                "reasoning": s.reasoning,
            }
            for s in scores
        ]

    def _build_comparison_table(self, evaluations: List[EvaluationResult]) -> list:
        rows = []
        ranked = sorted(evaluations, key=lambda e: e.final_score, reverse=True)
        for rank, ev in enumerate(ranked, 1):
            rows.append({
                "rank": rank,
                "agent_id": ev.proposal.agent_id,
                "actual_time_ms": round(ev.metrics.actual_time_ms, 3),
                "total_cost": round(ev.metrics.total_cost, 2),
                "seq_scans": ev.metrics.seq_scans,
                "index_scans": ev.metrics.index_scans,
                "time_improvement_pct": ev.improvement_vs_original.get("actual_time_ms", 0),
                "final_score": round(ev.final_score, 2),
            })
        return rows

    def _highlight_differences(self, original: str, optimized: str) -> dict:
        """Return both queries side by side for display."""
        return {
            "original": original.strip(),
            "optimized": optimized.strip(),
        }
