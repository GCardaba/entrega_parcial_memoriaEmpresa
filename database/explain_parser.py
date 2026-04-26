# database/explain_parser.py
class ExplainAnalyzeParser:
  def parse(self, explain_json: dict) -> EvaluationMetrics:
      return EvaluationMetrics(
          total_cost=self._extract_total_cost(explain_json),
          actual_time_ms=self._extract_actual_time(explain_json),
          rows_processed=self._extract_rows(explain_json),
          buffer_hits=self._extract_buffers(explain_json),
          seq_scans=self._count_seq_scans(explain_json),
          index_scans=self._count_index_scans(explain_json),
          nested_loops=self._count_nested_loops(explain_json),
          node_breakdown=self._extract_nodes(explain_json)
      )