import sys
import os
import time
import uuid

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
from openai import AsyncOpenAI

from database.connector import PostgreSQLConnector
from orchestrator.workflow import build_optimization_workflow

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SQL Query Optimizer — Multi-Agent System",
    description="Optimizes PostgreSQL queries using a pipeline of specialist + master agents.",
    version="0.2.0",
)

db_connector = PostgreSQLConnector()

def _get_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in environment")
    return AsyncOpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    sql_query: str
    schema: Optional[str] = "tpch"


class ExplainRequest(BaseModel):
    query: str
    query_name: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"message": "SQL Query Optimizer API is running", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    try:
        await db_connector.execute_query("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}


@app.post("/explain")
async def explain_query(request: ExplainRequest):
    """Run EXPLAIN ANALYZE on a query and return the raw plan + parsed metrics."""
    from database.explain_parser import ExplainAnalyzeParser
    try:
        start = time.time()
        plan = await db_connector.execute_explain_analyze(request.query)
        elapsed_ms = (time.time() - start) * 1000
        parser = ExplainAnalyzeParser()
        metrics = parser.parse(plan)
        return {
            "original_query": request.query,
            "wall_time_ms": round(elapsed_ms, 3),
            "metrics": metrics.model_dump(exclude={"plan_json"}),
            "node_types": parser.get_node_types(plan),
            "planning_time_ms": parser.get_planning_time_ms(plan),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/schema")
async def get_schema(schema: str = "tpch"):
    """Return the schema metadata used by the optimizer agents."""
    try:
        return await db_connector.get_schema_info(schema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimize")
async def optimize_query(request: QueryRequest):
    """
    Full multi-agent optimization pipeline:
    1. 5 specialist optimizer agents run in parallel.
    2. 5 master agents each combine the proposals into a pre-final query.
    3. All master agents score all pre-final queries (trim mean).
    4. The highest-scoring query is returned with consolidated explanations.
    """
    session_id = str(uuid.uuid4())
    try:
        llm = _get_llm()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    initial_state = {
        "session_id": session_id,
        "original_query": request.sql_query,
        "schema_context": {},
        "baseline_metrics": None,
        "proposals": [],
        "combined_proposals": [],
        "evaluations": [],
        "winner": None,
        "report": None,
        "status": "pending",
    }

    try:
        workflow = build_optimization_workflow(llm, db_connector)
        final_state = await workflow.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Workflow error: {e}")

    return {
        "session_id": session_id,
        "status": final_state.get("status"),
        "report": final_state.get("report"),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
