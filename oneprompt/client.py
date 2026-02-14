"""
oneprompt Python Client — High-level API.

Provides a simple interface to run data queries, Python analysis, and chart generation
without worrying about MCP servers, sessions, or artifact management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from oneprompt.config import Config
from oneprompt.services.credentials import load_oneprompt_api_key

# Suppress noisy warnings from Google/LangChain internals
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)
logging.getLogger("google_genai.types").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


@dataclass
class ArtifactRef:
    """Reference to a generated artifact (file).

    Artifacts live in the artifact store (Docker container). Access them
    on demand — nothing is downloaded until you ask for it.

    Examples:
        >>> text = artifact.read_text()        # fetch + return content
        >>> artifact.download("./output/")     # save to a local directory
        >>> df = pd.read_csv(artifact.download())  # download then read
    """

    id: str
    name: str
    type: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None
    _download_url: Optional[str] = field(default=None, repr=False)
    _auth_token: Optional[str] = field(default=None, repr=False)
    _cached_bytes: Optional[bytes] = field(default=None, repr=False)

    # -- reading ---------------------------------------------------------------

    def read_bytes(self) -> bytes:
        """Read artifact content as bytes.

        Checks (in order): local file, memory cache, remote URL.
        The result is cached in memory so subsequent calls are free.
        """
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

    # -- downloading -----------------------------------------------------------

    def download(self, dest: Optional[str | Path] = None) -> Path:
        """Download the artifact to a local file.

        Args:
            dest: Destination file path or directory.  Defaults to
                  ``<cwd>/<artifact_name>``.

        Returns:
            Path to the downloaded file.
        """
        content = self.read_bytes()
        target = Path(dest) if dest else Path.cwd() / self.name
        if target.is_dir():
            target = target / self.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        self.path = str(target)
        return target

    # -- internals -------------------------------------------------------------

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


class Client:
    """
    oneprompt client for running AI agents.

    The simplest way to get started:

        >>> import oneprompt as op
        >>> client = op.Client(
        ...     oneprompt_api_key="op_live_...",
        ... )
        >>> result = client.query("Show me total revenue by month")
        >>> print(result.summary)
        >>> print(result.preview)

    For chart generation:

        >>> chart = client.chart("Create a bar chart of revenue by month", data_from=result)
        >>> print(chart.artifacts[0].path)

    For Python analysis:

        >>> analysis = client.analyze("Calculate the growth rate", data_from=result)
        >>> print(analysis.summary)
    """

    def __init__(
        self,
        oneprompt_api_key: Optional[str] = None,
        oneprompt_api_url: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        database_url: Optional[str] = None,
        schema_docs: Optional[str] = None,
        schema_docs_path: Optional[str] = None,
        data_dir: Optional[str] = None,
        config: Optional[Config] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the oneprompt client.

        Args:
            oneprompt_api_key: API key for oneprompt cloud mode.
            oneprompt_api_url: Base URL for oneprompt cloud API.
            llm_api_key: API key for the LLM provider. Falls back to LLM_API_KEY env var.
            llm_provider: LLM provider — google, openai, or anthropic (default: google).
            llm_model: Model name. Defaults per provider if not set.
            database_url: PostgreSQL connection string. Falls back to DATABASE_URL env var.
            schema_docs: SQL schema documentation (helps the LLM understand your database).
            schema_docs_path: Path to a DATABASE.md file with schema docs.
            data_dir: Directory for local data/output storage (default: ./op_data relative to cwd).
            config: Full Config object (overrides individual params).
            **kwargs: Additional config parameters passed to Config.
        """
        # Load .env from current directory
        load_dotenv(Path.cwd() / ".env")

        if config:
            self._config = config
        else:
            extra: Dict[str, Any] = dict(kwargs)
            if data_dir:
                extra["data_dir"] = data_dir
            resolved_oneprompt_key = oneprompt_api_key or os.getenv("ONEPROMPT_API_KEY", "")
            if not resolved_oneprompt_key:
                resolved_oneprompt_key = load_oneprompt_api_key()
            self._config = Config(
                oneprompt_api_key=resolved_oneprompt_key,
                oneprompt_api_url=(
                    oneprompt_api_url or os.getenv("ONEPROMPT_API_URL", "https://api.oneprompt.eu")
                ),
                llm_provider=llm_provider or os.getenv("LLM_PROVIDER", "google"),
                llm_api_key=llm_api_key or os.getenv("LLM_API_KEY", ""),
                llm_model=llm_model or os.getenv("LLM_MODEL", ""),
                database_url=database_url or os.getenv("DATABASE_URL", ""),
                schema_docs=schema_docs or "",
                schema_docs_path=schema_docs_path,
                **extra,
            )

        # Resolve artifact store token: env var > persisted file > empty
        if not self._config.artifact_store_token:
            env_token = os.getenv("OP_ARTIFACT_TOKEN", "")
            if env_token:
                self._config.artifact_store_token = env_token
            else:
                token_file = Path(self._config.data_dir) / ".artifact_token"
                if token_file.exists():
                    self._config.artifact_store_token = token_file.read_text().strip()

        # Validate
        errors = self._config.validate()
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))

        self._is_cloud_mode = self._config.mode == "cloud"
        self._default_session_id: Optional[str] = None

        if self._is_cloud_mode:
            self._state = None
            self._user_id = "cloud_user"
            return

        # Set environment variables for local agents
        self._apply_env()

        # Local state
        from oneprompt.services.state_store import StateStore

        self._state = StateStore(db_path=self._config.state_db_path)
        self._user_id = "local_user"

    def _apply_env(self) -> None:
        """Set environment variables from config for agent/MCP consumption."""
        for key, value in self._config.to_env_dict().items():
            os.environ[key] = value

    def _get_session_id(self) -> str:
        """Get or create default session."""
        if self._state is None:
            return self._default_session_id or "cloud_default"

        if self._default_session_id:
            session = self._state.get_session(self._default_session_id)
            if session and session.get("status") == "active":
                return self._default_session_id

        session_id = f"default_{self._user_id}"
        session = self._state.get_session(session_id)
        if not session:
            self._state.create_session(session_id, self._user_id, name="Default Session")
        self._default_session_id = session_id
        return session_id

    def _build_context(self, session_id: str, run_id: str):
        """Build agent context."""
        from oneprompt.services.artifact_client import ArtifactStoreClient

        client = ArtifactStoreClient(
            base_url=self._config.artifact_store_url,
            token=self._config.artifact_store_token,
            session_id=session_id,
            run_id=run_id,
        )
        from oneprompt.agents.context import AgentContext

        return AgentContext(session_id=session_id, run_id=run_id, artifact_store=client)

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

    def _build_artifacts(
        self,
        raw_artifacts: list[dict[str, Any]],
        *,
        auth_token: Optional[str],
        base_url: str,
    ) -> list[ArtifactRef]:
        """Build artifact references from a serialized artifact list."""
        artifacts: list[ArtifactRef] = []
        for item in raw_artifacts:
            name = str(item.get("name", "unknown"))
            remote_ref = item.get("url") or item.get("path") or item.get("file_path")
            full_url: Optional[str] = None
            if isinstance(remote_ref, str):
                if remote_ref.startswith("/"):
                    full_url = f"{base_url}{remote_ref}"
                elif remote_ref.startswith("http"):
                    full_url = remote_ref

            artifacts.append(
                ArtifactRef(
                    id=str(item.get("id", uuid.uuid4().hex)),
                    name=name,
                    type=item.get("type"),
                    url=str(remote_ref) if remote_ref else None,
                    _download_url=full_url,
                    _auth_token=auth_token,
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
            artifacts=self._build_artifacts(
                artifacts,
                auth_token=self._config.oneprompt_api_key or None,
                base_url=self._config.oneprompt_api_url,
            ),
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

    def _parse_result(self, result_json: str, run_id: str, session_id: str) -> AgentResult:
        """Parse agent JSON response into AgentResult."""
        data = json.loads(result_json)
        raw_artifacts = data.get("artifacts", [])
        parsed_artifacts: list[dict[str, Any]] = []
        if isinstance(raw_artifacts, list):
            parsed_artifacts = [item for item in raw_artifacts if isinstance(item, dict)]

        return AgentResult(
            ok=data.get("ok", False),
            run_id=run_id,
            session_id=session_id,
            summary=data.get("summary") or data.get("name"),
            data=data,
            artifacts=self._build_artifacts(
                parsed_artifacts,
                auth_token=self._config.artifact_store_token or None,
                base_url=self._config.artifact_store_url,
            ),
            error=str(data["error"]) if data.get("error") else None,
        )

    @staticmethod
    def _read_artifact_data(data_from: Optional[AgentResult]) -> str | None:
        """Read JSON data from the first artifact (local file or remote URL)."""
        if not data_from or not data_from.artifacts:
            return None
        for art in data_from.artifacts:
            if art.name.endswith(".json"):
                try:
                    return art.read_text()
                except Exception:
                    continue
        return None

    # ---- Public API ----

    def query(
        self,
        question: str,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """
        Query your database using natural language.

        Args:
            question: Natural language question about your data.
            session_id: Optional session ID for isolation.

        Returns:
            AgentResult with query results, preview data, and artifacts.

        Example:
            >>> result = client.query("What are the top 10 customers by revenue?")
            >>> for row in result.preview:
            ...     print(row)
        """
        return asyncio.run(self._query_async(question, session_id))

    async def _query_async(self, question: str, session_id: Optional[str] = None) -> AgentResult:
        if self._is_cloud_mode:
            payload: dict[str, Any] = {"query": question}
            if session_id:
                payload["session_id"] = session_id
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

        sid = session_id or self._get_session_id()
        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        dataset_config = {
            "dsn": self._config.database_url,
            "schema_docs": self._config.schema_docs,
            "name": "default",
            "id": "default",
        }

        from oneprompt.agents import data_agent

        try:
            result_json = await data_agent.run(question, context, dataset_config=dataset_config)
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=f"Query failed: {exc}",
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid)

    def chart(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """
        Generate a chart/visualization.

        Args:
            question: Description of the chart you want.
            data_from: Previous AgentResult to use as data source.
            data_preview: Raw data preview text.
            session_id: Optional session ID.

        Returns:
            AgentResult with chart spec artifact.

        Example:
            >>> data = client.query("Revenue by month")
            >>> chart = client.chart("Bar chart of revenue trends", data_from=data)
        """
        return asyncio.run(self._chart_async(question, data_from, data_preview, session_id))

    async def _chart_async(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        if self._is_cloud_mode:
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

        sid = session_id or self._get_session_id()
        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        msg = question.strip()
        inline_data = self._read_artifact_data(data_from)
        if inline_data is not None:
            msg += f"\nDATA_INLINE: {inline_data}"
        elif data_preview:
            msg += f"\npreview:\n{data_preview}"
        elif data_from and data_from.preview:
            msg += f"\nDATA_INLINE: {json.dumps(data_from.preview)}"

        from oneprompt.agents import chart_agent

        try:
            result_json = await chart_agent.run(msg, context)
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=f"Chart generation failed: {exc}",
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid)

    def analyze(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
        """
        Run Python analysis on your data.

        Args:
            instruction: What analysis to perform.
            data_from: Previous AgentResult to use as input data.
            output_name: Name for the output file.
            session_id: Optional session ID.

        Returns:
            AgentResult with analysis output and artifacts.

        Example:
            >>> data = client.query("All transactions this year")
            >>> analysis = client.analyze("Calculate monthly growth rate", data_from=data)
            >>> print(analysis.summary)
        """
        return asyncio.run(self._analyze_async(instruction, data_from, output_name, session_id))

    async def _analyze_async(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
        if self._is_cloud_mode:
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

        sid = session_id or self._get_session_id()
        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        msg = instruction.strip()
        inline_data = self._read_artifact_data(data_from)
        if inline_data is not None:
            msg += f"\nDATA_INLINE: {inline_data}"
        elif data_from and data_from.preview:
            msg += f"\nDATA_INLINE: {json.dumps(data_from.preview)}"

        from oneprompt.agents import python_agent

        try:
            result_json = await python_agent.run(msg, context, output_name=output_name)
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=f"Analysis failed: {exc}",
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid)

    @property
    def config(self) -> Config:
        """Get the current configuration."""
        return self._config
