"""
ThinkingProducts local API server.

Simplified FastAPI application for local/self-hosted use.
No multi-tenant auth, no Firestore — just configure and go.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from thinkingproducts.agents.context import AgentContext
from thinkingproducts.agents import data_agent, python_agent, chart_agent
from thinkingproducts.services.artifact_client import ArtifactStoreClient
from thinkingproducts.services.state_store import StateStore

import logging

logger = logging.getLogger("thinkingproducts")

EXPORT_DIR = Path(
    os.getenv("EXPORT_DIR", Path(__file__).resolve().parents[2] / "tp_data" / "exports")
).resolve()

store = StateStore()

app = FastAPI(
    title="ThinkingProducts API",
    version="1.0.0",
    description="AI agents API for data querying, Python analysis, and chart generation.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Models ----

class CreateSessionRequest(BaseModel):
    name: Optional[str] = None


class SessionInfo(BaseModel):
    session_id: str
    name: Optional[str] = None
    created_at: str
    status: str


class DataAgentRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class PythonAgentRequest(BaseModel):
    instruction: str
    session_id: Optional[str] = None
    data_artifact_id: Optional[str] = None
    output_name: Optional[str] = None


class ChartAgentRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    data_artifact_id: Optional[str] = None
    data_preview: Optional[str] = None


class AgentRunResponse(BaseModel):
    run_id: str
    session_id: str
    ok: bool
    summary: Optional[str] = None
    artifacts: List[Dict[str, Any]]
    result: Dict[str, Any]


# ---- Helpers ----

USER_ID = "local_user"


def _artifact_store_settings() -> tuple[str, Optional[str]]:
    base_url = os.getenv("ARTIFACT_STORE_URL", "http://localhost:3336")
    token = os.getenv("ARTIFACT_STORE_TOKEN")
    return base_url, token


def _build_context(session_id: str, run_id: str) -> AgentContext:
    base_url, token = _artifact_store_settings()
    client = ArtifactStoreClient(
        base_url=base_url, token=token, session_id=session_id, run_id=run_id,
    )
    return AgentContext(session_id=session_id, run_id=run_id, artifact_store=client)


def _get_default_session() -> str:
    session_id = f"default_{USER_ID}"
    session = store.get_session(session_id)
    if not session:
        store.create_session(session_id, USER_ID, name="Default Session")
    return session_id


def _resolve_session_id(requested: Optional[str]) -> str:
    if requested:
        session = store.get_session(requested)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return requested
    return _get_default_session()


def _register_artifacts(
    run_id: str, session_id: str, payload: Dict[str, Any], default_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    raw_artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    candidates: List[Dict[str, Any]] = []
    if isinstance(raw_artifacts, list):
        candidates.extend([a for a in raw_artifacts if isinstance(a, dict)])
    for key in ("file_path", "csv_path"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if value:
            candidates.append({"name": Path(value).name, "file_path": value})

    seen_paths: set[str] = set()
    registered: List[Dict[str, Any]] = []

    for item in candidates:
        store_path = item.get("path")
        if not store_path:
            url = item.get("url", "")
            if "/artifacts/" in url:
                tail = url.split("/artifacts/", 1)[1].lstrip("/")
                if tail.startswith(f"{session_id}/"):
                    store_path = tail[len(session_id) + 1:]
                else:
                    store_path = tail

        if not store_path or store_path in seen_paths:
            continue
        seen_paths.add(store_path)
        store_path = store_path.lstrip("/")
        if store_path.startswith(f"{session_id}/"):
            store_path = store_path[len(session_id) + 1:]

        name = item.get("name") or Path(store_path).name
        artifact_type = item.get("type") or default_type
        artifact_id = uuid.uuid4().hex

        store.add_artifact(
            artifact_id=artifact_id, run_id=run_id, session_id=session_id,
            name=name, store_path=store_path, artifact_type=artifact_type,
        )
        registered.append({
            "id": artifact_id, "type": artifact_type,
            "name": name, "url": f"/runs/{run_id}/artifacts/{artifact_id}",
        })
    return registered


# ---- Endpoints ----

@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/sessions", response_model=SessionInfo)
async def create_session(payload: CreateSessionRequest) -> SessionInfo:
    session_id = uuid.uuid4().hex
    record = store.create_session(session_id, USER_ID, name=payload.name)
    return SessionInfo(
        session_id=record["session_id"], name=record.get("name"),
        created_at=record["created_at"], status=record["status"],
    )


@app.get("/sessions")
async def list_sessions():
    sessions = store.list_user_sessions(USER_ID)
    return {"sessions": [
        SessionInfo(
            session_id=s["session_id"], name=s.get("name"),
            created_at=s["created_at"], status=s["status"],
        ) for s in sessions
    ]}


@app.post("/agents/data", response_model=AgentRunResponse)
async def run_data_agent(payload: DataAgentRequest) -> AgentRunResponse:
    """Query your database using natural language."""
    session_id = _resolve_session_id(payload.session_id)
    run_id = uuid.uuid4().hex
    store.create_run(run_id, session_id)
    context = _build_context(session_id, run_id)

    dataset_config = {
        "dsn": os.getenv("DATABASE_URL", os.getenv("POSTGRES_DSN", "")),
        "schema_docs": os.getenv("TP_SCHEMA_DOCS", ""),
        "name": "default",
        "id": "default",
    }

    try:
        result_json = await data_agent.run(payload.query, context, dataset_config=dataset_config)
        data = json.loads(result_json)
        artifacts = _register_artifacts(run_id, session_id, data, default_type="data")
        store.update_run_status(run_id, "completed")
        result_clean = {k: v for k, v in data.items() if k not in ("file_path", "csv_path", "artifacts")}
        return AgentRunResponse(
            run_id=run_id, session_id=session_id, ok=bool(data.get("ok", True)),
            summary=data.get("summary"), artifacts=artifacts, result=result_clean,
        )
    except Exception as exc:
        store.update_run_status(run_id, "failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/agents/python", response_model=AgentRunResponse)
async def run_python_agent(payload: PythonAgentRequest) -> AgentRunResponse:
    """Run Python data analysis."""
    session_id = _resolve_session_id(payload.session_id)
    run_id = uuid.uuid4().hex
    store.create_run(run_id, session_id)
    context = _build_context(session_id, run_id)

    data_path = None
    if payload.data_artifact_id:
        artifact = store.get_artifact(payload.data_artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Data artifact not found")
        data_path = artifact.get("store_path")

    try:
        output_name = payload.output_name or "result.csv"
        result_json = await python_agent.run(
            payload.instruction, context, data_path=data_path, output_name=output_name,
        )
        data = json.loads(result_json)
        if isinstance(data, dict) and not data.get("artifacts"):
            expected_path = context.artifact_store.build_artifact_path(
                artifact_type="results", filename=output_name,
            )
            data["artifacts"] = [{"type": "result", "name": output_name, "path": expected_path}]
        artifacts = _register_artifacts(run_id, session_id, data, default_type="result")
        store.update_run_status(run_id, "completed")
        result_clean = {k: v for k, v in data.items() if k not in ("file_path", "csv_path", "artifacts")}
        return AgentRunResponse(
            run_id=run_id, session_id=session_id, ok=bool(data.get("ok", True)),
            summary=data.get("summary"), artifacts=artifacts, result=result_clean,
        )
    except Exception as exc:
        store.update_run_status(run_id, "failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/agents/chart", response_model=AgentRunResponse)
async def run_chart_agent(payload: ChartAgentRequest) -> AgentRunResponse:
    """Generate chart visualizations."""
    session_id = _resolve_session_id(payload.session_id)
    run_id = uuid.uuid4().hex
    store.create_run(run_id, session_id)
    context = _build_context(session_id, run_id)

    data_url = None
    if payload.data_artifact_id:
        artifact = store.get_artifact(payload.data_artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Data artifact not found")
        data_url = context.artifact_store.build_url(artifact.get("store_path"))

    question = payload.question.strip()
    if payload.data_preview:
        question += f"\npreview:\n{payload.data_preview}"

    try:
        result_json = await chart_agent.run(question, context, data_url=data_url)
        data = json.loads(result_json)
        artifacts = _register_artifacts(run_id, session_id, data, default_type="chart")
        store.update_run_status(run_id, "completed")
        result_clean = {k: v for k, v in data.items() if k not in ("file_path", "csv_path", "artifacts")}
        return AgentRunResponse(
            run_id=run_id, session_id=session_id, ok=bool(data.get("ok", True)),
            summary=data.get("summary"), artifacts=artifacts, result=result_clean,
        )
    except Exception as exc:
        store.update_run_status(run_id, "failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/runs/{run_id}/artifacts/{artifact_id}")
async def get_artifact(run_id: str, artifact_id: str) -> StreamingResponse:
    """Download an artifact by ID."""
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    artifact = store.get_artifact(artifact_id)
    if not artifact or artifact.get("run_id") != run_id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    base_url, token = _artifact_store_settings()
    session_id = run.get("session_id")
    artifact_path = artifact.get("store_path")
    if not artifact_path:
        raise HTTPException(status_code=404, detail="Artifact path missing")

    url = f"{base_url.rstrip('/')}/artifacts/{session_id}/{artifact_path.lstrip('/')}"
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code >= 400:
                raise HTTPException(status_code=resp.status_code, detail="Artifact store error")
            return StreamingResponse(
                resp.aiter_bytes(),
                media_type=resp.headers.get("content-type", "application/octet-stream"),
            )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("TP_HOST", "0.0.0.0")
    port = int(os.getenv("TP_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
