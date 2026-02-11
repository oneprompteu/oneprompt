# CLI

The `tp` command-line tool manages your ThinkingProducts project: scaffolding, starting/stopping services, and launching the API server.

```bash
tp --help
```

---

## Commands

### `tp init`

Initialize a new ThinkingProducts project in the current directory.

```bash
tp init [--dir TARGET_DIR]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dir` | `.` | Target directory to initialize |

Creates the following files:

| File | Purpose |
|------|---------|
| `.env` | Configuration template with API key and database URL placeholders |
| `DATABASE.md` | Schema documentation template |
| `docker-compose.yml` | Docker stack for MCP servers |
| `example.py` | Ready-to-run example script |

!!! note
    Existing files are never overwritten. Only missing files are created.

---

### `tp start`

Build and start all MCP servers and the Artifact Store via Docker Compose.

```bash
tp start [OPTIONS]
```

| Option | Env Variable | Description |
|--------|-------------|-------------|
| `--gemini-key` | `GOOGLE_API_KEY` | Gemini API key |
| `--database-url` | `DATABASE_URL` | PostgreSQL connection string |
| `--schema` | `TP_SCHEMA_DOCS_PATH` | Path to DATABASE.md |
| `-d / --detach` | — | Run in background (default: yes) |
| `--no-detach` | — | Run in foreground |

If credentials are not provided via options or environment variables, you will be prompted interactively.

**Example:**

```bash
# Using .env file (recommended)
tp start

# With explicit options
tp start --gemini-key "your-key" --database-url "postgresql://..."

# Run in foreground to see logs
tp start --no-detach
```

**Services started:**

| Service | Port | Description |
|---------|------|-------------|
| Artifact Store | 3336 | File storage for generated outputs |
| PostgreSQL MCP | 3333 | SQL query execution engine |
| Chart MCP | 3334 | AntV chart generation |
| Python MCP | 3335 | Sandboxed Python execution |

---

### `tp stop`

Stop all running Docker services.

```bash
tp stop
```

---

### `tp status`

Show the status of all Docker services.

```bash
tp status
```

Runs `docker compose ps` to display running containers and their ports.

---

### `tp logs`

Tail the Docker service logs.

```bash
tp logs
```

Shows the last 50 lines and follows new output. Press `Ctrl+C` to stop.

---

### `tp api`

Start the local REST API server.

```bash
tp api [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `0.0.0.0` | API server host |
| `--port` | `8000` | API server port |
| `--reload / --no-reload` | `--reload` | Auto-reload on code changes |

**Example:**

```bash
# Default settings
tp api

# Custom port
tp api --port 9000

# Production mode (no auto-reload)
tp api --no-reload
```

!!! warning "Prerequisite"
    Run `tp start` before `tp api`. The API server depends on the MCP Docker services.

---

### `tp --version`

Show the installed SDK version.

```bash
tp --version
```

---

## Typical Workflow

```bash
# 1. Set up the project
tp init

# 2. Edit configuration
#    → .env (API key, database URL)
#    → DATABASE.md (schema documentation)

# 3. Start services
tp start

# 4. Verify everything is running
tp status

# 5. Use the SDK or start the API
python example.py    # Python SDK
tp api               # REST API

# 6. View logs if needed
tp logs

# 7. Stop when done
tp stop
```
