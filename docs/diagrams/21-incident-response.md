# 21 — Incident response

ไม่มี runbook ใน repo; flow นี้ประกอบจาก alert channel และ rollback ที่มีอยู่จริง

```mermaid
flowchart TD
  A1["Uptime worker: api-gateway /healthz down, Telegram"] --> T["Triage"]
  A2["Consumer reports errors, e.g. MCP hub sweep, CLI"] --> T
  A3["Deploy healthcheck fails (new deploy not activated) or process crash restarts up to 3; a hung process is only caught by uptime-worker"] --> T
  T --> Q1{"Gateway or upstream?"}
  Q1 -->|"request.completed status 502 or 504 for one system"| U["Upstream: check that service directly"]
  Q1 -->|"401 or 503 token verification unavailable"| J["Issuer JWKS or GATEWAY_TRUSTED_ISSUERS"]
  Q1 -->|"403 direct access not allowed"| E["Cloudflare Transform Rule vs GATEWAY_EDGE_SECRET"]
  Q1 -->|"403 from Cloudflare to API clients"| B["BIC Configuration Rule, User-Agent"]
  Q1 -->|"gateway down"| G["Gateway deployment"]
  G --> R1["Railway rollback to previous deployment"]
  G --> R2["Consumer rollback: point back at direct registry URL"]
  U --> FIX["Fix and redeploy: git archive main then railway up"]
  J --> FIX
  E --> FIX
  R1 --> FIX
  FIX --> V["Verify: /healthz, parity sweep direct vs gateway"]
  V --> PM["Postmortem: record in contract.json migration or ops record"]
```

ตัวอย่างจริง (ops record 2026-11-03): Cloudflare BIC ตอบ 403 ให้ `Python-urllib` → แก้ด้วย Configuration Rule `bic: false`; MCP hub deploy ทำ `PUBLIC_ORIGIN` หาย → `/mcp` 503 แก้ภายในไม่กี่นาที (ฝั่ง worker ไม่ใช่ gateway)

Sources: platform-uptime-worker `src/targets.ts`, `.railway/railway.ts`, `src/book_api_gateway/edge.py` (error messages), `API.md`, `contract.json` (`migration.rollback`), Railway `list-deployments` (`canRollback`), ops record: api-gateway-edge (2026-11-03), ops record: prod-baseline-monitoring-backups (2026-11-03)

## Open questions

- ไม่มี postmortem template หรือที่เก็บ incident ของ gateway โดยเฉพาะ
- severity/SLA ของ gateway (เป็น single point ของ 4 กลุ่ม consumer) ยังไม่ได้กำหนด
