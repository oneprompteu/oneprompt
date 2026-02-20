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
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from oneprompt.config import Config
from oneprompt.services.credentials import load_oneprompt_api_key

try:
    from oneprompt_sdk.client import Client as CloudClient
    from oneprompt_sdk.types import AgentResult, ArtifactRef, RunMetrics
except ImportError:
    # Ensure monorepo source imports work before oneprompt-sdk is published/installed.
    _monorepo_sdk_path = Path(__file__).resolve().parent.parent / "packages" / "oneprompt-sdk"
    if _monorepo_sdk_path.exists() and str(_monorepo_sdk_path) not in sys.path:
        sys.path.insert(0, str(_monorepo_sdk_path))
    from oneprompt_sdk.client import Client as CloudClient
    from oneprompt_sdk.types import AgentResult, ArtifactRef, RunMetrics

# Suppress noisy warnings from Google/LangChain internals
logging.getLogger("langchain_google_genai._function_utils").setLevel(logging.ERROR)
logging.getLogger("google_genai.types").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


def _iter_leaf_exceptions(exc: BaseException) -> list[BaseException]:
    """Return leaf exceptions from nested ExceptionGroup structures."""
    leaves: list[BaseException] = []
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            leaves.extend(_iter_leaf_exceptions(sub))
    else:
        leaves.append(exc)
    return leaves


def _is_mcp_connect_error(exc: BaseException) -> bool:
    """Whether an exception is a transport-level MCP connection error."""
    exc_type = type(exc)
    module_name = getattr(exc_type, "__module__", "")
    type_name = getattr(exc_type, "__name__", "")
    if type_name == "ConnectError" and (
        module_name.startswith("httpx") or module_name.startswith("httpcore")
    ):
        return True

    text = str(exc).lower()
    return "all connection attempts failed" in text or "failed to connect" in text


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
        self._cloud_client: Optional[CloudClient] = None

        if self._is_cloud_mode:
            self._state = None
            self._user_id = "cloud_user"
            self._cloud_client = CloudClient(
                oneprompt_api_key=self._config.oneprompt_api_key,
                oneprompt_api_url=self._config.oneprompt_api_url,
            )
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


    # Fields redundant with top-level AgentResult fields or internal to Docker containers.
    _STRIP_FROM_DATA = {"ok", "error", "artifacts", "file_path", "csv_path"}

    def _parse_result(
        self,
        result_json: str,
        run_id: str,
        session_id: str,
        metrics: Optional[RunMetrics] = None,
    ) -> AgentResult:
        """Parse agent JSON response into AgentResult."""
        data = json.loads(result_json)
        raw_artifacts = data.get("artifacts", [])
        parsed_artifacts: list[dict[str, Any]] = []
        if isinstance(raw_artifacts, list):
            parsed_artifacts = [item for item in raw_artifacts if isinstance(item, dict)]

        clean_data = {k: v for k, v in data.items() if k not in self._STRIP_FROM_DATA}

        return AgentResult(
            ok=data.get("ok", False),
            run_id=run_id,
            session_id=session_id,
            summary=data.get("summary") or data.get("name"),
            data=clean_data,
            artifacts=self._build_artifacts(
                parsed_artifacts,
                auth_token=self._config.artifact_store_token or None,
                base_url=self._config.artifact_store_url,
            ),
            metrics=metrics,
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

    def _format_local_agent_error(
        self,
        *,
        action: str,
        exc: Exception,
        mcp_url: str,
        service_name: str,
    ) -> str:
        """Render concise, actionable error messages for local MCP failures."""
        leaves = _iter_leaf_exceptions(exc)
        if any(_is_mcp_connect_error(item) for item in leaves):
            return (
                f"{action} failed: cannot connect to {service_name} at {mcp_url}. "
                "Run `op start` and confirm the container is Up."
            )

        details: list[str] = []
        seen: set[str] = set()
        for item in leaves[:3]:
            msg = str(item).strip() or item.__class__.__name__
            rendered = f"{item.__class__.__name__}: {msg}"
            if rendered not in seen:
                details.append(rendered)
                seen.add(rendered)

        if details:
            return f"{action} failed: {' | '.join(details)}"
        return f"{action} failed: {exc}"

    # ---- Public API ----

    def query(
        self,
        question: str,
        session_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        database_url: Optional[str] = None,
        schema_docs: Optional[str] = None,
    ) -> AgentResult:
        """
        Query your database using natural language.

        Args:
            question: Natural language question about your data.
            session_id: Optional session ID for isolation.
            dataset_id: Cloud mode only. Identifier of a stored dataset.
            database_url: Optional PostgreSQL DSN override.
                In cloud mode this enables ephemeral (non-persistent) credentials.
            schema_docs: Optional schema docs override. Used with ``database_url``.

        Returns:
            AgentResult with query results, preview data, and artifacts.

        Example:
            >>> result = client.query("What are the top 10 customers by revenue?")
            >>> for row in result.preview:
            ...     print(row)
        """
        if self._is_cloud_mode and self._cloud_client is not None:
            return self._cloud_client.query(
                question,
                session_id=session_id,
                dataset_id=dataset_id,
                database_url=database_url,
                schema_docs=schema_docs,
            )
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
        if self._is_cloud_mode:
            if self._cloud_client is None:
                return AgentResult(
                    ok=False,
                    run_id=uuid.uuid4().hex,
                    session_id=session_id or "",
                    error="Cloud client is not initialized.",
                )
            return await self._cloud_client._query_async(
                question,
                session_id=session_id,
                dataset_id=dataset_id,
                database_url=database_url,
                schema_docs=schema_docs,
            )

        sid = session_id or self._get_session_id()
        if dataset_id:
            return AgentResult(
                ok=False,
                run_id=uuid.uuid4().hex,
                session_id=sid,
                error="dataset_id is only supported in cloud mode.",
            )

        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        query_dsn = (database_url or "").strip() or self._config.database_url
        query_schema_docs = self._config.schema_docs if schema_docs is None else schema_docs
        dataset_config = {
            "dsn": query_dsn,
            "schema_docs": query_schema_docs,
            "name": "default",
            "id": "default",
        }

        from oneprompt.agents import data_agent

        try:
            result_json, metrics = await data_agent.run(
                question, context, dataset_config=dataset_config
            )
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=self._format_local_agent_error(
                    action="Query",
                    exc=exc,
                    mcp_url=self._config.mcp_postgres_url,
                    service_name="postgres-mcp",
                ),
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid, metrics=metrics)

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
        if self._is_cloud_mode and self._cloud_client is not None:
            return self._cloud_client.chart(
                question,
                data_from=data_from,
                data_preview=data_preview,
                session_id=session_id,
            )
        return asyncio.run(self._chart_async(question, data_from, data_preview, session_id))

    async def _chart_async(
        self,
        question: str,
        data_from: Optional[AgentResult] = None,
        data_preview: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> AgentResult:
        if self._is_cloud_mode:
            if self._cloud_client is None:
                return AgentResult(
                    ok=False,
                    run_id=uuid.uuid4().hex,
                    session_id=session_id or "",
                    error="Cloud client is not initialized.",
                )
            return await self._cloud_client._chart_async(
                question,
                data_from=data_from,
                data_preview=data_preview,
                session_id=session_id,
            )

        sid = session_id or self._get_session_id()
        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        msg = question.strip()

        # Pass artifact URL to the chart MCP so it fetches data directly —
        # the LLM must never see the full dataset, only a small preview.
        # Prefer JSON (chart MCP expects records format); fall back to CSV.
        chart_data_url: Optional[str] = None
        if data_from and data_from.artifacts:
            _csv_url: Optional[str] = None
            for art in data_from.artifacts:
                if art.url:
                    if art.name.endswith(".json") and chart_data_url is None:
                        chart_data_url = art.url
                    elif art.name.endswith(".csv") and _csv_url is None:
                        _csv_url = art.url
            if chart_data_url is None:
                chart_data_url = _csv_url  # fallback to CSV if no JSON artifact

        # Show only a small preview so the LLM understands column structure
        if data_from and data_from.preview:
            preview_rows = data_from.preview[:5]
            msg += f"\npreview:\n{json.dumps(preview_rows, ensure_ascii=False)}"
        elif data_preview:
            msg += f"\npreview:\n{data_preview}"

        from oneprompt.agents import chart_agent

        try:
            result_json, metrics = await chart_agent.run(msg, context, data_url=chart_data_url)
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=self._format_local_agent_error(
                    action="Chart generation",
                    exc=exc,
                    mcp_url=self._config.mcp_chart_url,
                    service_name="chart-mcp",
                ),
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid, metrics=metrics)

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
        if self._is_cloud_mode and self._cloud_client is not None:
            return self._cloud_client.analyze(
                instruction,
                data_from=data_from,
                output_name=output_name,
                session_id=session_id,
            )
        return asyncio.run(self._analyze_async(instruction, data_from, output_name, session_id))

    async def _analyze_async(
        self,
        instruction: str,
        data_from: Optional[AgentResult] = None,
        output_name: str = "result.csv",
        session_id: Optional[str] = None,
    ) -> AgentResult:
        if self._is_cloud_mode:
            if self._cloud_client is None:
                return AgentResult(
                    ok=False,
                    run_id=uuid.uuid4().hex,
                    session_id=session_id or "",
                    error="Cloud client is not initialized.",
                )
            return await self._cloud_client._analyze_async(
                instruction,
                data_from=data_from,
                output_name=output_name,
                session_id=session_id,
            )

        sid = session_id or self._get_session_id()
        run_id = uuid.uuid4().hex
        self._state.create_run(run_id, sid)
        context = self._build_context(sid, run_id)

        msg = instruction.strip()

        # Prefer CSV for pandas; extract relative path so python_agent wires up DATA_URL.
        # The LLM must never receive the full dataset — only a small structural preview.
        artifact_data_path: Optional[str] = None
        if data_from and data_from.artifacts:
            _json_path: Optional[str] = None
            for art in data_from.artifacts:
                if not art.url:
                    continue
                # Strip /artifacts/{session_id}/ prefix to get path relative to session
                prefix = f"/artifacts/{data_from.session_id}/"
                rel = art.url[len(prefix):] if art.url.startswith(prefix) else art.url.lstrip("/")
                if art.name.endswith(".csv") and artifact_data_path is None:
                    artifact_data_path = rel  # prefer CSV for pandas
                elif art.name.endswith(".json") and _json_path is None:
                    _json_path = rel
            if artifact_data_path is None:
                artifact_data_path = _json_path  # fallback to JSON

        # Show a small structural preview so the LLM understands column names/types
        if data_from and data_from.preview:
            preview_rows = data_from.preview[:5]
            msg += f"\npreview:\n{json.dumps(preview_rows, ensure_ascii=False)}"

        from oneprompt.agents import python_agent

        try:
            result_json, metrics = await python_agent.run(
                msg, context, data_path=artifact_data_path, output_name=output_name
            )
        except Exception as exc:
            self._state.update_run_status(run_id, "failed")
            return AgentResult(
                ok=False,
                run_id=run_id,
                session_id=sid,
                error=self._format_local_agent_error(
                    action="Analysis",
                    exc=exc,
                    mcp_url=self._config.mcp_python_url,
                    service_name="python-mcp",
                ),
            )
        self._state.update_run_status(run_id, "completed")
        return self._parse_result(result_json, run_id, sid, metrics=metrics)

    @property
    def config(self) -> Config:
        """Get the current configuration."""
        return self._config
