# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# All commands use the project venv
VENV=venv/bin/python

# Run full test suite
venv/bin/python -m pytest tests/ -v

# Run a single test file
venv/bin/python -m pytest tests/test_agents.py -v

# Run a single test by name
venv/bin/python -m pytest tests/test_agents.py::test_index_agent_returns_query_proposal -v

# Streamlit UI (no FastAPI needed)
venv/bin/streamlit run ui/app.py

# FastAPI server
venv/bin/uvicorn api.main:app --reload --port 8000

# PostgreSQL (Homebrew, NOT Docker)
brew services start postgresql@16
brew services stop postgresql@16
```

## Environment

Copy `.env.example` to `.env` in the project root (not inside a subdirectory). Required variables:

```
ANTHROPIC_API_KEY=sk-ant-...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=optimizer_db
DB_USER=optimizer_admin
DB_PASSWORD=practicas
DB_SCHEMA=tpch
```

`load_dotenv()` is called at module import time in `database/connector.py` and `config/settings.py`. When running scripts directly (not via `streamlit run` or `uvicorn`), pass `override=True` to `load_dotenv()` if the env var is already set to empty in the shell.

## Architecture

### Pipeline (7-node LangGraph graph)

```
parse_query → run_optimizer_agents → combine_optimizations
    → evaluate_proposals → score_proposals → select_winner → generate_report
```

All state flows as a plain `dict` through `StateGraph(dict)`. **Each node must return `{**state, ...updates}`** — partial returns lose keys because `StateGraph(dict)` doesn't auto-accumulate between nodes.

### Two-tier agent system

**Tier 1 — Optimizer agents** (`agents/`): 5 specialists run in parallel via `asyncio.gather`. Each extends `BaseOptimizerAgent` and returns a `QueryProposal` with an `optimized_query` + list of `OptimizationExplanation`.

| Agent | Specialization |
|-------|---------------|
| `IndexOptimizerAgent` | Covering/partial indexes |
| `JoinOptimizerAgent` | JOIN order and strategy |
| `QueryRewriterAgent` | Structural SQL rewrites |
| `CTEOptimizerAgent` | CTEs and subquery elimination |
| `CacheOptimizerAgent` | Buffer/cache-friendly access patterns |

**Tier 2 — Master agents** (`agents/master_agents/`): 5 agents, each with a different scoring strategy, run after the optimizer tier. Each master agent:
1. Calls `combine_optimizations()` — receives all 5 optimizer proposals and produces one pre-final query.
2. Calls `score_proposal()` — scores each of the 5 combined queries from 0 to 10.

Scoring uses **trim-mean**: sort 5 scores, drop the highest and lowest, average the remaining 3.

| Master Agent | Scoring focus |
|---|---|
| MA1 | Execution time (50%) + cost (30%) + index ratio (20%) |
| MA2 | Buffer hits (40%) + seq scan elimination (35%) + time (25%) |
| MA3 | Rows processed (40%) + plan simplicity (30%) + time (30%) |
| MA4 | Balanced across all metrics; penalises `risk_factor > 0.5` |
| MA5 | Conservative: confidence (40%) + risk penalty (30%) + time (30%); hard cap if `risk_factor > 0.8` |

### LLM integration

All LLM calls use `AsyncAnthropic` (`claude-sonnet-4-6`). The Anthropic API does **not** support `response_format={"type":"json_object"}`, so structured output is enforced via `RESPONSE_FORMAT_INSTRUCTIONS` in the prompt.

Both `BaseOptimizerAgent._parse_llm_response()` and `BaseMasterAgent._parse_json()` strip markdown fences before `json.loads`, then fall back to regex `{.*}` extraction — never raise on parse failure.

`BaseOptimizerAgent._validate_syntax()` runs `EXPLAIN` (no ANALYZE) on every optimised query. On failure it asks the LLM to fix it once; on second failure it returns the original query unchanged.

### Rate limits (important)

The scoring phase produces 25 API calls (5 evaluations × 5 masters). On Anthropic free-tier (30k tokens/min), these **must run sequentially** — they're already sequential in `score_proposals()`. Do not convert them back to `asyncio.gather`.

### Database

`PostgreSQLConnector` opens a new `asyncpg` connection per call and closes it in `finally`. `execute_explain_analyze` returns a parsed Python list (asyncpg returns EXPLAIN JSON as a raw string; `json.loads` is applied inside the method).

`get_schema_info` uses `information_schema.key_column_usage` JOIN to detect primary keys — not `table_constraints` alone, which assigns PK to the wrong column.

`EvaluationMetrics.plan_json` is typed `List`, not `dict`, because PostgreSQL EXPLAIN FORMAT JSON returns a list at the top level.

### Tests

49 tests across 5 files. `asyncio_mode = auto` in `pytest.ini` — no `@pytest.mark.asyncio` needed.

- `test_connector.py` — integration tests, requires live PostgreSQL with TPC-H loaded
- `test_explain_parser.py` — unit tests using `EXPLAIN_FIXTURE` (captured JSON, no DB)
- `test_agents.py`, `test_scoring_system.py`, `test_workflow.py` — use `MockLLM` from `conftest.py`

`MockLLM` mirrors the Anthropic shape: `llm.messages.create(...)` returns an object with `content[0].text`. Any local mock LLM inside a test must use the same shape.

### Report structure

`ReportGenerator.create_report()` returns a plain dict (not a Pydantic model). Key fields:

- `summary` — plain string (executive summary)
- `winner.metrics` — dict with `actual_time_ms`, `total_cost`, `seq_scans`, `index_scans`, `improvement_vs_original` (values are pre-formatted strings like `"+20.6%"`)
- `comparison_table` — list of dicts with `rank`, `agent_id`, `final_score`, `actual_time_ms`, `time_improvement_pct`
- `explanations` — from the winning proposal only
