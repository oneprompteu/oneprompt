"""
Data agent — queries PostgreSQL databases using natural language.

Uses a LangChain agent with Gemini LLM connected to a PostgreSQL MCP server
to translate natural language questions into SQL queries.
"""

import logging
import os
import warnings
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

import httpx
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared._httpx_utils import MCP_DEFAULT_SSE_READ_TIMEOUT, MCP_DEFAULT_TIMEOUT
from pydantic import BaseModel, Field

from oneprompt.agents.context import AgentContext
from oneprompt.agents.llm import create_llm
from oneprompt.services.dataset_token import (
    DatasetTokenError,
    create_dataset_token,
    dataset_token_enabled,
)

warnings.filterwarnings(
    "ignore",
    message="Key 'additionalProperties' is not supported in schema, ignoring",
)


def _create_mcp_http_client(
    headers: Optional[dict[str, str]] = None,
    timeout: Optional[httpx.Timeout] = None,
    auth: Optional[httpx.Auth] = None,
) -> httpx.AsyncClient:
    """Create MCP HTTP client for local services without env proxy inheritance."""
    resolved_timeout = timeout or httpx.Timeout(
        MCP_DEFAULT_TIMEOUT,
        read=MCP_DEFAULT_SSE_READ_TIMEOUT,
    )
    kwargs: dict[str, Any] = {
        "follow_redirects": True,
        "timeout": resolved_timeout,
        "trust_env": False,
    }
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


def _recursion_limit() -> int:
    raw = os.getenv("AGENT_MAX_RECURSION", "10").strip()
    try:
        limit = int(raw)
    except ValueError:
        return 10
    return max(1, limit)


def _dataset_token_ttl_seconds() -> int:
    raw = os.getenv("DATASET_TOKEN_TTL_SECONDS", "900").strip()
    try:
        ttl = int(raw)
    except ValueError:
        return 900
    return max(30, min(ttl, 3600))


class ArtifactRef(BaseModel):
    type: Optional[str] = None
    name: str
    url: str


async def run(
    question: str,
    context: AgentContext,
    dataset_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Execute a natural language question against a PostgreSQL MCP server.

    Args:
        question: Natural language question.
        context: Agent context with session_id, run_id, etc.
        dataset_config: Optional dataset configuration with keys: dsn, schema_docs, name, id.

    Returns:
        JSON string conforming to DataResponse schema.
    """
    mcp_url = os.environ.get("MCP_POSTGRES_URL")
    if not mcp_url:
        raise RuntimeError("MCP_POSTGRES_URL must be set (hint: start MCP servers with `op start`)")

    connection_headers = {
        "mcp-session-id": context.session_id,
        "mcp-run-id": context.run_id,
    }
    mcp_auth_token = os.getenv("MCP_AUTH_TOKEN") or os.getenv("MCP_SHARED_TOKEN")
    if mcp_auth_token:
        connection_headers["x-mcp-auth"] = mcp_auth_token

    if dataset_config:
        dsn_value = str(dataset_config.get("dsn", "")).strip()
        if dsn_value:
            if dataset_token_enabled():
                try:
                    token = create_dataset_token(
                        dsn_value,
                        audience="postgres-mcp",
                        ttl_seconds=_dataset_token_ttl_seconds(),
                        dataset_id=dataset_config.get("id"),
                        dataset_name=dataset_config.get("name"),
                        session_id=context.session_id,
                        run_id=context.run_id,
                    )
                except DatasetTokenError as exc:
                    raise RuntimeError(f"Failed to build dataset token: {exc}") from exc
                connection_headers["x-dataset-token"] = token
            else:
                # Backwards-compatible local mode fallback when no token secret is configured.
                connection_headers["x-dataset-dsn"] = dsn_value
        if dataset_config.get("id"):
            connection_headers["x-dataset-id"] = dataset_config["id"]
        if dataset_config.get("name"):
            connection_headers["x-dataset-name"] = dataset_config["name"]

    connection: Dict[str, Any] = {
        "transport": "http",
        "url": mcp_url,
        "headers": connection_headers,
    }

    def _httpx_factory(headers=None, timeout=None, auth=None):
        merged = dict(headers or {})
        merged.update(connection_headers)
        return _create_mcp_http_client(headers=merged, timeout=timeout, auth=auth)

    connection["httpx_client_factory"] = _httpx_factory

    client = MultiServerMCPClient({"postgres": connection})

    async with client.session("postgres") as session:
        tools = await load_mcp_tools(session)

        schema_context = ""
        if dataset_config and dataset_config.get("schema_docs"):
            schema_context = dataset_config["schema_docs"]
        else:
            try:
                prompt_result = await session.get_prompt("postgres_schema")
                schema_context = "\n".join([msg.content.text for msg in prompt_result.messages])
            except Exception:
                schema_context = "Schema not available. Assume standard tables."

        model = create_llm(temperature=0)

        class DataResponse(BaseModel):
            ok: bool
            intent: Literal["preview", "export", "unknown"] = "unknown"
            columns: List[str] = []
            preview: List[Dict[str, Optional[str]]] = []
            row_count: Optional[int] = None
            file_path: Optional[str] = None
            csv_path: Optional[str] = None
            format: Optional[str] = None
            artifacts: List[ArtifactRef] = Field(default_factory=list)
            error: Optional[Dict[str, Any]] = None

        prompt_path = Path(__file__).resolve().parent / "prompts" / "DATA_AGENT.md"
        try:
            prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise RuntimeError(f"Prompt not found: {prompt_path}")

        system_prompt = prompt_template.format(
            schema_context=schema_context,
            today_date=date.today().isoformat(),
        )

        agent = create_agent(
            model,
            tools,
            system_prompt=system_prompt,
            response_format=ProviderStrategy(DataResponse),
        )

        logger.info("[data_agent] invoking agent for: %s", question[:120])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            {"recursion_limit": _recursion_limit()},
        )
        structured = result.get("structured_response")
        if not structured:
            # Log last agent message to help diagnose
            messages = result.get("messages", [])
            if messages:
                last = messages[-1]
                content = getattr(last, "content", "")
                logger.error(
                    "[data_agent] no structured_response. Last agent message: %s",
                    str(content)[:500],
                )
            else:
                logger.error("[data_agent] no structured_response and no messages in result")
            fallback = DataResponse(
                ok=False,
                error={"tool": "agent", "kind": "no_tool_output"},
            )
            return fallback.model_dump_json()

        if isinstance(structured, DataResponse):
            logger.info("[data_agent] ok=%s", structured.ok)
            return structured.model_dump_json()
        if isinstance(structured, dict):
            resp = DataResponse(**structured)
            logger.info("[data_agent] ok=%s", resp.ok)
            return resp.model_dump_json()

        logger.error("[data_agent] unexpected structured_response type: %s", type(structured))
        fallback = DataResponse(
            ok=False,
            error={"tool": "agent", "kind": "unexpected_structured_response"},
        )
        return fallback.model_dump_json()
