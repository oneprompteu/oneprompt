"""
oneprompt configuration.

Handles all settings via environment variables, config files, or direct initialization.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from oneprompt.services.credentials import load_oneprompt_api_key


@dataclass
class Config:
    """
    Configuration for oneprompt.

    Can be initialized directly or loaded from environment variables.

    Args:
        oneprompt_api_key: API key for oneprompt cloud mode (env: ONEPROMPT_API_KEY)
        oneprompt_api_url: Base URL for oneprompt cloud API (env: ONEPROMPT_API_URL)
        llm_provider: LLM provider — google, openai, or anthropic (env: LLM_PROVIDER)
        llm_api_key: API key for the chosen LLM provider (env: LLM_API_KEY)
        llm_model: Model name (env: LLM_MODEL, default depends on provider)
        database_url: PostgreSQL connection string (env: DATABASE_URL)
        schema_docs: SQL schema documentation for LLM context (optional)
        data_dir: Directory for local data storage (env: OP_DATA_DIR, default: ./op_data)
        local_host: Host for local services (env: OP_LOCAL_HOST, default: 127.0.0.1)
        host: API host (env: OP_HOST, default: 0.0.0.0)
        port: API port (env: OP_PORT, default: 8000)
        artifact_store_port: Artifact store port (env: OP_ARTIFACT_PORT, default: 3336)
        postgres_mcp_port: PostgreSQL MCP server port (env: OP_POSTGRES_MCP_PORT, default: 3333)
        chart_mcp_port: Chart MCP server port (env: OP_CHART_MCP_PORT, default: 3334)
        python_mcp_port: Python MCP server port (env: OP_PYTHON_MCP_PORT, default: 3335)
    """

    # oneprompt cloud settings
    oneprompt_api_key: str = ""
    oneprompt_api_url: str = ""

    # LLM settings
    llm_provider: str = "google"
    llm_api_key: str = ""
    llm_model: str = ""

    # Required
    database_url: str = ""

    # Schema documentation
    schema_docs: str = ""
    schema_docs_path: Optional[str] = None

    # Directories
    data_dir: str = "./op_data"

    # Local services host
    local_host: str = "127.0.0.1"

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

    # Default models per provider
    _DEFAULT_MODELS: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Resolve relative paths, apply defaults, and load schema docs."""
        self._DEFAULT_MODELS = {
            "google": "gemini-3-flash-preview-preview",
            "openai": "gpt-5",
            "anthropic": "claude-sonnet-4.5",
        }

        self.oneprompt_api_key = self.oneprompt_api_key.strip()
        self.oneprompt_api_url = self.oneprompt_api_url.strip().rstrip("/")

        # Auto-load API URL from env if not provided
        if not self.oneprompt_api_url:
            self.oneprompt_api_url = os.getenv("ONEPROMPT_API_URL", "").strip().rstrip("/")

        self.llm_provider = self.llm_provider.lower().strip()
        if not self.llm_model:
            self.llm_model = self._DEFAULT_MODELS.get(self.llm_provider, "")

        # Resolve data_dir to absolute path
        self.data_dir = str(Path(self.data_dir).resolve())
        self.local_host = self.local_host.strip() or "127.0.0.1"

        if self.schema_docs_path and not self.schema_docs:
            path = Path(self.schema_docs_path)
            if path.exists():
                self.schema_docs = path.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> Config:
        """
        Create configuration from environment variables.

        Environment variables:
            ONEPROMPT_API_KEY: oneprompt cloud API key (enables cloud mode)
            ONEPROMPT_API_URL: oneprompt cloud API URL (required in cloud mode)
            LLM_PROVIDER: LLM provider — google, openai, anthropic (default: google)
            LLM_API_KEY: API key for the chosen provider
            LLM_MODEL: Model name (defaults per provider if not set)
            DATABASE_URL: PostgreSQL connection string
            OP_SCHEMA_DOCS: Inline schema documentation
            OP_SCHEMA_DOCS_PATH: Path to schema docs file (DATABASE.md)
            OP_DATA_DIR: Data directory (default: ./op_data)
            OP_LOCAL_HOST: Host for local services (default: 127.0.0.1)
            OP_HOST: API host (default: 0.0.0.0)
            OP_PORT: API port (default: 8000)
            OP_ARTIFACT_PORT: Artifact store port (default: 3336)
            OP_POSTGRES_MCP_PORT: PostgreSQL MCP port (default: 3333)
            OP_CHART_MCP_PORT: Chart MCP port (default: 3334)
            OP_PYTHON_MCP_PORT: Python MCP port (default: 3335)
            OP_ARTIFACT_TOKEN: Artifact store token (auto-generated if not set)
            OP_MAX_RECURSION: Agent max recursion (default: 10)
        """
        oneprompt_api_key = os.getenv("ONEPROMPT_API_KEY", "").strip()
        if not oneprompt_api_key:
            oneprompt_api_key = load_oneprompt_api_key()

        return cls(
            oneprompt_api_key=oneprompt_api_key,
            oneprompt_api_url=os.getenv("ONEPROMPT_API_URL", ""),
            llm_provider=os.getenv("LLM_PROVIDER", "google"),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            database_url=os.getenv("DATABASE_URL", ""),
            schema_docs=os.getenv("OP_SCHEMA_DOCS", ""),
            schema_docs_path=os.getenv("OP_SCHEMA_DOCS_PATH"),
            data_dir=os.getenv("OP_DATA_DIR", "./op_data"),
            local_host=os.getenv("OP_LOCAL_HOST", "127.0.0.1"),
            host=os.getenv("OP_HOST", "0.0.0.0"),
            port=int(os.getenv("OP_PORT", "8000")),
            artifact_store_port=int(os.getenv("OP_ARTIFACT_PORT", "3336")),
            postgres_mcp_port=int(os.getenv("OP_POSTGRES_MCP_PORT", "3333")),
            chart_mcp_port=int(os.getenv("OP_CHART_MCP_PORT", "3334")),
            python_mcp_port=int(os.getenv("OP_PYTHON_MCP_PORT", "3335")),
            artifact_store_token=os.getenv("OP_ARTIFACT_TOKEN", ""),
            agent_max_recursion=int(os.getenv("OP_MAX_RECURSION", "10")),
        )

    @property
    def artifact_store_url(self) -> str:
        return f"http://{self.local_host}:{self.artifact_store_port}"

    @property
    def mcp_postgres_url(self) -> str:
        return f"http://{self.local_host}:{self.postgres_mcp_port}/mcp"

    @property
    def mcp_chart_url(self) -> str:
        return f"http://{self.local_host}:{self.chart_mcp_port}/mcp"

    @property
    def mcp_python_url(self) -> str:
        return f"http://{self.local_host}:{self.python_mcp_port}/mcp"

    @property
    def export_dir(self) -> Path:
        """Path where exports would be stored (used by Docker containers)."""
        return Path(self.data_dir) / "exports"

    @property
    def state_db_path(self) -> str:
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        return str(Path(self.data_dir) / "state.db")

    @property
    def mode(self) -> str:
        """Runtime mode derived from configured credentials."""
        return "cloud" if self.oneprompt_api_key else "local"

    def to_env_dict(self) -> dict[str, str]:
        """Export configuration as environment variables dict (for Docker/subprocess)."""
        env = {
            "ONEPROMPT_API_KEY": self.oneprompt_api_key,
            "ONEPROMPT_API_URL": self.oneprompt_api_url,
            "LLM_PROVIDER": self.llm_provider,
            "LLM_API_KEY": self.llm_api_key,
            "LLM_MODEL": self.llm_model,
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
        if self.mode == "cloud":
            if not self.oneprompt_api_url:
                errors.append("oneprompt_api_url is required (env: ONEPROMPT_API_URL)")
            return errors

        if not self.llm_api_key:
            errors.append("llm_api_key is required (env: LLM_API_KEY)")
        if self.llm_provider not in ("google", "openai", "anthropic"):
            errors.append(
                f"llm_provider must be google, openai, or anthropic (got: {self.llm_provider})"
            )
        if not self.database_url:
            errors.append("database_url is required (env: DATABASE_URL)")
        return errors
