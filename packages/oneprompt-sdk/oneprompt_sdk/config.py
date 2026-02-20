"""oneprompt cloud SDK configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from oneprompt_sdk.services.credentials import load_oneprompt_api_key


@dataclass
class Config:
    """Configuration for the cloud SDK.

    Args:
        oneprompt_api_key: API key for oneprompt cloud mode (env: ONEPROMPT_API_KEY).
            If not provided, loads automatically from credentials saved by ``op init``.
        oneprompt_api_url: Base URL for oneprompt cloud API (env: ONEPROMPT_API_URL)
        database_url: Default PostgreSQL connection string used in ephemeral queries
            (env: DATABASE_URL). Can be overridden per call in ``client.query()``.
        schema_docs_path: Path to a markdown file describing your database schema.
            Content is read once and used as the default ``schema_docs`` for queries.
        schema_docs: Raw schema documentation string. Overrides ``schema_docs_path``.
    """

    oneprompt_api_key: str = ""
    oneprompt_api_url: str = ""
    database_url: str = ""
    schema_docs_path: Optional[str] = None
    schema_docs: str = ""

    def __post_init__(self) -> None:
        self.oneprompt_api_key = self.oneprompt_api_key.strip()
        self.oneprompt_api_url = self.oneprompt_api_url.strip().rstrip("/")

        # Auto-load API key from credentials storage if not provided
        if not self.oneprompt_api_key:
            self.oneprompt_api_key = (
                os.getenv("ONEPROMPT_API_KEY", "").strip() or load_oneprompt_api_key()
            )

        # Auto-load API URL from env if not provided
        if not self.oneprompt_api_url:
            self.oneprompt_api_url = os.getenv("ONEPROMPT_API_URL", "").strip().rstrip("/")

        # Auto-load database_url from env if not provided
        if not self.database_url:
            self.database_url = os.getenv("DATABASE_URL", "").strip()

        # Read schema docs from file if path provided and docs not already set
        if not self.schema_docs and self.schema_docs_path:
            path = Path(self.schema_docs_path)
            if path.exists():
                self.schema_docs = path.read_text(encoding="utf-8")

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables."""
        key = os.getenv("ONEPROMPT_API_KEY", "").strip()
        if not key:
            key = load_oneprompt_api_key()

        return cls(
            oneprompt_api_key=key,
            oneprompt_api_url=os.getenv("ONEPROMPT_API_URL", ""),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors: list[str] = []
        if not self.oneprompt_api_key:
            errors.append("oneprompt_api_key is required (env: ONEPROMPT_API_KEY)")
        if not self.oneprompt_api_url:
            errors.append("oneprompt_api_url is required (env: ONEPROMPT_API_URL)")
        return errors
