# 🧠 oneprompt

> ⚠️ **License Notice**: This project is licensed under the **PolyForm Shield License 1.0.0**.
> 
> ✅ **Free for personal use**  
> ✅ **Free for internal business use**  
> ❌ **Prohibited to build a competing product or service**
> 
> For commercial licenses, OEM integration, or questions: contact@oneprompt.com

**AI agents for data querying, analysis, and chart generation.**

Connect your Gemini API key and PostgreSQL database — query data in natural language, run Python analysis, and generate interactive charts in minutes.

[![PyPI](https://img.shields.io/pypi/v/oneprompt)](https://pypi.org/project/oneprompt/)
[![Python](https://img.shields.io/pypi/pyversions/oneprompt)](https://pypi.org/project/oneprompt/)
[![License](https://img.shields.io/badge/license-PolyForm%20Shield-blue.svg)](LICENSE)

---

## ⚡ Quick Start

### 1. Install

```bash
pip install oneprompt
```

> **Prerequisite:** [Docker](https://docs.docker.com/get-docker/) must be installed and running.

### 2. Initialize a project

```bash
op init
```

This scaffolds your working directory with:

| File | Purpose |
|------|---------|
| `.env` | Configuration — add your API key and database URL |
| `DATABASE.md` | Schema documentation template for your database |
| `docker-compose.yml` | Docker stack for the MCP servers |
| `example.py` | Ready-to-run example script |

### 3. Configure

Edit `.env` with your credentials:

```env
GOOGLE_API_KEY=your-gemini-api-key
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
```

> Get your Gemini API key at [Google AI Studio](https://aistudio.google.com/apikey).

### 4. Document your schema

Edit `DATABASE.md` to describe your tables, columns, and relationships. The more detail you provide, the better the AI agent will write SQL queries. See [Schema Documentation](docs/guides/schema-docs.md) for the recommended format.

### 5. Start services

```bash
op start
```

This builds and launches 4 Docker containers:

| Service | Port | Description |
|---------|------|-------------|
| Artifact Store | 3336 | Generated file storage (CSV, JSON, HTML) |
| PostgreSQL MCP | 3333 | SQL query execution engine |
| Chart MCP | 3334 | AntV (G2Plot) chart generation |
| Python MCP | 3335 | Sandboxed Python execution for analysis |

### 6. Use it!

```python
import oneprompt as op

client = op.Client()  # Reads from .env automatically

# 1. Query your database with natural language
result = client.query("What are the top 10 products by revenue?")
print(result.summary)
print(result.preview)

# 2. Generate a chart from the results
chart = client.chart("Bar chart of top products", data_from=result)
print(f"Chart saved to: {chart.artifacts[0].path}")

# 3. Run Python analysis
analysis = client.analyze("Calculate month-over-month growth", data_from=result)
print(analysis.summary)
```

Or run the generated example directly:

```bash
python example.py
```

---

## 📖 Python SDK

### `Client`

The `Client` class is the main entry point. It reads configuration from `.env`, environment variables, or explicit parameters:

```python
import oneprompt as op

# Option A: Read from .env (recommended)
client = op.Client()

# Option B: Pass credentials directly
client = op.Client(
    gemini_api_key="your-key",
    database_url="postgresql://user:pass@localhost:5432/mydb",
    schema_docs_path="./DATABASE.md",
)
```

### Three core methods

| Method | Description | Returns |
|--------|-------------|---------|
| `client.query(question)` | Query your database with natural language | `AgentResult` — SQL results + preview data |
| `client.chart(description, data_from=...)` | Generate an interactive AntV chart | `AgentResult` — HTML chart file |
| `client.analyze(instruction, data_from=...)` | Run Python analysis code | `AgentResult` — analysis results + output files |

### `AgentResult`

Every method returns an `AgentResult` with:

| Property | Type | Description |
|----------|------|-------------|
| `ok` | `bool` | Whether the operation succeeded |
| `summary` | `str \| None` | Human-readable summary of the result |
| `preview` | `list[dict]` | Preview rows (for data queries) |
| `columns` | `list[str]` | Column names (for data queries) |
| `artifacts` | `list[ArtifactRef]` | Generated files (CSV, JSON, HTML) |
| `error` | `str \| None` | Error message if `ok` is `False` |
| `run_id` | `str` | Unique identifier of this execution |
| `session_id` | `str` | Session the execution belongs to |

### `ArtifactRef`

Each artifact in `result.artifacts` has:

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Unique artifact identifier |
| `name` | `str` | Filename (e.g. `top_products.csv`) |
| `type` | `str \| None` | `"data"`, `"result"`, or `"chart"` |
| `path` | `str \| None` | Local file path (after download) |

```python
# Read artifact content
artifact = result.artifacts[0]
text = artifact.read_text()    # As string
data = artifact.read_bytes()   # As bytes
```

### Chaining agents

Results can be piped between agents using `data_from`:

```python
# Query → Chart
data = client.query("Revenue by month for 2025")
chart = client.chart("Line chart of revenue trend", data_from=data)

# Query → Analyze
data = client.query("All transactions this quarter")
stats = client.analyze("Calculate descriptive statistics", data_from=data)

# Query → Analyze → Chart
data = client.query("Daily active users last 90 days")
trend = client.analyze("Calculate 7-day moving average", data_from=data)
chart = client.chart("Line chart with original and smoothed data", data_from=trend)
```

---

## 🌐 REST API

For integration with non-Python applications, start a local API server:

```bash
op api
```

The API runs at `http://localhost:8000` with these endpoints:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/agents/data` | Run natural language data queries |
| `POST` | `/agents/python` | Run Python analysis |
| `POST` | `/agents/chart` | Generate chart visualizations |
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions` | List sessions |
| `GET` | `/runs/{run_id}/artifacts/{artifact_id}` | Download a generated artifact |

See [docs/reference/rest-api.md](docs/reference/rest-api.md) for the full API reference.

---

## 🖥️ CLI Commands

```bash
op init       # Scaffold a new project (.env, DATABASE.md, example.py, docker-compose.yml)
op start      # Build and start all MCP services (Docker Compose)
op stop       # Stop all services
op status     # Check which services are running
op logs       # Tail service logs
op api        # Start the local REST API server
```

Run `op --help` for details, or `op <command> --help` for command-specific options.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│  Your App / SDK Client / REST API           │
├─────────────────────────────────────────────┤
│  AI Agents (Gemini + LangChain)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │   Data   │ │  Python  │ │  Chart   │    │
│  │  Agent   │ │  Agent   │ │  Agent   │    │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘    │
├───────┼─────────────┼────────────┼──────────┤
│  MCP Servers (Docker)                       │
│  ┌────┴─────┐ ┌────┴─────┐ ┌────┴─────┐    │
│  │ Postgres │ │  Python  │ │  Chart   │    │
│  │   MCP    │ │   MCP    │ │   MCP    │    │
│  └──────────┘ └──────────┘ └──────────┘    │
├─────────────────────────────────────────────┤
│  Artifact Store (generated file storage)    │
└─────────────────────────────────────────────┘
```

See [docs/architecture/overview.md](docs/architecture/overview.md) for the full architecture documentation.

---

## 📝 Schema Documentation

For best results, describe your database schema in `DATABASE.md`. This gives the AI context to write accurate SQL:

```markdown
# Database Schema

## Tables

### products
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| name | text | Product name |
| price | numeric | Unit price |
| category | text | Product category |

### orders
| Column | Type | Description |
|--------|------|-------------|
| id | integer | Primary key |
| product_id | integer | FK → products.id |
| quantity | integer | Units ordered |
| created_at | timestamp | Order date |
```

Then point the client to it:

```python
client = op.Client(schema_docs_path="./DATABASE.md")
```

See [docs/guides/schema-docs.md](docs/guides/schema-docs.md) for the complete guide and best practices.

---

## 🔧 Configuration

Configuration is loaded in this order (later overrides earlier):

1. `.env` file in the current directory
2. Environment variables
3. Arguments passed to `op.Client()`

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Gemini API key | **Required** |
| `DATABASE_URL` | PostgreSQL connection string | **Required** |
| `GEMINI_MODEL` | Gemini model name | `gemini-3-flash-preview` |
| `OP_SCHEMA_DOCS_PATH` | Path to your `DATABASE.md` | `./DATABASE.md` |
| `OP_DATA_DIR` | Directory for local data/state | `./op_data` |
| `OP_PORT` | REST API server port | `8000` |
| `OP_ARTIFACT_PORT` | Artifact store port | `3336` |
| `OP_POSTGRES_MCP_PORT` | PostgreSQL MCP port | `3333` |
| `OP_CHART_MCP_PORT` | Chart MCP port | `3334` |
| `OP_PYTHON_MCP_PORT` | Python MCP port | `3335` |
| `OP_MAX_RECURSION` | Max agent iterations | `10` |

See [docs/guides/configuration.md](docs/guides/configuration.md) for the complete reference.

---

## 📚 Documentation

Full documentation is available at [docs.oneprompt.com](https://docs.oneprompt.com) or in the `docs/` directory:

| Section | Contents |
|---------|----------|
| [Getting Started](docs/getting-started/quickstart.md) | Installation and quick start guide |
| [Guides](docs/guides/configuration.md) | Configuration, schema docs, agent chaining |
| [Reference](docs/reference/client.md) | Python SDK, REST API, and CLI reference |
| [Architecture](docs/architecture/overview.md) | System design, components, and data flow |

---

## 📄 License

PolyForm Shield License 1.0.0 — see [LICENSE](LICENSE) for details.
