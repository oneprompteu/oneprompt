"""
Custom MCP server for PostgreSQL with preview and export tools.

Tools:
- list_tables(): tables in public schema.
- describe_table(table_name): columns + data types.
- query_preview(sql, sample_rows=5): runs SELECT/WITH and returns small preview.
- export_query(sql, sample_rows=5, file_name="export"): exports full result to CSV + JSON and returns preview + metadata.

The server never returns the full dataset to the model.
Database DSN can be provided through encrypted `x-dataset-token`/`x-dataset-dsn`
headers, or fallback to POSTGRES_DSN env var.
Optional EXPORT_DIR for output files (default: current working directory).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import httpx
import pandas as pd
import psycopg2
from fastmcp import Context, FastMCP
from psycopg2.extensions import connection as PgConnection
from psycopg2.extensions import parse_dsn

try:
    from oneprompt.services.dataset_token import DatasetTokenError, parse_dataset_token
except (ImportError, ModuleNotFoundError):
    # Docker image runs a standalone script and ships dataset_token.py directly.
    from dataset_token import DatasetTokenError, parse_dataset_token

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_RESOURCES_DIR = os.getenv(
    "RESOURCES_DIR",
    os.path.join(BASE_DIR, "resources"),
)
EXPORT_DIR = os.getenv("EXPORT_DIR", os.path.join(BASE_DIR, "exports"))
_DB_DOC_PATH = os.getenv("DATABASE_MD", os.path.join(_RESOURCES_DIR, "DATABASE.md"))
try:
    with open(_DB_DOC_PATH, "r", encoding="utf-8") as f:
        _CACHED_DB_SCHEMA = f.read()
except FileNotFoundError:
    _CACHED_DB_SCHEMA = "No schema documentation found."

logger = logging.getLogger(__name__)

mcp = FastMCP("Postgres Export Server")

# ---------------------------
# Utils
# ---------------------------

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "grant", "revoke", "vacuum", "analyze", "copy", "call", "do",
}
ROW_COUNT_TIMEOUT_MS = 2000
METADATA_HOSTS = {"metadata.google.internal", "metadata", "169.254.169.254"}


def _expected_mcp_auth_token() -> Optional[str]:
    token = (os.getenv("MCP_AUTH_TOKEN") or os.getenv("MCP_SHARED_TOKEN") or "").strip()
    return token or None


def _require_mcp_auth(ctx: Optional[Context] = None) -> None:
    """
    Enforce internal service authentication when MCP_AUTH_TOKEN is configured.

    Local mode stays backwards compatible: if no token is configured, auth is skipped.
    """
    expected = _expected_mcp_auth_token()
    if not expected:
        return

    presented = None
    if ctx is not None:
        try:
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
        raise PermissionError("permission denied: unauthorized MCP request")


def _env_int(name: str, default: int, *, minimum: int = 0, maximum: int = 3_600_000) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _private_or_local_host(host: str) -> bool:
    host_value = (host or "").strip().lower()
    if not host_value:
        return False
    if host_value in {"localhost", "host.docker.internal"}:
        return True
    if host_value.endswith(".local"):
        return True
    if host_value.startswith("/"):
        # Unix socket paths are local endpoints.
        return True

    try:
        ip = ipaddress.ip_address(host_value)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return False


def _is_metadata_host(host: str) -> bool:
    host_value = (host or "").strip().lower().rstrip(".")
    if host_value in METADATA_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host_value)
    except ValueError:
        return False
    return str(ip) == "169.254.169.254"


def _dsn_hosts(dsn: str) -> List[str]:
    try:
        parsed = parse_dsn(dsn)
        host_value = str(parsed.get("host", "")).strip()
        if host_value:
            return [h.strip() for h in host_value.split(",") if h.strip()]
    except Exception:
        pass

    if "://" in dsn:
        parsed_uri = urlsplit(dsn)
        if parsed_uri.hostname:
            return [parsed_uri.hostname]

    return []


def _validate_dsn_destination(dsn: str) -> None:
    allowed_hosts = {
        h.strip().lower()
        for h in (os.getenv("POSTGRES_ALLOWED_HOSTS", "") or "").split(",")
        if h.strip()
    }
    block_metadata = _env_bool("POSTGRES_BLOCK_METADATA_HOSTS", True)
    allow_private = _env_bool("POSTGRES_ALLOW_PRIVATE_HOSTS", True)

    hosts = _dsn_hosts(dsn)
    for host in hosts:
        host_lc = host.lower().rstrip(".")

        if allowed_hosts and host_lc not in allowed_hosts:
            raise PermissionError(f"DSN host '{host}' is not in POSTGRES_ALLOWED_HOSTS.")

        if block_metadata and _is_metadata_host(host_lc):
            raise PermissionError("DSN host resolves to blocked metadata endpoint.")

        if not allow_private and _private_or_local_host(host_lc):
            raise PermissionError("Private/local DSN hosts are blocked by configuration.")


def _redact_sensitive_text(text: str) -> str:
    redacted = text
    # URI credential style: postgresql://user:password@host/db
    redacted = re.sub(
        r"((?:postgres|postgresql)://[^:/@\s]+:)[^@/\s]+(@)",
        r"\1***\2",
        redacted,
        flags=re.IGNORECASE,
    )
    # key=value style: password=secret
    redacted = re.sub(
        r"(\bpassword\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s;]+)",
        r"\1***",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


def _get_dsn_from_context(ctx: Optional[Context] = None) -> Optional[str]:
    """
    Extract DSN from request context headers.

    Allows dynamic dataset configuration via x-dataset-token (encrypted)
    or x-dataset-dsn (legacy plaintext) headers.
    Falls back to POSTGRES_DSN environment variable.
    """
    if ctx is None:
        return None

    try:
        request_ctx = getattr(ctx, "request_context", None)
        if request_ctx:
            request = getattr(request_ctx, "request", None)
            if request and hasattr(request, "headers"):
                headers = request.headers
                token = headers.get("x-dataset-token")
                if token:
                    run_id = None
                    for key in ("mcp-run-id", "x-run-id"):
                        value = headers.get(key)
                        if value:
                            run_id = _safe_run_id(value)
                            break
                    payload = parse_dataset_token(
                        token,
                        expected_audience="postgres-mcp",
                        expected_session_id=_safe_session_id(getattr(ctx, "session_id", None)),
                        expected_run_id=run_id,
                    )
                    dsn_from_token = str(payload.get("dsn", "")).strip()
                    if dsn_from_token:
                        return dsn_from_token
                    raise DatasetTokenError("Dataset token has no DSN.")

                dsn = headers.get("x-dataset-dsn")
                if dsn:
                    return dsn
    except DatasetTokenError as exc:
        raise PermissionError(f"Invalid dataset token: {exc}") from exc
    except Exception:
        pass

    return None


def _connect(ctx: Optional[Context] = None) -> PgConnection:
    """
    Connect to PostgreSQL database.

    Priority for DSN:
    1. x-dataset-token / x-dataset-dsn header from request context
    2. POSTGRES_DSN environment variable (fallback)
    """
    # Try to get DSN from context headers first
    dsn = _get_dsn_from_context(ctx)

    # Fallback to environment variable
    if not dsn:
        dsn = os.getenv("POSTGRES_DSN")

    if not dsn:
        raise RuntimeError(
            "No database connection configured. Provide x-dataset-token/x-dataset-dsn header "
            "or set POSTGRES_DSN environment variable."
        )

    _validate_dsn_destination(dsn)
    connect_timeout = _env_int("POSTGRES_CONNECT_TIMEOUT_SEC", 10, minimum=1, maximum=300)

    return psycopg2.connect(dsn, connect_timeout=connect_timeout)

def _is_readonly_sql(query: str) -> bool:
    q = query.strip().lower()

    # allow WITH ... SELECT ... (CTE)
    if not (q.startswith("select") or q.startswith("with")):
        return False

    # cheap guardrails
    if ";" in q:
        # avoid multiple statements / injection-by-statement-chaining
        return False

    # block obvious DDL/DML
    tokens = set(q.replace("\n", " ").replace("\t", " ").split())
    if tokens & FORBIDDEN_KEYWORDS:
        return False

    return True

def _to_str(v):
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return str(v)

def _safe_session_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or None

def _safe_run_id(value: Optional[str]) -> Optional[str]:
    return _safe_session_id(value)


def _extract_session_id(ctx: Optional[Context]) -> Optional[str]:
    """Extract session_id from Context object."""
    if ctx is None:
        return None

    # FastMCP Context has session_id as a built-in property that reads from mcp-session-id header
    try:
        return _safe_session_id(ctx.session_id)
    except Exception:
        pass

    return None


def _extract_run_id(ctx: Optional[Context]) -> Optional[str]:
    """Extract run_id from Context object - must read from request headers."""
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


# Legacy functions for backward compatibility (use get_context)
def _get_session_id() -> Optional[str]:
    """Extract session_id from MCP context."""
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        return _extract_session_id(ctx)
    except Exception as e:
        logger.debug("_get_session_id error: %s", e)
        return None


def _get_run_id() -> Optional[str]:
    """Extract run_id from MCP context headers."""
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        return _extract_run_id(ctx)
    except Exception as e:
        logger.debug("_get_run_id error: %s", e)
        return None


def _artifact_store_config() -> tuple[Optional[str], Optional[str]]:
    base_url = os.getenv("ARTIFACT_STORE_URL")
    token = os.getenv("ARTIFACT_STORE_TOKEN")
    return base_url, token

def _artifact_store_url(base_url: str, session_id: str, artifact_path: str, upload: bool = False) -> str:
    base = base_url.rstrip("/")
    path = artifact_path.lstrip("/")
    url = f"{base}/artifacts/{session_id}/{path}"
    if upload:
        url += "?upload=true"
    return url

def _upload_to_artifact_store(file_path: str, session_id: str, artifact_path: str) -> Optional[Dict[str, Any]]:
    base_url, token = _artifact_store_config()
    if not base_url or not session_id:
        return None
    url = _artifact_store_url(base_url, session_id, artifact_path, upload=True)
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=60.0) as client, open(file_path, "rb") as f:
        resp = client.post(url, content=f, headers=headers)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return None

def _rows_to_dict_preview(columns, rows, limit: int):
    out = []
    for r in rows[:limit]:
        # r puede ser tuple/list
        out.append({columns[i]: _to_str(r[i]) for i in range(len(columns))})
    return out

def _tool_error(tool: str, exc: Exception, sql_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Return a small, consistent error payload (safe for LLM context).
    """
    msg = _redact_sensitive_text(str(exc)).strip().replace("\n", " ")
    msg = msg[:240]  # hard cap to protect context

    # Minimal classification (helps agent self-correct)
    lower = msg.lower()
    if "syntax error" in lower:
        kind = "sql_syntax_error"
    elif "does not exist" in lower:
        kind = "sql_missing_relation_or_column"
    elif "permission denied" in lower:
        kind = "sql_permission_denied"
    elif "timeout" in lower:
        kind = "sql_timeout"
    else:
        kind = "sql_execution_error"

    payload: Dict[str, Any] = {
        "ok": False,
        "error": {
            "tool": tool,
            "kind": kind,
            "message": msg,
        },
    }
    # Optionally include a tiny hint of the query (first chars) for debugging/self-correction
    if sql_text:
        payload["error"]["sql_snippet"] = sql_text.strip().replace("\n", " ")[:120]
    return payload

# ---------------------------
# Prompts
# ---------------------------

@mcp.prompt("postgres_schema")
def database_schema_prompt() -> str:
    """
    Devuelve la documentación y el esquema de la base de datos PostgreSQL.
    Útil para dar contexto al LLM antes de generar SQL.
    """
    # Aquí podrías incluso hacer una consulta SQL en tiempo real para obtener
    # el esquema actualizado si no quisieras usar el archivo .md
    return f"""
Información de la base de datos (Schema):
{_CACHED_DB_SCHEMA}

Reglas generales:
1. Usa solo consultas de lectura (SELECT/WITH).
2. No uses punto y coma (;) al final.
"""

# ---------------------------
# Tools
# ---------------------------

@mcp.tool
def query_preview(sql: str, sample_rows: int = 5, ctx: Context = None) -> Dict[str, Any]:
    """
    Execute a read-only SELECT/WITH query and return a small preview + columns.

    - Never returns the full dataset.
    - Row count is included by default; it may be skipped if the count times out.
    - Do not add ";", multiple statements, or any non-SELECT/WITH commands.
    """
    try:
        _require_mcp_auth(ctx)
    except Exception as e:
        return _tool_error("query_preview", e, sql)

    if not _is_readonly_sql(sql):
        return _tool_error("query_preview", ValueError("Only single-statement read-only SELECT/WITH queries are allowed."), sql)

    try:
        sample_rows = max(1, min(int(sample_rows), 50))  # cap preview
        query_timeout_ms = _env_int("POSTGRES_QUERY_TIMEOUT_MS", 30_000, minimum=1_000, maximum=600_000)

        with _connect(ctx) as conn, conn.cursor() as cur:
            preview_sql = f"SELECT * FROM ({sql}) AS subq LIMIT {sample_rows}"
            cur.execute("SET LOCAL statement_timeout = %s", (f"{query_timeout_ms}ms",))
            cur.execute(preview_sql)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]

            preview = _rows_to_dict_preview(columns, rows, sample_rows)

            row_count = None
            comment = None
            count_sql = f"SELECT COUNT(*) FROM ({sql}) AS subq"
            try:
                cur.execute("SET LOCAL statement_timeout = %s", (f"{ROW_COUNT_TIMEOUT_MS}ms",))
                cur.execute(count_sql)
                row_count = int(cur.fetchone()[0])
            except psycopg2.errors.QueryCanceled:
                conn.rollback()
                comment = (
                    "No se ha podido calcular el count porque hay muchos datos y el conteo excedio el tiempo limite."
                )

        payload = {
            "ok": True,
            "columns": columns,
            "preview": preview,
        }
        if row_count is not None:
            payload["row_count"] = row_count
        if comment:
            payload["comment"] = comment
        return payload

    except Exception as e:
        return _tool_error("query_preview", e, sql)


@mcp.tool
def export_query(
    sql: str,
    sample_rows: int = 5,
    file_name: str = "export",
    ctx: Context = None,
) -> Dict[str, Any]:
    """Ejecuta una SELECT/WITH y exporta el resultado a CSV y JSON. file_name define el nombre base del archivo. No pongas ";" ni extension."""
    try:
        _require_mcp_auth(ctx)
    except Exception as e:
        return _tool_error("export_query", e, sql)

    # Validate query
    if not _is_readonly_sql(sql):
        return _tool_error("export_query", ValueError("Only single-statement read-only SELECT/WITH queries are allowed."), sql)

    # Get context IDs - try from injected ctx first, then fallback to get_context()
    session_id = _extract_session_id(ctx) if ctx else None
    run_id = _extract_run_id(ctx) if ctx else None

    # Fallback to global context if ctx didn't have the values
    if not session_id:
        session_id = _get_session_id()
    if not run_id:
        run_id = _get_run_id()

    logger.debug("export_query: ctx=%s, session_id=%s, run_id=%s", ctx, session_id, run_id)

    if not session_id:
        return _tool_error("export_query", ValueError("session_id is required. Ensure mcp-session-id header is set."), sql)

    if not run_id:
        return _tool_error("export_query", ValueError("run_id is required. Ensure mcp-run-id header is set."), sql)

    # Build consistent path: {session_id}/runs/{run_id}/data/{filename}
    base_dir = EXPORT_DIR.strip('"').strip("'")
    out_dir = os.path.join(base_dir, session_id, "runs", run_id, "data")
    os.makedirs(out_dir, exist_ok=True)

    try:
        query_timeout_ms = _env_int("POSTGRES_QUERY_TIMEOUT_MS", 30_000, minimum=1_000, maximum=600_000)
        export_max_rows = _env_int("POSTGRES_EXPORT_MAX_ROWS", 0, minimum=0, maximum=10_000_000)

        # Siempre exportamos primero a CSV por eficiencia
        safe_name = os.path.basename(file_name).strip()
        if not safe_name:
            safe_name = "export"
        safe_name = os.path.splitext(safe_name)[0]
        csv_path = os.path.join(out_dir, f"{safe_name}.csv")

        with _connect(ctx) as conn, conn.cursor() as cur, open(csv_path, "wb") as f:
            cur.execute("SET LOCAL statement_timeout = %s", (f"{query_timeout_ms}ms",))
            export_sql = sql
            if export_max_rows > 0:
                export_sql = f"SELECT * FROM ({sql}) AS subq LIMIT {export_max_rows}"
            copy_sql = f"COPY ({export_sql}) TO STDOUT WITH CSV HEADER"
            cur.copy_expert(copy_sql, f)

        # Previsualización: lee solo sample_rows con pandas
        df_preview = pd.read_csv(csv_path, nrows=max(1, min(int(sample_rows), 50)))
        columns: List[str] = df_preview.columns.tolist()
        preview = [
            {c: _to_str(val) for c, val in row.items()}
            for _, row in df_preview.iterrows()
        ]

        # Export JSON as array of objects (chart-ready data)
        json_path = os.path.join(out_dir, f"{safe_name}.json")
        with open(json_path, "w", encoding="utf-8") as out:
            out.write("[")
            first = True
            for chunk in pd.read_csv(csv_path, chunksize=200_000):
                chunk_json = chunk.to_json(orient="records", date_format="iso")
                if chunk_json == "[]":
                    continue
                chunk_body = chunk_json[1:-1]
                if not chunk_body:
                    continue
                if not first:
                    out.write(",\n")
                out.write(chunk_body)
                first = False
            out.write("]")

        artifacts: List[Dict[str, Any]] = []
        base_url, _ = _artifact_store_config()

        # Canonical artifact paths: runs/{run_id}/data/{filename}
        csv_artifact_path = f"runs/{run_id}/data/{safe_name}.csv"
        json_artifact_path = f"runs/{run_id}/data/{safe_name}.json"
        csv_url = f"/artifacts/{session_id}/{csv_artifact_path}"
        json_url = f"/artifacts/{session_id}/{json_artifact_path}"

        if base_url:
            csv_upload = _upload_to_artifact_store(csv_path, session_id, csv_artifact_path)
            json_upload = _upload_to_artifact_store(json_path, session_id, json_artifact_path)

            if csv_upload and isinstance(csv_upload, dict):
                uploaded_url = (csv_upload.get("artifact") or {}).get("url")
                if uploaded_url:
                    csv_url = uploaded_url

            if json_upload and isinstance(json_upload, dict):
                uploaded_url = (json_upload.get("artifact") or {}).get("url")
                if uploaded_url:
                    json_url = uploaded_url

        artifacts = [
            {"type": "data", "name": f"{safe_name}.csv", "url": csv_url, "path": csv_artifact_path},
            {"type": "data", "name": f"{safe_name}.json", "url": json_url, "path": json_artifact_path},
        ]

        if os.getenv("ARTIFACT_STORE_CLEANUP", "false").lower() == "true":
            for path in (csv_path, json_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        return {
            "ok": True,
            "columns": columns,
            "preview": preview,
            "row_count": None,
            "file_path": json_path,
            "csv_path": csv_path,
            "format": "json",
            "session_id": session_id,
            "run_id": run_id,
            "artifacts": artifacts,
            "comment": (
                f"Export capped to {export_max_rows} rows by POSTGRES_EXPORT_MAX_ROWS."
                if export_max_rows > 0
                else None
            ),
        }

    except Exception as e:
        return _tool_error("export_query", e, sql)


if __name__ == "__main__":
    # HTTP server instead of stdio
    # Use PORT env var (Cloud Run) or fallback to 3333 (local)
    port = int(os.getenv("PORT", "3333"))
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=port,
        stateless_http=True,
    )
