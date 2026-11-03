"""`/v1/<system>/…`: edge lock, token check, limits and a faithful proxy (SPEC-001)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from http.client import HTTPException
from typing import TYPE_CHECKING, Any
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request

from .config import ConfigError
from .jwt_verify import IssuerKeys, KeysUnavailable, TokenError, TokenVerifier
from .limiter import FixedWindowRateLimiter
from .routes import Route, load_routes, match

if TYPE_CHECKING:
    from .server import GatewayRequestHandler

EDGE_HEADER = "X-Gateway-Edge"
METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"})
FORWARD_REQUEST = ("Authorization", "Accept", "Content-Type", "If-Match", "If-None-Match", "Idempotency-Key")
FORWARD_RESPONSE = ("ETag", "Retry-After", "WWW-Authenticate")
MAX_QUERY_CHARS = 2048
CONTENT_LENGTH_RE = re.compile(r"[0-9]{1,19}")
IP_RE = re.compile(r"[0-9a-fA-F:.]{2,45}")


@dataclass
class EdgeSettings:
    routes: dict[str, Route]
    verifier: TokenVerifier
    edge_secret: str
    subject_limit_per_minute: int = 120
    failure_limit_per_minute: int = 10
    upstream_timeout_seconds: float = 30.0
    subject_limiter: FixedWindowRateLimiter = field(init=False)
    failure_limiter: FixedWindowRateLimiter = field(init=False)

    def __post_init__(self) -> None:
        self.subject_limiter = FixedWindowRateLimiter(self.subject_limit_per_minute)
        self.failure_limiter = FixedWindowRateLimiter(self.failure_limit_per_minute)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> EdgeSettings | None:
        """None when GATEWAY_TRUSTED_ISSUERS is unset (pilot-only process)."""
        env = dict(os.environ if env is None else env)
        raw = env.get("GATEWAY_TRUSTED_ISSUERS", "").strip()
        if not raw:
            return None
        try:
            issuers = json.loads(raw)
        except ValueError as exc:
            raise ConfigError("GATEWAY_TRUSTED_ISSUERS must be a JSON object issuer -> JWKS URL") from exc
        if not isinstance(issuers, dict) or not issuers:
            raise ConfigError("GATEWAY_TRUSTED_ISSUERS must be a non-empty JSON object")
        for issuer, url in issuers.items():
            if not isinstance(url, str) or urlsplit(url).scheme != "https" or not issuer:
                raise ConfigError("every trusted issuer needs an https JWKS URL")
        secret = env.get("GATEWAY_EDGE_SECRET", "")
        if len(secret) < 32:
            raise ConfigError("GATEWAY_EDGE_SECRET must be set (32+ characters) when the edge is enabled")
        routes_path = env.get("GATEWAY_ROUTES")
        try:
            routes = load_routes(**({"path": __import__("pathlib").Path(routes_path)} if routes_path else {}))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        verifier = TokenVerifier({iss: IssuerKeys(url) for iss, url in issuers.items()})
        return cls(
            routes=routes,
            verifier=verifier,
            edge_secret=secret,
            subject_limit_per_minute=_positive_int(env, "GATEWAY_SUBJECT_LIMIT_PER_MINUTE", 120),
            failure_limit_per_minute=_positive_int(env, "GATEWAY_FAILURE_LIMIT_PER_MINUTE", 10),
            upstream_timeout_seconds=float(_positive_int(env, "GATEWAY_UPSTREAM_TIMEOUT_SECONDS", 30)),
        )


def _positive_int(env: dict[str, str], name: str, default: int) -> int:
    try:
        value = int(env.get(name, str(default)))
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero")
    return value


def unsafe_path(path: str) -> bool:
    """Dot segments, backslashes, encoded slashes or control characters could escape the route."""
    lowered = path.casefold()
    if "\\" in path or "%5c" in lowered or "%2f" in lowered:
        return True
    decoded = unquote(path)
    if "\\" in decoded or any(ord(c) < 0x20 or ord(c) == 0x7F for c in decoded):
        return True
    return any(segment in {".", ".."} for segment in decoded.split("/")[1:])


def _clean(value: str | None, limit: int = 512) -> str | None:
    if value is None or len(value) > limit or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        return None
    return value


def _rewrite_location(location: str, route: Route, request_url: str) -> str | None:
    """Resolve the redirect against the upstream request (relative forms included); keep it only on-route."""
    absolute = urljoin(request_url, location)
    if absolute != route.base_url and not absolute.startswith(route.base_url + "/"):
        return None  # another host: never pass a redirect off-route
    rest = absolute[len(route.base_url):] or "/"
    return f"/v1/{route.system}{rest}"


def handle_v1(h: GatewayRequestHandler, edge: EdgeSettings, request_id: str, path: str, query: str) -> int:
    if not hmac.compare_digest(h.headers.get(EDGE_HEADER, "").encode(), edge.edge_secret.encode()):
        return h._error(403, "direct access not allowed", request_id)
    if h.command not in METHODS:
        return h._error(405, "method not allowed", request_id, extra_headers={"Allow": ", ".join(sorted(METHODS))})
    if unsafe_path(path) or len(query) > MAX_QUERY_CHARS or _clean(query, MAX_QUERY_CHARS) is None:
        return h._error(400, "invalid request path", request_id)
    found = match(edge.routes, path)
    if found is None:
        return h._error(404, "route not found", request_id)
    route, rest = found
    h._system = route.system

    peer = h.client_address[0]
    forwarded = h.headers.get("CF-Connecting-IP", "").strip()
    client = forwarded if IP_RE.fullmatch(forwarded) else str(peer)
    failure_key = "ip:" + client
    locked_for = edge.failure_limiter.is_blocked(failure_key)
    if locked_for:
        return h._error(429, "too many failed authentication attempts", request_id,
                        extra_headers={"Retry-After": str(locked_for)})

    scheme, _, token = h.headers.get("Authorization", "").partition(" ")
    try:
        if scheme.casefold() != "bearer" or not token:
            raise TokenError("missing token")
        principal = edge.verifier.verify(token.strip())
    except KeysUnavailable:
        return h._error(503, "token verification unavailable", request_id)
    except TokenError:
        edge.failure_limiter.allow(failure_key)
        return h._error(401, "authentication required", request_id, extra_headers={"WWW-Authenticate": "Bearer"})
    subject = hashlib.sha256(f"{principal.issuer}\n{principal.subject}".encode()).hexdigest()[:16]
    h._subject_hash = subject
    allowed, retry_after = edge.subject_limiter.allow(subject)
    if not allowed:
        return h._error(429, "rate limit exceeded", request_id, extra_headers={"Retry-After": str(retry_after)})

    body = _read_body(h, request_id)
    if body is None:
        return h._last_status
    return _proxy(h, edge, route, rest + (f"?{query}" if query else ""), body, request_id)


def _read_body(h: GatewayRequestHandler, request_id: str) -> bytes | None:
    if h.headers.get("Transfer-Encoding") is not None:
        h._error(411, "chunked request bodies are not supported", request_id)
        return None
    lengths = {v.strip() for v in h.headers.get_all("Content-Length", [])}
    raw = lengths.pop() if len(lengths) == 1 else "0" if not lengths else ""
    if not CONTENT_LENGTH_RE.fullmatch(raw):
        h._error(400, "invalid content length", request_id)
        return None
    length = int(raw)
    if length > h.state.config.max_body_bytes:
        h._error(413, "request body too large", request_id)
        return None
    body = h.rfile.read(length) if length else b""
    h._body_consumed = True
    if len(body) != length:
        h._error(400, "incomplete request body", request_id)
        return None
    return body


def _proxy(h: GatewayRequestHandler, edge: EdgeSettings, route: Route, target: str, body: bytes,
           request_id: str) -> int:
    headers = {name: v for name in FORWARD_REQUEST if (v := _clean(h.headers.get(name), 8192)) is not None}
    headers["X-Request-ID"] = request_id
    request = Request(route.base_url + target, data=body if body or h.command in {"POST", "PUT", "PATCH"} else None,
                      headers=headers, method=h.command)
    limit = h.state.config.max_body_bytes
    try:
        response: Any = h.state.opener.open(request, timeout=edge.upstream_timeout_seconds)
    except HTTPError as exc:
        response = exc  # 3xx/4xx/5xx: the upstream's answer, passed through
    except (TimeoutError, URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError):
            return h._error(504, "upstream timeout", request_id)
        return h._error(502, "upstream unavailable", request_id)
    try:
        payload = response.read(limit + 1)
        status = int(response.getcode() if hasattr(response, "getcode") else response.code)
        upstream_headers = response.headers
    except (TimeoutError, OSError):
        return h._error(504, "upstream timeout", request_id)
    except HTTPException:  # IncompleteRead and friends: a cut-off answer is not an answer
        return h._error(502, "upstream response incomplete", request_id)
    finally:
        response.close()
    if len(payload) > limit:
        return h._error(502, "upstream response too large", request_id)
    declared = (upstream_headers.get("Content-Length") or "").strip()
    if h.command != "HEAD" and CONTENT_LENGTH_RE.fullmatch(declared) and int(declared) != len(payload):
        return h._error(502, "upstream response incomplete", request_id)
    extra = {name: v for name in FORWARD_RESPONSE if (v := _clean(upstream_headers.get(name))) is not None}
    location = _clean(upstream_headers.get("Location"), 2048)
    if location and (rewritten := _rewrite_location(location, route, route.base_url + target)):
        extra["Location"] = rewritten
    content_type = _clean(upstream_headers.get("Content-Type"), 200) or "application/octet-stream"
    head_length = None
    if h.command == "HEAD":  # no body to measure: report the upstream's length, as a GET would
        declared = upstream_headers.get("Content-Length", "")
        head_length = int(declared) if CONTENT_LENGTH_RE.fullmatch(declared.strip()) else None
    return h._send_bytes(status, payload, request_id, content_type=content_type, extra_headers=extra,
                         content_length=head_length)
