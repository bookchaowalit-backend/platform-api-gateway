# 11 — State machines

ไม่มี entity ที่มี field `status` ใน DB (ไม่มี DB); lifecycle ที่มีจริงในโค้ดคือ JWKS cache, limiter window ต่อ key และ assertion mode ของ service (กำหนดใน SPEC-002, implement ฝั่ง service)

## JWKS cache per issuer (`IssuerKeys`)

```mermaid
stateDiagram-v2
  [*] --> Empty
  Empty --> Loaded: fetch ok with keys
  Empty --> Unavailable: fetch fails, 503
  Unavailable --> Unavailable: retry blocked within 60 s
  Unavailable --> Loaded: later fetch ok
  Loaded --> Stale: older than 600 s
  Loaded --> Refetching: unknown kid and last attempt over 60 s ago
  Stale --> Refetching: next request
  Refetching --> Loaded: fetch ok, replace key set
  Refetching --> Loaded: fetch fails, keep last good keys
  Refetching --> Withdrawn: fetch ok with empty key set
  Withdrawn --> Unavailable: no keys, 503
```

## Failure limiter window per client IP

```mermaid
stateDiagram-v2
  [*] --> Open
  Open --> Counting: failed token
  Counting --> Counting: failures below 10
  Counting --> Locked: 10 failures in window
  Locked --> Open: window of 60 s ends
  Counting --> Open: window ends
  Counting --> Evicted: over max_keys, oldest first
  Evicted --> Open
```

## Service assertion mode (SPEC-002 R4, R6, R7)

```mermaid
stateDiagram-v2
  [*] --> off
  off --> report: GATEWAY_ASSERTION_KEY set, mode report
  report --> enforce: 7 days without legitimate missing, recorded in contract
  enforce --> report: rollback
  report --> off: rollback
```

## Consumer cutover

```mermaid
stateDiagram-v2
  [*] --> Direct
  Direct --> ParityChecked: same status and size direct vs gateway
  ParityChecked --> ViaGateway: env points at gateway, recorded in contract
  ViaGateway --> Direct: rollback
```

Sources: `src/book_api_gateway/jwt_verify.py` (`_due`, `_load`), `src/book_api_gateway/limiter.py`, `src/book_api_gateway/edge.py`, `docs/specs/002-gateway-assertion.md`, `contract.json` (`migration`)
