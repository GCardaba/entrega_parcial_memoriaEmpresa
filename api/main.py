from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uvicorn
import os
import sys
import time

# Añadir el directorio raíz al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar nuestro conector
from database.connector import PostgreSQLConnector

class QueryRequest(BaseModel):
    query: str
    query_name: Optional[str] = None

class ExplainResult(BaseModel):
    plan: Dict[str, Any]
    execution_time_ms: float

class QueryResponse(BaseModel):
    original_query: str
    explain_result: ExplainResult

app = FastAPI(
    title="SQL Query Optimizer",
    description="Multi-agent system for PostgreSQL query optimization using TPC-H",
    version="0.1.0"
    )

# Inicializar conector
db_connector = PostgreSQLConnector()

@app.get("/")
async def root():
    return {"message": "SQL Query Optimizer API is running with TPC-H"}

@app.get("/health")
async def health_check():
    try:
        # Verificar conexión ejecutando una consulta simple
        result = db_connector.execute_query("SELECT 1")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": str(e)}

@app.post("/explain", response_model=QueryResponse)
async def explain_query(request: QueryRequest):
    try:
        # Medir tiempo
        start_time = time.time()
        
        # Ejecutar EXPLAIN ANALYZE
        plan = db_connector.execute_explain_analyze(request.query)
        
        # Calcular tiempo de ejecución
        execution_time = (time.time() - start_time) * 1000  # en ms
        
        return QueryResponse(
            original_query=request.query,
            explain_result=ExplainResult(
                plan=plan,
                execution_time_ms=execution_time
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing query: {str(e)}")

@app.get("/schema")
async def get_schema():
    try:
        return db_connector.get_schema_info("tpch")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting schema: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)