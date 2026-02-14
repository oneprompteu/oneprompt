from __future__ import annotations

from dataclasses import dataclass

from oneprompt.services.artifact_client import ArtifactStoreClient


@dataclass(frozen=True)
class AgentContext:
    """Shared context for all agents."""

    session_id: str
    run_id: str
    artifact_store: ArtifactStoreClient
