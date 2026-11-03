# 07 — C4 Component

```mermaid
C4Component
  title Gateway process - components
  Container_Boundary(p, "book_api_gateway package") {
    Component(srv, "server.py", "GatewayRequestHandler", "dispatch, ROUTE_ACCESS, pilot /api, headers, telemetry")
    Component(edge, "edge.py", "handle_v1, _proxy", "edge lock, path rules, limits, proxy, Location rewrite")
    Component(jwt, "jwt_verify.py", "TokenVerifier, IssuerKeys", "RS256 PKCS1 v1.5, JWKS cache")
    Component(asr, "assertion.py", "sign, verify, system_key", "SPEC-002 HMAC")
    Component(rts, "routes.py", "load_routes, match", "route table")
    Component(lim, "limiter.py", "FixedWindowRateLimiter", "bounded fixed windows")
    Component(cfg, "config.py", "GatewayConfig", "pilot settings and allow list")
  }
  Rel(srv, edge, "path starts with /v1/")
  Rel(srv, cfg, "from_env")
  Rel(srv, lim, "pilot subject and IP limits")
  Rel(edge, jwt, "verify token")
  Rel(edge, asr, "sign forwarded request")
  Rel(edge, rts, "match system")
  Rel(edge, lim, "subject and failure limiters")
```

Scripts (ไม่อยู่ใน runtime image): `scripts/generate_routes.py`, `scripts/assertion_key.py`, `scripts/check.py`, `scripts/check_schema_pin.py`, `scripts/check_registry_alignment.py`, `scripts/check.sh`

Sources: `src/book_api_gateway/*.py`, `scripts/*.py`, `Dockerfile` (`COPY src`, `COPY routes.json` only)
