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


def _save_oneprompt_api_key_interactive(api_key: str | None = None) -> Path:
    """Prompt for and persist oneprompt cloud API key."""
    key = (api_key or "").strip()
    if not key:
        key = click.prompt("Enter your oneprompt API key", hide_input=True).strip()
    if not key:
        raise click.ClickException("API key cannot be empty")
    return save_oneprompt_api_key(key)


def _parse_init_mode(value: str) -> str | None:
    """Parse init mode accepting local/cloud aliases."""
    normalized = value.strip().lower()
    if normalized in {"0", "local"}:
        return "local"
    if normalized in {"1", "cloud"}:
        return "cloud"
    return None


def _resolve_init_mode(explicit_mode: str | None = None) -> str:
    """Resolve init mode from option or interactive prompt."""
    if explicit_mode:
        parsed = _parse_init_mode(explicit_mode)
        if parsed is None:
            raise click.ClickException("Invalid mode. Use: 0, 1, local, or cloud.")
        return parsed

    while True:
        raw = click.prompt("Select mode [0=local, 1=cloud]", default="0")
        parsed = _parse_init_mode(raw)
        if parsed is not None:
            return parsed
        click.echo("Invalid value. Use 0, 1, local, or cloud.")


@click.group()
@click.version_option(version=__version__, prog_name="oneprompt")
def main():
    """oneprompt — AI agents for data analysis."""
    pass


@main.command()
@click.option("--api-key", envvar="ONEPROMPT_API_KEY", default=None, help="oneprompt cloud API key")
def login(api_key: str | None):
    """Save oneprompt cloud API key for cloud mode."""
    path = _save_oneprompt_api_key_interactive(api_key)
    click.echo(f"Saved oneprompt API key to: {path}")
    click.echo("Cloud mode is enabled. Use `oneprompt_sdk.Client(oneprompt_api_key=...)` in your code.")
    click.echo("For cloud-only usage, prefer: pip install oneprompt-sdk")


@main.command()
@click.option(
    "--schema",
    "schema_path",
    envvar="OP_SCHEMA_DOCS_PATH",
    default=None,
    help="Path to DATABASE.md schema docs (default: ./DATABASE.md)",
)
@click.option("--detach/--no-detach", "-d", default=True, help="Run in background")
def start(
    schema_path: str | None,
    detach: bool,
):
    """Start local MCP services (Docker)."""
    load_dotenv(Path.cwd() / ".env")

    schema_path = schema_path or os.environ.get("OP_SCHEMA_DOCS_PATH")

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




@main.command()
@click.option("--dir", "target_dir", default=".", help="Target directory")
@click.option("--mode", default=None, help="Mode: 0/1 or local/cloud")
def init(target_dir: str, mode: str | None):
    """Initialize a new oneprompt project."""
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    init_mode = _resolve_init_mode(mode)

    # Create DATABASE.md template (useful in both modes)
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
    _LOCAL_EXAMPLE_TEMPLATE = (
        '"""Example: Query your database with oneprompt."""\n'
        "\n"
        "# import logging\n"
        "# logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')\n"
        "\n"
        "from oneprompt import Client, Config\n"
        "\n"
        "config = Config(\n"
        '    llm_api_key="YOUR_API_KEY",         # Google / OpenAI / Anthropic key\n'
        '    llm_provider="google",              # "google", "openai", or "anthropic"\n'
        '    database_url="YOUR_POSTGRES_URL",   # postgresql://user:pass@host:5432/db\n'
        '    schema_docs_path="./DATABASE.md",   # optional but recommended\n'
        ")\n"
        "\n"
        "client = Client(config=config)\n"
        "\n"
        "# ── 1. Query your database ──────────────────────────────────────────\n"
        'result = client.query("Give me the sales data for the last 30 days.")\n'
        "print(result.summary)\n"
        "for row in result.preview:\n"
        "    print(row)\n"
        "\n"
        "# Artifacts are fetched on-demand — nothing downloads until you ask.\n"
        "for art in result.artifacts:\n"
        "    print(art.read_text())         # fetch content from the artifact store\n"
        '    art.download("./output/")      # save to a local directory\n'
        "\n"
        "# ── 2. Generate a chart ─────────────────────────────────────────────\n"
        'chart = client.chart("Bar chart of sales by day", data_from=result)\n'
        "print(f\"ok={chart.ok}  summary={chart.summary}  error={chart.error}\")\n"
        "for art in chart.artifacts:\n"
        "    print(art.read_text())\n"
        '    art.download("./output/")\n'
        "\n"
        "# ── 3. Run Python analysis ──────────────────────────────────────────\n"
        "analysis = client.analyze(\n"
        '    "Identify sales trends and highlight top-performing days.",\n'
        "    data_from=result,\n"
        ")\n"
        "print(f\"ok={analysis.ok}  summary={analysis.summary}  error={analysis.error}\")\n"
        "for art in analysis.artifacts:\n"
        "    print(art.read_text())\n"
        '    art.download("./output/")\n'
    )
    _CLOUD_EXAMPLE_TEMPLATE = (
        '"""Example: Query your database with oneprompt Cloud."""\n'
        "\n"
        "from oneprompt_sdk import Client, Config\n"
        "\n"
        "config = Config(\n"
        '    database_url="YOUR_POSTGRES_URL",   # postgresql://user:pass@host:5432/db\n'
        '    schema_docs_path="./DATABASE.md",   # optional but recommended\n'
        ")\n"
        "\n"
        "# API key is loaded automatically from credentials saved by `op init`.\n"
        "# You can also set ONEPROMPT_API_KEY in your environment or .env file.\n"
        "client = Client(config=config)\n"
        "\n"
        "# ── 1. Query your database ──────────────────────────────────────────\n"
        'result = client.query("Give me the sales data for the last 30 days.")\n'
        "print(result.summary)\n"
        "for row in result.preview:\n"
        "    print(row)\n"
        "\n"
        "# Artifacts are fetched on-demand — nothing downloads until you ask.\n"
        "for art in result.artifacts:\n"
        "    print(art.read_text())         # fetch content from the artifact store\n"
        '    art.download("./output/")      # save to a local directory\n'
        "\n"
        "# ── 2. Generate a chart ─────────────────────────────────────────────\n"
        'chart = client.chart("Bar chart of sales by day", data_from=result)\n'
        "print(f\"ok={chart.ok}  summary={chart.summary}  error={chart.error}\")\n"
        "for art in chart.artifacts:\n"
        "    print(art.read_text())\n"
        '    art.download("./output/")\n'
        "\n"
        "# ── 3. Run Python analysis ──────────────────────────────────────────\n"
        "analysis = client.analyze(\n"
        '    "Identify sales trends and highlight top-performing days.",\n'
        "    data_from=result,\n"
        ")\n"
        "print(f\"ok={analysis.ok}  summary={analysis.summary}  error={analysis.error}\")\n"
        "for art in analysis.artifacts:\n"
        "    print(art.read_text())\n"
        '    art.download("./output/")\n'
    )
    example_template = _LOCAL_EXAMPLE_TEMPLATE if init_mode == "local" else _CLOUD_EXAMPLE_TEMPLATE
    example_file = target / "example.py"
    if not example_file.exists():
        example_file.write_text(example_template)
        click.echo(f"  Created {example_file}")

    if init_mode == "local":
        # Copy docker-compose.yml
        compose_src = Path(__file__).resolve().parent.parent / "docker-compose.yml"
        compose_dst = target / "docker-compose.yml"
        if compose_src.exists() and not compose_dst.exists():
            shutil.copy2(compose_src, compose_dst)
            click.echo(f"  Created {compose_dst}")

    if init_mode == "cloud":
        existing_key = _resolve_oneprompt_api_key()
        if existing_key:
            click.echo("  oneprompt API key already configured.")
        raw = click.prompt(
            "Enter your oneprompt API key (press Enter to skip)",
            default="",
            hide_input=True,
            show_default=False,
        ).strip()
        if raw:
            path = save_oneprompt_api_key(raw)
            click.echo(f"  Saved oneprompt API key to: {path}")
        elif existing_key:
            click.echo("  Keeping existing API key.")
        else:
            click.echo("  Skipped. Set ONEPROMPT_API_KEY in your environment or .env file.")

    click.echo()
    click.echo(f"Project initialized in {init_mode} mode! Next steps:")
    click.echo()
    if init_mode == "local":
        click.echo("  1. Edit example.py — fill in YOUR_API_KEY and YOUR_POSTGRES_URL")
        click.echo("  2. Edit DATABASE.md with your database schema")
        click.echo("  3. Start services: op start")
        click.echo("  4. Run the example: python example.py")
        click.echo()
        click.echo("  Tip: you can also use environment variables (LLM_API_KEY, DATABASE_URL)")
        click.echo("       or a .env file instead of passing credentials in code.")
    else:
        click.echo("  1. Install cloud SDK: pip install oneprompt-sdk")
        click.echo("  2. Use `import oneprompt_sdk as op` in your app")
        click.echo("  3. Run without Docker (`op start` is not needed in cloud mode)")
    click.echo()


if __name__ == "__main__":
    main()
