"""
Custom MCP server for chart visualization.

Tools:
- generate_*: stores a chart specification in exports/ with a friendly name.

Notes:
- Any `data` argument can be provided inline or as a .json filename (absolute or
  relative to exports/).

This server does not render images. The frontend will render charts later.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import httpx

from fastmcp import FastMCP

mcp = FastMCP("Chart Visualization Server")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.getenv("EXPORT_DIR", os.path.join(BASE_DIR, "exports"))
_RESOURCES_DIR = os.getenv("RESOURCES_DIR", os.path.join(BASE_DIR, "resources"))
_CHARTS_DOC_PATH = os.getenv("CHARTS_MD", os.path.join(_RESOURCES_DIR, "CHARTS.md"))
try:
    with open(_CHARTS_DOC_PATH, "r", encoding="utf-8") as f:
        _CACHED_CHARTS_GUIDE = f.read()
except FileNotFoundError:
    _CACHED_CHARTS_GUIDE = "No chart guide found."

ChartData = Union[str, List[Dict[str, Any]], Dict[str, Any]]

# ---------------------------
# Utils
# ---------------------------


def _expected_mcp_auth_token() -> Optional[str]:
    token = (os.getenv("MCP_AUTH_TOKEN") or os.getenv("MCP_SHARED_TOKEN") or "").strip()
    return token or None


def _require_mcp_auth() -> None:
    """
    Enforce internal service authentication when MCP_AUTH_TOKEN is configured.

    Local mode remains compatible when no token is configured.
    """
    expected = _expected_mcp_auth_token()
    if not expected:
        return

    presented = None
    try:
        from fastmcp.server.dependencies import get_context

        ctx = get_context()
        request_ctx = getattr(ctx, "request_context", None)
        if request_ctx:
            request = getattr(request_ctx, "request", None)
            if request and hasattr(request, "headers"):
                headers = request.headers
                presented = headers.get("x-mcp-auth")
                if not presented:
                    auth_header = headers.get("authorization", "")
                    if auth_header.lower().startswith("bearer "):
                        presented = auth_header[7:].strip()
    except Exception:
        presented = None

    if presented != expected:
        raise PermissionError("Unauthorized MCP request")


def _safe_name(name: Optional[str], tool: str) -> str:
    if name:
        base = os.path.basename(name)
        base = os.path.splitext(base)[0]
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._-")
        if base:
            return base
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{tool}_{ts}_{uuid.uuid4().hex[:6]}"


def _safe_session_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or None


def _safe_run_id(value: Optional[str]) -> Optional[str]:
    return _safe_session_id(value)


def _extract_run_id_from_context(ctx) -> Optional[str]:
    """Extract run_id from Context - must read from request headers."""
    if ctx is None:
        return None

    try:
        # Try to get from request_context.request.headers (Starlette)
        request_ctx = getattr(ctx, "request_context", None)
        if request_ctx:
            request = getattr(request_ctx, "request", None)
            if request and hasattr(request, "headers"):
                for key in ("mcp-run-id", "x-run-id"):
                    val = request.headers.get(key)
                    if val:
                        return _safe_run_id(val)
        return None
    except Exception:
        return None


def _get_session_id() -> Optional[str]:
    """Extract session_id from MCP context (FastMCP built-in property)."""
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        return _safe_session_id(ctx.session_id)
    except Exception:
        return None


def _get_run_id() -> Optional[str]:
    """Extract run_id from MCP context request headers."""
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        return _extract_run_id_from_context(ctx)
    except Exception:
        return None


def _artifact_store_config() -> tuple:
    """Return (base_url, token) for artifact store."""
    base_url = os.getenv("ARTIFACT_STORE_URL")
    token = os.getenv("ARTIFACT_STORE_TOKEN")
    return base_url, token


def _upload_to_artifact_store(file_path: str, session_id: str, artifact_path: str) -> Optional[Dict[str, Any]]:
    """Upload file to artifact store."""
    base_url, token = _artifact_store_config()
    if not base_url or not session_id:
        return None

    url = f"{base_url.rstrip('/')}/artifacts/{session_id}/{artifact_path.lstrip('/')}?upload=true"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with httpx.Client(timeout=60.0) as client, open(file_path, "rb") as f:
            resp = client.post(url, content=f, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _build_style(
    backgroundColor: Optional[str] = None,
    lineWidth: Optional[float] = None,
    palette: Optional[List[str]] = None,
    texture: Optional[str] = None,
    color: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build style dict from optional parameters."""
    style: Dict[str, Any] = {}
    if backgroundColor:
        style["backgroundColor"] = backgroundColor
    if lineWidth is not None:
        style["lineWidth"] = lineWidth
    if palette:
        style["palette"] = palette
    if texture and texture != "default":
        style["texture"] = texture
    if color:
        style["color"] = color
    return style if style else None


def _parse_csv_to_records(text: str) -> List[Dict[str, Any]]:
    """Parse CSV text into list of dicts (records)."""
    import csv
    import io
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for row in reader:
        # Try to convert numeric values
        record = {}
        for k, v in row.items():
            if v is None or v == "":
                record[k] = None
            else:
                try:
                    if "." in v:
                        record[k] = float(v)
                    else:
                        record[k] = int(v)
                except ValueError:
                    record[k] = v
        records.append(record)
    return records


def _load_data(value: Any) -> Any:
    """Load data from inline value, URL (JSON/CSV), artifact path, or local file."""
    _require_mcp_auth()

    if not isinstance(value, str):
        return value

    # Handle relative artifact store paths like /artifacts/{session_id}/...
    if value.startswith("/artifacts/"):
        base_url, token = _artifact_store_config()
        if not base_url:
            raise FileNotFoundError(
                f"ARTIFACT_STORE_URL is not configured; cannot load artifact path: {value}"
            )
        full_url = f"{base_url.rstrip('/')}{value}"
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(timeout=30.0) as http_client:
            resp = http_client.get(full_url, headers=headers)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            is_csv = value.endswith(".csv") or "text/csv" in content_type
            if is_csv:
                return _parse_csv_to_records(resp.text)
            return resp.json()

    # Handle full HTTP/HTTPS URLs
    if value.startswith("http://") or value.startswith("https://"):
        _, token = _artifact_store_config()
        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(value, headers=headers)
            resp.raise_for_status()

            # Detect format from URL or Content-Type
            content_type = resp.headers.get("content-type", "")
            is_csv = value.endswith(".csv") or "text/csv" in content_type

            if is_csv:
                return _parse_csv_to_records(resp.text)
            return resp.json()

    # Handle local files
    path = value
    if not os.path.isabs(path):
        session_id = _get_session_id()
        if session_id:
            session_dir = os.path.join(EXPORT_DIR, session_id, "data")
            candidate = os.path.join(session_dir, path)
            if os.path.exists(candidate):
                path = candidate
            elif not path.endswith(".json") and not path.endswith(".csv"):
                for ext in (".json", ".csv"):
                    candidate = os.path.join(session_dir, f"{path}{ext}")
                    if os.path.exists(candidate):
                        path = candidate
                        break
        if not os.path.exists(path):
            candidate = os.path.join(EXPORT_DIR, path)
            if os.path.exists(candidate):
                path = candidate
            elif not path.endswith(".json") and not path.endswith(".csv"):
                for ext in (".json", ".csv"):
                    candidate = os.path.join(EXPORT_DIR, f"{path}{ext}")
                    if os.path.exists(candidate):
                        path = candidate
                        break

    if not os.path.exists(path):
        raise FileNotFoundError(f"Data file not found: {value}")

    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".csv"):
            return _parse_csv_to_records(f.read())
        return json.load(f)


def _write_export(tool: str, args: Dict[str, Any], file_name: Optional[str]) -> Dict[str, Any]:
    """
    Write chart specification to file and upload to artifact store.
    
    Uses canonical path structure: {session_id}/runs/{run_id}/charts/{name}.json
    """
    try:
        _require_mcp_auth()
    except Exception:
        return {"ok": False, "error": "Unauthorized MCP request"}

    session_id = _get_session_id()
    run_id = _get_run_id()
    
    if not session_id:
        return {
            "ok": False,
            "error": "session_id is required. Ensure mcp-session-id header is set.",
        }
    
    if not run_id:
        return {
            "ok": False, 
            "error": "run_id is required. Ensure mcp-run-id header is set.",
        }
    
    # Canonical path: {session_id}/runs/{run_id}/charts/{name}.json
    out_dir = os.path.join(EXPORT_DIR, session_id, "runs", run_id, "charts")
    os.makedirs(out_dir, exist_ok=True)
    name = _safe_name(file_name, tool)
    file_path = os.path.join(out_dir, f"{name}.json")
    payload = {
        "tool": tool,
        "name": name,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "args": args,
        "status": "generated",
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    artifacts: List[Dict[str, Any]] = []
    base_url, _ = _artifact_store_config()
    
    # Canonical artifact path: runs/{run_id}/charts/{name}.json
    artifact_path = f"runs/{run_id}/charts/{name}.json"
    
    if base_url:
        upload = _upload_to_artifact_store(file_path, session_id, artifact_path)
        url = f"/artifacts/{session_id}/{artifact_path}"
        if upload and isinstance(upload, dict):
            uploaded_url = (upload.get("artifact") or {}).get("url")
            if uploaded_url:
                url = uploaded_url
        
        artifacts.append({
            "type": "chart",
            "name": f"{name}.json",
            "url": url,
            "path": artifact_path,
        })

        if os.getenv("ARTIFACT_STORE_CLEANUP", "false").lower() == "true":
            try:
                os.remove(file_path)
            except OSError:
                pass
    
    return {
        "ok": True,
        "tool": tool,
        "name": name,
        "file_path": file_path,
        "session_id": session_id,
        "run_id": run_id,
        "message": f"Generated {tool} and saved it as {name}.json",
        "artifacts": artifacts,
    }


# ---------------------------
# Tools
# ---------------------------

@mcp.prompt("charts_guide")
def charts_guide_prompt() -> str:
    """
    Return chart selection guidance and chart tool information.
    """
    return _CACHED_CHARTS_GUIDE

@mcp.tool
def generate_area_chart(
    data: ChartData,
    stack: bool = False,
    backgroundColor: Optional[str] = None,
    lineWidth: Optional[float] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an area chart for time-based trends (stacked or single series).

    Required:
    - data: list of objects with time (string) and value (number). Add group (string) for stacking.

    Optional:
    - stack, backgroundColor, lineWidth, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: keep time formats consistent (e.g., YYYY-MM) and align time points across groups.
    """
    data = _load_data(data)
    style = _build_style(
        backgroundColor=backgroundColor,
        lineWidth=lineWidth,
        palette=palette,
        texture=texture,
    )
    args: Dict[str, Any] = {
        "data": data,
        "stack": stack,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_area_chart", args, file_name)


@mcp.tool
def generate_bar_chart(
    data: ChartData,
    group: bool = False,
    stack: bool = True,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a horizontal bar chart for category comparisons.

    Required:
    - data: list of objects with category (string) and value (number). Add group (string) for grouped/stacked bars.

    Optional:
    - group, stack, backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: keep category labels short; consider stacking when there are many series.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "group": group,
        "stack": stack,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_bar_chart", args, file_name)


@mcp.tool
def generate_boxplot_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a boxplot chart for distribution comparisons by category.

    Required:
    - data: list of objects with category (string) and value (number). Optional group for multi-set comparison.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: provide at least 5 samples per category for meaningful statistics.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_boxplot_chart", args, file_name)


@mcp.tool
def generate_column_chart(
    data: ChartData,
    group: bool = True,
    stack: bool = False,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a vertical column chart for category or time comparisons.

    Required:
    - data: list of objects with category (string) and value (number). Add group (string) for grouped/stacked columns.

    Optional:
    - group, stack, backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: for many categories, use Top-N or aggregation to keep the chart readable.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "group": group,
        "stack": stack,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_column_chart", args, file_name)


@mcp.tool
def generate_district_map(
    title: str,
    data: ChartData,
    dataStyleFillColor: Optional[str] = None,
    dataColors: Optional[List[str]] = None,
    dataType: Optional[str] = None,
    dataLabel: Optional[str] = None,
    dataValue: Optional[str] = None,
    dataValueUnit: Optional[str] = None,
    showAllSubdistricts: bool = False,
    subdistricts: Optional[List[Dict[str, Any]]] = None,
    width: int = 1600,
    height: int = 1000,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a China district map (province/city/county) with thematic coloring.

    Required:
    - title: string (<=16 chars), map title.
    - data: object with at least data.name (Chinese administrative region name).

    Optional:
    - dataStyleFillColor, dataColors, dataType ('number'|'enum'), dataLabel, dataValue,
      dataValueUnit, showAllSubdistricts, subdistricts
    - width, height

    Tips: use precise administrative names; only supports locations in China.
    """
    data = _load_data(data)
    data_payload = dict(data)
    if dataStyleFillColor is not None:
        style = dict(data_payload.get("style") or {})
        style["fillColor"] = dataStyleFillColor
        data_payload["style"] = style
    if dataColors is not None:
        data_payload["colors"] = dataColors
    if dataType is not None:
        data_payload["dataType"] = dataType
    if dataLabel is not None:
        data_payload["dataLabel"] = dataLabel
    if dataValue is not None:
        data_payload["dataValue"] = dataValue
    if dataValueUnit is not None:
        data_payload["dataValueUnit"] = dataValueUnit
    data_payload["showAllSubdistricts"] = showAllSubdistricts
    if subdistricts is not None:
        data_payload["subdistricts"] = subdistricts

    args = {
        "title": title,
        "data": data_payload,
        "width": width,
        "height": height,
    }
    return _write_export("generate_district_map", args, file_name)


@mcp.tool
def generate_dual_axes_chart(
    categories: List[str],
    series: List[Dict[str, Any]],
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a dual-axes chart combining columns and lines.

    Required:
    - categories: list of x-axis labels (strings).
    - series: list of objects with type ('column'|'line') and data (number[] matching categories).

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle

    Tips: keep series count <=2; use secondary axis when magnitudes differ greatly.
    """
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "categories": categories,
        "series": series,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_dual_axes_chart", args, file_name)


@mcp.tool
def generate_fishbone_diagram(
    data: ChartData,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a fishbone (cause-effect) diagram for root cause analysis.

    Required:
    - data: object with root node name and optional children (recursive).

    Optional:
    - texture ('default'|'rough'), theme ('default'|'academy'|'dark'), width, height

    Tips: use short phrases for causes; keep depth to about 3 levels.
    """
    data = _load_data(data)
    style = _build_style(texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if style:
        args["style"] = style
    return _write_export("generate_fishbone_diagram", args, file_name)


@mcp.tool
def generate_flow_diagram(
    data: ChartData,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a flow diagram with nodes and edges.

    Required:
    - data.nodes: list of nodes with unique name.
    - data.edges: list of edges with source and target.

    Optional:
    - texture ('default'|'rough'), theme ('default'|'academy'|'dark'), width, height

    Tips: define nodes first, then edges; keep the flow direction consistent.
    """
    data = _load_data(data)
    style = _build_style(texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if style:
        args["style"] = style
    return _write_export("generate_flow_diagram", args, file_name)


@mcp.tool
def generate_funnel_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a funnel chart for staged conversion or drop-off.

    Required:
    - data: list of objects with category (string) and value (number), ordered by stage.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: keep stages <=6 and order them by the actual process flow.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_funnel_chart", args, file_name)


@mcp.tool
def generate_histogram_chart(
    data: ChartData,
    binNumber: Optional[int] = None,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a histogram for numeric distribution analysis.

    Required:
    - data: list of numbers (>=1).

    Optional:
    - binNumber, backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: use sample sizes >=30 and tune binNumber for readability.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if binNumber is not None:
        args["binNumber"] = binNumber
    if style:
        args["style"] = style
    return _write_export("generate_histogram_chart", args, file_name)


@mcp.tool
def generate_line_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    lineWidth: Optional[float] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a line chart for time or continuous trends.

    Required:
    - data: list of objects with time (string) and value (number). Add group (string) for multiple series.

    Optional:
    - backgroundColor, lineWidth, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: align time points across series and use ISO time strings like 2025-01-01.
    """
    data = _load_data(data)
    style = _build_style(
        backgroundColor=backgroundColor,
        lineWidth=lineWidth,
        palette=palette,
        texture=texture,
    )
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_line_chart", args, file_name)


@mcp.tool
def generate_liquid_chart(
    percent: float,
    shape: str = "circle",
    backgroundColor: Optional[str] = None,
    color: Optional[str] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a liquid (progress) chart.

    Required:
    - percent: number in [0, 1].

    Optional:
    - shape ('circle'|'rect'|'pin'|'triangle'), backgroundColor, color, texture
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: normalize to 0-1 and use a descriptive title like "Completion 85%".
    """
    style = _build_style(backgroundColor=backgroundColor, color=color, texture=texture)
    args: Dict[str, Any] = {
        "percent": percent,
        "shape": shape,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_liquid_chart", args, file_name)


@mcp.tool
def generate_mind_map(
    data: ChartData,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a mind map with a root topic and hierarchical branches.

    Required:
    - data: object with name and optional children (recursive).

    Optional:
    - texture ('default'|'rough'), theme ('default'|'academy'|'dark'), width, height

    Tips: keep depth <=3 and use short phrases for nodes.
    """
    data = _load_data(data)
    style = _build_style(texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if style:
        args["style"] = style
    return _write_export("generate_mind_map", args, file_name)


@mcp.tool
def generate_network_graph(
    data: ChartData,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a network graph with nodes and edges.

    Required:
    - data.nodes: list of nodes with unique name.
    - data.edges: list of edges with source and target (strings).

    Optional:
    - texture ('default'|'rough'), theme ('default'|'academy'|'dark'), width, height

    Tips: keep node count around 10-50 and ensure edges reference existing nodes.
    """
    data = _load_data(data)
    style = _build_style(texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if style:
        args["style"] = style
    return _write_export("generate_network_graph", args, file_name)


@mcp.tool
def generate_organization_chart(
    data: ChartData,
    orient: str = "vertical",
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an organization chart for hierarchy visualization.

    Required:
    - data: object with name (string) and optional description, children.

    Optional:
    - orient ('horizontal'|'vertical'), texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height

    Tips: keep depth <=3 and describe roles briefly in node descriptions.
    """
    data = _load_data(data)
    style = _build_style(texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "orient": orient,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if style:
        args["style"] = style
    return _write_export("generate_organization_chart", args, file_name)


@mcp.tool
def generate_path_map(
    title: str,
    data: ChartData,
    width: int = 1600,
    height: int = 1000,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a China path map by connecting ordered POIs.

    Required:
    - title: string (<=16 chars).
    - data: list of route objects. Each route must include data: string[] of POI names.

    Optional:
    - width, height

    Tips: POI names must be precise and located in China; add multiple routes as separate objects.
    """
    data = _load_data(data)
    args = {
        "title": title,
        "data": data,
        "width": width,
        "height": height,
    }
    return _write_export("generate_path_map", args, file_name)


@mcp.tool
def generate_pie_chart(
    data: ChartData,
    innerRadius: float = 0,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a pie (or donut) chart for part-to-whole comparison.

    Required:
    - data: list of objects with category (string) and value (number).

    Optional:
    - innerRadius, backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: keep categories <=6 and aggregate the rest into "Other" if needed.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "innerRadius": innerRadius,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_pie_chart", args, file_name)


@mcp.tool
def generate_pin_map(
    title: str,
    data: ChartData,
    markerPopupType: str = "image",
    markerPopupWidth: int = 40,
    markerPopupHeight: int = 40,
    markerPopupBorderRadius: int = 8,
    width: int = 1600,
    height: int = 1000,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a China pin map for multiple POI locations.

    Required:
    - title: string (<=16 chars).
    - data: list of POI names (strings) in China.

    Optional:
    - markerPopupType, markerPopupWidth, markerPopupHeight, markerPopupBorderRadius
    - width, height

    Tips: include city + landmark for accurate geocoding; supports China only.
    """
    data = _load_data(data)
    args = {
        "title": title,
        "data": data,
        "markerPopup": {
            "type": markerPopupType,
            "width": markerPopupWidth,
            "height": markerPopupHeight,
            "borderRadius": markerPopupBorderRadius,
        },
        "width": width,
        "height": height,
    }
    return _write_export("generate_pin_map", args, file_name)


@mcp.tool
def generate_radar_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    lineWidth: Optional[float] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a radar chart for multi-dimensional comparison.

    Required:
    - data: list of objects with name (string) and value (number). Use group for multiple subjects.

    Optional:
    - backgroundColor, lineWidth, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: use 4-8 dimensions and normalize values when units differ.
    """
    data = _load_data(data)
    style = _build_style(
        backgroundColor=backgroundColor,
        lineWidth=lineWidth,
        palette=palette,
        texture=texture,
    )
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_radar_chart", args, file_name)


@mcp.tool
def generate_sankey_chart(
    data: ChartData,
    nodeAlign: str = "center",
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a Sankey chart to visualize flow between nodes.

    Required:
    - data: list of objects with source (string), target (string), value (number).

    Optional:
    - nodeAlign, backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: keep node names unique and filter tiny flows for readability.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "nodeAlign": nodeAlign,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_sankey_chart", args, file_name)


@mcp.tool
def generate_scatter_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a scatter chart for correlation analysis.

    Required:
    - data: list of objects with x (number) and y (number). Use group for categories.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: standardize units or sample large datasets to reduce clutter.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_scatter_chart", args, file_name)


@mcp.tool
def generate_spreadsheet(
    data: ChartData,
    rows: Optional[List[str]] = None,
    columns: Optional[List[str]] = None,
    values: Optional[List[str]] = None,
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a spreadsheet or pivot table from structured data.

    Required:
    - data: list of row objects (keys are column names).

    Optional:
    - rows, columns, values (for pivot table)
    - theme ('default'|'dark'), width, height

    Tips: ensure rows/columns/values fields exist in each data object.
    """
    data = _load_data(data)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
    }
    if rows is not None:
        args["rows"] = rows
    if columns is not None:
        args["columns"] = columns
    if values is not None:
        args["values"] = values
    return _write_export("generate_spreadsheet", args, file_name)


@mcp.tool
def generate_treemap_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a treemap for hierarchical part-to-whole analysis.

    Required:
    - data: list of nodes with name (string) and value (number). Children can be nested.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: keep depth shallow and ensure values sum correctly across levels.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_treemap_chart", args, file_name)


@mcp.tool
def generate_venn_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a Venn chart for set overlaps.

    Required:
    - data: list of objects with value (number) and sets (string[]). Optional label.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: keep set count <=4 and use concise set names.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_venn_chart", args, file_name)


@mcp.tool
def generate_violin_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    axisXTitle: str = "",
    axisYTitle: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a violin chart for distribution comparison by category.

    Required:
    - data: list of objects with category (string) and value (number). Optional group.

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title, axisXTitle, axisYTitle

    Tips: use >=30 samples per category for stable density estimates.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
        "axisXTitle": axisXTitle,
        "axisYTitle": axisYTitle,
    }
    if style:
        args["style"] = style
    return _write_export("generate_violin_chart", args, file_name)


@mcp.tool
def generate_word_cloud_chart(
    data: ChartData,
    backgroundColor: Optional[str] = None,
    palette: Optional[List[str]] = None,
    texture: str = "default",
    theme: str = "default",
    width: int = 600,
    height: int = 400,
    title: str = "",
    file_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate a word cloud based on text frequency or weight.

    Required:
    - data: list of objects with text (string) and value (number).

    Optional:
    - backgroundColor, palette, texture ('default'|'rough')
    - theme ('default'|'academy'|'dark'), width, height, title

    Tips: remove stopwords and normalize casing before sending data.
    """
    data = _load_data(data)
    style = _build_style(backgroundColor=backgroundColor, palette=palette, texture=texture)
    args: Dict[str, Any] = {
        "data": data,
        "theme": theme,
        "width": width,
        "height": height,
        "title": title,
    }
    if style:
        args["style"] = style
    return _write_export("generate_word_cloud_chart", args, file_name)


if __name__ == "__main__":
    # Use PORT env var (Cloud Run) or fallback to 3334 (local)
    port = int(os.getenv("PORT", "3334"))
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
    )
