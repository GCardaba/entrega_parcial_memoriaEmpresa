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

# ---------------------------------------------------------------------------
# Demo queries
# ---------------------------------------------------------------------------

DEMO_QUERIES = {
    "— Elige una query de ejemplo —": "",
    "JOIN customer + orders (simple)": """\
SELECT c.c_name, SUM(o.o_totalprice) AS total
FROM tpch.customer c
JOIN tpch.orders o ON c.c_custkey = o.o_custkey
WHERE c.c_mktsegment = 'BUILDING'
GROUP BY c.c_name
ORDER BY total DESC
LIMIT 20""",
    "Subconsulta correlacionada (part)": """\
SELECT p.p_name, p.p_retailprice
FROM tpch.part p
WHERE p.p_retailprice > (
    SELECT AVG(p2.p_retailprice)
    FROM tpch.part p2
    WHERE p2.p_type = p.p_type
)
ORDER BY p.p_retailprice DESC""",
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
}

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("⚙️ Configuración")

    st.subheader("Anthropic")
    api_key = st.text_input(
        "ANTHROPIC_API_KEY",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Necesaria para que los agentes LLM funcionen.",
    )

    st.subheader("PostgreSQL")
    db_host = st.text_input("Host", value=os.getenv("DB_HOST", "localhost"))
    db_port = st.number_input("Puerto", value=int(os.getenv("DB_PORT", "5432")), step=1)
    db_name = st.text_input("Base de datos", value=os.getenv("DB_NAME", "optimizer_db"))
    db_user = st.text_input("Usuario", value=os.getenv("DB_USER", "optimizer_admin"))
    db_password = st.text_input(
        "Contraseña",
        value=os.getenv("DB_PASSWORD", "practicas"),
        type="password",
    )
    db_schema = st.text_input("Schema TPC-H", value=os.getenv("DB_SCHEMA", "tpch"))

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
    "Sistema multi-agente: 5 agentes especializados → 5 master agents → "
    "scoring trim-mean → query ganadora"
)

# --- Query input ---
col_left, col_right = st.columns([2, 1])

with col_right:
    selected = st.selectbox("Cargar query de ejemplo", list(DEMO_QUERIES.keys()))

with col_left:
    if selected and DEMO_QUERIES[selected]:
        default_query = DEMO_QUERIES[selected]
    else:
        default_query = st.session_state.get("last_query", "")

    query_input = st.text_area(
        "Query SQL a optimizar",
        value=default_query,
        height=220,
        placeholder="SELECT ... FROM tpch.orders ...",
    )

run_btn = st.button("🚀 Optimizar", type="primary", use_container_width=True)

# --- Validation ---
if run_btn:
    if not api_key:
        st.error("Introduce tu ANTHROPIC_API_KEY en la barra lateral.")
        st.stop()
    if not query_input.strip():
        st.error("Escribe o selecciona una query SQL.")
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

    with st.spinner("Ejecutando pipeline multi-agente… (puede tardar 30-90 s con API real)"):
        try:
            result = _run(
                _run_pipeline(query_input.strip(), api_key, db_cfg)
            )
            st.session_state["result"] = result
            st.session_state["query_used"] = query_input.strip()
        except Exception as exc:
            st.error(f"Error durante el pipeline: {exc}")
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
    summary = report.get("summary") or {}
    original_query = st.session_state.get("query_used", "")
    optimized_query = winner.get("optimized_query", "")

    st.divider()
    st.subheader("📊 Resultados")

    # --- KPI row ---
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Query ganadora", f"Master Agent {winner.get('agent_id', '?')}")
    k2.metric("Score final", f"{winner.get('final_score', 0):.2f} / 10")
    k3.metric(
        "Tiempo original",
        f"{summary.get('baseline_time_ms', 0):.1f} ms",
    )
    k4.metric(
        "Tiempo optimizado",
        f"{summary.get('winner_time_ms', 0):.1f} ms",
        delta=f"{summary.get('time_improvement_pct', 0):+.1f}%",
        delta_color="inverse",
    )

    st.divider()

    tab_query, tab_compare, tab_explain, tab_raw = st.tabs(
        ["🏆 Query optimizada", "📈 Comparativa agentes", "🔍 Explicaciones", "🗂️ JSON raw"]
    )

    # --- Tab 1: winning query + diff ---
    with tab_query:
        col_orig, col_opt = st.columns(2)
        with col_orig:
            st.markdown("**Query original**")
            st.code(original_query, language="sql")
        with col_opt:
            st.markdown(f"**Query optimizada** — `{winner.get('agent_id', '')}`")
            st.code(optimized_query, language="sql")

        removed, added = _diff_lines(original_query, optimized_query)
        if added or removed:
            with st.expander("Ver cambios (diff simplificado)"):
                if added:
                    st.markdown("**Líneas añadidas / modificadas:**")
                    for line in sorted(added):
                        st.markdown(f"```+ {line}```")
                if removed:
                    st.markdown("**Líneas eliminadas / simplificadas:**")
                    for line in sorted(removed):
                        st.markdown(f"```- {line}```")

        st.markdown(f"**Estrategia:** {winner.get('optimization_strategy', '—')}")
        st.markdown(f"**Confianza:** {winner.get('confidence_score', 0):.0%}")

    # --- Tab 2: comparison table ---
    with tab_compare:
        st.markdown("Cada fila es un master agent. La puntuación final es la media recortada (se descarta la mayor y la menor).")

        if comparison:
            import pandas as pd
            df = pd.DataFrame(comparison)

            # Rename columns for display
            display_cols = {
                "agent_id": "Master Agent",
                "final_score": "Score final",
                "actual_time_ms": "Tiempo (ms)",
                "total_cost": "Coste planificador",
                "seq_scans": "Seq scans",
                "index_scans": "Index scans",
                "optimization_strategy": "Estrategia",
            }
            df_show = df.rename(columns=display_cols)[[c for c in display_cols.values() if c in df_show.columns or c in [display_cols[k] for k in df.columns]]]
            df_show = df.rename(columns={k: v for k, v in display_cols.items() if k in df.columns})

            # Highlight winner row
            winner_id = winner.get("agent_id", "")

            def highlight_winner(row):
                color = "background-color: #1e3a2f" if row.get("Master Agent") == winner_id or row.get("agent_id") == winner_id else ""
                return [color] * len(row)

            numeric_cols = ["Score final", "Tiempo (ms)", "Coste planificador"]
            format_dict = {}
            for col in numeric_cols:
                if col in df_show.columns:
                    format_dict[col] = "{:.2f}"

            st.dataframe(
                df_show.style.apply(highlight_winner, axis=1).format(format_dict, na_rep="—"),
                use_container_width=True,
            )
        else:
            st.info("No hay datos de comparativa disponibles.")

    # --- Tab 3: explanations ---
    with tab_explain:
        if explanations_list:
            for i, exp in enumerate(explanations_list, 1):
                risk = exp.get("risk_factor", 0)
                risk_icon = "🟢" if risk < 0.3 else ("🟡" if risk < 0.6 else "🔴")
                with st.expander(f"{i}. {exp.get('technique', 'Técnica')}  {risk_icon} riesgo {risk:.1f}"):
                    st.markdown(f"**Motivo:** {exp.get('reason', '—')}")
                    st.markdown(f"**Beneficio esperado:** {exp.get('expected_benefit', '—')}")
                    limitations = exp.get("limitations", [])
                    if limitations:
                        st.markdown("**Limitaciones:**")
                        for lim in limitations:
                            st.markdown(f"- {lim}")
        else:
            st.info("No hay explicaciones detalladas disponibles.")

    # --- Tab 4: raw JSON ---
    with tab_raw:
        st.json(report)
