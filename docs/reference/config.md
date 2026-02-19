# Config

The `Config` dataclass holds all oneprompt settings. It can be created from environment variables, a `.env` file, or direct initialization.

```python
from oneprompt import Config

config = Config.from_env()
```

---

## Constructor

```python
Config(
    llm_provider: str = "google",
    llm_api_key: str = "",
    llm_model: str = "",
    database_url: str = "",
    schema_docs: str = "",
    schema_docs_path: str = None,
    data_dir: str = "./op_data",
    host: str = "0.0.0.0",
    port: int = 8000,
    artifact_store_port: int = 3336,
    postgres_mcp_port: int = 3333,
    chart_mcp_port: int = 3334,
    python_mcp_port: int = 3335,
    artifact_store_token: str = "",
    agent_max_recursion: int = 10,
    # Cloud mode
    oneprompt_api_key: str = "",
    oneprompt_api_url: str = "https://api.oneprompt.eu",
)
```

### Parameters

| Parameter | Type | Default | Env Variable | Description |
|-----------|------|---------|-------------|-------------|
| `llm_provider` | `str` | `"google"` | `LLM_PROVIDER` | LLM provider: `google`, `openai`, or `anthropic` |
| `llm_api_key` | `str` | `""` | `LLM_API_KEY` | API key for the chosen LLM provider |
| `llm_model` | `str` | `""` | `LLM_MODEL` | Model name. If empty, uses provider default (`gemini-3-flash-preview`, `gpt-5`, `claude-sonnet-4.5`) |
| `database_url` | `str` | `""` | `DATABASE_URL` | PostgreSQL connection string |
| `schema_docs` | `str` | `""` | `OP_SCHEMA_DOCS` | Inline schema documentation |
| `schema_docs_path` | `str` | `None` | `OP_SCHEMA_DOCS_PATH` | Path to schema docs file |
| `data_dir` | `str` | `./op_data` | `OP_DATA_DIR` | Local data directory |
| `host` | `str` | `0.0.0.0` | `OP_HOST` | API server bind address |
| `port` | `int` | `8000` | `OP_PORT` | API server port |
| `artifact_store_port` | `int` | `3336` | `OP_ARTIFACT_PORT` | Artifact Store port |
| `postgres_mcp_port` | `int` | `3333` | `OP_POSTGRES_MCP_PORT` | PostgreSQL MCP port |
| `chart_mcp_port` | `int` | `3334` | `OP_CHART_MCP_PORT` | Chart MCP port |
| `python_mcp_port` | `int` | `3335` | `OP_PYTHON_MCP_PORT` | Python MCP port |
| `artifact_store_token` | `str` | `""` | `OP_ARTIFACT_TOKEN` | Shared auth token (auto-loaded from `op_data/.artifact_token` if not set) |
| `agent_max_recursion` | `int` | `10` | `OP_MAX_RECURSION` | Max agent iterations |
| `oneprompt_api_key` | `str` | `""` | `ONEPROMPT_API_KEY` | Cloud mode API key |
| `oneprompt_api_url` | `str` | `https://api.oneprompt.eu` | `ONEPROMPT_API_URL` | Cloud API base URL |

---

## Class Methods

### `from_env()`

Create a `Config` from environment variables:

```python
config = Config.from_env()
```

Reads all settings from the corresponding environment variables listed in the parameters table above.

---

## Properties

### `mode`

```python
config.mode  # "local" or "cloud"
```

Returns `"cloud"` if `oneprompt_api_key` is set, otherwise `"local"`.

---

## Computed Properties

| Property | Type | Description |
|----------|------|-------------|
| `artifact_store_url` | `str` | `http://localhost:{artifact_store_port}` |
| `mcp_postgres_url` | `str` | `http://localhost:{postgres_mcp_port}/mcp` |
| `mcp_chart_url` | `str` | `http://localhost:{chart_mcp_port}/mcp` |
| `mcp_python_url` | `str` | `http://localhost:{python_mcp_port}/mcp` |
| `export_dir` | `Path` | `{data_dir}/exports` — used by Docker containers for artifact storage |
| `state_db_path` | `str` | `{data_dir}/state.db` |

```python
config = Config.from_env()

print(config.artifact_store_url)  # http://localhost:3336
print(config.mcp_postgres_url)    # http://localhost:3333/mcp
print(config.export_dir)          # /absolute/path/op_data/exports
print(config.state_db_path)       # /absolute/path/op_data/state.db
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
# ["llm_api_key is required (env: LLM_API_KEY)",
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
# {"LLM_API_KEY": "...", "DATABASE_URL": "...", ...}
```

---

## Path Resolution

Relative paths in `data_dir` are resolved to absolute paths at initialization time, based on the current working directory.

```python
# If cwd is /home/user/project
config = Config(data_dir="./op_data")
print(config.data_dir)  # /home/user/project/op_data

# Absolute paths are kept as-is
config = Config(data_dir="/var/data/op")
print(config.data_dir)  # /var/data/op
```

---

## Auto-loading Schema Docs

If `schema_docs_path` is provided and the file exists, the content is automatically loaded into `schema_docs` during initialization:

```python
config = Config(
    llm_api_key="...",
    database_url="...",
    schema_docs_path="./DATABASE.md",
)
# config.schema_docs now contains the file content
```
