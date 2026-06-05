import os
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "optimizer_db")
DB_USER = os.getenv("DB_USER", "optimizer_admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "practicas")
DB_SCHEMA = os.getenv("DB_SCHEMA", "tpch")

# LLM
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
LLM_TEMPERATURE_OPTIMIZE = float(os.getenv("LLM_TEMPERATURE_OPTIMIZE", "0.2"))
LLM_TEMPERATURE_SCORE = float(os.getenv("LLM_TEMPERATURE_SCORE", "0.1"))

# Evaluation
EXPLAIN_ANALYZE_RUNS = int(os.getenv("EXPLAIN_ANALYZE_RUNS", "3"))

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
