# BOO-147 — External provider and webhook map (system gate evidence)

- Issue: BOO-147 (system `integrations` in `repository-catalog/registries/system-repositories.yaml:480-503`, solo-empire `63efeeb0`)
- Next gate (verbatim): **"Map every external provider, signature check, idempotency key, and privacy class."**
- Contract: `bookchaowalit/architecture-docs` →
  `systems/architecture/solo-empire-api-contract-v1.md#signed-and-authenticated-webhook-routes`
  (origin/main `a9c84724`, lines 136-143; auth classes at 55-61; provider read routes at 111-134)
- Gateway source: this repository at origin/main `6e1fb34`
- Machine-readable map: [`fixtures/gates/webhook-provider-map.json`](../../fixtures/gates/webhook-provider-map.json)
- Drift tests: [`tests/test_webhook_provider_map.py`](../../tests/test_webhook_provider_map.py) (run by `bash scripts/check.sh`)

This is evidence for an owner decision. It does not change any route, does not
activate a runtime, and does not record an accepted decision.

## Where the routes live today

| Location | State | Evidence |
|---|---|---|
| Contract `solo-empire-api-contract-v1.md` | `status: retired` (2026-10-11); kept as the historical contract | contract front matter lines 7-8, 16 |
| solo-empire `integrations/` | **Directory removed** in `daf06f31` (2026-10-11). Mapped from the last tree that had it, `981a12db` | `git ls-tree 981a12db -- integrations` (14 files) |
| solo-empire `infra/api/server.ts` | Removed; last live LINE/Stripe handlers at `1d0e04bb`, last live analytics/revenue handlers at `aa567aab` | see table citations |
| `bookchaowalit/platform-legacy-api-archive` @ `74b68443` | All four webhook routes return **410 Gone** behind the `api:write` Bearer guard; `line.ts` / `stripe.ts` verifiers are kept but no longer imported | `server.ts:961-990`, `line.ts`, `stripe.ts` |
| This gateway (`src/book_api_gateway/server.py`) | **No webhook or provider route.** Only `/healthz`, `/readyz` (public GET) and `/api/*` (Bearer, GET/POST passthrough) | `server.py:38-42` |

So no inbound provider webhook is served anywhere in scope right now. The map
below is the contract inventory plus what the gateway would do if a provider
delivery reached it.

## Inbound webhook routes (contract section)

| Route | Provider | Signature scheme / header | Verification location | Idempotency key source | Replay window | Privacy class |
|---|---|---|---|---|---|---|
| `POST /api/webhook/line` | LINE Messaging API | HMAC-SHA256(raw body), base64, `x-line-signature`; secret `LINE_SOLO_EMPIRE_WEBHOOK_SECRET`; 401 on mismatch, 503 unconfigured | archive `line.ts:8-23`; called at solo-empire `1d0e04bb:infra/api/server.ts:975`. **Gateway: missing** | `event.webhookEventId`, else `event.message.id` (`line.ts:34-42`); `webhook_log(source,external_id)` lookup (`server.ts:1004-1012`) | **missing** — no timestamp check (`server.ts:965-1031`) | `restricted` (cited: `integrations/line/README.md:97-101`) |
| `POST /api/webhook/stripe` | Stripe | Stripe v1: HMAC-SHA256 hex of `${t}.${rawBody}`, `stripe-signature`; secret `STRIPE_WEBHOOK_SECRET`; 400 on mismatch, 503 unconfigured | archive `stripe.ts:12-53`; called at `1d0e04bb:infra/api/server.ts:1046`. **Gateway: missing** | Stripe event `id`; `webhook_log` lookup (`server.ts:1062-1079`) | **300 s** on `t` (`stripe.ts:17,33-37`) | `restricted` (proposed: raw event body stored verbatim, `server.ts:1079`) |
| `POST /api/webhook/analytics` | internal caller (Bearer) | none; Bearer `api:write` via `/api/webhook/*` guard | `aa567aab:infra/api/server.ts:1294-1300`. Gateway: Bearer only (`server.py:212-229`) | natural key `(asset_id, metric_date)` upsert (`server.ts:1416-1487`) | not applicable (idempotent upsert) | `internal` (proposed) |
| `POST /api/webhook/revenue` | internal caller (Bearer) | none; Bearer `api:write` | `aa567aab:infra/api/server.ts:1294-1300`. Gateway: Bearer only | `Idempotency-Key` header, 1..255 chars, duplicate → `{success, id, duplicate:true}` (`server.ts:1492-1531`) | **missing** (no timestamp, no key expiry) | `restricted` (proposed: finance ledger rows) |

## Outbound read-only providers (contract lines 122-134, `integrations/`)

None of these receive provider deliveries, so signature, idempotency and replay
are `not-applicable`; each was Bearer-protected and read-only.

| Provider | Route(s) | Privacy class (proposed) | Evidence |
|---|---|---|---|
| Sentry | `GET /api/integrations/sentry/issues` | internal | contract:122; `EXTERNAL-APP-REGISTRY.md:52-56` |
| PostHog | `GET /api/integrations/posthog/insights` | internal | contract:123; registry:58-63 |
| Slack | `GET /api/integrations/slack/channels` | internal | contract:124; registry:65-69 |
| Notion | `GET /api/integrations/notion/search` | private | contract:125; registry:71-76 |
| Asana | `GET /api/integrations/asana/workspaces`, `/projects` | internal | contract:126-127; registry:78-83 |
| Linear | `GET /api/integrations/linear/teams`, `/projects` | internal | contract:128-129 |
| Discord | `GET /api/integrations/discord/guilds` | internal | contract:130; `integrations/discord/README.md` |
| WhatsApp Business | `GET /api/integrations/whatsapp-business/phone-numbers` | private | contract:131; `integrations/whatsapp-business/README.md` |
| Microsoft Graph | `GET /api/integrations/microsoft-graph/me` | private | contract:132; `integrations/microsoft-graph/README.md` |
| Zoom | `GET /api/integrations/zoom/me` | private | contract:133; `integrations/zoom/README.md` |
| monday.com | `GET /api/integrations/monday/boards` | internal | contract:134; `integrations/monday/README.md` |
| Google Calendar | none (local `setup_calendar.py`) | private | `integrations/google/` |
| Brave Bookmarks | none (local pipeline) | private | `integrations/brave-bookmarks/README.md`, `integrations/README.md:71` |

Privacy vocabulary is `public | internal | private | restricted`
(solo-empire `9f44f602^:infra/scripts/cli/data-intake-cli.py:63`). Only LINE's
class is cited from source; every other class is marked `proposed` in the
fixture and needs owner acceptance.

## Gateway behaviour against these routes (tested with synthetic secrets)

| Check | Result on origin/main | Test |
|---|---|---|
| Signed-webhook route class (public `POST`, signature instead of Bearer) | **missing** — `ROUTE_ACCESS` has no public write route (`server.py:38-42`) | `test_signed_webhook_class_and_verification_are_recorded_as_missing` |
| LINE/Stripe delivery with a synthetic signature, no Bearer | rejected **401**, nothing proxied | `test_provider_signed_delivery_without_bearer_is_rejected` |
| Wrong Bearer on every webhook route | rejected **401**, nothing proxied | `test_bad_bearer_is_rejected_on_every_webhook_route` |
| Valid Bearer + `x-line-signature` + `stripe-signature` + `Idempotency-Key` | proxied, but **all three headers dropped** (allow-list `server.py:28`) | `test_authenticated_passthrough_drops_signature_and_idempotency_headers` |
| Signature verifier in the gateway module | **none** | `test_gateway_module_has_no_signature_verifier` |

The gateway does not implement provider signature verification, so there is no
gateway signature verifier to exercise with a bad signature; the bad-credential
test covers the Bearer check it does implement (`server.py:212-229`).

## Gaps

1. No signed-webhook route class in the gateway: LINE/Stripe cannot send the gateway Bearer, so a delivery through the gateway is always 401.
2. Even on the Bearer path the gateway strips `x-line-signature`, `stripe-signature` and `Idempotency-Key`, so an upstream cannot verify signatures and `/api/webhook/revenue` would reject (400) or lose idempotency.
3. LINE has no replay window; LINE events without `webhookEventId`/`message.id` were inserted without dedupe.
4. Dedupe for LINE/Stripe was check-then-insert with no unique index (race on concurrent redelivery).
5. `Idempotency-Key` has no retention/expiry rule; revenue has no replay window.
6. Stripe payloads were persisted verbatim (`server.ts:1079`); no redaction rule before storage.
7. 16 of 17 privacy classes are proposals, not sourced classifications.
8. The contract is `retired` and the webhook routes are 410 in the archive; no live owner for inbound provider ingress is recorded.
9. The architecture-docs contract comparison runs only when a local checkout is present (`ARCHITECTURE_DOCS_ROOT`); CI checks the vendored route list.

## Owner decision — PROPOSED, NOT ACCEPTED

Proposed for the owner to accept, amend or reject:

1. Accept this fixture as the provider/webhook inventory for the `integrations` system, including the proposed privacy classes (LINE, Stripe, revenue `restricted`; analytics and the read-only metadata providers `internal`; Notion, WhatsApp Business, Microsoft Graph, Zoom, Google Calendar, Brave Bookmarks `private`).
2. Decide where signed provider ingress lives before any route is reactivated: either (a) a gateway `signed-webhook` route class (public `POST` per provider, raw-body HMAC verified at the gateway with LINE/Stripe schemes above, Stripe 300 s tolerance, a LINE timestamp window to be chosen, and verified provider/event-id headers forwarded), or (b) direct delivery to the owning cell with the gateway staying Bearer-only. Until decided, the gateway stays as is and the routes stay retired.
3. Whichever option is chosen, require a unique `(source, external_id)` constraint, an `Idempotency-Key` retention window, and a redaction rule for stored Stripe payloads before reactivation.

No status change, runtime move, production cutover or human acceptance is
claimed by this document.

## Re-running

```bash
bash scripts/check.sh
# with the private contract checkout present, also compare the vendored route list:
ARCHITECTURE_DOCS_ROOT=../../../../bookchaowalit/private/architecture-docs bash scripts/check.sh
```
