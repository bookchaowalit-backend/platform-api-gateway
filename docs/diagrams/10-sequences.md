# 10 — Sequences

## 1. Authenticated edge call (happy path)

```mermaid
sequenceDiagram
  participant C as Consumer
  participant CF as Cloudflare
  participant G as Gateway
  participant J as Issuer JWKS
  participant S as Registry service
  C->>CF: GET /v1/habits/... Bearer JWT
  CF->>G: request plus X-Gateway-Edge, CF-Connecting-IP
  G->>G: edge lock, unsafe_path, match route, IP lock check
  G->>G: TokenVerifier.verify
  opt keys missing, stale or unknown kid, at most once a minute
    G->>J: GET JWKS
    J-->>G: keys
  end
  G->>G: subject limit, read body
  G->>G: sign X-Gateway-Assertion with system key
  G->>S: request with Authorization, X-Request-ID, X-Gateway-Assertion
  S-->>G: status, body, ETag, Location
  G->>G: check length, rewrite Location if same upstream
  G-->>CF: status, body, X-Request-ID, HSTS, nosniff, no-store
  CF-->>C: response
  G->>G: print request.completed to stdout
```

## 2. Rejected token and IP lock

```mermaid
sequenceDiagram
  participant A as Caller
  participant G as Gateway
  participant L as failure_limiter
  A->>G: /v1/system/x with bad token
  G->>L: is_blocked ip:client
  L-->>G: 0
  G->>G: verify raises TokenError
  G->>L: allow ip:client counts a failure
  G-->>A: 401 authentication required, WWW-Authenticate Bearer
  Note over A,G: after 10 failures in the window
  A->>G: any /v1/ request
  G->>L: is_blocked ip:client
  L-->>G: seconds left
  G-->>A: 429 too many failed authentication attempts, Retry-After
```

## 3. Tokenless OpenAPI read (describe_cell)

```mermaid
sequenceDiagram
  participant H as MCP hub describe_cell
  participant G as Gateway
  participant S as Service
  H->>G: GET /v1/system/openapi.json, no token
  G->>G: edge lock, path, route, IP lock
  G->>G: subject_limiter.allow public:client
  G->>S: GET /openapi.json, Accept only, X-Request-ID, assertion
  S-->>G: 200 OpenAPI JSON
  G-->>H: 200
```

## 4. Upstream failure

```mermaid
sequenceDiagram
  participant G as Gateway
  participant S as Sleeping Railway service
  G->>S: forwarded request, timeout 30 s
  alt timeout
    G-->>G: 504 upstream timeout
  else connection or protocol error
    G-->>G: 502 upstream unavailable
  else body cut off or length mismatch
    G-->>G: 502 upstream response incomplete
  else body above 1 MiB
    G-->>G: 502 upstream response too large
  end
```

Sources: `src/book_api_gateway/edge.py` (`handle_v1`, `_proxy`), `src/book_api_gateway/jwt_verify.py`, `src/book_api_gateway/assertion.py`, `src/book_api_gateway/server.py`, `docs/specs/001-edge-gateway.md`, `tests/test_edge.py`
