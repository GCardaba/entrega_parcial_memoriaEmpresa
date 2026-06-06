import asyncpg
import json
import os
from dotenv import load_dotenv

# asyncpg returns EXPLAIN FORMAT JSON as a text string, not a parsed object.
# All explain methods return parsed Python objects (list/dict) for consistency.

load_dotenv()


class PostgreSQLConnector:
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        schema: str = None,
    ):
        self.dbname   = database or os.getenv("DB_NAME", "optimizer_db")
        self.user     = user     or os.getenv("DB_USER", "optimizer_admin")
        self.password = password or os.getenv("DB_PASSWORD", "practicas")
        self.host     = host     or os.getenv("DB_HOST", "localhost")
        self.port     = port     or int(os.getenv("DB_PORT", "5432"))
        self.schema   = schema   or os.getenv("DB_SCHEMA", "tpch")

    async def _get_connection(self) -> asyncpg.Connection:
        return await asyncpg.connect(
            database=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )

    async def execute_query(self, query: str) -> list:
        """Execute a query and return rows as list of dicts."""
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(query)
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    async def execute_explain(self, query: str) -> list:
        """Run EXPLAIN (no ANALYZE) and return the parsed plan JSON. Used for syntax validation."""
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(f"EXPLAIN (FORMAT JSON) {query}")
            # asyncpg returns EXPLAIN JSON as a text column — parse explicitly.
            raw = rows[0][0]
            return json.loads(raw) if isinstance(raw, str) else raw
        finally:
            await conn.close()

    async def execute_explain_analyze(self, query: str) -> list:
        """Run EXPLAIN ANALYZE with full metrics and return the parsed plan JSON."""
        explain_query = f"""
        EXPLAIN (
            ANALYZE true,
            BUFFERS true,
            FORMAT JSON,
            TIMING true
        ) {query}
        """
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(explain_query)
            raw = rows[0][0]
            return json.loads(raw) if isinstance(raw, str) else raw
        finally:
            await conn.close()

    async def get_schema_info(self, schema_name: str = "tpch") -> dict:
        """Return tables with columns, primary keys and indexes for the given schema."""
        schema_query = """
        SELECT
            t.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            kcu.column_name AS pk_column,
            idx.indexname,
            idx.indexdef
        FROM
            information_schema.tables t
        LEFT JOIN
            information_schema.columns c
            ON t.table_name = c.table_name AND t.table_schema = c.table_schema
        LEFT JOIN
            information_schema.table_constraints tc
            ON t.table_name = tc.table_name
            AND t.table_schema = tc.table_schema
            AND tc.constraint_type = 'PRIMARY KEY'
        LEFT JOIN
            information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            AND c.column_name = kcu.column_name
        LEFT JOIN
            pg_indexes idx
            ON t.table_name = idx.tablename AND t.table_schema = idx.schemaname
        WHERE
            t.table_schema = $1
            AND t.table_type = 'BASE TABLE'
        ORDER BY
            t.table_name, c.ordinal_position
        """
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(schema_query, schema_name)
        finally:
            await conn.close()

        schema_info: dict = {}
        for row in rows:
            table_name = row["table_name"]
            if table_name not in schema_info:
                schema_info[table_name] = {
                    "columns": [],
                    "primary_key": None,
                    "indexes": [],
                }

            schema_info[table_name]["columns"].append(
                {
                    "name": row["column_name"],
                    "type": row["data_type"],
                    "nullable": row["is_nullable"] == "YES",
                }
            )

            # pk_column is non-null only for the row where this column is the PK column
            if row["pk_column"] is not None:
                schema_info[table_name]["primary_key"] = row["pk_column"]

            if row["indexname"] and row["indexdef"]:
                existing = [i["name"] for i in schema_info[table_name]["indexes"]]
                if row["indexname"] not in existing:
                    schema_info[table_name]["indexes"].append(
                        {"name": row["indexname"], "definition": row["indexdef"]}
                    )

        return schema_info

    async def get_table_statistics(self, table_name: str, schema: str = "tpch") -> dict:
        """Return planner statistics (row count, page count) for a table."""
        query = """
        SELECT
            relname,
            reltuples::bigint AS estimated_rows,
            relpages AS pages
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = $1 AND c.relname = $2
        """
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(query, schema, table_name)
            if rows:
                return dict(rows[0])
            return {}
        finally:
            await conn.close()
