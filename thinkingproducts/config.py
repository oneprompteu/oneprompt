"""
ThinkingProducts configuration.

Handles all settings via environment variables, config files, or direct initialization.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    """
    Configuration for ThinkingProducts.

    Can be initialized directly or loaded from environment variables.

    Args:
        gemini_api_key: Google Gemini API key (env: GOOGLE_API_KEY)
        gemini_model: Gemini model to use (env: GEMINI_MODEL, default: gemini-3-flash-preview)
        database_url: PostgreSQL connection string (env: DATABASE_URL)
        schema_docs: SQL schema documentation for LLM context (optional)
        data_dir: Directory for local data storage (env: TP_DATA_DIR, default: ./tp_data)
        host: API host (env: TP_HOST, default: 0.0.0.0)
        port: API port (env: TP_PORT, default: 8000)
        artifact_store_port: Artifact store port (env: TP_ARTIFACT_PORT, default: 3336)
        postgres_mcp_port: PostgreSQL MCP server port (env: TP_POSTGRES_MCP_PORT, default: 3333)
        chart_mcp_port: Chart MCP server port (env: TP_CHART_MCP_PORT, default: 3334)
        python_mcp_port: Python MCP server port (env: TP_PYTHON_MCP_PORT, default: 3335)
    """

    # Required
    gemini_api_key: str = ""
    database_url: str = ""

    # Model
    gemini_model: str = "gemini-3-flash-preview"

    # Schema documentation
    schema_docs: str = ""
    schema_docs_path: Optional[str] = None

    # Directories
    data_dir: str = "./tp_data"

    # Network
    host: str = "0.0.0.0"
    port: int = 8000
    artifact_store_port: int = 3336
    postgres_mcp_port: int = 3333
    chart_mcp_port: int = 3334
    python_mcp_port: int = 3335

    # Artifact store
    artifact_store_token: str = ""

    # Agent settings
    agent_max_recursion: int = 10

    def __post_init__(self) -> None:
        """Load schema docs from file if path is provided."""
        if self.schema_docs_path and not self.schema_docs:
            path = Path(self.schema_docs_path)
            if path.exists():
                self.schema_docs = path.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> Config:
        """
        Create configuration from environment variables.

        Environment variables:
            GOOGLE_API_KEY: Gemini API key
            GEMINI_MODEL: Model name (default: gemini-3-flash-preview)
            DATABASE_URL: PostgreSQL connection string
            TP_SCHEMA_DOCS: Inline schema documentation
            TP_SCHEMA_DOCS_PATH: Path to schema docs file (DATABASE.md)
            TP_DATA_DIR: Data directory (default: ./tp_data)
            TP_HOST: API host (default: 0.0.0.0)
            TP_PORT: API port (default: 8000)
            TP_ARTIFACT_PORT: Artifact store port (default: 3336)
            TP_POSTGRES_MCP_PORT: PostgreSQL MCP port (default: 3333)
            TP_CHART_MCP_PORT: Chart MCP port (default: 3334)
            TP_PYTHON_MCP_PORT: Python MCP port (default: 3335)
            TP_ARTIFACT_TOKEN: Artifact store token (auto-generated if not set)
            TP_MAX_RECURSION: Agent max recursion (default: 10)
        """
        return cls(
            gemini_api_key=os.getenv("GOOGLE_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
            database_url=os.getenv("DATABASE_URL", ""),
            schema_docs=os.getenv("TP_SCHEMA_DOCS", ""),
            schema_docs_path=os.getenv("TP_SCHEMA_DOCS_PATH"),
            data_dir=os.getenv("TP_DATA_DIR", "./tp_data"),
            host=os.getenv("TP_HOST", "0.0.0.0"),
            port=int(os.getenv("TP_PORT", "8000")),
            artifact_store_port=int(os.getenv("TP_ARTIFACT_PORT", "3336")),
            postgres_mcp_port=int(os.getenv("TP_POSTGRES_MCP_PORT", "3333")),
            chart_mcp_port=int(os.getenv("TP_CHART_MCP_PORT", "3334")),
            python_mcp_port=int(os.getenv("TP_PYTHON_MCP_PORT", "3335")),
            artifact_store_token=os.getenv("TP_ARTIFACT_TOKEN", ""),
            agent_max_recursion=int(os.getenv("TP_MAX_RECURSION", "10")),
        )

    @property
    def artifact_store_url(self) -> str:
        return f"http://localhost:{self.artifact_store_port}"

    @property
    def mcp_postgres_url(self) -> str:
        return f"http://localhost:{self.postgres_mcp_port}/mcp"

    @property
    def mcp_chart_url(self) -> str:
        return f"http://localhost:{self.chart_mcp_port}/mcp"

    @property
    def mcp_python_url(self) -> str:
        return f"http://localhost:{self.python_mcp_port}/mcp"

    @property
    def export_dir(self) -> Path:
        path = Path(self.data_dir) / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def state_db_path(self) -> str:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self.data_dir) / "state.db")

    def to_env_dict(self) -> dict[str, str]:
        """Export configuration as environment variables dict (for Docker/subprocess)."""
        env = {
            "GOOGLE_API_KEY": self.gemini_api_key,
            "GEMINI_MODEL": self.gemini_model,
            "POSTGRES_DSN": self.database_url,
            "DATABASE_URL": self.database_url,
            "EXPORT_DIR": str(self.export_dir),
            "ARTIFACT_STORE_URL": self.artifact_store_url,
            "ARTIFACT_STORE_TOKEN": self.artifact_store_token,
            "MCP_POSTGRES_URL": self.mcp_postgres_url,
            "MCP_CHART_URL": self.mcp_chart_url,
            "MCP_PYTHON_URL": self.mcp_python_url,
            "STATE_DB_PATH": self.state_db_path,
            "AGENT_MAX_RECURSION": str(self.agent_max_recursion),
        }
        return {k: v for k, v in env.items() if v}

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        if not self.gemini_api_key:
            errors.append("gemini_api_key is required (env: GOOGLE_API_KEY)")
        if not self.database_url:
            errors.append("database_url is required (env: DATABASE_URL)")
        return errors
