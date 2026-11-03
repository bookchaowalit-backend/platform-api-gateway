# 05 — C4 Context

```mermaid
C4Context
  title platform-api-gateway - system context
  Person(owner, "Owner", "Uses CLI, MCP and owner-web")
  System_Ext(cons, "Consumers", "owner CLI, local MCP, remote MCP hub, owner-web, posture-monitor")
  System_Ext(cf, "Cloudflare", "Proxy, TLS, Transform Rule, rate-limit rule")
  System(gw, "platform-api-gateway", "Edge gateway /v1/system/path on Railway")
  System_Ext(idp, "Trusted issuers", "platform-identity and empire-platform JWKS")
  System_Ext(svc, "Registry services", "44 systems in routes.json on up.railway.app")
  System_Ext(up, "Uptime worker", "solo-empire-monitor probes /healthz hourly")
  Rel(owner, cons, "uses")
  Rel(cons, cf, "HTTPS gateway.bookchaowalit.com")
  Rel(cf, gw, "HTTPS plus X-Gateway-Edge")
  Rel(gw, idp, "GET JWKS")
  Rel(gw, svc, "HTTPS proxy plus X-Gateway-Assertion")
  Rel(up, cf, "GET /healthz")
```

หมายเหตุ: `routes.json` มี **44** systems ณ `origin/main` `4c81817` (ops record บันทึก 43 ก่อนเพิ่ม `platform-payment` ใน `51c4711`)

Sources: `routes.json`, `API.md`, `docs/specs/001-edge-gateway.md`, `contract.json` (`depends_on`, `migration.cutover`), `src/book_api_gateway/jwt_verify.py`, platform-uptime-worker `src/targets.ts` (line 85), ops record: api-gateway-edge (2026-11-03)

## Open questions

- trusted issuer URLs จริงอยู่ใน Railway variable `GATEWAY_TRUSTED_ISSUERS` (ไม่อยู่ใน repo) — diagram อ้างตาม SPEC/ops record
