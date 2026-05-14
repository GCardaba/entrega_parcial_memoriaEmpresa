import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.agent_state import EvaluationMetrics


class ExplainAnalyzeParser:
    """
    Parses the JSON output of EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) from PostgreSQL.

    The top-level structure is:
      [
        {
          "Plan": { ... },
          "Planning Time": float,   # ms
          "Execution Time": float   # ms
        }
      ]
    """

    def parse(self, explain_json: list) -> EvaluationMetrics:
        root = explain_json[0]
        plan_node = root["Plan"]

        # PostgreSQL index node types: Index Scan, Index Only Scan, Bitmap Index Scan
        index_scans = (
            self._count_node_type(plan_node, "Index Scan")
            + self._count_node_type(plan_node, "Index Only Scan")
            + self._count_node_type(plan_node, "Bitmap Index Scan")
        )
        return EvaluationMetrics(
            total_cost=self._extract_total_cost(plan_node),
            actual_time_ms=self._extract_actual_time(root),
            rows_processed=self._extract_rows(plan_node),
            buffer_hits=self._extract_buffer_hits(plan_node),
            seq_scans=self._count_node_type(plan_node, "Seq Scan"),
            index_scans=index_scans,
            plan_json=explain_json,
        )

    # ------------------------------------------------------------------
    # Top-level extractors
    # ------------------------------------------------------------------

    def _extract_total_cost(self, plan_node: dict) -> float:
        return float(plan_node.get("Total Cost", 0.0))

    def _extract_actual_time(self, root: dict) -> float:
        """
        'Execution Time' at the root level is the most accurate wall-clock figure.
        Falls back to the root plan node's Actual Total Time.
        """
        if "Execution Time" in root:
            return float(root["Execution Time"])
        return float(root["Plan"].get("Actual Total Time", 0.0))

    def _extract_rows(self, plan_node: dict) -> int:
        """Actual rows returned by the root node (after any LIMIT)."""
        return int(plan_node.get("Actual Rows", 0))

    def _extract_buffer_hits(self, plan_node: dict) -> int:
        """
        Aggregate Shared Hit Blocks across every node in the tree.
        Shared Read Blocks (cold reads) are intentionally excluded here;
        they matter for I/O cost analysis, not cache hit count.
        """
        return self._sum_field_recursive(plan_node, "Shared Hit Blocks")

    # ------------------------------------------------------------------
    # Tree-walking helpers
    # ------------------------------------------------------------------

    def _count_node_type(self, node: dict, node_type: str) -> int:
        count = 1 if node.get("Node Type") == node_type else 0
        for child in node.get("Plans", []):
            count += self._count_node_type(child, node_type)
        return count

    def _sum_field_recursive(self, node: dict, field: str) -> int:
        total = int(node.get(field, 0))
        for child in node.get("Plans", []):
            total += self._sum_field_recursive(child, field)
        return total

    # ------------------------------------------------------------------
    # Convenience helpers for external use
    # ------------------------------------------------------------------

    def get_planning_time_ms(self, explain_json: list) -> float:
        return float(explain_json[0].get("Planning Time", 0.0))

    def get_shared_read_blocks(self, explain_json: list) -> int:
        """Cold disk reads — useful for I/O cost analysis."""
        return self._sum_field_recursive(explain_json[0]["Plan"], "Shared Read Blocks")

    def get_node_types(self, explain_json: list) -> list[str]:
        """Return all node types present in the plan (for display in reports)."""
        nodes: list[str] = []
        self._collect_node_types(explain_json[0]["Plan"], nodes)
        return nodes

    def _collect_node_types(self, node: dict, result: list) -> None:
        result.append(node.get("Node Type", "Unknown"))
        for child in node.get("Plans", []):
            self._collect_node_types(child, result)
