"""Shared cloud SDK response and artifact types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


@dataclass
class ArtifactRef:
    """Reference to a generated artifact (file)."""

    id: str
    name: str
    type: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    _download_url: Optional[str] = field(default=None, repr=False)
    _auth_token: Optional[str] = field(default=None, repr=False)
    _cached_bytes: Optional[bytes] = field(default=None, repr=False)

    def read_bytes(self) -> bytes:
        """Read artifact content as bytes."""
        if self.path and Path(self.path).exists():
            return Path(self.path).read_bytes()
        if self._cached_bytes is not None:
            return self._cached_bytes
        if self._download_url:
            self._cached_bytes = self._fetch()
            return self._cached_bytes
        raise FileNotFoundError(
            f"Artifact '{self.name}' not available locally and no download URL set"
        )

    def read_text(self, encoding: str = "utf-8") -> str:
        """Read artifact content as text."""
        return self.read_bytes().decode(encoding)

    def download(self, dest: Optional[str | Path] = None) -> Path:
        """Download the artifact to a local file."""
        content = self.read_bytes()
        target = Path(dest) if dest else Path.cwd() / self.name
        if target.is_dir():
            target = target / self.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        self.path = str(target)
        return target

    def _fetch(self) -> bytes:
        """Fetch artifact bytes from the remote artifact store."""
        if not self._download_url:
            raise FileNotFoundError("No download URL configured")
        headers: Dict[str, str] = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
            headers["X-API-Key"] = self._auth_token
        with httpx.Client(timeout=30.0) as http:
            resp = http.get(self._download_url, headers=headers)
            resp.raise_for_status()
            return resp.content


@dataclass
class AgentResult:
    """Result from an agent execution."""

    ok: bool
    run_id: str
    session_id: str
    summary: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[ArtifactRef] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def preview(self) -> List[Dict[str, Any]]:
        """Get data preview rows (for data agent results)."""
        return self.data.get("preview", [])

    @property
    def columns(self) -> List[str]:
        """Get column names (for data agent results)."""
        return self.data.get("columns", [])
