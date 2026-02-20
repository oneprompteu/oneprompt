"""oneprompt cloud-only Python client."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

from oneprompt_sdk.config import Config
from oneprompt_sdk.services.credentials import load_oneprompt_api_key
from oneprompt_sdk.types import AgentResult, ArtifactRef


class Client:
    """oneprompt cloud client for running agents through oneprompt API."""

    def __init__(
        self,
        oneprompt_api_key: Optional[str] = None,
        oneprompt_api_url: Optional[str] = None,
        config: Optional[Config] = None,
    ) -> None:
        """Initialize the cloud client."""
        load_dotenv(Path.cwd() / ".env")

        if config:
            self._config = config
            # Override specific fields if explicitly passed to the constructor
            if oneprompt_api_key:
                self._config.oneprompt_api_key = oneprompt_api_key.strip()
            if oneprompt_api_url:
                self._config.oneprompt_api_url = oneprompt_api_url.strip().rstrip("/")
        else:
            self._config = Config(
                oneprompt_api_key=oneprompt_api_key or "",
                oneprompt_api_url=oneprompt_api_url or "",
            )

        errors = self._config.validate()
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

        self._default_session_id: Optional[str] = None

    def _cloud_headers(self) -> dict[str, str]:
        """Build request headers for oneprompt cloud API."""
        key = self._config.oneprompt_api_key
        return {
            "Authorization": f"Bearer {key}",
            "X-API-Key": key,
            "Content-Type": "application/json",
        }

    async def _cloud_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a POST request to oneprompt cloud API."""
        url = f"{self._config.oneprompt_api_url}{path}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=self._cloud_headers())
            response.raise_for_status()
            return response.json()

    def _build_artifacts(self, raw_artifacts: list[dict[str, Any]]) -> list[ArtifactRef]:
        """Build artifact references from a serialized artifact list."""
        artifacts: list[ArtifactRef] = []
        for item in raw_artifacts:
            name = str(item.get("name", "unknown"))
            remote_ref = item.get("url") or item.get("path") or item.get("file_path")
            full_url: Optional[str] = None
            if isinstance(remote_ref, str):
                if remote_ref.startswith("/"):
                    full_url = f"{self._config.oneprompt_api_url}{remote_ref}"
                elif remote_ref.startswith("http"):
                    full_url = remote_ref

            artifacts.append(
                ArtifactRef(
                    id=str(item.get("id", uuid.uuid4().hex)),
                    name=name,
                    type=item.get("type"),
                    url=str(remote_ref) if remote_ref else None,
                    _download_url=full_url,
                    _auth_token=self._config.oneprompt_api_key or None,
                )
            )
        return artifacts

    def _parse_cloud_result(self, payload: dict[str, Any]) -> AgentResult:
        """Parse cloud API response payload into AgentResult."""
        run_id = str(payload.get("run_id", uuid.uuid4().hex))
        session_id = str(payload.get("session_id", ""))
        result_data = payload.get("result", {})
        if not isinstance(result_data, dict):
            result_data = {}

        raw_artifacts = payload.get("artifacts", [])
        artifacts: list[dict[str, Any]] = []
        if isinstance(raw_artifacts, list):
            artifacts = [item for item in raw_artifacts if isinstance(item, dict)]

        parsed = AgentResult(
            ok=bool(payload.get("ok", False)),
            run_id=run_id,
            session_id=session_id,
            summary=payload.get("summary"),
            data=result_data,
            artifacts=self._build_artifacts(artifacts),
            error=None,
        )
        if not parsed.ok and not parsed.error:
            parsed.error = str(payload.get("error") or "Cloud request failed")
        if parsed.session_id:
            self._default_session_id = parsed.session_id
        return parsed

    @staticmethod
    def _first_artifact_id(data_from: Optional[AgentResult]) -> Optional[str]:
        """Return the first artifact ID from a result if available."""
        if not data_from:
            return None
        for artifact in data_from.artifacts:
            if artifact.id:
                return artifact.id
        return None

    def query(
        self,
        question: str,
        session_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        database_url: Optional[str] = None,
        schema_docs: Optional[str] = None,
    ) -> AgentResult:
        """Query a cloud dataset using natural language."""
        return asyncio.run(
            self._query_async(
                question,
                session_id=session_id,
                dataset_id=dataset_id,
                database_url=database_url,
                schema_docs=schema_docs,
            )
        )

    async def _query_async(
        self,
        question: str,
        session_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        database_url: Optional[str] = None,
        schema_docs: Optional[str] = None,
    ) -> AgentResult:
        payload: dict[str, Any] = {"query": question}
        if session_id:
            payload["session_id"] = session_id
        has_dataset_id = bool((dataset_id or "").strip())
        # Fall back to config defaults when not provided per-call
        ephemeral_dsn = (database_url or self._config.database_url or "").strip()
        if schema_docs is None and self._config.schema_docs:
            schema_docs = self._config.schema_docs
        has_ephemeral = bool(ephemeral_dsn)

        if has_dataset_id and has_ephemeral:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=session_id or "",
                error="Cloud query requires either dataset_id or database_url, not both.",
            )

        if not has_dataset_id and not has_ephemeral:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=session_id or "",
                error="Cloud query requires dataset_id or database_url.",
            )

        if has_dataset_id:
            payload["dataset_id"] = dataset_id
            if schema_docs is not None:
                return AgentResult(
                    ok=False,
                    run_id=uuid.uuid4().hex,
                    session_id=session_id or "",
                    error="schema_docs is only supported with database_url in cloud mode.",
                )
        else:
            ephemeral_payload: dict[str, Any] = {"dsn": ephemeral_dsn}
            if schema_docs is not None:
                ephemeral_payload["schema_docs"] = schema_docs
            payload["ephemeral_dataset"] = ephemeral_payload

        try:
            response = await self._cloud_post("/agents/data", payload)
            return self._parse_cloud_result(response)
        except Exception as exc:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=session_id or "",
                error=f"Cloud query failed: {exc}",
            )

    def chart(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Generate a cloud chart."""
        return asyncio.run(self._chart_async(question, data_from, data_preview, session_id))

    async def _chart_async(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        payload: dict[str, Any] = {"question": question}
        sid = session_id or (data_from.session_id if data_from else None)
        if sid:
            payload["session_id"] = sid

        data_artifact_id = self._first_artifact_id(data_from)
        if data_artifact_id:
            payload["data_artifact_id"] = data_artifact_id
        elif data_preview:
            payload["data_preview"] = data_preview
        elif data_from and data_from.preview:
            payload["data_preview"] = json.dumps(data_from.preview)

        try:
            response = await self._cloud_post("/agents/chart", payload)
            return self._parse_cloud_result(response)
        except Exception as exc:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=sid or "",
                error=f"Cloud chart generation failed: {exc}",
            )

    def analyze(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """Run cloud Python analysis."""
        return asyncio.run(self._analyze_async(instruction, data_from, output_name, session_id))

    async def _analyze_async(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
        payload: dict[str, Any] = {
            "instruction": instruction,
            "output_name": output_name,
        }
        sid = session_id or (data_from.session_id if data_from else None)
        if sid:
            payload["session_id"] = sid

        data_artifact_id = self._first_artifact_id(data_from)
        if data_artifact_id:
            payload["data_artifact_id"] = data_artifact_id

        try:
            response = await self._cloud_post("/agents/python", payload)
            return self._parse_cloud_result(response)
        except Exception as exc:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=sid or "",
                error=f"Cloud analysis failed: {exc}",
            )

    @property
    def config(self) -> Config:
        """Get the current configuration."""
        return self._config
