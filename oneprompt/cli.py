"""
oneprompt CLI — Quick start for local development.

Commands:
    op login     Save oneprompt cloud API key
    op start     Start all MCP servers (Docker Compose)
    op stop      Stop all services
    op status    Check service health
    op api       Start the API server
    op init      Create a config file template
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import click
from dotenv import load_dotenv

from oneprompt._version import __version__
from oneprompt.services.credentials import load_oneprompt_api_key, save_oneprompt_api_key


def _find_compose_file() -> Path:
    """Find docker-compose.yml shipped with the package."""
    pkg_dir = Path(__file__).resolve().parent.parent
    packaged = pkg_dir / "docker-compose.yml"
    if packaged.exists():
        return packaged

    local = Path.cwd() / "docker-compose.yml"
    if local.exists():
        return local

    raise click.ClickException(
        "docker-compose.yml not found. Run `op init` first or cd into your project directory."
    )


def _docker_compose_cmd() -> list[str]:
    """Return the correct docker compose command."""
    result = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return ["docker", "compose"]

    if shutil.which("docker-compose"):
        return ["docker-compose"]

    raise click.ClickException(
        "Docker Compose not found. Install Docker Desktop or docker-compose."
    )


def _resolve_oneprompt_api_key(explicit_key: str | None = None) -> str:
    """Resolve oneprompt API key from CLI arg, env var, or secure credentials."""
    if explicit_key:
        return explicit_key.strip()
    env_key = os.environ.get("ONEPROMPT_API_KEY", "").strip()
    if env_key:
        return env_key
    return load_oneprompt_api_key()


@click.group()
@click.version_option(version=__version__, prog_name="oneprompt")
def main():
    """oneprompt — AI agents for data analysis."""
    pass


@main.command()
@click.option("--api-key", envvar="ONEPROMPT_API_KEY", default=None, help="oneprompt cloud API key")
def login(api_key: str | None):
    """Save oneprompt cloud API key for cloud mode."""
    key = (api_key or "").strip()
    if not key:
        key = click.prompt("Enter your oneprompt API key", hide_input=True).strip()
    if not key:
        raise click.ClickException("API key cannot be empty")

    path = save_oneprompt_api_key(key)
    click.echo(f"Saved oneprompt API key to: {path}")
    click.echo("Cloud mode is enabled. `op start` will skip Docker services.")


@main.command()
@click.option("--oneprompt-key", envvar="ONEPROMPT_API_KEY", help="oneprompt cloud API key")
@click.option("--llm-key", envvar="LLM_API_KEY", help="LLM API key")
@click.option("--database-url", envvar="DATABASE_URL", help="PostgreSQL connection string")
@click.option(
    "--schema",
    "schema_path",
    envvar="OP_SCHEMA_DOCS_PATH",
    default=None,
    help="Path to DATABASE.md schema docs (default: ./DATABASE.md)",
)
@click.option("--detach/--no-detach", "-d", default=True, help="Run in background")
def start(
    oneprompt_key: str | None,
    llm_key: str | None,
    database_url: str | None,
    schema_path: str | None,
    detach: bool,
):
    """Start local MCP services, or no-op when cloud mode is configured."""
    load_dotenv(Path.cwd() / ".env")
    oneprompt_key = _resolve_oneprompt_api_key(oneprompt_key)
    if oneprompt_key:
        click.echo("Cloud mode detected (ONEPROMPT_API_KEY configured).")
        click.echo("Skipping local Docker startup. Use op.Client(oneprompt_api_key=...) directly.")
        return

    llm_key = llm_key or os.environ.get("LLM_API_KEY")
    database_url = database_url or os.environ.get("DATABASE_URL")
    schema_path = schema_path or os.environ.get("OP_SCHEMA_DOCS_PATH")

    if not llm_key:
        llm_key = click.prompt("Enter your LLM API key", hide_input=True)
    if not database_url:
        database_url = click.prompt(
            "Enter your PostgreSQL connection string",
            default="postgresql://user:pass@localhost:5432/mydb",
        )

    # Resolve DATABASE.md path
    if schema_path:
        schema_file = Path(schema_path).resolve()
    else:
        schema_file = Path.cwd() / "DATABASE.md"

    if not schema_file.exists():
        schema_file_str = click.prompt(
            "DATABASE.md not found. Enter path to your schema docs file",
            default=str(schema_file),
        )
        schema_file = Path(schema_file_str).resolve()
        if not schema_file.exists():
            raise click.ClickException(
                f"Schema file not found: {schema_file}\n"
                "Run `op init` to create a template, then edit DATABASE.md with your schema."
            )

    click.echo(f"Using schema: {schema_file}")

    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    artifact_token = os.environ.get("OP_ARTIFACT_TOKEN", "")
    if not artifact_token:
        import secrets

        artifact_token = secrets.token_hex(16)

    # Persist token so the SDK can authenticate with the artifact store
    data_dir = Path(os.environ.get("OP_DATA_DIR", "./op_data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file = data_dir / ".artifact_token"
    token_file.write_text(artifact_token)

    env = os.environ.copy()
    env["LLM_API_KEY"] = llm_key
    env["DATABASE_URL"] = database_url
    env["OP_ARTIFACT_TOKEN"] = artifact_token
    env["OP_SCHEMA_DOCS_PATH"] = str(schema_file)

    click.echo("Building and starting services...")
    cmd = [*compose_cmd, "-f", str(compose_file), "up", "--build"]
    if detach:
        cmd.append("-d")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        raise click.ClickException("Failed to start services")

    if detach:
        click.echo()
        click.echo("Services started successfully!")
        click.echo()
        click.echo("  Artifact Store  -> http://localhost:3336")
        click.echo("  PostgreSQL MCP  -> http://localhost:3333")
        click.echo("  Chart MCP       -> http://localhost:3334")
        click.echo("  Python MCP      -> http://localhost:3335")
        click.echo()
        click.echo("Now start the API with: op api")
        click.echo("Or use the Python SDK directly:")
        click.echo()
        click.echo("  import oneprompt as op")
        click.echo("  client = op.Client()")
        click.echo('  result = client.query("Show me all tables")')


@main.command()
def stop():
    """Stop all services."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    click.echo("Stopping services...")
    subprocess.run([*compose_cmd, "-f", str(compose_file), "down"])
    click.echo("All services stopped.")


@main.command()
def status():
    """Check service health."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    subprocess.run([*compose_cmd, "-f", str(compose_file), "ps"])


@main.command()
def logs():
    """Show service logs."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    subprocess.run([*compose_cmd, "-f", str(compose_file), "logs", "-f", "--tail=50"])


@main.command()
@click.option("--host", default="0.0.0.0", help="API host")
@click.option("--port", default=8000, type=int, help="API port")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on changes")
def api(host: str, port: int, reload: bool):
    """Start the local API server."""
    click.echo(f"Starting API server on http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")

    try:
        import uvicorn

        uvicorn.run(
            "oneprompt.api:app",
            host=host,
            port=port,
            reload=reload,
        )
    except ImportError:
        raise click.ClickException("uvicorn is required. Install with: pip install uvicorn")


_ENV_TEMPLATE = """\
# oneprompt Configuration
# Documentation: https://github.com/oneprompt/oneprompt

# ---- oneprompt Cloud (optional) ----
# If ONEPROMPT_API_KEY is set, the SDK/CLI use cloud mode and skip local Docker.
# ONEPROMPT_API_KEY=op_live_xxx
# ONEPROMPT_API_URL=https://api.oneprompt.eu

# ---- LLM Provider ----
# Supported: google, openai, anthropic
LLM_PROVIDER=google

# ---- LLM API Key ----
# Google / Vertex AI: https://aistudio.google.com/apikey
# OpenAI: https://platform.openai.com/api-keys
# Anthropic: https://console.anthropic.com/settings/keys
LLM_API_KEY=your-api-key-here

# ---- LLM Model ----
# Leave empty to use the default model for your provider
# LLM_MODEL=

# ---- Database ----
DATABASE_URL=postgresql://user:password@localhost:5432/mydb

# ---- Schema Documentation ----
# Path to your DATABASE.md with table/column descriptions
OP_SCHEMA_DOCS_PATH=./DATABASE.md

# ---- Data Directory ----
OP_DATA_DIR=./op_data

# ---- Agent Settings ----
# Maximum agent reasoning iterations (default: 10)
# OP_MAX_RECURSION=10

# ---- Service Ports ----
# OP_PORT=8000
# OP_ARTIFACT_PORT=3336
# OP_POSTGRES_MCP_PORT=3333
# OP_CHART_MCP_PORT=3334
# OP_PYTHON_MCP_PORT=3335

# ---- Artifact Store ----
# Auto-generated on `op start` and saved to {data_dir}/.artifact_token
# Only set manually if you need a specific token
# OP_ARTIFACT_TOKEN=your-secret-token

# ---- LangSmith (optional) ----
# LANGSMITH_TRACING=true
# LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
# LANGSMITH_API_KEY=your-langsmith-key
# LANGSMITH_PROJECT=your-project-name
"""

_CLOUD_ENV_EXAMPLE = """\
# oneprompt Cloud example configuration
# Use this instead of local Docker credentials when running in cloud mode.

ONEPROMPT_API_KEY=op_live_your_api_key
ONEPROMPT_API_URL=https://api.oneprompt.eu
"""


@main.command()
@click.option("--dir", "target_dir", default=".", help="Target directory")
def init(target_dir: str):
    """Initialize a new oneprompt project."""
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    # Create .env template
    env_file = target / ".env"
    if not env_file.exists():
        env_file.write_text(_ENV_TEMPLATE)
        click.echo(f"  Created {env_file}")

    cloud_env_file = target / ".env.cloud.example"
    if not cloud_env_file.exists():
        cloud_env_file.write_text(_CLOUD_ENV_EXAMPLE)
        click.echo(f"  Created {cloud_env_file}")

    # Create DATABASE.md template
    schema_file = target / "DATABASE.md"
    if not schema_file.exists():
        schema_file.write_text(
            "# Database Schema\n"
            "\n"
            "Describe your database tables here. This helps the AI agent\n"
            "understand your data structure and write better SQL queries.\n"
            "\n"
            "## Tables\n"
            "\n"
            "### users\n"
            "| Column | Type | Description |\n"
            "|--------|------|-------------|\n"
            "| id | integer | Primary key |\n"
            "| name | text | User name |\n"
            "| email | text | User email |\n"
            "| created_at | timestamp | Registration date |\n"
            "\n"
            "### orders\n"
            "| Column | Type | Description |\n"
            "|--------|------|-------------|\n"
            "| id | integer | Primary key |\n"
            "| user_id | integer | Foreign key to users |\n"
            "| total | numeric | Order total |\n"
            "| created_at | timestamp | Order date |\n"
            "\n"
            "## Relationships\n"
            "- users.id -> orders.user_id (one-to-many)\n"
        )
        click.echo(f"  Created {schema_file}")

    # Create example script
    example_file = target / "example.py"
    if not example_file.exists():
        example_file.write_text(
            '"""Example: Query your database with oneprompt."""\n'
            "\n"
            "import oneprompt as op\n"
            "\n"
            "# Initialize client (reads from .env or pass directly)\n"
            "client = op.Client()\n"
            "\n"
            "# ── 1. Query your database ──────────────────────────────────────────\n"
            'result = client.query("Show me the top 10 customers by order total.")\n'
            "print(result.summary)\n"
            "for row in result.preview:\n"
            "    print(row)\n"
            "\n"
            "# Artifacts are fetched on-demand — nothing downloads until you ask.\n"
            "for art in result.artifacts:\n"
            "    print(art.read_text())         # fetch content from the artifact store\n"
            '    art.download("./output/")     # save to a local directory\n'
            "\n"
            "# ── 2. Generate a chart ─────────────────────────────────────────────\n"
            'chart = client.chart("Bar chart of top customers", data_from=result)\n'
            "print(chart.summary)\n"
            "for art in chart.artifacts:\n"
            "    print(art.read_text())\n"
            '    art.download("./output/")\n'
            "\n"
            "# ── 3. Run Python analysis ──────────────────────────────────────────\n"
            "analysis = client.analyze(\n"
            '    "Calculate average order value per customer",\n'
            "    data_from=result,\n"
            ")\n"
            "print(analysis.summary)\n"
            "for art in analysis.artifacts:\n"
            "    print(art.read_text())\n"
            '    art.download("./output/")\n'
        )
        click.echo(f"  Created {example_file}")

    # Copy docker-compose.yml
    compose_src = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    compose_dst = target / "docker-compose.yml"
    if compose_src.exists() and not compose_dst.exists():
        shutil.copy2(compose_src, compose_dst)
        click.echo(f"  Created {compose_dst}")

    click.echo()
    click.echo("Project initialized! Next steps:")
    click.echo()
    click.echo("  1. Local mode: edit .env with LLM + database settings, then run: op start")
    click.echo("  2. Cloud mode: run `op login` (or set ONEPROMPT_API_KEY) and skip op start")
    click.echo("  3. Edit DATABASE.md with your database schema (local mode)")
    click.echo("  4. Run the example: python example.py")
    click.echo()


if __name__ == "__main__":
    main()
