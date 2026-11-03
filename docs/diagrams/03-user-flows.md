# 03 — User flows (per caller)

ไม่มี UI; "user flow" คือเส้นทางของ caller แต่ละประเภทผ่าน route classes

## Edge consumer (RS256 token)

```mermaid
flowchart TD
  A["Set EMPIRE_*_API to gateway/v1/system"] --> B["Send request with Bearer token and named User-Agent"]
  B --> C["Cloudflare: BIC off for host, rate-limit 60 per 10 s per IP"]
  C --> D["Gateway checks edge header, path, route, IP lock, token, subject limit, body"]
  D -->|ok| E["Upstream answers; status and body unchanged"]
  D -->|reject| F["JSON error with request_id"]
  E --> G["Response with X-Request-ID, HSTS, nosniff, no-store"]
```

## Tokenless OpenAPI reader (describe_cell)

```mermaid
flowchart LR
  A["GET /v1/system/openapi.json, no token"] --> B["Edge lock and path rules"]
  B --> C["Per-IP limit key public:client"]
  C --> D["Forward Accept only"]
  D --> E["Service openapi.json"]
```

## Platform probe

```mermaid
flowchart LR
  P["Railway healthcheck or uptime worker"] --> H["GET /healthz: always 200 with auth_configured"]
  P --> R["GET /readyz: 200 when auth configured and route table loaded, else 503"]
```

## Pilot caller (`/api/*`, unset in production)

```mermaid
flowchart LR
  A["GET or POST /api/path with pilot token"] --> B["No query allowed, safe path"]
  B --> C["IP failure lock, hmac compare token"]
  C --> D["Subject limit 60 per minute"]
  D --> E["Forward to UPSTREAM_BASE_URL with X-Authenticated-Subject, no Authorization"]
```

Sources: `src/book_api_gateway/edge.py`, `src/book_api_gateway/server.py` (`_dispatch` readiness branch, `_proxy`), `src/book_api_gateway/config.py` (pilot defaults), `API.md`, ops record: api-gateway-edge (2026-11-03) (Cloudflare BIC rule, named User-Agent)

## Open questions

- ไม่มี flow สำหรับ caller ที่ต้องการ WebSocket หรือ streaming (SPEC-001 Out of scope)
