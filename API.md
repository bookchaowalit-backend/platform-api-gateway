# API Surface

Contract: `book-api-gateway.v1` (REST over HTTP, JSON errors). The
machine-readable interface list is `interfaces` in [`contract.json`](contract.json);
`scripts/check.py` fails when an interface listed there is missing from this page.

| ID | Method | Path | Authentication | Downstream behavior |
|---|---|---|---|---|
| `api-gateway.http.healthz` | `GET` | `/healthz` | Public | No upstream call; reports process health |
| `api-gateway.http.readyz` | `GET` | `/readyz` | Public | TCP connect to the upstream (no HTTP request); 503 when not ready |
| `api-gateway.http.proxy` | `GET`, `POST` | `/api/*` | `Authorization: Bearer <configured token>` | Proxies to the configured, allow-listed upstream |
| `api-gateway.http.edge` | `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE` | `/v1/<system>/*` | `X-Gateway-Edge` (added by Cloudflare) and `Authorization: Bearer <RS256 token>` from a trusted issuer | Proxies to the system's registry URL from `routes.json`; the token is forwarded for the service's own audience and scope checks |

`/healthz` is liveness only and always returns 200 with
`{"contract": "book-api-gateway.v1", "status": "ok", "auth_configured": <bool>}`.
`/readyz` adds `"upstream_reachable": <bool>` and returns 200 with
`"status": "ok"` only when a gateway token is configured and a TCP connection
to the upstream host and port succeeds within `min(UPSTREAM_TIMEOUT_SECONDS, 1)`
seconds; otherwise 503 with `"status": "not_ready"`. The upstream address is
never included. Other methods on these routes return 405.

The gateway does not own domain objects or make object-level authorization
decisions. The downstream platform remains responsible for tenant, role and
resource authorization. The pilot token is a local compatibility credential;
the identity platform is the dependency for a production subject assertion
(`api-gateway.consumes.identity`, planned).

## Request handling

Every `/api/*` request receives a validated `X-Request-ID`. Failed bearer
tokens are counted per client IP (socket peer, `AUTH_FAILURE_LIMIT_PER_MINUTE`,
default 10); once a client exceeds that, every `/api/*` request from it gets 429
until the window resets, even with the right token, and nothing reaches the
upstream. Authenticated requests are then rate-limited per
authenticated subject (at most 10,000 tracked windows; expired then oldest
windows are evicted first), and forwards only `Accept`, `Content-Type`, conditional
request headers, `X-Request-ID` and a hashed subject marker
(`X-Authenticated-Subject`) to the upstream (`api-gateway.http.upstream`). The
original `Authorization` header is never forwarded. Query parameters are
rejected by the pilot, request and response bodies are capped at 1 MiB,
upstream redirects are disabled, and upstream calls time out after the
configured interval.

Ingress hardening:

- Paths with `.` or `..` segments (raw or percent-encoded) or backslashes are
  rejected with 400 so an upstream cannot normalise them outside `/api/`.
- `Transfer-Encoding` request bodies are rejected with 411; `Content-Length`
  must be a plain decimal, and conflicting duplicate values are rejected with
  400.
- When a response is sent before a declared request body was read (for example
  401, 413 or 429), the gateway replies with `Connection: close` so the unread
  bytes are never parsed as another request.
- The `Server` header is `book-api-gateway` and does not disclose the runtime
  version.

| Status | `error` | Cause |
|---|---|---|
| 400 | `invalid request path`, `invalid content length`, `incomplete request body`, `query parameters are not supported by the pilot` | Rejected request shape |
| 401 | `authentication required` | Missing or wrong bearer token (`WWW-Authenticate: Bearer`) |
| 404 | `route not found` | Outside `/healthz`, `/readyz`, `/api/*` |
| 405 | `method not allowed` | Method outside the route's `Allow` list |
| 411 | `chunked request bodies are not supported` | `Transfer-Encoding` present |
| 413 | `request body too large` | Body above `MAX_BODY_BYTES` |
| 429 | `rate limit exceeded` | Per-subject fixed window exhausted (`Retry-After`) |
| 429 | `too many failed authentication attempts` | Client IP exceeded `AUTH_FAILURE_LIMIT_PER_MINUTE` wrong tokens (`Retry-After`) |
| 502 | `upstream unavailable`, `upstream response too large` | Upstream error, redirect or oversize body; upstream bodies are not relayed |
| 503 | `gateway authentication unavailable` | No gateway token configured (fails closed) |
| 504 | `upstream timeout` | Upstream exceeded `UPSTREAM_TIMEOUT_SECONDS` |

Every error body is `{"error": "<message>", "request_id": "<id>"}`.

## Telemetry

`api-gateway.event.request-completed` is a redacted completion event containing
`event: "request.completed"`, method, route class (`healthz`, `readyz`, `api`,
`other`), request ID, status, latency and (for authenticated calls) a short
subject hash. It never contains authorization headers, request bodies, query
values or upstream response bodies.

## Edge routes (`/v1/`, SPEC-001)

Production ingress is `https://gateway.bookchaowalit.com`, proxied by Cloudflare. Zone rules for
this host only: a request-header Transform Rule sets `X-Gateway-Edge`; a Configuration Rule turns
Browser Integrity Check off (it answered 403 to API clients with default user agents such as
`Python-urllib`); one rate-limit rule (60 requests / 10 s per IP and colo). First consumer:
platform-posture-monitor's security-api audit calls (2026-11-03). The
`/v1/` route class exists only when `GATEWAY_TRUSTED_ISSUERS` is set; the full requirements
and acceptance criteria are in [docs/specs/001-edge-gateway.md](docs/specs/001-edge-gateway.md).

| Step | Rule | Answer when it fails |
|---|---|---|
| Edge lock | `X-Gateway-Edge` equals `GATEWAY_EDGE_SECRET` (constant-time) | 403 `direct access not allowed` |
| Path | no dot segments, backslashes, encoded slashes or control characters; query ≤ 2048 characters | 400 |
| Route | `<system>` is in `routes.json` (generated from the registry: online systems with an https URL, minus web frontends, `identity` and `ai-gateway`) | 404 |
| Client lock | failed tokens per client IP (`CF-Connecting-IP`, trusted only behind the edge lock), default 10/min | 429 |
| Token | RS256 (`kid`, or each published key when the token has none), trusted `iss` (`GATEWAY_TRUSTED_ISSUERS`: issuer → JWKS URL), valid signature, `exp`/`nbf`/`iat` within 60 s skew, `sub` and `aud` present | 401 (`WWW-Authenticate: Bearer`); 503 when no key of the issuer can be loaded |
| Subject limit | per `iss`+`sub`, default 120/min | 429 with `Retry-After` |
| Body | ≤ 1 MiB, no chunked encoding | 411 / 413 / 400 |

The one tokenless path is `GET`/`HEAD /v1/<system>/openapi.json` (the cells' public OpenAPI
document, read by the MCP hub's `describe_cell`): edge lock and path rules still apply, it is
limited per client IP, and only `Accept` is forwarded.

Forwarded to the upstream: `Authorization`, `Accept`, `Content-Type`, `If-Match`,
`If-None-Match`, `Idempotency-Key`, `X-Empire-Channel`, `X-Correlation-Id` and the gateway's
`X-Request-ID`; never the edge header.
The upstream's status and body come back unchanged (errors included); kept response headers:
`Content-Type`, `ETag`, `Retry-After`, `WWW-Authenticate`, and `Location` only when it stays on
the same upstream (rewritten to `/v1/<system>/…`). Connection errors are 502, timeouts 504
(`GATEWAY_UPSTREAM_TIMEOUT_SECONDS`, default 30). Every response, on every route, carries
`X-Request-ID`, `Strict-Transport-Security: max-age=31536000`,
`X-Content-Type-Options: nosniff` and `Cache-Control: no-store`.

Telemetry (one JSON line per request on stdout) adds `system` and the hashed `iss`+`sub` to `request.completed`; tokens, path tails,
query strings and bodies are never logged.

| Variable | Meaning |
|---|---|
| `GATEWAY_TRUSTED_ISSUERS` | JSON object issuer → https JWKS URL; enables `/v1/` |
| `GATEWAY_EDGE_SECRET` | 32+ characters; the same value is set by the Cloudflare request-header Transform Rule |
| `GATEWAY_ROUTES` | optional path to a route table (default `routes.json`) |
| `GATEWAY_SUBJECT_LIMIT_PER_MINUTE`, `GATEWAY_FAILURE_LIMIT_PER_MINUTE`, `GATEWAY_UPSTREAM_TIMEOUT_SECONDS` | limits (120, 10, 30) |
| `GATEWAY_HOST`, `GATEWAY_PORT` / `PORT` | bind address |
