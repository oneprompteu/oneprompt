# CLI

The `op` command-line tool manages your oneprompt project: scaffolding, starting/stopping services, and launching the API server.

```bash
op --help
```

---

## Commands

### `op init`

Initialize a new oneprompt project in the current directory.

```bash
op init [--dir TARGET_DIR] [--mode MODE]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dir` | `.` | Target directory to initialize |
| `--mode` | interactive prompt | `0`/`local` or `1`/`cloud` |

`op init` asks for mode if `--mode` is not provided.

- `0` or `local`: local Docker mode
- `1` or `cloud`: oneprompt cloud mode

Creates mode-specific files:

| File | Purpose |
|------|---------|
| `.env` | Local mode only. Configuration template with API key and database URL placeholders |
| `DATABASE.md` | Local mode only. Schema documentation template |
| `docker-compose.yml` | Local mode only. Docker stack for MCP servers |
| `example.py` | Ready-to-run example script |

!!! note
    Existing files are not overwritten. If `.env` already exists, `op init` appends only missing required local keys (`LLM_PROVIDER`, `LLM_API_KEY`, `DATABASE_URL`, `OP_SCHEMA_DOCS_PATH`).
    In cloud mode, `op init` runs the equivalent of `op login` and asks for your API key interactively.

---

### `op start`

Build and start all MCP servers and the Artifact Store via Docker Compose.

```bash
op start [OPTIONS]
```

| Option | Env Variable | Description |
|--------|-------------|-------------|
| `--llm-key` | `LLM_API_KEY` | LLM API key |
| `--database-url` | `DATABASE_URL` | PostgreSQL connection string |
| `--schema` | `OP_SCHEMA_DOCS_PATH` | Path to DATABASE.md |
| `-d / --detach` | — | Run in background (default: yes) |
| `--no-detach` | — | Run in foreground |

If credentials are not provided via options or environment variables, you will be prompted interactively.

**Example:**

```bash
# Using .env file (recommended)
op start

# With explicit options
op start --llm-key "your-key" --database-url "postgresql://..."

# Run in foreground to see logs
op start --no-detach
```

**Services started:**

| Service | Port | Description |
|---------|------|-------------|
| Artifact Store | 3336 | File storage for generated outputs |
| PostgreSQL MCP | 3333 | SQL query execution engine |
| Chart MCP | 3334 | AntV chart generation |
| Python MCP | 3335 | Sandboxed Python execution |

---

### `op stop`

Stop all running Docker services.

```bash
op stop
```

---

### `op status`

Show the status of all Docker services.

```bash
op status
```

Runs `docker compose ps` to display running containers and their ports.

---

### `op logs`

Tail the Docker service logs.

```bash
op logs
```

Shows the last 50 lines and follows new output. Press `Ctrl+C` to stop.

---

### `op api`

Start the local REST API server.

```bash
op api [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | API server host |
| `--port` | `8000` | API server port |
| `--reload / --no-reload` | `--reload` | Auto-reload on code changes |

**Example:**

```bash
# Default settings
op api

# Custom port
op api --port 9000

# Production mode (no auto-reload)
op api --no-reload
```

!!! warning "Prerequisite"
    Run `op start` before `op api`. The API server depends on the MCP Docker services.

---

### `op --version`

Show the installed SDK version.

```bash
op --version
```

---

## Typical Workflow

```bash
# Local mode
op init --mode local

# 1. Edit configuration
#    → .env (API key, database URL)
#    → DATABASE.md (schema documentation)

# 2. Start services
op start

# 3. Verify everything is running
op status

# 4. Use the SDK or start the API
python example.py    # Python SDK
op api               # REST API

# 5. View logs if needed
op logs

# 6. Stop when done
op stop
```

```bash
# Cloud mode
op init --mode cloud

# `op init` asks for your oneprompt API key and saves it securely.
# No local Docker startup is needed.
python example.py
```
