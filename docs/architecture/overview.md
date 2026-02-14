# Architecture Overview

Technical documentation of the oneprompt system architecture.

## Overview

oneprompt is built as a **local-first SDK** that orchestrates AI agents via Docker-based MCP servers. The system runs entirely on your machine — no cloud services, no external APIs beyond the Gemini LLM.

```
Your Application
  ├── Python SDK (op.Client)     or     REST API (op api)
  │
  ▼
AI Agents (Gemini + LangChain)
  ├── Data Agent ──── PostgreSQL MCP (:3333) ──── Your PostgreSQL DB
  ├── Python Agent ── Python MCP (:3335)
  └── Chart Agent ─── Chart MCP (:3334)
                         │
                   Artifact Store (:3336)
                   (shared file storage)
```

---

## Components

### Python SDK

The `Client` class is the main entry point. It handles:

- Configuration loading (`.env`, environment variables, or explicit args)
- Session and run management via local SQLite
- Agent orchestration (calling the correct agent for each method)
- On-demand artifact access via the Artifact Store

| File | Purpose |
|------|---------|
| `client.py` | `Client` class with `query()`, `chart()`, `analyze()` |
| `config.py` | `Config` dataclass with all settings |
| `cli.py` | CLI commands (`op init`, `op start`, etc.) |
| `api.py` | FastAPI REST API server |

### AI Agents

Each agent is a LangChain agent powered by Google Gemini that connects to a specific MCP server:

| Agent | MCP Server | Purpose |
|-------|------------|---------|
| Data Agent | PostgreSQL MCP | Translate natural language → SQL, execute, export results |
| Python Agent | Python MCP | Execute Python analysis code in a sandbox |
| Chart Agent | Chart MCP | Generate interactive AntV (G2Plot) charts |

Each agent:

1. Connects to its MCP server via HTTP
2. Loads available tools from the MCP server
3. Uses Gemini to reason about the request and call the appropriate tools
4. Returns a structured JSON response with results and artifacts

### PostgreSQL MCP Server

**Port:** 3333 · **Framework:** FastMCP

| Tool | Description |
|------|-------------|
| `query_preview` | Execute SQL and return first rows |
| `export_query` | Execute SQL and export to CSV/JSON |
| `get_tables` | List available tables |

The database connection string (DSN) is passed dynamically via HTTP headers, allowing the same MCP server to query different databases.

### Python MCP Server

**Port:** 3335 · **Framework:** FastMCP

| Tool | Description |
|------|-------------|
| `run_python` | Execute Python code in a secure subprocess |

The sandbox runs with restricted permissions:

- Read-only filesystem
- Limited memory (2GB) and CPU (2 cores)
- No network access from within the sandbox
- Temporary files only in `/tmp`

### Chart MCP Server

**Port:** 3334 · **Framework:** FastMCP

| Tool | Description |
|------|-------------|
| `generate_chart` | Create an HTML file with an AntV G2Plot chart |

Supports bar, line, pie, scatter, area, and other chart types.

### Artifact Store

**Port:** 3336 · **Framework:** FastAPI

A simple file storage service:

- **PUT** — Upload generated files (CSV, JSON, HTML)
- **GET** — Download files by path

Files are organized by session and run:

```
exports/
  {session_id}/
    runs/
      {run_id}/
        data/       ← Data Agent outputs (CSV, JSON)
        results/    ← Python Agent outputs
        charts/     ← Chart Agent outputs (HTML)
```

### State Store (SQLite)

Local SQLite database for metadata, stored at `op_data/state.db`:

| Table | Contents |
|-------|----------|
| `sessions` | Session ID, name, status, timestamps |
| `runs` | Run ID, session ID, status, timestamps |
| `artifacts` | Artifact ID, run ID, session ID, filename, store path |

---

## Data Flow

### Single Query

```
1. Client.query("Top 10 products by revenue")
   ├── Creates session (if needed)
   ├── Generates unique run_id
   └── Calls Data Agent

2. Data Agent
   ├── Connects to PostgreSQL MCP via HTTP
   ├── Passes DATABASE.md schema as context to Gemini
   ├── Gemini generates SQL query
   └── Calls MCP tool: export_query(sql="SELECT ...")

3. PostgreSQL MCP
   ├── Connects to your PostgreSQL database
   ├── Executes the SQL query
   ├── Exports results to CSV + JSON
   └── Stores files in Artifact Store

4. Client
   ├── Creates ArtifactRef objects with remote URLs
   ├── Artifacts are fetched on-demand via read_text() or download()
   └── Returns AgentResult to your code
```

### Chained Workflow

```
query("Revenue by month")
  └── AgentResult with CSV/JSON artifacts
        │  passed via data_from parameter
        ▼
analyze("Calculate growth rate", data_from=result)
  └── Reads JSON data from artifact (fetched on-demand)
        │  passed via data_from parameter
        ▼
chart("Line chart of growth", data_from=analysis)
  └── Reads JSON data from artifact (fetched on-demand)
  └── Returns HTML chart artifact
```

---

## MCP (Model Context Protocol)

### What is MCP?

[MCP](https://modelcontextprotocol.io/) is an open protocol for connecting LLMs to external tools in a standardized way. Each MCP server exposes:

- **Tools** — Functions the LLM can call (e.g. `export_query`, `run_python`)
- **Prompts** — Contextual information for the LLM
- **Resources** — Static content (e.g. database schema documentation)

### Why MCP?

1. **Separation of concerns** — Each server handles one domain (SQL, Python, Charts)
2. **Security** — Code execution is isolated in Docker containers
3. **Scalability** — Servers are stateless and independently deployable
4. **Reusability** — The same MCP server can serve multiple agents

### Agent → MCP Connection

```python
# Simplified from agents/data_agent.py
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "postgres": {
        "transport": "http",
        "url": "http://localhost:3333/mcp",
        "headers": {
            "mcp-session-id": "session_abc",
            "mcp-run-id": "run_xyz",
            "x-dataset-dsn": "postgresql://...",
        }
    }
})

async with client.session("postgres") as session:
    tools = await load_mcp_tools(session)
    agent = create_agent(gemini_llm, tools)
    result = await agent.run("Top 10 products by revenue")
```

---

## Local Storage

All local data is stored under `op_data/` (configurable via `OP_DATA_DIR`):

```
op_data/
  ├── state.db          ← SQLite: sessions, runs, artifacts metadata
  ├── .artifact_token   ← Auto-generated auth token for Artifact Store
  └── exports/          ← Shared Docker volume for artifact files
      └── {session_id}/
          └── runs/
              └── {run_id}/
                  ├── data/
                  ├── results/
                  └── charts/
```

Artifacts are stored in the Artifact Store (Docker container). Use `artifact.read_text()` to fetch content on demand, or `artifact.download("./output/")` to save locally.

---

## Docker Services

All MCP servers and the Artifact Store run as Docker containers managed by Docker Compose.

### Services

| Service | Dockerfile | Port | Purpose |
|---------|-----------|------|---------|
| `artifact-store` | `Dockerfile.artifact-store` | 3336 | File storage |
| `postgres-mcp` | `Dockerfile.postgres` | 3333 | SQL query engine |
| `chart-mcp` | `Dockerfile.chart` | 3334 | Chart generation |
| `python-mcp` | `Dockerfile.python` | 3335 | Sandboxed Python |

### Shared Volume

All services share a Docker volume (`op_exports`) mounted at `/app/exports`. This allows:

- MCP servers to write output files
- Artifact Store to serve those files via HTTP
- Files to persist across container restarts

### Security

The Python MCP runs with hardened settings:

```yaml
read_only: true
tmpfs: /tmp:size=100M
security_opt: [no-new-privileges:true]
cap_drop: [ALL]
resources:
  limits:
    memory: 2G
    cpus: "2"
```
