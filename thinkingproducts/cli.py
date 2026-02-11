"""
ThinkingProducts CLI — Quick start for local development.

Commands:
    tp start     Start all MCP servers (Docker Compose)
    tp stop      Stop all services
    tp status    Check service health
    tp api       Start the API server
    tp init      Create a config file template
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

from thinkingproducts._version import __version__


def _find_compose_file() -> Path:
    """Find docker-compose.yml shipped with the package.

    Always prefer the SDK-packaged compose file since it has the correct
    build context relative to the Dockerfiles.
    """
    # 1. Packaged with the SDK (preferred — correct build context)
    pkg_dir = Path(__file__).resolve().parent.parent
    packaged = pkg_dir / "docker-compose.yml"
    if packaged.exists():
        return packaged

    # 2. Current directory (fallback)
    local = Path.cwd() / "docker-compose.yml"
    if local.exists():
        return local

    raise click.ClickException(
        "docker-compose.yml not found. Run `tp init` first or cd into your project directory."
    )


def _docker_compose_cmd() -> list[str]:
    """Return the correct docker compose command."""
    # Try 'docker compose' (v2) first
    result = subprocess.run(
        ["docker", "compose", "version"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return ["docker", "compose"]

    # Fall back to 'docker-compose' (v1)
    if shutil.which("docker-compose"):
        return ["docker-compose"]

    raise click.ClickException(
        "Docker Compose not found. Install Docker Desktop or docker-compose."
    )


@click.group()
@click.version_option(version=__version__, prog_name="thinkingproducts")
def main():
    """🧠 ThinkingProducts — AI agents for data analysis."""
    pass


@main.command()
@click.option("--gemini-key", envvar="GOOGLE_API_KEY", help="Gemini API key")
@click.option("--database-url", envvar="DATABASE_URL", help="PostgreSQL connection string")
@click.option(
    "--schema",
    "schema_path",
    envvar="TP_SCHEMA_DOCS_PATH",
    default=None,
    help="Path to DATABASE.md schema docs (default: ./DATABASE.md)",
)
@click.option("--detach/--no-detach", "-d", default=True, help="Run in background")
def start(gemini_key: str | None, database_url: str | None, schema_path: str | None, detach: bool):
    """🚀 Start all MCP servers and services."""
    # Load .env from current directory so users don't need to export vars
    load_dotenv(Path.cwd() / ".env")
    gemini_key = gemini_key or os.environ.get("GOOGLE_API_KEY")
    database_url = database_url or os.environ.get("DATABASE_URL")
    schema_path = schema_path or os.environ.get("TP_SCHEMA_DOCS_PATH")

    if not gemini_key:
        gemini_key = click.prompt("Enter your Gemini API key", hide_input=True)
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
                "Run `tp init` to create a template, then edit DATABASE.md with your schema."
            )

    click.echo(f"📄 Using schema: {schema_file}")

    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    # Generate a random artifact store token if none is configured
    artifact_token = os.environ.get("TP_ARTIFACT_TOKEN", "")
    if not artifact_token:
        import secrets
        artifact_token = secrets.token_hex(16)

    env = os.environ.copy()
    env["GOOGLE_API_KEY"] = gemini_key
    env["DATABASE_URL"] = database_url
    env["TP_ARTIFACT_TOKEN"] = artifact_token
    env["TP_SCHEMA_DOCS_PATH"] = str(schema_file)

    click.echo("🔧 Building and starting services...")
    cmd = [*compose_cmd, "-f", str(compose_file), "up", "--build"]
    if detach:
        cmd.append("-d")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        raise click.ClickException("Failed to start services")

    if detach:
        click.echo()
        click.echo("✅ Services started successfully!")
        click.echo()
        click.echo("  📊 Artifact Store  → http://localhost:3336")
        click.echo("  🗄️  PostgreSQL MCP  → http://localhost:3333")
        click.echo("  📈 Chart MCP       → http://localhost:3334")
        click.echo("  🐍 Python MCP      → http://localhost:3335")
        click.echo()
        click.echo("Now start the API with: tp api")
        click.echo("Or use the Python SDK directly:")
        click.echo()
        click.echo("  import thinkingproducts as tp")
        click.echo(f'  client = tp.Client(gemini_api_key="{gemini_key[:8]}...")')
        click.echo('  result = client.query("Show me all tables")')


@main.command()
def stop():
    """🛑 Stop all services."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    click.echo("Stopping services...")
    subprocess.run([*compose_cmd, "-f", str(compose_file), "down"])
    click.echo("✅ All services stopped.")


@main.command()
def status():
    """📋 Check service health."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    subprocess.run([*compose_cmd, "-f", str(compose_file), "ps"])


@main.command()
def logs():
    """📜 Show service logs."""
    compose_file = _find_compose_file()
    compose_cmd = _docker_compose_cmd()

    subprocess.run([*compose_cmd, "-f", str(compose_file), "logs", "-f", "--tail=50"])


@main.command()
@click.option("--host", default="0.0.0.0", help="API host")
@click.option("--port", default=8000, type=int, help="API port")
@click.option("--reload/--no-reload", default=True, help="Auto-reload on changes")
def api(host: str, port: int, reload: bool):
    """🌐 Start the local API server."""
    click.echo(f"Starting API server on http://{host}:{port}")
    click.echo("Press Ctrl+C to stop")

    try:
        import uvicorn
        uvicorn.run(
            "thinkingproducts.api:app",
            host=host,
            port=port,
            reload=reload,
        )
    except ImportError:
        raise click.ClickException("uvicorn is required. Install with: pip install uvicorn")


@main.command()
@click.option("--dir", "target_dir", default=".", help="Target directory")
def init(target_dir: str):
    """📁 Initialize a new ThinkingProducts project."""
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    # Create .env template
    env_file = target / ".env"
    if not env_file.exists():
        env_file.write_text(
            "# ThinkingProducts Configuration\n"
            "# Get your Gemini API key at: https://aistudio.google.com/apikey\n"
            "\n"
            "GOOGLE_API_KEY=your-gemini-api-key-here\n"
            "DATABASE_URL=postgresql://user:password@localhost:5432/mydb\n"
            "\n"
            "# Path to your database schema documentation (default: ./DATABASE.md)\n"
            "# TP_SCHEMA_DOCS_PATH=./DATABASE.md\n"
            "\n"
            "# Optional: Custom ports\n"
            "# TP_PORT=8000\n"
            "# TP_ARTIFACT_PORT=3336\n"
            "# TP_POSTGRES_MCP_PORT=3333\n"
            "# TP_CHART_MCP_PORT=3334\n"
            "# TP_PYTHON_MCP_PORT=3335\n"
        )
        click.echo(f"  ✅ Created {env_file}")

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
            "- users.id → orders.user_id (one-to-many)\n"
        )
        click.echo(f"  ✅ Created {schema_file}")

    # Create example script
    example_file = target / "example.py"
    if not example_file.exists():
        example_file.write_text(
            '"""Example: Query your database with ThinkingProducts."""\n'
            "\n"
            "import thinkingproducts as tp\n"
            "\n"
            "# Initialize client (reads from .env or pass directly)\n"
            "client = tp.Client()\n"
            "\n"
            "# Query your database\n"
            'result = client.query("Show me the top 10 customers by order total")\n'
            "print(result.summary)\n"
            "for row in result.preview:\n"
            "    print(row)\n"
            "\n"
            "# Generate a chart\n"
            'chart = client.chart("Bar chart of top customers", data_from=result)\n'
            "print(f\"Chart saved: {chart.artifacts[0].path}\")\n"
            "\n"
            "# Run Python analysis\n"
            'analysis = client.analyze("Calculate average order value per customer", data_from=result)\n'
            "print(analysis.summary)\n"
        )
        click.echo(f"  ✅ Created {example_file}")

    # Copy docker-compose.yml
    compose_src = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    compose_dst = target / "docker-compose.yml"
    if compose_src.exists() and not compose_dst.exists():
        shutil.copy2(compose_src, compose_dst)
        click.echo(f"  ✅ Created {compose_dst}")

    click.echo()
    click.echo("🎉 Project initialized! Next steps:")
    click.echo()
    click.echo("  1. Edit .env with your Gemini API key and database URL")
    click.echo("  2. Edit DATABASE.md with your database schema (tables, columns, relationships)")
    click.echo("  3. Start services: tp start")
    click.echo("     (or specify a custom schema path: tp start --schema /path/to/DATABASE.md)")
    click.echo("  4. Run the example: python example.py")
    click.echo()


if __name__ == "__main__":
    main()
