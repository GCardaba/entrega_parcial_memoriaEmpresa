# Sistema Multiagente para la Optimización de Consultas SQL en PostgreSQL

**TFG — Universidad Nebrija · Escuela Politécnica Superior**

> Diseño e implementación de un sistema multiagente capaz de generar, evaluar y comparar distintas estrategias de optimización de consultas SQL en el entorno de PostgreSQL. Cada agente está especializado en un criterio concreto y compite para producir la versión más eficiente de una consulta dada.

---

## Tabla de contenidos

1. [Descripción general](#descripción-general)
2. [Diagrama de flujo del pipeline](#diagrama-de-flujo-del-pipeline)
3. [Diagrama del sistema de agentes](#diagrama-del-sistema-de-agentes)
4. [Sistema de puntuación Trim-mean](#sistema-de-puntuación-trim-mean)
5. [Arquitectura de componentes](#arquitectura-de-componentes)
6. [Requisitos previos](#requisitos-previos)
7. [Instalación](#instalación)
8. [Configuración](#configuración)
9. [Uso](#uso)
10. [Cómo funciona por dentro](#cómo-funciona-por-dentro)
11. [Tests](#tests)
12. [Estructura del proyecto](#estructura-del-proyecto)

---

## Descripción general

El sistema recibe una consulta SQL arbitraria y devuelve la versión optimizada con mayor puntuación, junto con un informe detallado que explica qué cambios se han aplicado, por qué, y qué mejora de rendimiento se espera.

El flujo completo pasa por **dos capas de agentes LLM** (10 agentes en total) más **medición real con EXPLAIN ANALYZE** contra una instancia PostgreSQL 16 con el dataset TPC-H (escala SF=1: ~600K filas en `lineitem`, ~150K en `orders`, ~15K en `customer`).

---

## Diagrama de flujo del pipeline

El orquestador es un grafo LangGraph de 7 nodos. El estado completo (`SystemState`) fluye entre nodos como un diccionario plano.

```mermaid
flowchart TD
    A([🔍 Consulta SQL de entrada])

    B["**parse_query**\n─────────────────\nObtiene schema de TPC-H\nEXPLAIN ANALYZE → métricas baseline"]

    subgraph PAR1 ["⚡  Ejecución paralela  ─  5 agentes simultáneos"]
        direction LR
        C1["Index\nOptimizer"]
        C2["JOIN\nOptimizer"]
        C3["Query\nRewriter"]
        C4["CTE\nOptimizer"]
        C5["Cache\nOptimizer"]
    end

    P1(["5 QueryProposal\nindependientes"])

    subgraph PAR2 ["🧠  Ejecución paralela  ─  5 master agents simultáneos"]
        direction LR
        D1["Master\nAgent 1"]
        D2["Master\nAgent 2"]
        D3["Master\nAgent 3"]
        D4["Master\nAgent 4"]
        D5["Master\nAgent 5"]
    end

    P2(["5 propuestas\npre-finales"])

    E["**evaluate_proposals**\n─────────────────\nEXPLAIN ANALYZE real\n3 ejecuciones por propuesta → media"]

    F["**score_proposals**\n─────────────────\n5 MA × 5 propuestas = 25 puntuaciones\nTrim-mean por propuesta → puntuación final"]

    G["**select_winner**\n─────────────────\nMáxima puntuación final"]

    H["**generate_report**\n─────────────────\nQuery ganadora · comparativa · explicaciones"]

    Z([✅ Resultado final])

    A --> B --> PAR1 --> P1 --> PAR2 --> P2 --> E --> F --> G --> H --> Z
```

---

## Diagrama del sistema de agentes

### Capa 1 — Agentes Optimizadores Especializados

Cada agente recibe la query original + schema y produce una propuesta de optimización independiente.

```mermaid
flowchart LR
    Q["🔍 Query SQL\n+ Schema TPC-H"]

    subgraph AGENTS ["CAPA 1 · Agentes Optimizadores  (asyncio.gather)"]
        direction TB
        A1["**Index Optimizer**\nÍndices cubrientes\nÍndices parciales\nBitmap Index Scan"]
        A2["**JOIN Optimizer**\nOrden de joins\nHash / Merge / Nested Loop\nSelectividad"]
        A3["**Query Rewriter**\nEliminación de subconsultas\nSimplificación estructural\nPredicados equivalentes"]
        A4["**CTE Optimizer**\nMaterialización de CTEs\nSubqueries correlacionadas\nWith clauses"]
        A5["**Cache Optimizer**\nBuffer pool de PostgreSQL\nPatrones de acceso secuencial\nWork_mem y shared_buffers"]
    end

    subgraph PROPS ["5 QueryProposal independientes"]
        direction TB
        P1["Propuesta 1\noptimized_query\nexplanations\nconfidence_score"]
        P2["Propuesta 2"]
        P3["Propuesta 3"]
        P4["Propuesta 4"]
        P5["Propuesta 5"]
    end

    Q --> A1 & A2 & A3 & A4 & A5
    A1 --> P1
    A2 --> P2
    A3 --> P3
    A4 --> P4
    A5 --> P5
```

### Capa 2 — Master Agents

Cada Master Agent recibe las 5 propuestas, las combina según su estrategia y produce una propuesta pre-final propia.

```mermaid
flowchart LR
    subgraph IN ["5 propuestas de Capa 1"]
        direction TB
        P1["Propuesta Index"]
        P2["Propuesta JOIN"]
        P3["Propuesta Rewriter"]
        P4["Propuesta CTE"]
        P5["Propuesta Cache"]
    end

    subgraph MA ["CAPA 2 · Master Agents  (asyncio.gather)"]
        direction TB
        M1["**MA1 · Performance First**\nTiempo 50% · Coste 30%\nIndex ratio 20%"]
        M2["**MA2 · Cache & I/O Aware**\nBuffer hits 40%\nElim. seq scans 35% · t 25%"]
        M3["**MA3 · Structural Rewriter**\nFilas procesadas 40%\nSimplicidad plan 30% · t 30%"]
        M4["**MA4 · Balanced Integrator**\nTodas las métricas\nPenaliza risk > 0.5"]
        M5["**MA5 · Conservative**\nConfianza 40% · Riesgo 30%\nVeto si risk > 0.8"]
    end

    subgraph OUT ["5 propuestas pre-finales"]
        direction TB
        R1["Combinada MA1"]
        R2["Combinada MA2"]
        R3["Combinada MA3"]
        R4["Combinada MA4"]
        R5["Combinada MA5"]
    end

    P1 & P2 & P3 & P4 & P5 --> M1 & M2 & M3 & M4 & M5
    M1 --> R1
    M2 --> R2
    M3 --> R3
    M4 --> R4
    M5 --> R5
```

---

## Sistema de puntuación Trim-mean

Tras la evaluación real con `EXPLAIN ANALYZE`, los 5 Master Agents puntúan **cada una** de las 5 propuestas pre-finales (25 llamadas LLM en total). La puntuación final de cada propuesta es la **media recortada** (trim-mean): se descartan la puntuación más alta y la más baja, y se hace la media de las 3 restantes.

```mermaid
flowchart TD
    subgraph PROP ["Propuesta pre-final (ejemplo: MA4)"]
        direction LR
        S1["MA1 puntúa:\n**7.5**"]
        S2["MA2 puntúa:\n**9.2** ← máx"]
        S3["MA3 puntúa:\n**6.8**"]
        S4["MA4 puntúa:\n**8.1**"]
        S5["MA5 puntúa:\n**4.3** ← mín"]
    end

    SORT["Ordenar: 4.3 · 6.8 · 7.5 · 8.1 · 9.2"]
    TRIM["✂️  Descartar máximo y mínimo\n→ quedan: 6.8 · 7.5 · 8.1"]
    AVG["Media de los 3 restantes\n(6.8 + 7.5 + 8.1) / 3 = **7.47**"]
    WIN["Puntuación final: **7.47 / 10**"]

    PROP --> SORT --> TRIM --> AVG --> WIN

    subgraph COMPARE ["Comparativa final de las 5 propuestas"]
        direction LR
        W1["MA1: 4.97"]
        W2["MA2: 4.63"]
        W3["MA3: 6.73"]
        W4["MA4: **7.20** 🏆"]
        W5["MA5: 7.07"]
    end

    WIN --> COMPARE
```

---

## Arquitectura de componentes

```mermaid
graph TB
    subgraph INTERFACES ["Interfaces de usuario"]
        UI["🖥️ Streamlit UI\nui/app.py\nlocalhost:8501"]
        API["⚡ FastAPI REST\napi/main.py\nlocalhost:8000\nPOST /optimize\nGET /schema · /health · /explain"]
    end

    subgraph CORE ["Core — Orquestador LangGraph"]
        WF["orchestrator/workflow.py\nStateGraph de 7 nodos\nEstado como dict plano"]
    end

    subgraph LAYER1 ["Capa 1 — Agentes Optimizadores"]
        OA["agents/base_agent.py\nBaseOptimizerAgent\n+ 5 agentes especializados\nValidación SQL con EXPLAIN\nAuto-corrección LLM"]
    end

    subgraph LAYER2 ["Capa 2 — Master Agents"]
        MA["agents/master_agents/\nBaseMasterAgent\n+ master_agent_1..5\nCombinación + Scoring\nTrim-mean en workflow.py"]
    end

    subgraph REPORT ["Reporting"]
        RG["reporter/report_generator.py\nSummary · Winner · Explanations\nComparison table · Query diff"]
    end

    subgraph INFRA ["Infraestructura"]
        DB["🐘 PostgreSQL 16\nHomebrew local\nDB: optimizer_db\nSchema: tpch\nDataset TPC-H SF=1"]
        LLM["🤖 Anthropic API\nclaude-sonnet-4-6\nAsyncAnthropic\nJSON via prompt engineering"]
    end

    subgraph DATA ["Capa de datos"]
        CONN["database/connector.py\nPostgreSQLConnector\nasyncpg · 1 conexión/llamada"]
        PARSER["database/explain_parser.py\nEXPLAIN JSON → EvaluationMetrics"]
        MODELS["models/agent_state.py\nPydantic v2\nQueryProposal · EvaluationResult\nSystemState · MasterAgentScore"]
    end

    UI -->|"llama directo\nsin servidor"| WF
    API --> WF
    WF --> OA
    WF --> MA
    WF --> RG
    OA <-->|"messages.create()"| LLM
    MA <-->|"messages.create()"| LLM
    OA <-->|"execute_explain()"| CONN
    WF <-->|"execute_explain_analyze()"| CONN
    CONN <--> DB
    CONN --> PARSER
    OA & MA & WF & RG --> MODELS
```

---

## Requisitos previos

- **Python 3.11+**
- **PostgreSQL 16** instalado localmente vía Homebrew (`brew install postgresql@16`)
- Una **ANTHROPIC_API_KEY** activa ([console.anthropic.com](https://console.anthropic.com))

> ⚠️ El sistema no usa Docker. Requiere una instancia local de PostgreSQL 16 con el dataset TPC-H cargado.

---

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/GCardaba/entrega_parcial_memoriaEmpresa.git
cd entrega_parcial_memoriaEmpresa

# 2. Crear entorno virtual e instalar dependencias
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Iniciar PostgreSQL
brew services start postgresql@16

# 4. Crear base de datos y usuario
psql postgres -c "CREATE USER optimizer_admin WITH PASSWORD 'practicas';"
psql postgres -c "CREATE DATABASE optimizer_db OWNER optimizer_admin;"
psql optimizer_db -c "CREATE SCHEMA tpch AUTHORIZATION optimizer_admin;"

# 5. Cargar el dataset TPC-H
#    (Los CSVs deben estar disponibles en tpch/data/ o generarse con tpch-dbgen)
psql -U optimizer_admin -d optimizer_db -f database/setup.py
```

---

## Configuración

Crea un fichero `.env` en la raíz del proyecto (existe `.env.example` como plantilla):

```env
# Anthropic Claude API
ANTHROPIC_API_KEY=sk-ant-...

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=optimizer_db
DB_USER=optimizer_admin
DB_PASSWORD=practicas
DB_SCHEMA=tpch
```

---

## Uso

### Interfaz web (recomendado)

```bash
venv/bin/streamlit run ui/app.py
```

Abre `http://localhost:8501`. Desde la UI puedes:

- Seleccionar una query de ejemplo (JOIN simple, subconsulta correlacionada, TPC-H Q1)
- Escribir tu propia consulta SQL
- Configurar la conexión a PostgreSQL y la API key desde la barra lateral
- Ver el resultado en 4 pestañas: query optimizada con diff, tabla comparativa de agentes, explicaciones por técnica, y JSON raw del informe

### API REST

```bash
venv/bin/uvicorn api.main:app --reload --port 8000
```

```bash
# Optimizar una query
curl -X POST http://localhost:8000/optimize \
  -H "Content-Type: application/json" \
  -d '{"sql_query": "SELECT c.c_name, SUM(o.o_totalprice) FROM tpch.customer c JOIN tpch.orders o ON c.c_custkey = o.o_custkey WHERE c.c_mktsegment = '\''BUILDING'\'' GROUP BY c.c_name LIMIT 10"}'

# Obtener el schema de TPC-H
curl http://localhost:8000/schema

# EXPLAIN ANALYZE de una query
curl -X POST http://localhost:8000/explain \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM tpch.orders LIMIT 10"}'
```

La respuesta del endpoint `/optimize` contiene:

```json
{
  "session_id": "...",
  "status": "done",
  "report": {
    "summary": "The winning query (from master_4) achieves a +20.6% execution time change...",
    "winner": {
      "agent_id": "master_4",
      "optimized_query": "SELECT ...",
      "optimization_strategy": "...",
      "confidence_score": 0.83,
      "final_score": 7.20,
      "metrics": { "actual_time_ms": 26.2, "total_cost": 5298.3, "seq_scans": 1, "index_scans": 1 }
    },
    "explanations": [
      {
        "technique": "Partial Covering Index on customer",
        "reason": "Eliminates heap fetches for BUILDING segment",
        "expected_benefit": "Reduces I/O by 60-70%",
        "risk_factor": 0.1,
        "limitations": ["Index maintenance on INSERT/UPDATE"]
      }
    ],
    "comparison_table": [
      { "rank": 1, "agent_id": "master_4", "final_score": 7.20, "actual_time_ms": 26.2, "time_improvement_pct": 20.6 }
    ]
  }
}
```

---

## Cómo funciona por dentro

### Validación de SQL

Antes de proponer cualquier query optimizada, el sistema la valida con `EXPLAIN` (sin `ANALYZE`). Si falla, le pide al LLM que la corrija una vez. Si vuelve a fallar, devuelve la query original sin cambios.

### Prompts en inglés

Todos los prompts del sistema están escritos en inglés para maximizar la consistencia y calidad de las respuestas del LLM, independientemente del idioma de la consulta.

### Límites de rate de la API

El tier gratuito de Anthropic tiene un límite de 30.000 tokens/minuto. La fase de puntuación (25 llamadas: 5 evaluaciones × 5 master agents) se ejecuta secuencialmente para no superarlo. Con una cuenta de pago este límite desaparece y puede paralelizarse.

### Métricas de evaluación

Se extraen del JSON de `EXPLAIN ANALYZE FORMAT JSON` de PostgreSQL 16:

| Métrica | Fuente en el JSON |
|---------|--------|
| `actual_time_ms` | `root["Execution Time"]` (nivel raíz) |
| `total_cost` | `Plan.Total Cost` del nodo raíz |
| `buffer_hits` | Suma de `Shared Hit Blocks` en todos los nodos |
| `seq_scans` | Conteo de nodos `Seq Scan` |
| `index_scans` | Conteo de `Index Scan` + `Index Only Scan` + `Bitmap Index Scan` |

---

## Tests

```bash
# Suite completa (49 tests, ~7s)
venv/bin/python -m pytest tests/ -v

# Un fichero concreto
venv/bin/python -m pytest tests/test_explain_parser.py -v

# Un test por nombre
venv/bin/python -m pytest tests/test_agents.py::test_invalid_llm_output_falls_back_to_original -v
```

| Fichero | Tipo | Requiere BD |
|---------|------|-------------|
| `test_explain_parser.py` | Unitario | No (usa fixture JSON capturado) |
| `test_connector.py` | Integración | Sí |
| `test_agents.py` | Unitario + integración | Sí (validación de sintaxis SQL) |
| `test_scoring_system.py` | Unitario | No |
| `test_workflow.py` | Integración | Sí |

---

## Estructura del proyecto

```
├── agents/
│   ├── base_agent.py            # BaseOptimizerAgent: LLM call, parsing, validación SQL
│   ├── index_agent.py
│   ├── join_agent.py
│   ├── rewrite_agent.py
│   ├── cte_agent.py
│   ├── cache_agent.py
│   └── master_agents/
│       ├── base_master_agent.py # BaseMasterAgent: combine + score + _parse_json
│       ├── master_agent_1..5.py # Estrategias diferenciadas
│       └── scoring_system.py    # Trim-mean
├── database/
│   ├── connector.py             # PostgreSQLConnector (asyncpg)
│   └── explain_parser.py        # EXPLAIN JSON → EvaluationMetrics
├── models/
│   └── agent_state.py           # Pydantic v2: QueryProposal, EvaluationResult, SystemState…
├── orchestrator/
│   └── workflow.py              # LangGraph StateGraph(dict), 7 nodos
├── reporter/
│   └── report_generator.py      # Dict final: summary, winner, comparison_table
├── api/
│   └── main.py                  # FastAPI: POST /optimize, GET /schema · /health · /explain
├── ui/
│   └── app.py                   # Streamlit UI (llama al workflow directamente)
├── tests/
│   └── conftest.py              # MockLLM (forma Anthropic), fixtures TPC-H
├── config/
│   └── settings.py              # Variables de entorno centralizadas
├── .env.example
├── requirements.txt
├── pytest.ini                   # asyncio_mode = auto
└── CLAUDE.md                    # Guía para Claude Code
```

---

*TFG · Gabriel Cárdaba López · Universidad Nebrija 2025*
