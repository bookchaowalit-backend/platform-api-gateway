---
title: "SPEC-003 Gateway production standard: one contract for every route"
status: accepted
created: 2026-11-12
updated: 2026-11-12
description: What every route behind gateway.bookchaowalit.com must declare, how a service is onboarded and rolled back, what is observed and alerted, how keys rotate, how the gateway is deployed and what to do when it is down.
---

# SPEC-003 Gateway production standard

SPEC-001 built the edge, SPEC-002 the assertion that proves a request passed it. This spec is the
standard that makes them one service: the same contract, checks and runbook for every route.
Owner goal 2026-11-12: "the central gateway is really used, with one production standard".

## 1. Route contract

Every route `/v1/<system>/…` has these properties. The table is the contract; the column says where
the value lives, and `scripts/check.sh` fails when a route lacks one.

| Property | Default | Where it is set |
|---|---|---|
| Upstream origin (bare https origin) | — | `routes.json` `routes` |
| Owner repository, kind | — | hub registry `online-systems.yaml` (same id) |
| Body limit, request and response | 1 MiB (`MAX_BODY_BYTES`); per route up to 16 MiB | `routes.json` `limits` (knowledge 16 MiB) |
| Upstream timeout | 30 s (`GATEWAY_UPSTREAM_TIMEOUT_SECONDS`) | gateway env |
| Rate limit per subject | 120 / min (`GATEWAY_SUBJECT_LIMIT_PER_MINUTE`) | gateway env |
| Failed-token limit per client IP | 10 / min, then 429 (`GATEWAY_FAILURE_LIMIT_PER_MINUTE`) | gateway env |
| Edge rate limit per colo + IP | 60 / 10 s | Cloudflare rule `http_ratelimit` |
| Accepted token issuers | identity, empire-platform, Solo Web (RS256, JWKS) | `GATEWAY_TRUSTED_ISSUERS` |
| Audience | the service's own (`<name>-api`); checked by the service, not the gateway | service config |
| Assertion state | `enforce` / `report` (+ review date) / `planned` (+ dates) / `exempt` (+ reason) | `assertion-status.json` |

The gateway checks issuer, signature, expiry, `sub` and that `aud` is present; the service checks its
own audience, scopes and authorization. A new issuer is trusted only with owner approval, an https
JWKS URL and a parity test (section 2).

## 2. Onboarding a service (checklist)

1. Route: add `<system>: https://<origin>` to `routes.json` (the id = the registry id = the
   assertion system), set a `limits` entry only if bodies exceed 1 MiB, add a `planned`
   entry to `assertion-status.json`, run `scripts/check.sh`, deploy (section 6).
2. Assertion in report mode: the service gets the SPEC-002 check (cellkit `gateway.py` byte-identical,
   or the module of its stack) and `GATEWAY_ASSERTION_MODE=report` + its own `GATEWAY_ASSERTION_KEY`
   (`scripts/assertion_key.py <system>`, piped, never printed). Verify one `result=valid` through the
   gateway and one `result=missing` direct in the service log; mark it `report` with a review date
   7 days on.
3. Callers: for each caller, a parity test with the caller's own token — the same status and size
   through the gateway and direct, for health, a read and (if it writes) a write — then point its
   variable at `https://gateway.bookchaowalit.com/v1/<system>`. Record the caller in the inventory.
4. Review: read every deployment's `gateway_assertion` lines since the report date. Only test,
   scanner or one-off `missing` lines may remain; a recurring caller is moved first.
5. Enforce: `GATEWAY_ASSERTION_MODE=enforce` after owner approval, then a direct call must get 403
   and a gateway call must still work. Mark it `enforce` with the date.

Rollback at any step: set the caller variable back to the direct origin (kept in a comment or the
inventory), set the mode back to `report`, or remove the route. No step deletes the direct origin.

## 3. Observability

- Gateway log (one JSON line per request): `event`, `route`, `system`, `method`, `status`,
  `latency_ms`, `request_id`, `subject_hash` (16 hex of `sha256(iss \n sub)`); never the path tail,
  query, body or token.
- Service log (report/enforce): `gateway_assertion result=<valid|missing|invalid> method=… path=<family>`.
- Daily report (platform-uptime-worker `gateway-report.ts`, 01:00 UTC to Telegram): requests per route
  over 24 h by 401/403/429/4xx/5xx from Cloudflare analytics of the gateway host, read-only token
  `GATEWAY_REPORT_CF_TOKEN` (Infisical `/cloudflare`). `ALERT` when 5xx > 2 % and at least 5.
- Uptime: `api-gateway` probed every 5 minutes by the same monitor.

## 4. Security

- Keys: `GATEWAY_ASSERTION_MASTER_KEY` and `GATEWAY_EDGE_SECRET` rotate every 90 days or on
  suspicion. Master: generate 32 bytes, store in Infisical `/platform-api-gateway`, re-derive and set
  every service key in `report` mode first (a key change makes `enforce` services refuse until both
  sides match), then the gateway, then restore modes. Edge secret: update the Cloudflare
  request-header Transform Rule and the gateway variable in the same minute; a mismatch is 403 for all.
- Headers: HSTS, `X-Content-Type-Options: nosniff`, `X-Request-ID` on every answer; no CORS — the
  gateway serves server-to-server callers only, so no `Access-Control-*` header is ever sent and
  browsers cannot call it cross-origin.
- JWKS fetching (gateway and services alike): https only, no redirects, a response cap, cached
  with a TTL, refetched once when a token names or needs an unknown key (at most once a minute),
  the last good keys kept when a fetch fails, and an empty answer withdraws trust.
- Automation tokens: audiences beyond the cell defaults are opt-in per automation
  (`extra_audiences` in platform-empire), and a service that grants owner access names the allowed
  subjects. Next step: scope-based authorization in such services instead of owner access.

## 5. Decision B (decided 2026-11-12: stay direct)

Cells call tasks-api (`EMPIRE_PLATFORM_URL`) for authz decide, begin/finish and publish on every
write. Owner decision 2026-11-12: these calls stay direct, so `empire-platform` is `exempt`.

- Through the gateway (option a) each call costs about +65 ms server to server (section 8), so a write
  pays +200–260 ms, and all cells share one Railway egress, so they would compete for the
  60 req / 10 s edge rule.
- Railway private networking (option b) costs nothing and has no egress fees, but it only connects
  services inside one project and environment; tasks-api is in `platform-empire` and each cell has its
  own project (about 40), so it would mean moving every cell into one project (new services, variables,
  CD, crons and domains for each) for ~10–20 ms per call.
- tasks-api verifies its own RS256 tokens, so the direct path keeps the same caller check.

Revisit only if the cells are consolidated into one Railway project.

## 6. Deploy

`infisical run --path=/railway -- scripts/deploy.sh` (or `REF=<sha>` to roll back): runs
`scripts/check.sh` on a clean `git archive` of the ref, uploads it with `railway up`, then
`scripts/smoke.py`, which checks `/healthz`, that every route reaches its service (tokenless
`/openapi.json` is not the gateway's own 404 or a 5xx), three tokenless 401s and an unknown-route 404.

## 7. Runbook: gateway down or failing

1. Confirm: uptime alert, `scripts/smoke.py`, Railway deployment state of `platform-api-gateway`,
   Cloudflare status. A 403 for every call means the edge secret and the Transform Rule disagree.
2. If a deploy caused it: `REF=<last good sha> scripts/deploy.sh`.
3. If the gateway cannot be restored within 15 minutes: set every `enforce` service to `report`
   (they then accept direct calls), and point the urgent callers back to their direct origin
   (rollback values are in the inventory and the comments next to each variable).
4. After recovery: callers back through the gateway, modes back, an incident note with the cause.

## 8. Measured latency (2026-11-12, from Bangkok, 40 sequential calls each)

| Route | Direct p50 / p95 | Gateway p50 / p95 |
|---|---|---|
| health `/health` | 116 / 134 ms | 78 / 94 ms |
| knowledge catalog | 125 / 138 ms | 86 / 117 ms |
| crm-income workspace | 4334 / 4508 ms | 4326 / 4425 ms |

From this client the gateway adds no measurable latency (Cloudflare terminates TLS nearer); the CRM
time is the service's own query time.

Server to server (from the health-api container on Railway, tasks-api `/openapi.json`, 30 calls):
direct p50 20 ms / p95 39 ms, through the gateway p50 85 ms / p95 144 ms — about +65 ms per call
(Railway → Cloudflare edge → Railway). A cell write makes 3–4 platform calls (decide, begin, finish,
publish), so option (a) of Decision B costs roughly +200–260 ms per write and puts every write
behind the 60 req / 10 s edge rule shared by all cells (same Railway egress); option (b) keeps the
~20 ms path. Recommendation for the owner: (b), or keep direct with tasks-api's own token check.
