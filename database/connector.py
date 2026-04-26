import psycopg2
import json
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class PostgreSQLConnector:
  def __init__(self):
    # Connection parameters
    self.dbname = os.getenv("DB_NAME")
    self.user = os.getenv("DB_USER")
    self.password = os.getenv("DB_PASSWORD")
    self.host = os.getenv("DB_HOST")
    self.port = os.getenv("DB_PORT")

def _get_connection(self):
    """Get PostgreSQL connection"""
    return psycopg2.connect(
        dbname=self.dbname,
        user=self.user,
        password=self.password,
        host=self.host,
        port=self.port
    )

def execute_query(self, query):
    """Execute a query and return results"""
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute(query)
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results

def execute_explain(self, query):
    """Execute EXPLAIN (without ANALYZE) and return plan"""
    explain_query = f"EXPLAIN (FORMAT JSON) {query}"
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute(explain_query)
    plan = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return plan

def execute_explain_analyze(self, query):
    """Execute EXPLAIN ANALYZE and return plan with metrics"""
    explain_query = f"""
    EXPLAIN (
        ANALYZE true,
        BUFFERS true,
        FORMAT JSON,
        TIMING true
    ) {query}
    """
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute(explain_query)
    plan = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return plan

def get_schema_info(self, schema_name="tpch"):
    """Get schema information: tables, columns, indexes"""
    schema_query = f"""
    SELECT
        t.table_name,
        c.column_name,
        c.data_type,
        c.is_nullable,
        tc.constraint_type,
        idx.indexname,
        idx.indexdef
    FROM
        information_schema.tables t
    LEFT JOIN
        information_schema.columns c ON t.table_name = c.table_name AND t.table_schema = c.table_schema
    LEFT JOIN
        information_schema.table_constraints tc ON t.table_name = tc.table_name AND t.table_schema = tc.table_schema AND tc.constraint_type = 'PRIMARY KEY'
    LEFT JOIN
        pg_indexes idx ON t.table_name = idx.tablename AND t.table_schema = idx.schemaname
    WHERE
        t.table_schema = '{schema_name}'
        AND t.table_type = 'BASE TABLE'
    ORDER BY
        t.table_name, c.ordinal_position;
    """
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute(schema_query)
    results = cursor.fetchall()
    
    schema_info = {}
    for row in results:
        table_name, column_name, data_type, is_nullable, constraint_type, index_name, index_def = row
        
        if table_name not in schema_info:
            schema_info[table_name] = {
                "columns": [],
                "primary_key": None,
                "indexes": []
            }
        
        # Add column info
        schema_info[table_name]["columns"].append({
            "name": column_name,
            "type": data_type,
            "nullable": is_nullable == "YES"
        })
        
        # Add primary key info
        if constraint_type == "PRIMARY KEY":
            schema_info[table_name]["primary_key"] = column_name
        
        # Add index info (avoid duplicates)
        if index_name and index_def:
            index_exists = False
            for idx in schema_info[table_name]["indexes"]:
                if idx["name"] == index_name:
                    index_exists = True
                    break
            
            if not index_exists:
                schema_info[table_name]["indexes"].append({
                    "name": index_name,
                    "definition": index_def
                })
    
    cursor.close()
    conn.close()
    return schema_info
