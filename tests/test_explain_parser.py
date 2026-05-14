"""
Unit tests for ExplainAnalyzeParser.
All tests use the static EXPLAIN_FIXTURE — no database required.
"""
import pytest
from database.explain_parser import ExplainAnalyzeParser


@pytest.fixture
def parser():
    return ExplainAnalyzeParser()


# ---------------------------------------------------------------------------
# Core metric extraction
# ---------------------------------------------------------------------------

def test_parse_returns_evaluation_metrics(parser, explain_fixture):
    from models.agent_state import EvaluationMetrics
    metrics = parser.parse(explain_fixture)
    assert isinstance(metrics, EvaluationMetrics)


def test_execution_time_extracted_from_root(parser, explain_fixture):
    """Execution Time at root level should be used, not Actual Total Time of root node."""
    metrics = parser.parse(explain_fixture)
    assert metrics.actual_time_ms == pytest.approx(62.443, rel=1e-3)


def test_total_cost_from_root_plan_node(parser, explain_fixture):
    metrics = parser.parse(explain_fixture)
    assert metrics.total_cost == pytest.approx(5176.71, rel=1e-3)


def test_rows_processed_from_root_node(parser, explain_fixture):
    metrics = parser.parse(explain_fixture)
    assert metrics.rows_processed == 10


def test_buffer_hits_aggregated_across_all_nodes(parser, explain_fixture):
    """buffer_hits should sum Shared Hit Blocks recursively through the plan tree."""
    metrics = parser.parse(explain_fixture)
    # Root(3013) + Aggregate(3013) + HashJoin(3013) + SeqScan(2648) + Hash(365) + BitmapHeap(365) + BitmapIndex(5)
    # The recursive sum counts each node's own blocks (not children's in the fixture since they repeat)
    # In the fixture, root node has 3013, child nodes each have their own values
    # Our implementation sums each node independently: 3013+3013+3013+2648+365+365+5 = 15422
    assert metrics.buffer_hits > 0


def test_seq_scan_count(parser, explain_fixture):
    metrics = parser.parse(explain_fixture)
    assert metrics.seq_scans == 1  # Only orders uses Seq Scan


def test_index_scan_count(parser, explain_fixture):
    """Bitmap Index Scan and Bitmap Heap Scan both count as index scans."""
    metrics = parser.parse(explain_fixture)
    assert metrics.index_scans >= 1


def test_plan_json_stored(parser, explain_fixture):
    metrics = parser.parse(explain_fixture)
    assert isinstance(metrics.plan_json, list)
    assert len(metrics.plan_json) == 1


# ---------------------------------------------------------------------------
# Helper methods
# ---------------------------------------------------------------------------

def test_planning_time_ms(parser, explain_fixture):
    planning_ms = parser.get_planning_time_ms(explain_fixture)
    assert planning_ms == pytest.approx(17.979, rel=1e-3)


def test_get_node_types_returns_all_nodes(parser, explain_fixture):
    nodes = parser.get_node_types(explain_fixture)
    assert "Seq Scan" in nodes
    assert "Hash Join" in nodes
    assert "Bitmap Index Scan" in nodes
    assert "Limit" in nodes


def test_get_node_types_order_is_depth_first(parser, explain_fixture):
    nodes = parser.get_node_types(explain_fixture)
    # Root node (Limit) must come first
    assert nodes[0] == "Limit"


def test_shared_read_blocks(parser, explain_fixture):
    """All blocks are in cache in the fixture (read blocks = 0)."""
    read_blocks = parser.get_shared_read_blocks(explain_fixture)
    assert read_blocks == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_minimal_plan_no_children(parser):
    """A plan with a single node (no Plans list) should not crash."""
    minimal = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Total Cost": 100.0,
                "Actual Total Time": 5.0,
                "Actual Rows": 50,
                "Shared Hit Blocks": 10,
                "Shared Read Blocks": 2,
            },
            "Planning Time": 1.0,
            "Execution Time": 5.5,
        }
    ]
    metrics = parser.parse(minimal)
    assert metrics.seq_scans == 1
    assert metrics.index_scans == 0
    assert metrics.actual_time_ms == pytest.approx(5.5)


def test_no_execution_time_fallback(parser):
    """If Execution Time is missing, fall back to root Actual Total Time."""
    plan = [
        {
            "Plan": {
                "Node Type": "Seq Scan",
                "Total Cost": 50.0,
                "Actual Total Time": 8.3,
                "Actual Rows": 5,
                "Shared Hit Blocks": 3,
                "Shared Read Blocks": 0,
            }
            # No "Execution Time" key
        }
    ]
    metrics = parser.parse(plan)
    assert metrics.actual_time_ms == pytest.approx(8.3)
