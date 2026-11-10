# 02 — Use cases

Actors คือ caller จริงตาม route access classes ใน `ROUTE_ACCESS` (`server.py`): public probe, edge caller ที่มี platform RS256 token, caller tokenless ของ `openapi.json`, pilot service token และ operator ที่ดูแล route table / key

```mermaid
flowchart LR
  subgraph Actors
    PROBE["Platform probe: Railway healthcheck, uptime worker"]
    CONS["Edge consumer with RS256 token: owner CLI, MCP hub, owner-web, posture-monitor"]
    DESC["Tokenless reader: MCP hub describe_cell"]
    PILOT["Pilot caller with BOOK_API_GATEWAY_TOKEN"]
    OPS["Owner or agent operator"]
    CFE["Cloudflare edge"]
  end
  subgraph Gateway["platform-api-gateway"]
    UC1(["Check liveness GET /healthz"])
    UC2(["Check readiness GET /readyz"])
    UC3(["Call a registry service via /v1/system/path"])
    UC4(["Read a service OpenAPI document tokenless"])
    UC5(["Call the pilot upstream via /api/*"])
    UC6(["Regenerate routes.json from the registry"])
    UC7(["Derive a service assertion key"])
    UC8(["Deploy gateway to Railway"])
    UC9(["Add X-Gateway-Edge header and rate-limit per IP"])
  end
  PROBE --> UC1
  PROBE --> UC2
  CONS --> UC3
  DESC --> UC4
  PILOT --> UC5
  OPS --> UC6
  OPS --> UC7
  OPS --> UC8
  CFE --> UC9
  UC9 --> UC3
  UC9 --> UC4
```

| Use case | Auth level | Methods | Source |
|---|---|---|---|
| `/healthz`, `/readyz` | public | GET | `server.py` `ROUTE_ACCESS` |
| `/v1/<system>/*` | platform-token (edge header + RS256) | GET, HEAD, POST, PUT, PATCH, DELETE | `edge.py` `METHODS`, `handle_v1` |
| `/v1/<system>/openapi.json` | public (แต่ยังต้องผ่าน edge lock) | GET, HEAD | `edge.py` `PUBLIC_OPENAPI` |
| `/api/*` | service token | GET, POST | `server.py` `_authenticate` |
| regenerate routes | local operator | — | `scripts/generate_routes.py` |
| derive assertion key | local operator, master key in env | — | `scripts/assertion_key.py` |

Sources: `src/book_api_gateway/server.py`, `src/book_api_gateway/edge.py`, `scripts/generate_routes.py`, `scripts/assertion_key.py`, `API.md`, `contract.json` (`migration.cutover`), `.railway/railway.ts`

## Open questions

- ไม่มี role/scope ภายใน gateway: audience และ scope เป็นการตัดสินใจของแต่ละ service (SPEC-001 R3) — ถ้าต้องการ allow-list ต่อ consumer ที่ gateway ต้องมี spec ใหม่
