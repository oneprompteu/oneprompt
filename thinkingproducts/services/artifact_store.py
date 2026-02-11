"""
Artifact Store — FastAPI file storage service.

Provides HTTP endpoints for reading and writing session artifacts.
Used by MCP servers and agents to persist generated files.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

_default_export_root = Path(__file__).resolve().parent
BASE_EXPORT_DIR = Path(
    os.getenv("EXPORT_DIR", _default_export_root / "exports")
).resolve()

ARTIFACTS_TOKEN = os.getenv("ARTIFACT_STORE_TOKEN") or os.getenv("ARTIFACTS_TOKEN")

app = FastAPI(
    title="ThinkingProducts Artifact Store",
    version="1.0.0",
    description="File storage service for session artifacts",
)


def _safe_session_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not safe:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    return safe


def _safe_rel_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Invalid artifact path")
    if not value or value.strip() == "":
        raise HTTPException(status_code=400, detail="Empty artifact path")
    return path


def _resolve_target(session_id: str, rel_path: str) -> Path:
    safe_session = _safe_session_id(session_id)
    safe_rel = _safe_rel_path(rel_path)
    session_root = (BASE_EXPORT_DIR / safe_session).resolve()
    target = (session_root / safe_rel).resolve()
    if session_root != target and session_root not in target.parents:
        raise HTTPException(status_code=400, detail="Path traversal detected")
    return target


def _check_auth(request: Request) -> None:
    if not ARTIFACTS_TOKEN:
        return
    header = request.headers.get("authorization") or request.headers.get("x-artifact-token")
    if not header:
        raise HTTPException(status_code=401, detail="Missing auth token")
    token = header
    if header.lower().startswith("bearer "):
        token = header[7:]
    if token.strip() != ARTIFACTS_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid auth token")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/artifacts/{session_id}/{artifact_path:path}")
async def get_artifact(session_id: str, artifact_path: str, request: Request) -> FileResponse:
    _check_auth(request)
    target = _resolve_target(session_id, artifact_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(target)


@app.post("/artifacts/{session_id}/{artifact_path:path}")
async def upload_artifact(
    session_id: str,
    artifact_path: str,
    request: Request,
    upload: bool = Query(False, description="Must be true to allow uploads"),
) -> JSONResponse:
    _check_auth(request)
    if not upload:
        raise HTTPException(status_code=400, detail="upload=true query param required")

    target = _resolve_target(session_id, artifact_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        content_type = (request.headers.get("content-type") or "").lower()
        if content_type.startswith("multipart/form-data"):
            form = await request.form()
            file_part = None
            for value in form.values():
                if hasattr(value, "filename") and hasattr(value, "file"):
                    file_part = value
                    break
            if file_part is not None:
                with target.open("wb") as f:
                    while True:
                        chunk = await file_part.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
            else:
                text_part = None
                for value in form.values():
                    if isinstance(value, str):
                        text_part = value
                        break
                if text_part is None:
                    raise HTTPException(status_code=400, detail="No multipart file payload found")
                with target.open("wb") as f:
                    f.write(text_part.encode("utf-8"))
        else:
            with target.open("wb") as f:
                async for chunk in request.stream():
                    if chunk:
                        f.write(chunk)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write artifact: {exc}") from exc

    rel_path = target.relative_to(BASE_EXPORT_DIR).as_posix()
    payload = {
        "ok": True,
        "artifact": {
            "name": target.name,
            "path": rel_path,
            "url": f"/artifacts/{rel_path}",
            "content_type": request.headers.get("content-type"),
            "size_bytes": target.stat().st_size,
        },
    }
    return JSONResponse(status_code=200, content=payload)


if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required") from exc

    host = os.getenv("ARTIFACT_STORE_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("ARTIFACT_STORE_PORT", "3336")))
    uvicorn.run(app, host=host, port=port)
