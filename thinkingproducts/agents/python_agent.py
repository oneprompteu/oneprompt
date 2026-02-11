"""
Python agent — executes data analysis in a sandboxed Python environment.

Uses a LangChain agent with Gemini LLM connected to a Python MCP server
that provides a secure sandbox for running data analysis code.
"""

import asyncio
import json
from datetime import date
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import warnings

from pydantic import BaseModel, Field

from thinkingproducts.agents.context import AgentContext

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import CallToolResult, TextContent

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


MAX_TOOL_TEXT_CHARS = 2000
MAX_STRUCTURED_CHARS = 1500


def _truncate_text(text: Optional[str], limit: int) -> Optional[str]:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _structured_preview(structured: dict[str, Any]) -> Optional[str]:
    if not structured:
        return None
    if "artifact" in structured and isinstance(structured["artifact"], dict):
        summary = {"artifact": structured["artifact"]}
    elif "artifacts" in structured and isinstance(structured["artifacts"], list):
        summary = {"artifacts": structured["artifacts"]}
    else:
        summary = structured
    try:
        text = json.dumps(summary, ensure_ascii=False)
    except Exception:
        text = str(summary)
    return _truncate_text(text, MAX_STRUCTURED_CHARS)


async def _tool_output_interceptor(request: MCPToolCallRequest, handler):
    result = await handler(request)
    if isinstance(result, CallToolResult):
        trimmed_content: list[Any] = []
        for block in result.content:
            if isinstance(block, TextContent):
                trimmed_content.append(
                    TextContent(type="text", text=_truncate_text(block.text, MAX_TOOL_TEXT_CHARS) or "")
                )
            else:
                trimmed_content.append(block)

        structured_preview = None
        if result.structuredContent:
            structured_preview = _structured_preview(result.structuredContent)
        if structured_preview:
            trimmed_content.append(TextContent(type="text", text=structured_preview))

        return result.model_copy(update={"content": trimmed_content})
    return result


class ArtifactRef(BaseModel):
    type: Optional[str] = None
    name: str
    url: str


class AnalysisResponse(BaseModel):
    ok: bool
    summary: Optional[str] = None
    artifacts: List[ArtifactRef] = Field(default_factory=list)
    error: Optional[Dict[str, Any]] = None


async def run(
    instruction: str,
    context: AgentContext,
    data_path: Optional[str] = None,
    output_name: Optional[str] = None,
) -> str:
    """
    Execute a Python analysis instruction via the Python MCP server.

    Args:
        instruction: Analysis instructions.
        context: Agent context.
        data_path: Optional path to input data artifact.
        output_name: Optional output file name.

    Returns:
        JSON string conforming to AnalysisResponse schema.
    """
    mcp_url = os.environ.get("MCP_PYTHON_URL")
    if not mcp_url:
        raise RuntimeError("MCP_PYTHON_URL must be set (hint: start MCP servers with `tp start`)")

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

    client = MultiServerMCPClient(
        {"python": connection},
        tool_interceptors=[_tool_output_interceptor],
    )

    async with client.session("python") as session:
        tools = await load_mcp_tools(session)

        try:
            prompt_result = await session.get_prompt("python_guide")
            python_context = "\n".join([msg.content.text for msg in prompt_result.messages])
        except Exception:
            python_context = "Python sandbox guide not available."

        model = ChatGoogleGenerativeAI(
            model=os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview"),
            temperature=0,
        )

        prompt_path = Path(__file__).resolve().parent / "prompts" / "PYTHON_AGENT.md"
        try:
            prompt_template = prompt_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise RuntimeError(f"Prompt not found: {prompt_path}")

        system_prompt = prompt_template.format(
            python_context=python_context,
            today_date=date.today().isoformat(),
        )

        agent = create_agent(
            model,
            tools,
            system_prompt=system_prompt,
            response_format=ProviderStrategy(AnalysisResponse),
        )

        message = instruction.strip()
        if data_path:
            data_url = context.artifact_store.build_url(data_path)
            message += f"\nDATA_URL: {data_url}"

        output_file = (output_name or "result.csv").strip()
        if output_file:
            output_path = context.artifact_store.build_artifact_path(
                artifact_type="results",
                filename=output_file,
            )
            output_url = context.artifact_store.build_upload_url(output_path)
            message += f"\nOUTPUT_URL: {output_url}"

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"recursion_limit": _recursion_limit()},
        )
        structured = result.get("structured_response")
        if not structured:
            fallback = AnalysisResponse(
                ok=False,
                error={"tool": "agent", "kind": "no_tool_output"},
            )
            return fallback.model_dump_json()

        if isinstance(structured, AnalysisResponse):
            return structured.model_dump_json()
        if isinstance(structured, dict):
            resp = AnalysisResponse(**structured)
            return resp.model_dump_json()

        fallback = AnalysisResponse(
            ok=False,
            error={"tool": "agent", "kind": "unexpected_structured_response"},
        )
        return fallback.model_dump_json()
