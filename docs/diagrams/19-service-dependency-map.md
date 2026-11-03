# 19 — Service dependency map (runtime)

```mermaid
flowchart LR
  subgraph Callers
    PM["platform-posture-monitor"]
    CLI["owner CLI and local MCP, client.env"]
    HUB["platform-mcp-remote-worker"]
    OW["owner-web on Vercel"]
    UPT["platform-uptime-worker"]
  end
  CF["Cloudflare proxy"]
  GW["platform-api-gateway on Railway"]
  subgraph Issuers
    IDN["platform-identity JWKS"]
    EMP["empire-platform JWKS on tasks-api"]
  end
  subgraph Routed["routes.json: 44 systems"]
    LIFE["life cells: habits, goals, diary, decisions, health, time, learning, content, projects, roles-skills, operating, opportunities"]
    FIN["finance: budgets, cash-flow, transactions, tax, investments, liabilities, reconciliations, business-assets, finance-accounts, subscriptions"]
    PLAT["platform-*: commerce, communication, data, developer, logistics, media, payment, security, workflow"]
    OTHER["empire-platform, accounts, automation, intake, notifications, integrations, knowledge, saas-catalog, crm, crm-income, offers, radar, book-job-data"]
  end
  PM --> CF
  CLI --> CF
  HUB --> CF
  OW --> CF
  UPT -->|"/healthz"| CF
  CF --> GW
  GW --> IDN
  GW --> EMP
  GW --> LIFE
  GW --> FIN
  GW --> PLAT
  GW --> OTHER
```

Not routed (by design, `scripts/generate_routes.py` `SKIP_IDS`/`SKIP_KINDS`): `api-gateway` itself, `identity`, `ai-gateway`, web frontends
ไม่มี DB, cache, queue หรือ CDN อื่นนอกจาก Cloudflare

Sources: `routes.json`, `scripts/generate_routes.py`, `contract.json` (`depends_on: identity`, `migration.cutover`), `src/book_api_gateway/jwt_verify.py`, platform-uptime-worker `src/targets.ts`, platform-posture-monitor `posture_monitor/audit.py`, platform-mcp-remote-worker `src/worker.ts` (grep `gateway.bookchaowalit`), ops record: api-gateway-edge (2026-11-03)
