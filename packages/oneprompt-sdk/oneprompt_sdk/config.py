"""oneprompt cloud SDK configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from oneprompt_sdk.services.credentials import load_oneprompt_api_key


@dataclass
class Config:
    """Configuration for the cloud SDK.

    Args:
        oneprompt_api_key: API key for oneprompt cloud mode (env: ONEPROMPT_API_KEY)
        oneprompt_api_url: Base URL for oneprompt cloud API (env: ONEPROMPT_API_URL)
    """

    oneprompt_api_key: str = ""
    oneprompt_api_url: str = "https://api.oneprompt.eu"

    def __post_init__(self) -> None:
        self.oneprompt_api_key = self.oneprompt_api_key.strip()
        self.oneprompt_api_url = self.oneprompt_api_url.strip().rstrip("/")

    @classmethod
    def from_env(cls) -> Config:
        """Create configuration from environment variables."""
        key = os.getenv("ONEPROMPT_API_KEY", "").strip()
        if not key:
            key = load_oneprompt_api_key()

        return cls(
            oneprompt_api_key=key,
            oneprompt_api_url=os.getenv("ONEPROMPT_API_URL", "https://api.oneprompt.eu"),
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors: list[str] = []
        if not self.oneprompt_api_key:
            errors.append("oneprompt_api_key is required (env: ONEPROMPT_API_KEY)")
        if not self.oneprompt_api_url:
            errors.append("oneprompt_api_url is required (env: ONEPROMPT_API_URL)")
        return errors
