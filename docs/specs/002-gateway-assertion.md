---
title: "SPEC-002 Gateway assertion: services accept gateway calls only"
status: accepted
created: 2026-11-03
updated: 2026-11-03
description: The gateway tags every forwarded request with a short-lived HMAC that only it can make; a service checks the tag, first reporting and then refusing calls that bypassed the gateway.
---

# SPEC-002 Gateway assertion

## Problem

SPEC-001 put one edge (Cloudflare WAF, rate limits, token check) in front of the registry
services, but every service still answers on its public `*.up.railway.app` host. Anyone with a
token can skip the edge, so its limits and its single audit trail are optional. SPEC-001 left
"services reject direct calls" to this spec. Owner decision 2026-11-03: build it.

## Outcome

Every request the gateway forwards carries `X-Gateway-Assertion`. A service with a gateway key
recomputes it and, in `enforce` mode, answers 403 to a request without a valid one. In `report`
mode it serves the request and logs whether the assertion was `valid`, `missing` or `invalid`,
which is how the remaining direct callers are found before a service switches to `enforce`.

## Requirements

- **R1 Per-service key.** `key(system) = HMAC-SHA256(master, "gateway-assertion/v1/" + system)`.
  The gateway holds the master (`GATEWAY_ASSERTION_MASTER_KEY`, 32+ bytes as 64+ hex
  characters); a service holds only its own key (`GATEWAY_ASSERTION_KEY`, 64 hex characters),
  so one service's key cannot vouch for a request to another. `scripts/assertion_key.py
  <system>` prints a service key from the master in the environment.
- **R2 What is signed.** One line per field, joined by `\n`: `gw1`, the system id, the method,
  the target exactly as forwarded (raw path tail plus `?query` when present), the issue time
  (Unix seconds), the gateway request id, and the SHA-256 hex of the forwarded `Authorization`
  value, the forwarded `Content-Type` value and the exact forwarded body (each the hash of the
  empty string when absent). The header is `v1.<iat>.<base64url request id>.<base64url HMAC>` (the request id
  is encoded because a caller-supplied `X-Request-ID` may contain `.` and `:`).
  The assertion proves the request passed the edge unchanged; the bearer token still proves the
  caller. Within the 60 s window a captured assertion can only replay the identical request.
- **R3 Gateway.** When the master key is set, every proxied request carries the header,
  computed after the forwarded headers are chosen. A caller's own `X-Gateway-Assertion` is never
  forwarded (it is not in the forwarded set). Without the master key nothing is added (SPEC-001
  behaviour).
- **R4 Service check.** `GATEWAY_ASSERTION_MODE` is `off` (default), `report` or `enforce`.
  The service rebuilds the signed text from its own view of the request (`scope["raw_path"]`,
  `scope["query_string"]`, method, `Authorization`) and its system id, compares in constant time,
  and accepts `iat` within 60 seconds either way. `/health`, `/readyz`, `/openapi.json` and
  `/.well-known/` stay open for platform probes and `describe_cell`.
- **R5 Report.** One `gateway_assertion` log line per checked request: result, method, and the
  route template or the first path segment; never the token, query, header value or body.
- **R6 Enforce.** A missing, malformed, stale or wrong assertion is 403
  `{"error": "gateway_required"}` before the route runs. A service switches to `enforce` only
  after its report log shows no `missing` from a legitimate caller for 7 days, and that switch is
  recorded in `contract.json` `migration`.
- **R7 Rollback.** Set `GATEWAY_ASSERTION_MODE=report` (or `off`) on the service; no gateway
  change is needed.

## Acceptance criteria

- AC1 With the master key set, a request through the gateway reaches the upstream with a header
  the service's key verifies; the same header fails against another system's key.
- AC2 Changing the method, the target, the request id, the `Authorization` or `Content-Type`
  value or the body, or moving
  `iat` more than 60 s, makes the check fail.
- AC3 A caller-supplied `X-Gateway-Assertion` never reaches the upstream.
- AC4 Service in `enforce`: missing or invalid gives 403 and the route does not run; health and
  `/openapi.json` stay 200. In `report`: the route runs and the result is logged.
- AC5 Without `GATEWAY_ASSERTION_MASTER_KEY` the gateway sends no assertion.

## Rollout

1. Gateway signs (this change). Pilot service `habits` in `report`.
2. Read the habits report for 7 days and move its direct callers to the gateway.
3. `habits` to `enforce`; then the other cells one at a time, each with its own key.

## Out of scope

Replay caches (the 60 s window plus the bound token, request id, body and target are the limit),
mTLS, and private networking between the gateway and the services.
