"""SPEC-002: the X-Gateway-Assertion HMAC that tells a service a request came through the gateway.

The gateway holds a master key and derives one key per system, so a service only ever holds the key
for itself. This module is the reference both sides follow; services copy `verify` (cells own their
code) rather than importing it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

HEADER = "X-Gateway-Assertion"
VERSION = "v1"
MAX_SKEW_SECONDS = 60
# v1.<iat>.<base64url request id>.<base64url MAC>: the gateway request id may contain "." and ":".
_HEADER_RE = re.compile(r"v1\.([0-9]{1,12})\.([A-Za-z0-9_-]{1,180})\.([A-Za-z0-9_-]{43})")


def system_key(master: bytes, system: str) -> bytes:
    return hmac.new(master, f"gateway-assertion/v1/{system}".encode(), hashlib.sha256).digest()


def _sha(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8", "surrogateescape")
    return hashlib.sha256(data).hexdigest()


def _signed_text(system: str, method: str, target: str, iat: int, request_id: str, authorization: str,
                 content_type: str, body: bytes) -> bytes:
    fields = ("gw1", system, method.upper(), target, str(iat), request_id, _sha(authorization), _sha(content_type),
              _sha(body))
    return "\n".join(fields).encode("utf-8", "surrogateescape")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(key: bytes, system: str, method: str, target: str, iat: int, request_id: str, authorization: str,
         content_type: str = "", body: bytes = b"") -> str:
    text = _signed_text(system, method, target, iat, request_id, authorization, content_type, body)
    mac = hmac.new(key, text, hashlib.sha256)
    return f"{VERSION}.{iat}.{_b64(request_id.encode())}.{_b64(mac.digest())}"


def verify(key: bytes, system: str, header: str | None, method: str, target: str, authorization: str,
           now: float, content_type: str = "", body: bytes = b"") -> str:
    """'valid', 'missing' or 'invalid' (malformed, stale or a wrong MAC)."""
    if not header:
        return "missing"
    found = _HEADER_RE.fullmatch(header.strip())
    if not found:
        return "invalid"
    iat = int(found[1])
    try:
        request_id = base64.urlsafe_b64decode(found[2] + "=" * (-len(found[2]) % 4)).decode()
    except (ValueError, UnicodeDecodeError):
        return "invalid"
    if abs(now - iat) > MAX_SKEW_SECONDS:
        return "invalid"
    expected = sign(key, system, method, target, iat, request_id, authorization, content_type, body)
    return "valid" if hmac.compare_digest(expected.encode(), header.strip().encode()) else "invalid"


def parse_master(value: str) -> bytes | None:
    """64+ hex characters (32+ bytes); None when unset; ValueError when set but unusable."""
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}){32,}", value):  # fromhex would skip inner whitespace
        raise ValueError("GATEWAY_ASSERTION_MASTER_KEY must be 64+ hex characters")
    return bytes.fromhex(value)
