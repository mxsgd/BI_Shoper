"""HMAC signature verification for Shoper App Store requests.

Algorithm (mirrors dreamcommerce/appstore-sf-mvc-example HashValidator):

1. Take all signed request parameters (decoded form/query values).
2. Remove the ``hash`` field.
3. Sort parameters alphabetically by key (byte-wise, like PHP ksort).
4. Build the canonical string ``key=value&key=value`` (values as received,
   no extra encoding or normalization).
5. Compute HMAC-SHA512 (hex) with the App Store secret.
6. Compare with ``hmac.compare_digest``.
"""

from __future__ import annotations

import hmac
import hashlib
import time
from typing import Mapping


class ShoperSignatureError(ValueError):
    """Base class for signature verification failures."""


class MissingSignatureError(ShoperSignatureError):
    """The request carries no ``hash`` parameter (or it is empty)."""


class InvalidSignatureError(ShoperSignatureError):
    """The provided ``hash`` does not match the computed HMAC."""


class MissingParameterError(ShoperSignatureError):
    """A required signed parameter is absent or empty."""


class StaleTimestampError(ShoperSignatureError):
    """The signed ``timestamp`` is outside the accepted time window."""


def canonical_string(params: Mapping[str, str]) -> str:
    filtered = {k: "" if v is None else str(v) for k, v in params.items() if k != "hash"}
    return "&".join(f"{key}={filtered[key]}" for key in sorted(filtered))


class ShoperSignatureValidator:
    def __init__(self, app_store_secret: str):
        secret = (app_store_secret or "").strip()
        if not secret:
            raise ValueError("App Store secret is not configured.")
        self._secret = secret.encode("utf-8")

    def compute(self, params: Mapping[str, str]) -> str:
        payload = canonical_string(params).encode("utf-8")
        return hmac.new(self._secret, payload, hashlib.sha512).hexdigest()

    def verify(
        self,
        params: Mapping[str, str],
        *,
        required: tuple[str, ...] = ("shop",),
    ) -> None:
        """Verify the signature; raises a subclass of ShoperSignatureError."""
        provided = params.get("hash")
        if provided is None or not str(provided).strip():
            raise MissingSignatureError("Missing authentication credentials.")

        for field in required:
            value = params.get(field)
            if value is None or not str(value).strip():
                raise MissingParameterError(f"Missing required parameter: {field}")

        expected = self.compute(params)
        if not hmac.compare_digest(expected, str(provided)):
            raise InvalidSignatureError("Invalid hash comparison")

    def verify_with_timestamp(
        self,
        params: Mapping[str, str],
        *,
        required: tuple[str, ...] = ("shop", "timestamp"),
        max_age_seconds: int = 300,
        now: float | None = None,
    ) -> None:
        """Signature verification + freshness check of the signed timestamp."""
        self.verify(params, required=required)

        raw_ts = str(params.get("timestamp", "")).strip()
        try:
            ts = float(raw_ts)
        except ValueError as exc:
            raise StaleTimestampError("timestamp is not a valid number") from exc

        current = time.time() if now is None else now
        # Reject both stale requests and timestamps too far in the future
        # (small clock skew is covered by the window itself).
        if abs(current - ts) > max_age_seconds:
            raise StaleTimestampError("timestamp outside the accepted window")

    def __repr__(self) -> str:  # never leak the secret
        return "<ShoperSignatureValidator>"
