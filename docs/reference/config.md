# Config

The `Config` dataclass holds all ThinkingProducts settings. It can be created from environment variables, a `.env` file, or direct initialization.

```python
from thinkingproducts import Config

config = Config.from_env()
```

---

## Constructor

```python
Config(
    gemini_api_key: str = "",
    database_url: str = "",
    gemini_model: str = "gemini-3-flash-preview",
    schema_docs: str = "",
    schema_docs_path: str = None,
    data_dir: str = "./tp_data",
    host: str = "0.0.0.0",
    port: int = 8000,
    artifact_store_port: int = 3336,
    postgres_mcp_port: int = 3333,
    chart_mcp_port: int = 3334,
    python_mcp_port: int = 3335,
    artifact_store_token: str = "",
    agent_max_recursion: int = 10,
)
```

### Parameters

| Parameter | Type | Default | Env Variable | Description |
|-----------|------|---------|-------------|-------------|
| `gemini_api_key` | `str` | `""` | `GOOGLE_API_KEY` | Google Gemini API key |
| `database_url` | `str` | `""` | `DATABASE_URL` | PostgreSQL connection string |
| `gemini_model` | `str` | `gemini-3-flash-preview` | `GEMINI_MODEL` | Gemini model name |
| `schema_docs` | `str` | `""` | `TP_SCHEMA_DOCS` | Inline schema documentation |
| `schema_docs_path` | `str` | `None` | `TP_SCHEMA_DOCS_PATH` | Path to schema docs file |
| `data_dir` | `str` | `./tp_data` | `TP_DATA_DIR` | Local data directory |
| `host` | `str` | `0.0.0.0` | `TP_HOST` | API server bind address |
| `port` | `int` | `8000` | `TP_PORT` | API server port |
| `artifact_store_port` | `int` | `3336` | `TP_ARTIFACT_PORT` | Artifact Store port |
| `postgres_mcp_port` | `int` | `3333` | `TP_POSTGRES_MCP_PORT` | PostgreSQL MCP port |
| `chart_mcp_port` | `int` | `3334` | `TP_CHART_MCP_PORT` | Chart MCP port |
| `python_mcp_port` | `int` | `3335` | `TP_PYTHON_MCP_PORT` | Python MCP port |
| `artifact_store_token` | `str` | `""` | `TP_ARTIFACT_TOKEN` | Shared auth token |
| `agent_max_recursion` | `int` | `10` | `TP_MAX_RECURSION` | Max agent iterations |

---

## Class Methods

### `from_env()`

Create a `Config` from environment variables:

```python
config = Config.from_env()
```

Reads all settings from the corresponding environment variables listed in the parameters table above.

---

## Computed Properties

| Property | Type | Description |
|----------|------|-------------|
| `artifact_store_url` | `str` | `http://localhost:{artifact_store_port}` |
| `mcp_postgres_url` | `str` | `http://localhost:{postgres_mcp_port}/mcp` |
| `mcp_chart_url` | `str` | `http://localhost:{chart_mcp_port}/mcp` |
| `mcp_python_url` | `str` | `http://localhost:{python_mcp_port}/mcp` |
| `export_dir` | `Path` | `{data_dir}/exports` |
| `state_db_path` | `str` | `{data_dir}/state.db` |

```python
config = Config.from_env()

print(config.artifact_store_url)  # http://localhost:3336
print(config.mcp_postgres_url)    # http://localhost:3333/mcp
print(config.export_dir)          # tp_data/exports
print(config.state_db_path)       # tp_data/state.db
```

---

## Methods

### `validate()`

Validate the configuration and return a list of errors:

```python
validate() -> list[str]
```

```python
config = Config()
errors = config.validate()
# ["gemini_api_key is required (env: GOOGLE_API_KEY)",
#  "database_url is required (env: DATABASE_URL)"]
```

### `to_env_dict()`

Export configuration as an environment variables dictionary (used internally for Docker/subprocess):

```python
to_env_dict() -> dict[str, str]
```

```python
config = Config.from_env()
env = config.to_env_dict()
# {"GOOGLE_API_KEY": "...", "DATABASE_URL": "...", ...}
```

---

## Auto-loading Schema Docs

If `schema_docs_path` is provided and the file exists, the content is automatically loaded into `schema_docs` during initialization:

```python
config = Config(
    gemini_api_key="...",
    database_url="...",
    schema_docs_path="./DATABASE.md",
)
# config.schema_docs now contains the file content
```
