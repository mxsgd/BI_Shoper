"""Validation of shop URLs received from Shoper lifecycle events.

The shop_url is later used to build REST API request URLs, so it must be
treated as untrusted input (SSRF risk). Shoper allows custom shop domains,
so we do not enforce a domain allowlist; instead we reject everything that
cannot be a legitimate public shop address.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


class ShopUrlValidationError(ValueError):
    """Raised when a shop_url is not acceptable."""


_ALLOWED_PORTS_HTTPS = {None, 443}
_ALLOWED_PORTS_HTTP = {None, 80}
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def validate_shop_url(raw_url: str, *, allow_insecure: bool = False) -> str:
    """Validate and normalize a shop base URL.

    Returns the normalized origin (scheme://host[:port]) without path,
    query, fragment or userinfo. Raises ShopUrlValidationError otherwise.
    """
    raw_url = (raw_url or "").strip()
    if not raw_url:
        raise ShopUrlValidationError("shop_url is empty")

    try:
        parts = urlsplit(raw_url)
    except ValueError as exc:
        raise ShopUrlValidationError("shop_url cannot be parsed") from exc

    if parts.scheme == "https":
        allowed_ports = _ALLOWED_PORTS_HTTPS
    elif parts.scheme == "http" and allow_insecure:
        allowed_ports = _ALLOWED_PORTS_HTTP
    else:
        raise ShopUrlValidationError(f"shop_url scheme '{parts.scheme or '(none)'}' is not allowed")

    if parts.username is not None or parts.password is not None:
        raise ShopUrlValidationError("shop_url must not contain userinfo")

    hostname = parts.hostname
    if not hostname:
        raise ShopUrlValidationError("shop_url has no hostname")

    try:
        port = parts.port  # raises ValueError on out-of-range port
    except ValueError as exc:
        raise ShopUrlValidationError("shop_url port is invalid") from exc
    if port not in allowed_ports:
        raise ShopUrlValidationError(f"shop_url port {port} is not allowed")

    lowered = hostname.lower().rstrip(".")
    if lowered in _BLOCKED_HOSTNAMES:
        raise ShopUrlValidationError("shop_url host is not allowed")

    # Reject IP literals pointing at loopback / private / link-local ranges.
    # Public IP literals are also rejected: real shops use domain names.
    try:
        ipaddress.ip_address(lowered)
    except ValueError:
        pass  # hostname is a domain name - OK
    else:
        raise ShopUrlValidationError("shop_url must use a domain name, not an IP address")

    if "." not in lowered:
        raise ShopUrlValidationError("shop_url host must be a fully qualified domain")

    netloc = lowered if port is None else f"{lowered}:{port}"
    return f"{parts.scheme}://{netloc}"


def rest_api_base(shop_url: str) -> str:
    """REST API base for a validated shop origin."""
    return f"{shop_url.rstrip('/')}/webapi/rest"
