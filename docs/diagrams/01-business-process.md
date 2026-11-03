# 01 — Business process (As-Is / To-Be)

repo นี้คือ **edge API gateway** ของ Book Platform: `https://gateway.bookchaowalit.com/v1/<system>/<path>` รับ request จาก consumer แล้ว proxy ไปยัง service ของ registry (Railway) ตาม `routes.json`
"business process" ของ repo นี้จึงเป็นกระบวนการรับ request ของ consumer หนึ่งครั้ง และกระบวนการย้าย consumer (cutover) ทีละราย ไม่ใช่ธุรกรรมของลูกค้า
นอกจากนี้ยังมี pilot เดิม `/api/*` (token เดียว, upstream เดียว) ที่ README บอกว่า unset ใน production

## As-Is (จากโค้ดวันนี้)

```mermaid
flowchart TD
  C["Consumer: CLI, MCP hub, owner-web, posture-monitor"] --> CF["Cloudflare proxy: TLS, rate-limit rule, Transform Rule adds X-Gateway-Edge"]
  CF --> GW["Gateway on Railway: handle_v1"]
  GW --> L1{"X-Gateway-Edge matches secret?"}
  L1 -->|no| R403["403 direct access not allowed"]
  L1 -->|yes| P1{"Path safe and system in routes.json?"}
  P1 -->|no| R4xx["400 or 404"]
  P1 -->|yes| IP{"Client IP locked by failed tokens?"}
  IP -->|yes| R429a["429 too many failed authentication attempts"]
  IP -->|no| OA{"GET or HEAD openapi.json?"}
  OA -->|yes| PUB["Proxy tokenless, Accept only"]
  OA -->|no| TK{"RS256 token from trusted issuer valid?"}
  TK -->|"keys unavailable"| R503["503 token verification unavailable"]
  TK -->|no| R401["401 and count failure for IP"]
  TK -->|yes| SL{"Subject under 120 per minute?"}
  SL -->|no| R429b["429 rate limit exceeded"]
  SL -->|yes| BD{"Body valid, at most 1 MiB, not chunked?"}
  BD -->|no| R41x["400, 411 or 413"]
  BD -->|yes| SIGN["Add X-Request-ID and X-Gateway-Assertion"]
  SIGN --> UP["Upstream registry service"]
  PUB --> UP
  UP --> RESP["Status and body passed back, security headers added"]
  RESP --> TEL["request.completed line on stdout"]
```

Sources: `src/book_api_gateway/edge.py` (`handle_v1`, `_proxy`), `src/book_api_gateway/server.py` (`_dispatch`, `_handle_request`), `API.md` (Edge routes table), `docs/specs/001-edge-gateway.md`

### Consumer cutover (As-Is process, ทีละราย)

```mermaid
flowchart LR
  A["Consumer calls direct up.railway.app URL"] --> B["Shadow parity: same status and size direct vs gateway"]
  B --> C["Point consumer env at gateway/v1/system"]
  C --> D["Record cutover in contract.json migration.cutover"]
  D --> E{"Problem?"}
  E -->|yes| F["Rollback: point consumer back at direct registry URL"]
  E -->|no| G["Next consumer"]
```

Cutovers ที่บันทึกแล้ว (2026-11-03): platform-posture-monitor, owner CLI + local MCP (`client.env`, 10 cells), remote MCP hub `platform-mcp-remote-worker` (29 cells), owner-web บน Vercel (14 cells)

Sources: `contract.json` (`migration.shadow_parity`, `migration.cutover`, `migration.rollback`), `README.md`, ops record: api-gateway-edge (2026-11-03)

## To-Be (จากเอกสารใน repo เท่านั้น)

```mermaid
flowchart LR
  S1["Gateway signs every forwarded request: done"] --> S2["habits in report mode 7 days"]
  S2 --> S3["Move remaining direct callers of habits to gateway"]
  S3 --> S4["habits to enforce: 403 gateway_required on direct calls"]
  S4 --> S5["Other cells one at a time, each with own derived key"]
```

Sources: `docs/specs/002-gateway-assertion.md` (Rollout), `contract.json` (`migration.cutover` "Next: ..."), `docs/UPGRADE-PLAN.md` (Backlog P0: identity subject assertion, shadow-parity fixtures; P2: rollback-route drill, cache `/readyz`)

## Open questions

- PRODUCT.md มี `[ต้องยืนยัน] The cutover criteria for activating the runtime` — เกณฑ์ cutover อย่างเป็นทางการยังไม่ถูกกำหนด
- consumer ที่ยังเรียก direct (crm-ledger, knowledge) จะย้ายมาหรือคงไว้ถาวร (ทั้งสองใช้ token ที่ไม่ใช่ platform RS256)
- pilot `/api/*` จะถูกลบออกหรือคงไว้ (UPGRADE-PLAN ยังถือ P0 "identity subject assertion" สำหรับ class นี้)
