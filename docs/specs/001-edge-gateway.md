---
title: "SPEC-001 Edge gateway for the registry services"
status: accepted
created: 2026-11-03
updated: 2026-11-03
description: One public ingress, gateway.bookchaowalit.com behind Cloudflare, that verifies platform tokens, rate-limits per subject and routes /v1/<system>/… to the registry's services.
---

# SPEC-001 Edge gateway for the registry services

## Problem

The network review of 2026-11-02 (architecture-docs `systems/architecture/network-architecture.md`)
found 45 Railway APIs and 9 platform services called directly on public `*.up.railway.app`
hosts: no edge WAF, no shared rate limit, no request id and no common response headers
(NET-04, NET-07). Every service checks tokens itself, so a flood of junk tokens reaches every
service and its database pool. Owner decision 2026-11-03: build the api-gateway as a running
system.

## Outcome

`https://gateway.bookchaowalit.com/v1/<system>/<path>` reaches the registry system `<system>`
at `<path>`. Cloudflare's proxy (WAF, DDoS, TLS) sits in front; the gateway rejects requests
that did not come through Cloudflare, rejects tokens that no trusted issuer signed, limits
each subject and each client IP, adds a request id and security headers, and passes the
caller's token through so each service keeps its own audience and scope checks.

Consumers move to the gateway one at a time; the direct `*.up.railway.app` URLs stay valid
until a consumer cutover is recorded (rollback = point the consumer back).

## Requirements

- **R1 Route table.** `routes.json` maps each system id to its HTTPS base URL. It is
  generated from the hub registry by `scripts/generate_routes.py --registry <path>` and
  committed, so the gateway never reads the hub at runtime. Only `https` URLs whose host is
  in the generated allow list are accepted; anything else stops the gateway at startup.
- **R2 Edge lock.** With `GATEWAY_EDGE_SECRET` set, every `/v1/` request must carry
  `X-Gateway-Edge: <secret>` (added by a Cloudflare request-header Transform Rule) or gets 403
  `direct access not allowed`. Only then is `CF-Connecting-IP` used as the client address;
  otherwise the socket peer is. `/healthz` and `/readyz` stay open for the platform
  healthcheck.
- **R3 Token check.** A `/v1/` request needs `Authorization: Bearer <JWT>`: header `alg`
  `RS256` (a token without `kid`, as empire-platform issues, is tried against each of the
  issuer's published keys, at most 8), `iss` one of `GATEWAY_TRUSTED_ISSUERS` (issuer → JWKS URL), a valid
  signature by that issuer's key, `exp` in the future and `nbf`/`iat` not in the future
  (60 s skew), `sub` and `aud` present. JWKS are cached 10 minutes and refetched at most once a
  minute for an unknown `kid`. When no issuer's keys can be loaded the answer is 503, never a
  pass. The token is forwarded unchanged; audience and scope stay the service's decision.
- **R3a Public OpenAPI.** `GET`/`HEAD /v1/<system>/openapi.json` is the one path without a
  token: the cells publish it unauthenticated and the MCP hub's `describe_cell` reads it tokenless.
  The edge lock and path rules still apply; it is limited per client IP; only `Accept` is
  forwarded (never `Authorization`).
- **R4 Limits.** Failed tokens per client IP (default 10/min → 429 for the rest of the window);
  accepted requests per `iss`+`sub` (default 120/min). Bodies up to 1 MiB, query strings up to
  2048 characters, no chunked bodies, upstream redirects disabled, upstream timeout 30 s
  (sleeping Railway services and Neon take several seconds to wake).
- **R5 Faithful proxy.** Methods GET, HEAD, POST, PUT, PATCH, DELETE. Request headers forwarded:
  `Authorization`, `Accept`, `Content-Type`, `If-Match`, `If-None-Match`, `Idempotency-Key`,
  `X-Empire-Channel`, `X-Correlation-Id` (first-party audit channel and correlation, added for the
  owner CLI cutover), `X-Workspace-Authorization` (the caller JWT platform-data verifies on its own), plus the gateway's `X-Request-ID`. The upstream status and body are returned as they are
  (4xx and 5xx included); response headers kept: `Content-Type`, `ETag`, `Retry-After`,
  `WWW-Authenticate`, `Location` (only when it points at the same upstream, rewritten to the
  gateway path). Connection failures are 502, timeouts 504.
- **R6 Response headers.** Every response carries `X-Request-ID`,
  `Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff`,
  `Cache-Control: no-store`.
- **R7 Telemetry.** One `request.completed` line per request: method, route class, system id,
  status, latency, request id, and a hash of `iss`+`sub`; never the token, path tail, query or
  body.
- **R8 Dependency-free.** Standard library only; RS256 verification is the RSA public-key
  operation with PKCS#1 v1.5 padding on JWKS `n`/`e` (public data, no secret timing).

## Acceptance criteria

- AC1 A token signed by a trusted issuer reaches the routed upstream with its
  `Authorization` header unchanged; the upstream's status and body come back.
- AC2 A wrong signature, unknown `kid`, untrusted `iss`, `alg` other than RS256, expired token or
  missing `sub`/`aud` gets 401 and nothing reaches the upstream.
- AC3 Without the edge header (when the secret is set) a `/v1/` request gets 403.
- AC4 An unknown system id gets 404; a path with `..`, encoded slashes or control characters 400.
- AC5 The 11th failed token from one IP within a minute gets 429, and so does a 121st accepted
  request from one subject.
- AC6 Every response has the R6 headers.
- AC7 Generated routes contain only `https` registry URLs of online systems and never the
  gateway itself.

## Out of scope

Consumer cutovers (each is its own change), response caching, WebSockets, request signing to
upstreams, and making services reject direct calls (needs a gateway-signed assertion each
service checks; a later spec).
