"""
Artifact Store client — builds URLs for artifact I/O.

Handles path construction for reading and writing artifacts
to the artifact store service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ArtifactStoreClient:
    """
    Client for the Artifact Store service.

    Path Structure (canonical):
        {session_id}/runs/{run_id}/{artifact_type}/{filename}

    Where:
        - session_id: User session identifier
        - run_id: Execution run identifier
        - artifact_type: "data", "results", or "charts"
        - filename: Output file name
    """

    base_url: str
    token: Optional[str]
    session_id: str
    run_id: Optional[str] = None

    def _base(self) -> str:
        return self.base_url.rstrip("/")

    def headers(self) -> Dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def build_artifact_path(
        self,
        run_id: Optional[str] = None,
        artifact_type: str = "data",
        filename: str = "",
    ) -> str:
        """Build a canonical artifact path relative to session."""
        effective_run_id = run_id or self.run_id
        if not effective_run_id:
            raise ValueError("run_id is required to build artifact path")
        parts = ["runs", effective_run_id, artifact_type]
        if filename:
            parts.append(filename.strip("/"))
        return "/".join(parts)

    def build_url(self, artifact_path: str) -> str:
        """Build full URL to read an artifact."""
        return f"{self._base()}/artifacts/{self.session_id}/{artifact_path.lstrip('/')}"

    def build_upload_url(self, artifact_path: str) -> str:
        """Build full URL to upload an artifact."""
        return f"{self.build_url(artifact_path)}?upload=true"

    def parse_artifact_path(self, full_path: str) -> Optional[Dict[str, str]]:
        """Parse a full filesystem path or URL to extract artifact components."""
        import re

        path = full_path.replace("\\", "/")
        pattern = r"([a-f0-9]{32})/runs/([a-f0-9]{32})/([^/]+)/([^/]+)$"
        match = re.search(pattern, path)

        if match:
            session_id, run_id, artifact_type, filename = match.groups()
            store_path = f"runs/{run_id}/{artifact_type}/{filename}"
            return {
                "session_id": session_id,
                "run_id": run_id,
                "artifact_type": artifact_type,
                "filename": filename,
                "store_path": store_path,
            }
        return None
