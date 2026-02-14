# AGENTS.md — Development guidelines for the oneprompt SDK

This document helps AI coding agents (and human contributors) understand and work with the oneprompt Python SDK.

## What is this project?

oneprompt is a Python SDK that provides AI agents for querying PostgreSQL databases with natural language, running Python analysis, and generating interactive charts. It uses Google Gemini as the LLM, LangChain for agent orchestration, and MCP (Model Context Protocol) servers running in Docker containers for tool execution.

**Key user-facing entry points:**
- Python SDK: `import oneprompt as op` → `op.Client()`
- CLI: `op init`, `op start`, `op stop`, `op api`
- REST API: FastAPI server at `http://localhost:8000`

## Repository structure

```
oneprompt/              # Main Python package
├── __init__.py                # Exports: Client, Config, __version__
├── _version.py                # Version string
├── config.py                  # Config dataclass (loads from .env / env vars)
├── client.py                  # Client class — main SDK interface
├── cli.py                     # Click CLI (op init/start/stop/status/logs/api)
├── api.py                     # FastAPI REST server
│
├── agents/                    # AI agent implementations
│   ├── context.py             # AgentContext dataclass (session_id, run_id, artifact_store)
│   ├── data_agent.py          # NL → SQL → results (uses PostgreSQL MCP)
│   ├── chart_agent.py         # Data → AntV chart (uses Chart MCP)
│   ├── python_agent.py        # Data → Python analysis (uses Python MCP)
│   └── prompts/               # System prompt markdown files
│       ├── DATA_AGENT.md
│       ├── CHART_AGENT.md
│       └── PYTHON_AGENT.md
│
├── mcps/                      # MCP server implementations (run in Docker)
│   ├── postgres_mcp.py        # SQL execution + data export
│   ├── chart_mcp.py           # 30+ AntV chart generators
│   ├── python_sandbox/        # Sandboxed Python execution
│   │   ├── server.py          # MCP entry point (run_python, list_available_libraries)
│   │   ├── executor.py        # Subprocess code execution
│   │   ├── sandbox.py         # Environment setup (pre-loaded libraries)
│   │   ├── validator.py       # AST-based code safety validation
│   │   └── helpers.py         # Artifact store helper functions
│   ├── resources/             # Static resources bundled into Docker images
│   │   ├── DATABASE.md        # Schema docs template
│   │   └── CHARTS.md          # Chart library reference
│   ├── Dockerfile.artifact-store
│   ├── Dockerfile.postgres
│   ├── Dockerfile.chart
│   └── Dockerfile.python
│
└── services/                  # Support services
    ├── artifact_store.py      # FastAPI file storage server (runs in Docker)
    ├── artifact_client.py     # URL builder for artifact store
    └── state_store.py         # SQLite persistence (sessions, runs, artifacts)

docs/                          # MkDocs documentation source
docker-compose.yml             # Docker Compose for all MCP services
pyproject.toml                 # Package config (hatchling build, deps, scripts)
mkdocs.yml                     # MkDocs Material config
```

## Architecture

```
User code (SDK / REST API / CLI)
         │
         ▼
   AI Agents (LangChain + Gemini)
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │   Data   │ │  Python  │ │  Chart   │
   │  Agent   │ │  Agent   │ │  Agent   │
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        │ HTTP        │ HTTP       │ HTTP
        ▼             ▼            ▼
   MCP Servers (Docker containers, shared volume)
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │ Postgres │ │  Python  │ │  Chart   │
   │ MCP:3333 │ │ MCP:3335 │ │ MCP:3334 │
   └────┬─────┘ └────┬─────┘ └────┬─────┘
        │             │            │
        └─────────────┼────────────┘
                      ▼
              Artifact Store :3336
              (file storage in Docker volume)
```

**Request flow (example: `client.query("Top 10 products")`):**
1. `Client` creates a session + run in SQLite (`state_store.py`)
2. `Client` calls `data_agent.run()` with an `AgentContext`
3. Data Agent connects to PostgreSQL MCP via HTTP (`http://localhost:3333/mcp`)
4. Gemini generates SQL, calls MCP tools (`query_preview` / `export_query`)
5. PostgreSQL MCP executes SQL, uploads CSV/JSON to Artifact Store
6. Agent returns structured JSON → `Client` parses into `AgentResult`
7. `Client` downloads artifacts locally to `op_data/out/{session}/{run}/`

**Agent chaining:** Results pipe between agents via `data_from=` parameter. The client reads artifact data and appends it to the next agent's message.

## Key classes

| Class | File | Purpose |
|-------|------|---------|
| `Client` | `client.py` | Main SDK: `query()`, `chart()`, `analyze()` |
| `Config` | `config.py` | Configuration dataclass, loads from `.env` / env vars |
| `AgentResult` | `client.py` | Unified response: `ok`, `summary`, `preview`, `artifacts`, `error` |
| `ArtifactRef` | `client.py` | File reference: `id`, `name`, `type`, `path`, `read_text()`, `read_bytes()` |
| `AgentContext` | `agents/context.py` | Immutable context passed to agents: session_id, run_id, artifact_store |
| `StateStore` | `services/state_store.py` | SQLite CRUD for sessions, runs, artifacts |
| `ArtifactStoreClient` | `services/artifact_client.py` | URL builder for artifact upload/download |

## Development setup

**Requirements:** Python >= 3.12, Docker

```bash
# Install in development mode
pip install -e ".[dev]"

# Or with uv
uv sync --all-groups
```

**Dev dependencies:** pytest, pytest-asyncio, pytest-cov, ruff, mypy

### Running services locally

```bash
op start      # Build and start all Docker containers
op status     # Check health
op stop       # Stop services
op logs       # Tail logs
```

### Linting and formatting

```bash
ruff check .                  # Lint
ruff format .                 # Format
mypy oneprompt/        # Type check
```

**Ruff config:** target Python 3.12, line-length 100, rules: E, F, I, W.

### Testing

```bash
pytest                        # Run all tests
pytest tests/test_client.py   # Run specific test file
```

**Config:** `asyncio_mode = "auto"`, test files match `test_*.py`, test path is `tests/`.

> **Note:** The test suite is not yet implemented. When adding tests, place them in `tests/` mirroring the source structure.

## Development guidelines

### Code style

- All code must have type hints and return types
- Line length: 100 characters
- Follow existing patterns in the file you are modifying
- Use Google-style docstrings for public functions (Args, Returns, Raises sections)
- Types go in function signatures, not in docstrings

### Working with agents

Each agent (`data_agent.py`, `chart_agent.py`, `python_agent.py`) follows the same pattern:
1. Connect to its MCP server via `MultiServerMCPClient`
2. Load system prompt from `agents/prompts/*.md`
3. Create a LangChain agent with `create_agent()` (from `deepagents`)
4. Invoke the agent with the user message + context
5. Return structured JSON matching a response schema (`DataResponse`, `ChartResponse`, `AnalysisResponse`)

Custom headers (`mcp-session-id`, `mcp-run-id`, `x-dataset-dsn`) are passed to MCP servers for multi-tenancy and artifact routing.

### Working with MCP servers

MCP servers are standalone Python scripts that run in Docker. Each uses `fastmcp` to define tools and prompts. Key points:
- They communicate via HTTP (`/mcp` endpoint)
- They share a Docker volume (`op_exports`) for file access
- They upload artifacts to the Artifact Store via HTTP POST
- `postgres_mcp.py` validates SQL is read-only (no INSERT/UPDATE/DELETE/DROP)
- `python_sandbox/` validates code via AST (blocks dangerous imports, `eval`, `exec`, file I/O)

### Artifact path convention

All artifacts follow: `{session_id}/runs/{run_id}/{type}/{filename}`

Where `type` is `data` (query results), `results` (Python outputs), or `charts` (chart specs).

### Security considerations

- PostgreSQL MCP: read-only SQL only, no DDL/DML, no statement chaining
- Python MCP: sandboxed execution, blocked dangerous imports, AST validation, timeout enforcement, resource limits, runs as non-root user
- Artifact Store: token authentication, path traversal protection
- Docker: Python MCP runs with `read_only: true`, `no-new-privileges`, `cap_drop: ALL`, memory/CPU limits
- Never use `eval()`, `exec()`, or `pickle` on user-controlled input
- No bare `except:` — always catch specific exceptions

### Configuration

Configuration loads in order (later overrides earlier):
1. `.env` file in working directory
2. Environment variables
3. Arguments to `op.Client()`

Required: `GOOGLE_API_KEY`, `DATABASE_URL`. See `config.py` for all options with defaults.

### CLI entry point

The CLI is registered as `tp` in `pyproject.toml`:
```toml
[project.scripts]
op = "oneprompt.cli:main"
```

It uses Click. Commands: `init`, `start`, `stop`, `status`, `logs`, `api`.

### Docker Compose

`docker-compose.yml` defines 4 services sharing a `op_exports` volume. Environment variables are passed from the host `.env`. The `op start` CLI command wraps `docker compose up --build`.

### Adding a new agent

To add a new agent type:
1. Create `agents/new_agent.py` following the pattern of `data_agent.py`
2. Create `agents/prompts/NEW_AGENT.md` with the system prompt
3. Create the MCP server in `mcps/new_mcp.py` (or `mcps/new_mcp/`)
4. Add a `Dockerfile.new` in `mcps/`
5. Add the service to `docker-compose.yml`
6. Add a new method to `Client` in `client.py`
7. Add the REST endpoint in `api.py`
8. Add a port config to `Config` in `config.py`

### Commit standards

Use Conventional Commits, all lowercase except proper nouns, always include scope:
```
feat(client): add batch query support
fix(postgres-mcp): handle empty result sets
docs(readme): update quick start guide
```
