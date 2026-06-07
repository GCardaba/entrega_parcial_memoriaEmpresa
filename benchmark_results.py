#!/usr/bin/env python3
"""
benchmark_results.py
Ejecuta el pipeline sobre 3 queries TPC-H y guarda los resultados en JSON.
Uso: venv/bin/python benchmark_results.py
"""
import asyncio, json, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from anthropic import AsyncAnthropic
from database.connector import PostgreSQLConnector
from database.explain_parser import ExplainAnalyzeParser
from orchestrator.workflow import build_optimization_workflow

# ── Queries TPC-H representativas ────────────────────────────────────────────
QUERIES = {
    "Q1_agregacion_lineitem": """
        SELECT
            l_returnflag,
            l_linestatus,
            SUM(l_quantity)        AS sum_qty,
            SUM(l_extendedprice)   AS sum_base_price,
            COUNT(*)               AS count_order
        FROM tpch.lineitem
        WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL '90 days'
        GROUP BY l_returnflag, l_linestatus
        ORDER BY l_returnflag, l_linestatus
    """,
    "Q3_join_cliente_pedido": """
        SELECT
            o.o_orderkey,
            SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue,
            o.o_orderdate,
            o.o_shippriority
        FROM tpch.customer c
        JOIN tpch.orders o   ON c.c_custkey  = o.o_custkey
        JOIN tpch.lineitem l ON o.o_orderkey = l.l_orderkey
        WHERE c.c_mktsegment = 'BUILDING'
          AND o.o_orderdate  < DATE '1995-03-15'
          AND l.l_shipdate   > DATE '1995-03-15'
        GROUP BY o.o_orderkey, o.o_orderdate, o.o_shippriority
        ORDER BY revenue DESC, o.o_orderdate
        LIMIT 10
    """,
    "Q5_subquery_correlacionada": """
        SELECT n.n_name, SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue
        FROM tpch.customer c
        JOIN tpch.orders o    ON c.c_custkey  = o.o_custkey
        JOIN tpch.lineitem l  ON o.o_orderkey = l.l_orderkey
        JOIN tpch.supplier s  ON l.l_suppkey  = s.s_suppkey
        JOIN tpch.nation n    ON c.c_nationkey = n.n_nationkey
                              AND s.s_nationkey = n.n_nationkey
        JOIN tpch.region r    ON n.n_regionkey = r.r_regionkey
        WHERE r.r_name = 'ASIA'
          AND o.o_orderdate >= DATE '1994-01-01'
          AND o.o_orderdate  < DATE '1994-01-01' + INTERVAL '1 year'
        GROUP BY n.n_name
        ORDER BY revenue DESC
    """,
}


async def run_query(name: str, sql: str, llm, db: PostgreSQLConnector) -> dict:
    print(f"\n{'='*60}")
    print(f"  Ejecutando: {name}")
    print(f"{'='*60}")
    t0 = time.time()

    app = build_optimization_workflow(llm, db)
    initial_state = {
        "session_id": f"benchmark_{name}",
        "original_query": sql.strip(),
        "schema_context": {},
        "baseline_metrics": None,
        "proposals": [],
        "combined_proposals": [],
        "evaluations": [],
        "winner": None,
        "report": None,
        "status": "pending",
    }

    result = await app.ainvoke(initial_state)
    elapsed = round(time.time() - t0, 1)

    report = result.get("report", {})
    winner = report.get("winner", {})
    baseline = result.get("baseline_metrics", {})
    comparison = report.get("comparison_table", [])

    out = {
        "query_name": name,
        "pipeline_time_s": elapsed,
        "baseline_time_ms": round(baseline.get("actual_time_ms", 0), 2),
        "winner_agent": winner.get("agent_id", "—"),
        "winner_time_ms": round(winner.get("metrics", {}).get("actual_time_ms", 0), 2),
        "winner_score": round(winner.get("final_score", 0), 2),
        "improvement_pct": winner.get("metrics", {}).get("improvement_vs_original", "—"),
        "comparison_table": comparison,
        "winning_strategy": winner.get("optimization_strategy", "—"),
        "explanations": report.get("explanations", []),
    }

    print(f"  ✓ Baseline:  {out['baseline_time_ms']} ms")
    print(f"  ✓ Ganador:   {out['winner_agent']}  →  {out['winner_time_ms']} ms  (score {out['winner_score']})")
    print(f"  ✓ Mejora:    {out['improvement_pct']}")
    print(f"  ✓ Tiempo pipeline: {elapsed}s")
    return out


async def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY no está configurada"); return
    llm = AsyncAnthropic(api_key=api_key)
    db  = PostgreSQLConnector()

    all_results = []
    for name, sql in QUERIES.items():
        try:
            r = await run_query(name, sql, llm, db)
            all_results.append(r)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ Error en {name}: {e}")
            all_results.append({"query_name": name, "error": str(e)})

    out_path = os.path.join(os.path.dirname(__file__), "entregables/benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Resultados guardados en: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
