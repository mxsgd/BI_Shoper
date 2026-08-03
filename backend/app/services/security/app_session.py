"""Short-lived app sessions issued after successful iframe verification.

Compact HMAC-SHA256 signed token: base64url(json payload) + "." + signature.
The payload carries only the local store_id, the Shoper shop id and an
expiry. It never contains Shoper API tokens.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


class AppSessionError(ValueError):
    """Session token missing, malformed, tampered with or expired."""


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload_b64: str, secret: str) -> str:
    return _b64e(
        hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    )


def create_session_token(
    *,
    store_id: int,
    shop_id: str,
    secret: str,
    ttl_seconds: int,
    now: float | None = None,
) -> str:
    issued = time.time() if now is None else now
    payload = {"store_id": store_id, "shop": shop_id, "exp": int(issued + ttl_seconds)}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def verify_session_token(token: str, *, secret: str, now: float | None = None) -> dict:
    """Verify and decode; returns the payload dict or raises AppSessionError."""
    token = (token or "").strip()
    if not token or "." not in token:
        raise AppSessionError("Missing or malformed session token")

    payload_b64, _, signature = token.rpartition(".")
    expected = _sign(payload_b64, secret)
    if not hmac.compare_digest(expected, signature):
        raise AppSessionError("Invalid session signature")

    try:
        payload = json.loads(_b64d(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AppSessionError("Malformed session payload") from exc
    if not isinstance(payload, dict):
        raise AppSessionError("Malformed session payload")

    current = time.time() if now is None else now
    if int(payload.get("exp", 0)) < current:
        raise AppSessionError("Session expired")
    if not isinstance(payload.get("store_id"), int):
        raise AppSessionError("Malformed session payload")
    return payload
