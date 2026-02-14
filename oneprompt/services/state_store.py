"""
State Store — SQLite-based session, run, and artifact management.

Provides local state management for the SDK. The SaaS layer extends this
with Firestore backends for production multi-tenant use.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class StateStore:
    """
    SQLite-based state store for local development and SDK usage.

    Usage:
        store = StateStore()  # Uses default path
        store = StateStore(db_path="./custom.db")
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        path = db_path or os.getenv("STATE_DB_PATH") or "./op_data/state.db"
        self.db_path = Path(path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            cursor = conn.execute("PRAGMA table_info(sessions)")
            columns = [row[1] for row in cursor.fetchall()]
            if "user_id" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT DEFAULT ''")
            if "name" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN name TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)"
            )
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    type TEXT,
                    store_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                )
            """)

    # ---- Sessions ----

    def create_session(
        self, session_id: str, user_id: str, name: Optional[str] = None
    ) -> Dict[str, Any]:
        record = {
            "session_id": session_id,
            "user_id": user_id,
            "name": name,
            "created_at": _utcnow_iso(),
            "status": "active",
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, name, created_at, status) VALUES (?, ?, ?, ?, ?)",
                (record["session_id"], record["user_id"], record["name"], record["created_at"], record["status"]),
            )
        return record

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id, user_id, name, created_at, status FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_user_sessions(self, user_id: str) -> Iterable[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT session_id, user_id, name, created_at, status FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM artifacts WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM runs WHERE session_id = ?", (session_id,))
            cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cursor.rowcount > 0

    def update_session_status(self, session_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE sessions SET status = ? WHERE session_id = ?", (status, session_id))

    # ---- Runs ----

    def create_run(self, run_id: str, session_id: str) -> Dict[str, Any]:
        record = {
            "run_id": run_id,
            "session_id": session_id,
            "created_at": _utcnow_iso(),
            "status": "running",
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (run_id, session_id, created_at, status) VALUES (?, ?, ?, ?)",
                (record["run_id"], record["session_id"], record["created_at"], record["status"]),
            )
        return record

    def update_run_status(self, run_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id, session_id, created_at, status FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    # ---- Artifacts ----

    def add_artifact(
        self,
        artifact_id: str,
        run_id: str,
        session_id: str,
        name: str,
        store_path: str,
        artifact_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = {
            "artifact_id": artifact_id,
            "run_id": run_id,
            "session_id": session_id,
            "name": name,
            "type": artifact_type,
            "store_path": store_path,
            "created_at": _utcnow_iso(),
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts (artifact_id, run_id, session_id, name, type, store_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (record["artifact_id"], record["run_id"], record["session_id"], record["name"], record["type"], record["store_path"], record["created_at"]),
            )
        return record

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT artifact_id, run_id, session_id, name, type, store_path, created_at FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_run_artifacts(self, run_id: str) -> Iterable[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT artifact_id, run_id, session_id, name, type, store_path, created_at FROM artifacts WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]
