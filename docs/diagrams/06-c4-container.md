# 06 — C4 Container

```mermaid
C4Container
  title platform-api-gateway - containers
  System_Ext(cf, "Cloudflare zone", "Proxy for gateway.bookchaowalit.com")
  Container_Boundary(rw, "Railway project platform-api-gateway, service gateway, Singapore") {
    Container(proc, "Gateway process", "Python 3.12 stdlib, ThreadingHTTPServer", "server.py main")
    ContainerDb(rt, "routes.json", "JSON file in image", "system to https base URL")
    Container(mem, "In-memory state", "Python objects", "limiter windows, JWKS cache")
  }
  System_Ext(idp, "Issuer JWKS endpoints", "identity, empire-platform tasks-api")
  System_Ext(svc, "Registry services", "Railway up.railway.app")
  System_Ext(logs, "Railway logs", "stdout request.completed")
  Rel(cf, proc, "HTTPS with X-Gateway-Edge")
  Rel(proc, rt, "load_routes at startup")
  Rel(proc, mem, "read and write")
  Rel(proc, idp, "urlopen JWKS, 10 s timeout")
  Rel(proc, svc, "urllib request, 30 s timeout")
  Rel(proc, logs, "JSON lines")
```

Sources: `Dockerfile`, `.railway/railway.ts`, `src/book_api_gateway/server.py` (`main`, `GatewayState`, `_default_telemetry`), `src/book_api_gateway/routes.py`, `src/book_api_gateway/limiter.py`, `src/book_api_gateway/jwt_verify.py` (`_default_fetch`), `src/book_api_gateway/edge.py`, ops record: api-gateway-edge (2026-11-03)

## Open questions

- จำนวน replica ของ service `gateway` — in-memory limiter เป็นต่อ process; ถ้ามีหลาย replica limit จริงจะคูณตามจำนวน (ไม่พบใน config)
