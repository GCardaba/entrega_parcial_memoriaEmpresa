"""
SQL Query Optimizer — Streamlit UI
Calls the LangGraph workflow directly (no FastAPI needed).
"""
import asyncio
import os
import sys
import uuid

import streamlit as st

# Make project root importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from anthropic import AsyncAnthropic
from database.connector import PostgreSQLConnector
from orchestrator.workflow import build_optimization_workflow

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SQL Query Optimizer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Reduce vertical gaps in the sidebar
st.markdown("""
<style>
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.25rem;
    }
    section[data-testid="stSidebar"] .stTextInput,
    section[data-testid="stSidebar"] .stNumberInput,
    section[data-testid="stSidebar"] .stPassword {
        margin-bottom: -0.4rem;
    }
    section[data-testid="stSidebar"] h3 {
        margin-top: 0.5rem;
        margin-bottom: 0rem;
    }
    section[data-testid="stSidebar"] h1 {
        margin-bottom: 0.25rem;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Demo queries
# ---------------------------------------------------------------------------

DEMO_QUERIES = {
    "— Pick an example query —": "",

    # ── Simple ───────────────────────────────────────────────────────────────
    "JOIN customer + orders (simple)": """\
SELECT c.c_name, SUM(o.o_totalprice) AS total
FROM tpch.customer c
JOIN tpch.orders o ON c.c_custkey = o.o_custkey
WHERE c.c_mktsegment = 'BUILDING'
GROUP BY c.c_name
ORDER BY total DESC
LIMIT 20""",

    # ── Correlated subquery ───────────────────────────────────────────────────
    "Correlated subquery (part)": """\
SELECT p.p_name, p.p_retailprice
FROM tpch.part p
WHERE p.p_retailprice > (
    SELECT AVG(p2.p_retailprice)
    FROM tpch.part p2
    WHERE p2.p_type = p.p_type
)
ORDER BY p.p_retailprice DESC""",

    # ── TPC-H benchmarks ─────────────────────────────────────────────────────
    "TPC-H Q1 — lineitem aggregation": """\
SELECT
    l_returnflag,
    l_linestatus,
    SUM(l_quantity)                                       AS sum_qty,
    SUM(l_extendedprice)                                  AS sum_base_price,
    SUM(l_extendedprice * (1 - l_discount))               AS sum_disc_price,
    SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
    AVG(l_quantity)                                       AS avg_qty,
    AVG(l_extendedprice)                                  AS avg_price,
    AVG(l_discount)                                       AS avg_disc,
    COUNT(*)                                              AS count_order
FROM tpch.lineitem
WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL '90 day'
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus""",

    "TPC-H Q3 — shipping priority": """\
SELECT
    l.l_orderkey,
    SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue,
    o.o_orderdate,
    o.o_shippriority
FROM tpch.customer c
JOIN tpch.orders o   ON c.c_custkey  = o.o_custkey
JOIN tpch.lineitem l ON l.l_orderkey = o.o_orderkey
WHERE c.c_mktsegment = 'BUILDING'
  AND o.o_orderdate  < DATE '1995-03-15'
  AND l.l_shipdate   > DATE '1995-03-15'
GROUP BY l.l_orderkey, o.o_orderdate, o.o_shippriority
ORDER BY revenue DESC, o.o_orderdate
LIMIT 10""",

    "TPC-H Q5 — local supplier volume": """\
SELECT
    n.n_name,
    SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue
FROM tpch.customer c
JOIN tpch.orders   o ON c.c_custkey  = o.o_custkey
JOIN tpch.lineitem l ON l.l_orderkey = o.o_orderkey
JOIN tpch.supplier s ON l.l_suppkey  = s.s_suppkey
JOIN tpch.nation   n ON s.s_nationkey = n.n_nationkey
                     AND c.c_nationkey = n.n_nationkey
JOIN tpch.region   r ON n.n_regionkey = r.r_regionkey
WHERE r.r_name        = 'ASIA'
  AND o.o_orderdate  >= DATE '1994-01-01'
  AND o.o_orderdate   < DATE '1994-01-01' + INTERVAL '1 year'
GROUP BY n.n_name
ORDER BY revenue DESC""",

    "TPC-H Q7 — volume shipping between nations": """\
SELECT
    supp_nation,
    cust_nation,
    l_year,
    SUM(volume) AS revenue
FROM (
    SELECT
        n1.n_name                                         AS supp_nation,
        n2.n_name                                         AS cust_nation,
        EXTRACT(YEAR FROM l.l_shipdate)                   AS l_year,
        l.l_extendedprice * (1 - l.l_discount)            AS volume
    FROM tpch.supplier s
    JOIN tpch.lineitem l ON l.l_suppkey  = s.s_suppkey
    JOIN tpch.orders   o ON o.o_orderkey = l.l_orderkey
    JOIN tpch.customer c ON c.c_custkey  = o.o_custkey
    JOIN tpch.nation  n1 ON s.s_nationkey = n1.n_nationkey
    JOIN tpch.nation  n2 ON c.c_nationkey = n2.n_nationkey
    WHERE (
        (n1.n_name = 'FRANCE' AND n2.n_name = 'GERMANY')
        OR
        (n1.n_name = 'GERMANY' AND n2.n_name = 'FRANCE')
    )
      AND l.l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
) AS shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year""",

    # ── Subquery / EXISTS ─────────────────────────────────────────────────────
    "EXISTS — orders with large-discount items": """\
SELECT o.o_orderkey, o.o_totalprice, o.o_orderdate
FROM tpch.orders o
WHERE EXISTS (
    SELECT 1
    FROM tpch.lineitem l
    WHERE l.l_orderkey = o.o_orderkey
      AND l.l_discount > 0.08
      AND l.l_extendedprice > 50000
)
ORDER BY o.o_totalprice DESC
LIMIT 50""",

    "NOT IN — customers with no orders": """\
SELECT c.c_custkey, c.c_name, c.c_acctbal
FROM tpch.customer c
WHERE c.c_custkey NOT IN (
    SELECT DISTINCT o.o_custkey
    FROM tpch.orders o
    WHERE o.o_orderdate >= DATE '1993-01-01'
)
  AND c.c_acctbal > 0
ORDER BY c.c_acctbal DESC
LIMIT 30""",

    # ── Window functions ──────────────────────────────────────────────────────
    "Window — rank suppliers by revenue per nation": """\
SELECT
    n.n_name,
    s.s_name,
    SUM(l.l_extendedprice * (1 - l.l_discount)) AS revenue,
    RANK() OVER (
        PARTITION BY n.n_name
        ORDER BY SUM(l.l_extendedprice * (1 - l.l_discount)) DESC
    ) AS nation_rank
FROM tpch.supplier s
JOIN tpch.lineitem l ON l.l_suppkey  = s.s_suppkey
JOIN tpch.nation   n ON s.s_nationkey = n.n_nationkey
JOIN tpch.orders   o ON o.o_orderkey  = l.l_orderkey
WHERE o.o_orderdate BETWEEN DATE '1993-01-01' AND DATE '1997-12-31'
GROUP BY n.n_name, s.s_name
ORDER BY n.n_name, nation_rank
LIMIT 50""",

    "Window — running total of order revenue": """\
SELECT
    o.o_orderdate,
    o.o_totalprice,
    SUM(o.o_totalprice) OVER (
        ORDER BY o.o_orderdate
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM tpch.orders o
WHERE o.o_orderdate >= DATE '1995-01-01'
  AND o.o_orderdate <  DATE '1996-01-01'
ORDER BY o.o_orderdate""",

    # ── CTE ───────────────────────────────────────────────────────────────────
    "CTE — top customers by segment": """\
WITH ranked_customers AS (
    SELECT
        c.c_custkey,
        c.c_name,
        c.c_mktsegment,
        SUM(o.o_totalprice) AS lifetime_value
    FROM tpch.customer c
    JOIN tpch.orders o ON c.c_custkey = o.o_custkey
    GROUP BY c.c_custkey, c.c_name, c.c_mktsegment
),
segment_stats AS (
    SELECT
        c_mktsegment,
        AVG(lifetime_value) AS avg_ltv,
        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY lifetime_value) AS p90_ltv
    FROM ranked_customers
    GROUP BY c_mktsegment
)
SELECT
    rc.c_name,
    rc.c_mktsegment,
    rc.lifetime_value,
    ss.avg_ltv,
    ROUND((rc.lifetime_value / ss.avg_ltv - 1) * 100, 1) AS pct_above_avg
FROM ranked_customers rc
JOIN segment_stats ss ON rc.c_mktsegment = ss.c_mktsegment
WHERE rc.lifetime_value >= ss.p90_ltv
ORDER BY rc.c_mktsegment, rc.lifetime_value DESC""",
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Settings")

    st.subheader("Anthropic")
    api_key = st.text_input(
        "ANTHROPIC_API_KEY",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Required for the LLM agents to work.",
    )

    st.subheader("PostgreSQL")
    db_host = st.text_input("Host", value=os.getenv("DB_HOST", "localhost"))
    db_port = st.number_input("Port", value=int(os.getenv("DB_PORT", "5432")), step=1)
    db_name = st.text_input("Database", value=os.getenv("DB_NAME", "optimizer_db"))
    db_user = st.text_input("User", value=os.getenv("DB_USER", "optimizer_admin"))
    db_password = st.text_input(
        "Password",
        value=os.getenv("DB_PASSWORD", "practicas"),
        type="password",
    )
    db_schema = st.text_input("TPC-H Schema", value=os.getenv("DB_SCHEMA", "tpch"))

    st.divider()
    st.caption("Multi-Agent SQL Optimizer · TFG 2025")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine from sync Streamlit context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _diff_lines(original: str, optimized: str):
    """Return (removed, added) line lists for a simple visual diff."""
    orig_lines = set(l.strip() for l in original.splitlines() if l.strip())
    opt_lines  = set(l.strip() for l in optimized.splitlines() if l.strip())
    removed = orig_lines - opt_lines
    added   = opt_lines  - orig_lines
    return removed, added


def _score_color(score: float) -> str:
    if score >= 8:
        return "🟢"
    if score >= 6:
        return "🟡"
    return "🔴"


async def _run_pipeline(query: str, api_key: str, db_cfg: dict) -> dict:
    os.environ["ANTHROPIC_API_KEY"] = api_key
    llm = AsyncAnthropic(api_key=api_key)
    db  = PostgreSQLConnector(
        host=db_cfg["host"],
        port=db_cfg["port"],
        database=db_cfg["name"],
        user=db_cfg["user"],
        password=db_cfg["password"],
        schema=db_cfg["schema"],
    )
    initial_state = {
        "session_id": str(uuid.uuid4()),
        "original_query": query,
        "schema_context": {},
        "baseline_metrics": None,
        "proposals": [],
        "combined_proposals": [],
        "evaluations": [],
        "winner": None,
        "report": None,
        "status": "pending",
    }
    workflow = build_optimization_workflow(llm, db)
    return await workflow.ainvoke(initial_state)

# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("⚡ SQL Query Optimizer")
st.caption(
    "Multi-agent system: 5 specialist agents → 5 master agents → "
    "trim-mean scoring → winning query"
)

# --- Query input ---
col_left, col_right = st.columns([2, 1])

with col_right:
    selected = st.selectbox("Load example query", list(DEMO_QUERIES.keys()))

with col_left:
    if selected and DEMO_QUERIES[selected]:
        default_query = DEMO_QUERIES[selected]
    else:
        default_query = st.session_state.get("last_query", "")

    query_input = st.text_area(
        "SQL query to optimize",
        value=default_query,
        height=220,
        placeholder="SELECT ... FROM tpch.orders ...",
    )

run_btn = st.button("🚀 Optimize", type="primary", use_container_width=True)

# --- Validation ---
if run_btn:
    if not api_key:
        st.error("Please set your ANTHROPIC_API_KEY in the sidebar.")
        st.stop()
    if not query_input.strip():
        st.error("Enter or select a SQL query.")
        st.stop()

    st.session_state["last_query"] = query_input
    db_cfg = {
        "host": db_host,
        "port": int(db_port),
        "name": db_name,
        "user": db_user,
        "password": db_password,
        "schema": db_schema,
    }

    with st.spinner("Running multi-agent pipeline… (may take 30–90 s with a real API key)"):
        try:
            result = _run(
                _run_pipeline(query_input.strip(), api_key, db_cfg)
            )
            st.session_state["result"] = result
            st.session_state["query_used"] = query_input.strip()
        except Exception as exc:
            st.error(f"Pipeline error: {exc}")
            st.stop()

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

if "result" in st.session_state:
    result = st.session_state["result"]
    report = result.get("report") or {}
    winner = report.get("winner") or {}
    comparison = report.get("comparison_table") or []
    explanations_list = report.get("explanations") or []
    summary = report.get("summary") or ""
    original_query = st.session_state.get("query_used", "")
    optimized_query = winner.get("optimized_query", "")

    st.divider()
    st.subheader("📊 Results")

    # --- KPI row ---
    metrics = winner.get("metrics") or {}
    impr    = metrics.get("improvement_vs_original") or {}
    time_delta = impr.get("actual_time_ms", "")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Winning query", winner.get("agent_id", "?"))
    k2.metric("Final score", f"{winner.get('final_score', 0):.2f} / 10")
    k3.metric("Optimized time", f"{metrics.get('actual_time_ms', 0):.1f} ms", delta=time_delta, delta_color="inverse")
    k4.metric("LLM confidence", f"{winner.get('confidence_score', 0):.0%}")

    if summary:
        st.info(f"📋 {summary}")

    st.divider()

    tab_query, tab_compare, tab_explain, tab_raw = st.tabs(
        ["🏆 Optimized query", "📈 Agent comparison", "🔍 Explanations", "🗂️ Raw JSON"]
    )

    # --- Tab 1: winning query + diff ---
    with tab_query:
        col_orig, col_opt = st.columns(2)
        with col_orig:
            st.markdown("**Original query**")
            st.code(original_query, language="sql")
        with col_opt:
            st.markdown(f"**Optimized query** — `{winner.get('agent_id', '')}`")
            st.code(optimized_query, language="sql")

        removed, added = _diff_lines(original_query, optimized_query)
        if added or removed:
            with st.expander("Show changes (simplified diff)"):
                if added:
                    st.markdown("**Added / modified lines:**")
                    for line in sorted(added):
                        st.markdown(f"```+ {line}```")
                if removed:
                    st.markdown("**Removed / simplified lines:**")
                    for line in sorted(removed):
                        st.markdown(f"```- {line}```")

        st.markdown(f"**Strategy:** {winner.get('optimization_strategy', '—')}")
        st.markdown(f"**Confidence:** {winner.get('confidence_score', 0):.0%}")

    # --- Tab 2: comparison table ---
    with tab_compare:
        st.markdown("Each row is a master agent. The final score is the trimmed mean (highest and lowest scores are dropped).")

        if comparison:
            import pandas as pd
            df = pd.DataFrame(comparison)

            display_cols = {
                "rank": "Rank",
                "agent_id": "Master Agent",
                "final_score": "Final score",
                "actual_time_ms": "Time (ms)",
                "time_improvement_pct": "Time improvement (%)",
                "total_cost": "Planner cost",
                "seq_scans": "Seq scans",
                "index_scans": "Index scans",
            }
            df_show = df.rename(columns={k: v for k, v in display_cols.items() if k in df.columns})
            show_cols = [v for k, v in display_cols.items() if k in df.columns]
            df_show = df_show[show_cols]

            winner_id = winner.get("agent_id", "")

            def highlight_winner(row):
                color = "background-color: #1e3a2f" if row.get("Master Agent") == winner_id else ""
                return [color] * len(row)

            format_dict = {
                "Final score": "{:.2f}",
                "Time (ms)": "{:.1f}",
                "Time improvement (%)": "{:+.1f}",
                "Planner cost": "{:.1f}",
            }
            format_dict = {k: v for k, v in format_dict.items() if k in df_show.columns}

            st.dataframe(
                df_show.style.apply(highlight_winner, axis=1).format(format_dict, na_rep="—"),
                use_container_width=True,
            )
        else:
            st.info("No comparison data available.")

    # --- Tab 3: explanations ---
    with tab_explain:
        if explanations_list:
            for i, exp in enumerate(explanations_list, 1):
                risk = exp.get("risk_factor", 0)
                risk_icon = "🟢" if risk < 0.3 else ("🟡" if risk < 0.6 else "🔴")
                with st.expander(f"{i}. {exp.get('technique', 'Technique')}  {risk_icon} risk {risk:.1f}"):
                    st.markdown(f"**Reason:** {exp.get('reason', '—')}")
                    st.markdown(f"**Expected benefit:** {exp.get('expected_benefit', '—')}")
                    limitations = exp.get("limitations", [])
                    if limitations:
                        st.markdown("**Limitations:**")
                        for lim in limitations:
                            st.markdown(f"- {lim}")
        else:
            st.info("No detailed explanations available.")

    # --- Tab 4: raw JSON ---
    with tab_raw:
        st.json(report)
