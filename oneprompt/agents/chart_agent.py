"""
Chart agent — generates AntV chart visualizations.

Uses a LangChain agent with Gemini LLM connected to a Chart MCP server
to generate chart specifications from data and descriptions.
"""

import logging
import os
import warnings
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

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
from oneprompt.agents.metrics import RunMetrics, UsageCallback

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


class ArtifactRef(BaseModel):
    type: Optional[str] = None
    name: str
    url: str


async def run(
    input_text: str,
    context: AgentContext,
    data_url: Optional[str] = None,
) -> tuple[str, RunMetrics]:
    """
    Execute a chart generation request against the Chart MCP server.

    Args:
        input_text: Text describing the chart with optional file_name and preview.
        context: Agent context.
        data_url: Optional HTTP URL to data in the Artifact Store.

    Returns:
        JSON string with chart specification.
    """
    usage_cb = UsageCallback()

    mcp_url = os.environ.get("MCP_CHART_URL")
    if not mcp_url:
        raise RuntimeError("MCP_CHART_URL must be set (hint: start MCP servers with `op start`)")

    headers: Dict[str, str] = {
        "mcp-session-id": context.session_id,
        "mcp-run-id": context.run_id,
    }
    mcp_auth_token = os.getenv("MCP_AUTH_TOKEN") or os.getenv("MCP_SHARED_TOKEN")
    if mcp_auth_token:
        headers["x-mcp-auth"] = mcp_auth_token

    connection: Dict[str, Any] = {
        "transport": "http",
        "url": mcp_url,
        "headers": headers,
    }

    def _httpx_factory(headers=None, timeout=None, auth=None):
        merged = dict(headers or {})
        for key, value in connection["headers"].items():
            merged.setdefault(key, value)
        return _create_mcp_http_client(headers=merged, timeout=timeout, auth=auth)

    connection["httpx_client_factory"] = _httpx_factory

    client = MultiServerMCPClient({"chart": connection})

    async with client.session("chart") as session:
        tools = await load_mcp_tools(session)

        try:
            prompt_result = await session.get_prompt("charts_guide")
            charts_context = "\n".join([msg.content.text for msg in prompt_result.messages])
        except Exception:
            charts_context = "Chart guide not available."

        model = create_llm(temperature=0, thinking_level="low")

        class ChartResponse(BaseModel):
            ok: bool
            tool: Optional[str] = None
            name: Optional[str] = None
            file_path: Optional[str] = None
            artifacts: list[ArtifactRef] = Field(default_factory=list)
            error: Optional[Dict[str, Any]] = None

        prompt_path = Path(__file__).resolve().parent / "prompts" / "CHART_AGENT.md"
        try:
            prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise RuntimeError(f"Prompt not found: {prompt_path}")

        system_prompt = prompt_template.format(
            charts_context=charts_context,
            today_date=date.today().isoformat(),
        )

        agent = create_agent(
            model,
            tools,
            system_prompt=system_prompt,
            response_format=ProviderStrategy(ChartResponse),
        )

        message = input_text.strip()
        if data_url:
            message += f"\nDATA_URL: {data_url}"

        logger.info("[chart_agent] invoking agent for: %s", message[:120])
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"recursion_limit": _recursion_limit(), "callbacks": [usage_cb]},
        )
        structured = result.get("structured_response")
        if not structured:
            messages = result.get("messages", [])
            if messages:
                last = messages[-1]
                content = getattr(last, "content", "")
                logger.error(
                    "[chart_agent] no structured_response. Last message: %s",
                    str(content)[:500],
                )
            else:
                logger.error("[chart_agent] no structured_response and no messages in result")
            fallback = ChartResponse(
                ok=False,
                error={"tool": "agent", "kind": "no_tool_output"},
            )
            return fallback.model_dump_json(), usage_cb.to_metrics()

        if isinstance(structured, ChartResponse):
            logger.info("[chart_agent] ok=%s name=%s", structured.ok, structured.name)
            return structured.model_dump_json(), usage_cb.to_metrics()
        if isinstance(structured, dict):
            resp = ChartResponse(**structured)
            logger.info("[chart_agent] ok=%s name=%s", resp.ok, resp.name)
            return resp.model_dump_json(), usage_cb.to_metrics()

        logger.error("[chart_agent] unexpected structured_response type: %s", type(structured))
        fallback = ChartResponse(
            ok=False,
            error={"tool": "agent", "kind": "unexpected_structured_response"},
        )
        return fallback.model_dump_json(), usage_cb.to_metrics()
