"""
Chart agent — generates AntV chart visualizations.

Uses a LangChain agent with Gemini LLM connected to a Chart MCP server
to generate chart specifications from data and descriptions.
"""

import asyncio
from datetime import date
from pydantic import BaseModel, Field
import os
from pathlib import Path
from typing import Any, Dict, Optional
import warnings

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from mcp.shared._httpx_utils import create_mcp_http_client

from thinkingproducts.agents.context import AgentContext

warnings.filterwarnings(
    "ignore",
    message="Key 'additionalProperties' is not supported in schema, ignoring",
)


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
) -> str:
    """
    Execute a chart generation request against the Chart MCP server.

    Args:
        input_text: Text describing the chart with optional file_name and preview.
        context: Agent context.
        data_url: Optional HTTP URL to data in the Artifact Store.

    Returns:
        JSON string with chart specification.
    """
    mcp_url = os.environ.get("MCP_CHART_URL")
    if not mcp_url:
        raise RuntimeError("MCP_CHART_URL must be set (hint: start MCP servers with `tp start`)")

    connection: Dict[str, Any] = {
        "transport": "http",
        "url": mcp_url,
        "headers": {
            "mcp-session-id": context.session_id,
            "mcp-run-id": context.run_id,
        },
    }

    def _httpx_factory(headers=None, timeout=None, auth=None):
        merged = dict(headers or {})
        merged.setdefault("mcp-session-id", context.session_id)
        merged.setdefault("mcp-run-id", context.run_id)
        return create_mcp_http_client(headers=merged, timeout=timeout, auth=auth)

    connection["httpx_client_factory"] = _httpx_factory

    client = MultiServerMCPClient({"chart": connection})

    async with client.session("chart") as session:
        tools = await load_mcp_tools(session)

        try:
            prompt_result = await session.get_prompt("charts_guide")
            charts_context = "\n".join([msg.content.text for msg in prompt_result.messages])
        except Exception:
            charts_context = "Chart guide not available."

        model = ChatGoogleGenerativeAI(
            model=os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"),
            temperature=0,
        )

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

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"recursion_limit": _recursion_limit()},
        )
        structured = result.get("structured_response")
        if not structured:
            fallback = ChartResponse(
                ok=False,
                error={"tool": "agent", "kind": "no_tool_output"},
            )
            return fallback.model_dump_json()

        if isinstance(structured, ChartResponse):
            return structured.model_dump_json()
        if isinstance(structured, dict):
            resp = ChartResponse(**structured)
            return resp.model_dump_json()

        fallback = ChartResponse(
            ok=False,
            error={"tool": "agent", "kind": "unexpected_structured_response"},
        )
        return fallback.model_dump_json()
