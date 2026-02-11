"""
ThinkingProducts Python Client — High-level API.

Provides a simple interface to run data queries, Python analysis, and chart generation
without worrying about MCP servers, sessions, or artifact management.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# Suppress noisy warnings from Google/LangChain internals
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)
logging.getLogger("google_genai.types").setLevel(logging.ERROR)

from thinkingproducts.config import Config


@dataclass
class ArtifactRef:
    """Reference to a generated artifact (file)."""

    id: str
    name: str
    type: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None

    def read_bytes(self) -> bytes:
        """Read artifact content as bytes."""
        if not self.path:
            raise FileNotFoundError("Artifact path not available")
        return Path(self.path).read_bytes()

    def read_text(self) -> str:
        """Read artifact content as text."""
        return self.read_bytes().decode("utf-8")


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
    ThinkingProducts client for running AI agents.

    The simplest way to get started:

        >>> import thinkingproducts as tp
        >>> client = tp.Client(
        ...     gemini_api_key="your-gemini-key",
        ...     database_url="postgresql://user:pass@localhost:5432/mydb",
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
        gemini_api_key: Optional[str] = None,
        database_url: Optional[str] = None,
        schema_docs: Optional[str] = None,
        schema_docs_path: Optional[str] = None,
        config: Optional[Config] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize the ThinkingProducts client.

        Args:
            gemini_api_key: Google Gemini API key. Falls back to GOOGLE_API_KEY env var.
            database_url: PostgreSQL connection string. Falls back to DATABASE_URL env var.
            schema_docs: SQL schema documentation (helps the LLM understand your database).
            schema_docs_path: Path to a DATABASE.md file with schema docs.
            config: Full Config object (overrides individual params).
            **kwargs: Additional config parameters passed to Config.
        """
        # Load .env from current directory
        load_dotenv(Path.cwd() / ".env")

        if config:
            self._config = config
        else:
            self._config = Config(
                gemini_api_key=gemini_api_key or os.getenv("GOOGLE_API_KEY", ""),
                database_url=database_url or os.getenv("DATABASE_URL", ""),
                schema_docs=schema_docs or "",
                schema_docs_path=schema_docs_path,
                **kwargs,
            )

        # Validate
        errors = self._config.validate()
        if errors:
            raise ValueError(
                "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
            )

        # Set environment variables for agents
        self._apply_env()

        # State
        from thinkingproducts.services.state_store import StateStore

        self._state = StateStore(db_path=self._config.state_db_path)
        self._user_id = "local_user"
        self._default_session_id: Optional[str] = None

    def _apply_env(self) -> None:
        """Set environment variables from config for agent/MCP consumption."""
        for key, value in self._config.to_env_dict().items():
            os.environ[key] = value

    def _get_session_id(self) -> str:
        """Get or create default session."""
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
        from thinkingproducts.services.artifact_client import ArtifactStoreClient

        client = ArtifactStoreClient(
            base_url=self._config.artifact_store_url,
            token=self._config.artifact_store_token,
            session_id=session_id,
            run_id=run_id,
        )
        from thinkingproducts.agents.context import AgentContext

        return AgentContext(session_id=session_id, run_id=run_id, artifact_store=client)

    def _parse_result(
        self, result_json: str, run_id: str, session_id: str
    ) -> AgentResult:
        """Parse agent JSON response into AgentResult and download artifacts locally."""
        data = json.loads(result_json)
        artifacts = []
        for a in data.get("artifacts", []):
            if isinstance(a, dict):
                name = a.get("name", "unknown")
                remote_ref = a.get("url") or a.get("path") or a.get("file_path")
                local_path = self._download_artifact(remote_ref, name, session_id, run_id)
                artifacts.append(
                    ArtifactRef(
                        id=a.get("id", uuid.uuid4().hex),
                        name=name,
                        type=a.get("type"),
                        path=local_path,
                        url=remote_ref,
                    )
                )
        return AgentResult(
            ok=data.get("ok", False),
            run_id=run_id,
            session_id=session_id,
            summary=data.get("summary") or data.get("name"),
            data=data,
            artifacts=artifacts,
            error=str(data["error"]) if data.get("error") else None,
        )

    def _download_artifact(
        self, url_or_path: str | None, name: str, session_id: str, run_id: str
    ) -> str | None:
        """Download an artifact from the artifact store to local out/ directory."""
        if not url_or_path:
            return None

        out_dir = Path(self._config.data_dir) / "out" / session_id / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        local_path = out_dir / name

        # Build full URL if relative
        if url_or_path.startswith("/"):
            download_url = f"{self._config.artifact_store_url}{url_or_path}"
        elif url_or_path.startswith("http"):
            download_url = url_or_path
        else:
            download_url = (
                f"{self._config.artifact_store_url}/artifacts/{session_id}/{url_or_path}"
            )

        try:
            headers = {}
            if self._config.artifact_store_token:
                headers["Authorization"] = f"Bearer {self._config.artifact_store_token}"
            with httpx.Client(timeout=30.0) as http:
                resp = http.get(download_url, headers=headers)
                resp.raise_for_status()
                local_path.write_bytes(resp.content)
            return str(local_path)
        except Exception:
            return None

    @staticmethod
    def _read_artifact_data(data_from: Optional[AgentResult]) -> str | None:
        """Read JSON data from the first local artifact file (if available)."""
        if not data_from or not data_from.artifacts:
            return None
        for art in data_from.artifacts:
            if art.path and art.name.endswith(".json") and Path(art.path).exists():
                try:
                    return Path(art.path).read_text(encoding="utf-8")
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

    async def _query_async(
        self, question: str, session_id: Optional[str] = None
    ) -> AgentResult:
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

        from thinkingproducts.agents import data_agent

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
        return asyncio.run(
            self._chart_async(question, data_from, data_preview, session_id)
        )

    async def _chart_async(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
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

        from thinkingproducts.agents import chart_agent

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
        return asyncio.run(
            self._analyze_async(instruction, data_from, output_name, session_id)
        )

    async def _analyze_async(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
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

        from thinkingproducts.agents import python_agent

        try:
            result_json = await python_agent.run(
                msg, context, output_name=output_name
            )
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
