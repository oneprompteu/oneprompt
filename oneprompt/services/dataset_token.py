"""
Dataset token helpers for agent->MCP credential forwarding.

When a shared secret is configured, the Data Agent can send an encrypted
dataset token instead of forwarding the DSN in clear text headers.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any, Optional


class DatasetTokenError(ValueError):
    """Raised when dataset token creation or validation fails."""


def _token_secret() -> str:
    """Return dataset token secret from env (empty when disabled)."""
    return (
        os.getenv("DATASET_TOKEN_SECRET")
        or os.getenv("MCP_AUTH_TOKEN")
        or os.getenv("MCP_SHARED_TOKEN")
        or ""
    ).strip()


def dataset_token_enabled() -> bool:
    """Whether encrypted dataset tokens are enabled."""
    return bool(_token_secret())


def _fernet_for_secret(secret: str):
    """Build a Fernet instance derived from a raw secret."""
    if not secret:
        raise DatasetTokenError(
            "Dataset token secret is not configured. Set DATASET_TOKEN_SECRET (or MCP_AUTH_TOKEN)."
        )
    try:
        from cryptography.fernet import Fernet
    except Exception as exc:  # pragma: no cover - import errors are environment-specific
        raise DatasetTokenError(
            "cryptography is required for encrypted dataset tokens. Install 'cryptography>=42'."
        ) from exc

    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _safe_positive_int(value: int, *, default: int, minimum: int, maximum: int) -> int:
    try:
        num = int(value)
    except Exception:
        return default
    return max(minimum, min(num, maximum))


def create_dataset_token(
    dsn: str,
    *,
    audience: str = "postgres-mcp",
    ttl_seconds: int = 900,
    dataset_id: Optional[str] = None,
    dataset_name: Optional[str] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """
    Create an encrypted dataset token containing DSN + scoped claims.

    Args:
        dsn: PostgreSQL DSN.
        audience: Target service audience.
        ttl_seconds: Token TTL in seconds.
        dataset_id: Optional dataset identifier.
        dataset_name: Optional dataset name.
        session_id: Optional session scope.
        run_id: Optional run scope.

    Returns:
        Encrypted token string.
    """
    dsn_value = (dsn or "").strip()
    if not dsn_value:
        raise DatasetTokenError("Cannot create dataset token: empty DSN.")

    secret = _token_secret()
    fernet = _fernet_for_secret(secret)

    now = int(time.time())
    ttl = _safe_positive_int(ttl_seconds, default=900, minimum=30, maximum=3600)
    payload: dict[str, Any] = {
        "dsn": dsn_value,
        "aud": audience,
        "iat": now,
        "exp": now + ttl,
    }
    if dataset_id:
        payload["dataset_id"] = str(dataset_id)
    if dataset_name:
        payload["dataset_name"] = str(dataset_name)
    if session_id:
        payload["sid"] = str(session_id)
    if run_id:
        payload["rid"] = str(run_id)

    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return fernet.encrypt(raw).decode("utf-8")


def parse_dataset_token(
    token: str,
    *,
    expected_audience: Optional[str] = None,
    expected_session_id: Optional[str] = None,
    expected_run_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Decrypt and validate a dataset token.

    Args:
        token: Encrypted token string.
        expected_audience: Optional expected audience claim.
        expected_session_id: Optional expected session scope.
        expected_run_id: Optional expected run scope.

    Returns:
        Decoded payload dict.
    """
    token_value = (token or "").strip()
    if not token_value:
        raise DatasetTokenError("Missing dataset token.")

    secret = _token_secret()
    fernet = _fernet_for_secret(secret)

    try:
        raw = fernet.decrypt(token_value.encode("utf-8"))
    except Exception as exc:
        raise DatasetTokenError("Invalid or expired dataset token.") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise DatasetTokenError("Malformed dataset token payload.") from exc

    if not isinstance(payload, dict):
        raise DatasetTokenError("Malformed dataset token payload.")

    dsn = payload.get("dsn")
    if not isinstance(dsn, str) or not dsn.strip():
        raise DatasetTokenError("Dataset token has no DSN.")

    if expected_audience and payload.get("aud") != expected_audience:
        raise DatasetTokenError("Dataset token audience mismatch.")

    if expected_session_id:
        sid = payload.get("sid")
        if sid and str(sid) != str(expected_session_id):
            raise DatasetTokenError("Dataset token session mismatch.")

    if expected_run_id:
        rid = payload.get("rid")
        if rid and str(rid) != str(expected_run_id):
            raise DatasetTokenError("Dataset token run mismatch.")

    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and int(time.time()) > int(exp):
        raise DatasetTokenError("Dataset token expired.")

    return payload
