# 14 — Backup and DR

gateway ไม่มีข้อมูลธุรกิจ (`data_owner: none`); สิ่งที่ต้องกู้คืนได้คือ code + route table, secrets และ config ของ Cloudflare/Railway

```mermaid
flowchart LR
  subgraph Assets
    GIT["Git: src, routes.json, Dockerfile"]
    SEC["Secrets: GATEWAY_EDGE_SECRET, GATEWAY_ASSERTION_MASTER_KEY"]
    VAR["Railway variables incl. GATEWAY_TRUSTED_ISSUERS"]
    CFR["Cloudflare zone rules: Transform, Config BIC off, rate limit, proxied CNAME"]
    MEM["In-memory limiter and JWKS cache"]
  end
  GIT -->|"copy on GitHub origin"| R1["Restore: git archive main then railway up"]
  SEC -->|"source of truth Infisical /platform-api-gateway"| R2["Restore: set Railway variables"]
  VAR --> R2
  CFR -->|"no export in repo"| R3["Restore: recreate rules by hand from API.md"]
  MEM -->|"rebuilt on start"| R4["Nothing to restore"]
  RB["Railway deployment history, canRollback"] --> R5["Rollback to previous deployment"]
  CON["Consumer env"] --> R6["Consumer rollback: point back at direct registry URL"]
```

| Item | Reality |
|---|---|
| Backup workflow | ไม่มี (ไม่จำเป็นสำหรับ DB) — repo มีแค่ `.github/workflows/check.yml` |
| Rollback ของ gateway | Railway deployments มี `canRollback: true` (14 deployments, 2026-11-03, Railway API) |
| Rollback ของ consumer | `contract.json` `migration.rollback`: point the consumer back at the direct registry URL |
| Secrets | Infisical `/platform-api-gateway` + Railway variable (ops record) |
| Cloudflare config | อธิบายใน `API.md` แต่ไม่มี IaC/export |
| RTO / RPO | **not defined** (ไม่มีใน PRODUCT.md, SPEC หรือ UPGRADE-PLAN); RPO ไม่เกี่ยวเพราะไม่มีข้อมูล |
| DR drill | UPGRADE-PLAN P2 "Rollback-route drill documentation" ยังเปิด |

Sources: `contract.json`, `.railway/railway.ts`, `Dockerfile`, `API.md`, `docs/UPGRADE-PLAN.md`, `.github/workflows/check.yml`, Railway `list-deployments` project `platform-api-gateway` (2026-11-03), ops record: api-gateway-edge (2026-11-03)

## Open questions

- RTO ของ gateway — เมื่อ gateway ล่ม consumer ทั้ง 4 กลุ่มล่มพร้อมกัน; ต้องการ fallback อัตโนมัติไป direct URL หรือไม่
- Cloudflare rules ควรถูก export/เก็บเป็น code ที่ไหน
