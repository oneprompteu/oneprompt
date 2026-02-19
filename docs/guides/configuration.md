# Configuration

All settings can be provided via environment variables, a `.env` file, or directly when creating the `Client`.

## Configuration Priority

Settings are loaded in this order (later overrides earlier):

1. **Default values** built into the SDK
2. **`.env` file** in the current working directory
3. **Environment variables** set in your shell
4. **Arguments** passed directly to `op.Client()`

---

## Required Settings

| Setting | Env Variable | Client Param | Description |
|---------|-------------|--------------|-------------|
| Gemini API Key | `GOOGLE_API_KEY` | `gemini_api_key` | Your Google Gemini API key. Get one at [Google AI Studio](https://aistudio.google.com/apikey) |
| Database URL | `DATABASE_URL` | `database_url` | PostgreSQL connection string, e.g. `postgresql://user:pass@host:5432/dbname` |

## Optional Settings

### Model

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `GEMINI_MODEL` | `gemini_model` | `gemini-3-flash-preview` | Gemini model to use |

### Schema Documentation

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `OP_SCHEMA_DOCS_PATH` | `schema_docs_path` | `./DATABASE.md` | Path to your database schema file |
| `OP_SCHEMA_DOCS` | `schema_docs` | — | Inline schema docs (alternative to file) |

### Directories

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `OP_DATA_DIR` | `data_dir` | `./op_data` | Directory for local data and state DB. Resolved to an absolute path at init time |

### Network Ports

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `OP_PORT` | `port` | `8000` | REST API server port |
| `OP_ARTIFACT_PORT` | `artifact_store_port` | `3336` | Artifact Store port |
| `OP_POSTGRES_MCP_PORT` | `postgres_mcp_port` | `3333` | PostgreSQL MCP server port |
| `OP_CHART_MCP_PORT` | `chart_mcp_port` | `3334` | Chart MCP server port |
| `OP_PYTHON_MCP_PORT` | `python_mcp_port` | `3335` | Python MCP server port |

### Agent Behavior

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `OP_MAX_RECURSION` | `agent_max_recursion` | `10` | Maximum iterations per agent invocation |

### Internal

| Env Variable | Client Param | Default | Description |
|-------------|--------------|---------|-------------|
| `OP_ARTIFACT_TOKEN` | `artifact_store_token` | Auto-generated | Shared auth token between SDK and Artifact Store |
| `OP_HOST` | `host` | `0.0.0.0` | API server bind address |

---

## .env File Example

Create a `.env` file in your project directory (or run `op init` and choose `local` mode):

```env
# Required
GOOGLE_API_KEY=AIzaSyB...your-key-here
DATABASE_URL=postgresql://myuser:mypassword@localhost:5432/mydb

# Optional
# GEMINI_MODEL=gemini-3-flash-preview
# OP_SCHEMA_DOCS_PATH=./DATABASE.md
# OP_DATA_DIR=./op_data
# OP_PORT=8000
# OP_ARTIFACT_PORT=3336
# OP_POSTGRES_MCP_PORT=3333
# OP_CHART_MCP_PORT=3334
# OP_PYTHON_MCP_PORT=3335
```

---

## Using the Config Object

For advanced control, create a `Config` object explicitly:

```python
from oneprompt import Client, Config

config = Config(
    gemini_api_key="your-key",
    database_url="postgresql://user:pass@localhost:5432/mydb",
    gemini_model="gemini-3-flash-preview",
    schema_docs_path="./DATABASE.md",
    data_dir="./my_data",
)

client = Client(config=config)
```

Or load from environment:

```python
from oneprompt import Config

config = Config.from_env()
print(config.gemini_model)       # gemini-3-flash-preview
print(config.artifact_store_url) # http://localhost:3336
print(config.mcp_postgres_url)   # http://localhost:3333/mcp
```

---

## Computed Properties

The `Config` object provides these derived properties:

| Property | Value | Description |
|----------|-------|-------------|
| `artifact_store_url` | `http://localhost:{artifact_store_port}` | Full URL to artifact store |
| `mcp_postgres_url` | `http://localhost:{postgres_mcp_port}/mcp` | Full URL to PostgreSQL MCP |
| `mcp_chart_url` | `http://localhost:{chart_mcp_port}/mcp` | Full URL to Chart MCP |
| `mcp_python_url` | `http://localhost:{python_mcp_port}/mcp` | Full URL to Python MCP |
| `export_dir` | `{data_dir}/exports` | Directory for artifact file storage |
| `state_db_path` | `{data_dir}/state.db` | Path to SQLite state database |

---

## Validation

The client validates required settings on initialization. If something is missing, you get a clear error:

```python
client = op.Client()
# ValueError: Configuration errors:
#   - gemini_api_key is required (env: GOOGLE_API_KEY)
#   - database_url is required (env: DATABASE_URL)
```

---

## PostgreSQL Connection Tips

### Local database

```env
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
```

### Docker database (from host)

```env
DATABASE_URL=postgresql://user:password@localhost:5432/mydb
```

### Remote database

```env
DATABASE_URL=postgresql://user:password@db.example.com:5432/mydb
```

### Special characters in password

URL-encode special characters:

```python
from urllib.parse import quote_plus

password = "p@ss!word#123"
url = f"postgresql://user:{quote_plus(password)}@host:5432/db"
```

!!! info
    If your PostgreSQL is running on your local machine, the Docker-based MCP server connects via `host.docker.internal` automatically.
