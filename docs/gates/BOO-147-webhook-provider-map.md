# BOO-147 — External provider and webhook map (system gate evidence)

- Issue: BOO-147 (system `integrations` in `repository-catalog/registries/system-repositories.yaml:480-503`, solo-empire `63efeeb0`)
- Next gate (verbatim): **"Map every external provider, signature check, idempotency key, and privacy class."**
- Contract: architecture-docs@a9c84727 (`a9c8472744e0f97599589a38afcd3ae5cc5c8a2a`) →
  `systems/architecture/solo-empire-api-contract-v1.md#signed-and-authenticated-webhook-routes`
  (lines 136-143; auth classes 55-61; AI and provider routes 111-134; file sha256
  `ceba7be6…0e548`, unchanged at architecture-docs origin/main `9471af55`)
- Gateway source: this repository at origin/main `6e1fb34`
- Machine-readable map: [`fixtures/gates/webhook-provider-map.json`](../../fixtures/gates/webhook-provider-map.json) (34 providers)
- Pinned source snapshot: [`fixtures/gates/webhook-provider-sources.json`](../../fixtures/gates/webhook-provider-sources.json)
- Drift tests: [`tests/test_webhook_provider_map.py`](../../tests/test_webhook_provider_map.py) (run by `bash scripts/check.sh`)

This is evidence for an owner decision. It does not change any route, does not
activate a runtime, and does not record an accepted decision.

## Scope of "every provider" (what the tests enforce)

"Every" means every provider reachable from the sources pinned in
`webhook-provider-sources.json`, and every route in this gateway. Each source
is pinned by commit, git blob and sha256, and the relevant lines are copied
verbatim. In CI (no sibling checkout needed) the tests fail if any of these is
unmapped or lacks a required field:

| Pinned source | What is derived from it | Test |
|---|---|---|
| architecture-docs@a9c84727 `solo-empire-api-contract-v1.md` lines 55-61, 111-143 | every webhook row, every AI/integration route row, the signed-webhook auth class | `test_contract_webhook_section_matches_snapshot`, `test_every_contract_ai_and_integration_route_is_mapped`, `test_signed_webhook_auth_class_matches_snapshot` |
| solo-empire@981a12db `infra/scripts/sync/integration_health.py` (every `def check_*` line and the live probe list, lines 1103-1134). This is the probe set behind `GET /api/integrations/health` | 28 external probes, active or paused | `test_every_health_probe_is_mapped` |
| solo-empire@981a12db `infra/scripts/sync/discover_external_apps.py:26-27`. These are the sources behind `GET /api/integrations/discovery` | `APIS_GURU_URL`, `MCP_REGISTRY_URL` | `test_every_discovery_source_is_mapped` |
| solo-empire@328b2537 `infra/api/ai_gateway.ts:274-287`. This is the provider behind `POST /api/ai/generate` and `GET /api/ai/status` (the last tree before `/api/ai/*` was retired in `72c1cd98`) | `openai-compatible` provider and its `AI_GATEWAY_*` credential names | `test_every_ai_gateway_provider_is_mapped` |
| solo-empire@981a12db `integrations/` tree (14 files, 8 provider dirs; the directory was removed in `daf06f31`) | every provider directory | `test_every_integrations_directory_is_mapped` |
| this repo `server.py` `ROUTE_ACCESS`, path literals, `contract.json` interfaces | every gateway route class | `GatewaySourceCoverageTests` |

With local checkouts (`ARCHITECTURE_DOCS_ROOT`, `SOLO_EMPIRE_ROOT`, or the Book
Dev sibling layout), `LiveSourceDriftTests` also re-read each pinned line and
sha256 from git. They also check that the working-tree contract still matches
the pin. CI skips these three tests.

Providers used by solo-empire code outside these sources are **not** claimed
(for example, adapters in other cells, such as `solo-ai-gateway`, `solo-crm`
and `solo-integrations`).

## Where the routes live today

| Location | State | Evidence |
|---|---|---|
| Contract `solo-empire-api-contract-v1.md` | `status: retired` (2026-10-11); kept as the historical contract | contract front matter lines 7-8, 16 |
| solo-empire `integrations/` | **Directory removed** in `daf06f31` (2026-10-11). Mapped from `981a12db` | snapshot `trees.integrations_dir` |
| solo-empire `infra/api/server.ts` | Removed; last live LINE/Stripe handlers at `1d0e04bb`, last live analytics/revenue handlers at `aa567aab`, last live AI gateway at `328b2537` | see table citations |
| `bookchaowalit/platform-legacy-api-archive` @ `74b68443` | Webhook routes return **410 Gone** behind the `api:write` Bearer guard; `/api/ai/*` returns 410; `line.ts` / `stripe.ts` verifiers kept but no longer imported | `server.ts:541-546`, `server.ts:961-990` |
| This gateway (`src/book_api_gateway/server.py`) | **No webhook or provider route.** Only `/healthz`, `/readyz` (public GET) and `/api/*` (Bearer, GET/POST passthrough) | `server.py:38-42` |

No inbound provider webhook is served anywhere in scope right now. The map is
the contract and source inventory, plus what the gateway would do if a
provider delivery reached it.

## Inbound webhook routes (contract section)

| Route | Direction | Signature scheme / header | Verification location | Idempotency key source | Replay window | Privacy class |
|---|---|---|---|---|---|---|
| `POST /api/webhook/line` | inbound (+ outbound health probe `api.line.me/v2/bot/info`, `integration_health.py:259`) | HMAC-SHA256(raw body), base64, `x-line-signature`; secret ref `LINE_SOLO_EMPIRE_WEBHOOK_SECRET`; 401 on mismatch, 503 unconfigured | archive `line.ts:8-23`; called at solo-empire `1d0e04bb:infra/api/server.ts:975`. **Gateway: missing** | `event.webhookEventId`, else `event.message.id` (`line.ts:34-42`); `webhook_log(source,external_id)` lookup (`server.ts:1004-1012`) | **missing**: no timestamp check (`server.ts:965-1031`) | `restricted` (cited: `integrations/line/README.md:97-101`) |
| `POST /api/webhook/stripe` | inbound (+ outbound `GET api.stripe.com/v1/balance`, `integration_health.py:288`, ref `STRIPE_SECRET_KEY`) | Stripe v1: HMAC-SHA256 hex of `${t}.${rawBody}`, `stripe-signature`; secret ref `STRIPE_WEBHOOK_SECRET`; 400 on mismatch, 503 unconfigured | archive `stripe.ts:12-53`; called at `1d0e04bb:infra/api/server.ts:1046`. **Gateway: missing** | Stripe event `id`; `webhook_log` lookup (`server.ts:1062-1079`) | **300 s** on `t` (`stripe.ts:17,33-37`) | `restricted` (proposed: raw event body stored verbatim, `server.ts:1079`) |
| `POST /api/webhook/analytics` | inbound (internal caller) | none; Bearer `api:write` via `/api/webhook/*` guard (refs `API_TOKEN`, `API_TOKENS_JSON`) | `aa567aab:infra/api/server.ts:1294-1300`. Gateway: Bearer only (`server.py:212-229`) | natural key `(asset_id, metric_date)` upsert (`server.ts:1416-1487`) | not applicable (idempotent upsert) | `internal` (proposed) |
| `POST /api/webhook/revenue` | inbound (internal caller) | none; Bearer `api:write` | `aa567aab:infra/api/server.ts:1294-1300`. Gateway: Bearer only | `Idempotency-Key` header, 1..255 chars, duplicate → `{success, id, duplicate:true}` (`server.ts:1492-1531`) | **missing** (no timestamp, no key expiry) | `restricted` (proposed: finance ledger rows) |

## Outbound providers (health probes, provider read routes, discovery, AI)

None of these receive provider deliveries. Signature, idempotency and replay
are therefore `not-applicable`. The one exception is the AI provider, whose
idempotency is `none`. Each outbound provider was reached only through a
Bearer-protected route. Credential columns list **reference names only**; the
fixture test rejects anything that is not an upper-case name.

| Provider | Reached via | Source probe / key | Outbound call | Credential reference names (never values) | Privacy (proposed) |
|---|---|---|---|---|---|
| Sentry | `GET /api/integrations/health`, `GET /api/integrations/sentry/issues` | `check_sentry (active)` | `https://sentry.io/api/0/organizations/{org}/` (integration_health.py:326) | `SENTRY_AUTH_TOKEN`, `SENTRY_ORG_SLUG`, `SENTRY_BASE_URL` | internal |
| PostHog | `GET /api/integrations/health`, `GET /api/integrations/posthog/insights` | `check_posthog (active)` | `https://us.posthog.com/api/projects/{project}/insights/` (integration_health.py:373) | `POSTHOG_API_KEY`, `POSTHOG_PROJECT_ID`, `POSTHOG_HOST` | internal |
| Slack | `GET /api/integrations/health`, `GET /api/integrations/slack/channels` | `check_slack (active)` | `https://slack.com/api/auth.test` (integration_health.py:403) | `SLACK_BOT_TOKEN` | internal |
| Notion | `GET /api/integrations/health`, `GET /api/integrations/notion/search` | `check_notion (active)` | `https://api.notion.com/v1/search` (integration_health.py:441) | `NOTION_BOT_TOKEN` | private |
| Asana | `GET /api/integrations/asana/projects`, `GET /api/integrations/asana/workspaces`, `GET /api/integrations/health` | `check_asana (active)` | `https://app.asana.com/api/1.0/workspaces` (integration_health.py:480) | `ASANA_PERSONAL_ACCESS_TOKEN` | internal |
| Linear | `GET /api/integrations/health`, `GET /api/integrations/linear/projects`, `GET /api/integrations/linear/teams` | `check_linear (active)` | `https://api.linear.app/graphql` (integration_health.py:516) | `LINEAR_API_KEY` | internal |
| Discord | `GET /api/integrations/discord/guilds`, `GET /api/integrations/health` | `check_discord (active)` | `https://discord.com/api/v10/users/@me` (integration_health.py:561) | `DISCORD_BOT_TOKEN` | internal |
| WhatsApp Business Cloud API | `GET /api/integrations/health`, `GET /api/integrations/whatsapp-business/phone-numbers` | `check_whatsapp_business (active)` | `https://graph.facebook.com/{version}/{waba_id}` (integration_health.py:610) | `WHATSAPP_CLOUD_API_TOKEN`, `WHATSAPP_BUSINESS_ACCOUNT_ID` | private |
| Microsoft Graph | `GET /api/integrations/health`, `GET /api/integrations/microsoft-graph/me` | `check_microsoft_graph (active)` | `https://graph.microsoft.com/v1.0/me` (integration_health.py:648) | `MICROSOFT_GRAPH_ACCESS_TOKEN` | private |
| Zoom | `GET /api/integrations/health`, `GET /api/integrations/zoom/me` | `check_zoom (active)` | `https://api.zoom.us/v2/users/me` (integration_health.py:688) | `ZOOM_ACCESS_TOKEN` | private |
| monday.com | `GET /api/integrations/health`, `GET /api/integrations/monday/boards` | `check_monday (active)` | `https://api.monday.com/v2` (integration_health.py:730) | `MONDAY_API_TOKEN` | internal |
| Google Calendar (local setup script) | `GET /api/integrations/health` | `check_google_calendar (active)` | `https://www.googleapis.com/calendar/v3/calendars/primary` (integration_health.py:82) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | private |
| Brave Bookmarks (local lake-first pipeline) | none (local only) | `-` | - | none | private |
| Gmail API | `GET /api/integrations/health` | `check_gmail (active)` | `https://gmail.googleapis.com/gmail/v1/users/me/labels` (integration_health.py:103) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | restricted |
| Google Drive API | `GET /api/integrations/health` | `check_google_drive (active)` | `https://www.googleapis.com/drive/v3/files` (integration_health.py:124) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | private |
| GitHub API | `GET /api/integrations/health` | `check_github (active)` | `https://api.github.com/user` (integration_health.py:148) | `GITHUB_PERSONAL_ACCESS_TOKEN` | internal |
| Cloudflare API | `GET /api/integrations/health` | `check_cloudflare (active)` | `https://api.cloudflare.com/client/v4/user/tokens/verify` (integration_health.py:172) | `CLOUDFLARE_API_TOKEN` | internal |
| Vercel API | `GET /api/integrations/health` | `check_vercel (active)` | `https://api.vercel.com/v9/projects?limit=1` (integration_health.py:193) | `VERCEL_TOKEN`, `VERCEL_TEAM_ID` | internal |
| Render API | `GET /api/integrations/health` | `check_render (active)` | `https://api.render.com/v1/services?limit=1` (paas_health.py:174) | `RENDER_API_KEY` | internal |
| Railway GraphQL API | `GET /api/integrations/health` | `check_railway (active)` | `https://backboard.railway.com/graphql/v2` (paas_health.py:201) | `RAILWAY_TOKEN`, `RAILWAY_API_TOKEN` | internal |
| Fly.io Machines API | `GET /api/integrations/health` | `check_fly_io (active)` | `https://api.machines.dev/v1/apps` (paas_health.py:233) | `FLY_API_TOKEN`, `FLY_TOKEN`, `FLY_ORG_SLUG` | internal |
| Heroku Platform API | `GET /api/integrations/health` | `check_heroku (active)` | `https://api.heroku.com/account` (paas_health.py:260) | `HEROKU_TOKEN`, `HEROKU_API_KEY` | internal |
| Telegram Bot API | `GET /api/integrations/health` | `check_telegram (active)` | `https://api.telegram.org/bot<token>/getMe` (integration_health.py:233) | `TELEGRAM_INFRA_BOT_TOKEN`, `TELEGRAM_BOT_TOKEN` | internal |
| Leantime (MCP endpoint) | `GET /api/integrations/health` | `check_leantime (active)` | `https://mcp.project.cocofriday.com/mcp` (integration_health.py:851) | none | internal |
| Todoist API | `GET /api/integrations/health` | `check_todoist (active)` | `https://api.todoist.com/api/v1/projects` (integration_health.py:887) | `TODOIST_API_TOKEN` | private |
| Strava API | `GET /api/integrations/health` | `check_strava (paused)` | `https://www.strava.com/api/v3/athlete` (integration_health.py:911) | `STRAVA_ACCESS_TOKEN` | restricted |
| Binance TH API | `GET /api/integrations/health` | `check_binance_th (paused)` | `https://api.binance.th/api/v3/ping` (integration_health.py:936) | `BINANCE_TH_API_KEY`, `BINANCE_TH_API_SECRET` | restricted |
| APIs.guru directory | `GET /api/integrations/discovery` | `APIS_GURU_URL` | `https://api.apis.guru/v2/list.json` (discover_external_apps.py:26) | none | public |
| MCP Registry | `GET /api/integrations/discovery` | `MCP_REGISTRY_URL` | `https://registry.modelcontextprotocol.io/v0.1/servers` (discover_external_apps.py:27) | none | public |
| LLM provider behind the AI gateway (AI_GATEWAY_PROVIDER=openai-compatible) | `POST /api/ai/generate` | `openai-compatible` | `HTTPS AI_GATEWAY_BASE_URL` (ai_gateway.ts:274-287) | `AI_GATEWAY_PROVIDER`, `AI_GATEWAY_BASE_URL`, `AI_GATEWAY_API_KEY` | private |

Evidence lines in the outbound-call column refer to solo-empire@981a12db, except
`ai_gateway.ts` (solo-empire@328b2537). `paas_health.py` is at
`infra/scripts/platform/`; the others are at `infra/scripts/sync/`.

Privacy vocabulary is `public | internal | private | restricted`
(solo-empire `9f44f602^:infra/scripts/cli/data-intake-cli.py:63`). Only LINE's
class is cited from source. The other 33 are marked `proposed` in the fixture
and need owner acceptance.

## Gateway behaviour against these routes (tested with synthetic secrets)

| Check | Result on origin/main | Test |
|---|---|---|
| Signed-webhook route class (public `POST`, signature instead of Bearer) | **missing**: `ROUTE_ACCESS` has no public write route (`server.py:38-42`) | `test_signed_webhook_class_and_verification_are_recorded_as_missing` |
| LINE/Stripe delivery with a synthetic signature, no Bearer | rejected **401**, nothing proxied | `test_provider_signed_delivery_without_bearer_is_rejected` |
| Wrong Bearer on every webhook route | rejected **401**, nothing proxied | `test_bad_bearer_is_rejected_on_every_webhook_route` |
| Valid Bearer + `x-line-signature` + `stripe-signature` + `Idempotency-Key` | proxied, but **all three headers dropped** (allow-list `server.py:28`) | `test_authenticated_passthrough_drops_signature_and_idempotency_headers` |
| Signature verifier in the gateway module | **none** (no signature/webhook names, no `hmac.new`/`hmac.digest`) | `test_gateway_module_has_no_signature_verifier` |

The gateway does not implement provider signature verification, so there is no
gateway signature verifier to exercise with a bad signature. The bad-credential
test covers the Bearer check that the gateway does implement (`server.py:212-229`).

## Gaps

1. No signed-webhook route class in the gateway. LINE and Stripe cannot send the gateway Bearer, so a delivery through the gateway always gets 401.
2. Even on the Bearer path, the gateway strips `x-line-signature`, `stripe-signature` and `Idempotency-Key`. An upstream therefore cannot verify signatures, and `/api/webhook/revenue` would reject the request (400) or lose idempotency.
3. LINE has no replay window. LINE events without `webhookEventId`/`message.id` were inserted without dedupe.
4. Dedupe for LINE/Stripe was check-then-insert with no unique index. This was safe in the single synchronous SQLite process, but it is a race for a multi-instance cell.
5. `Idempotency-Key` has no retention/expiry rule; revenue has no replay window.
6. Stripe payloads were persisted verbatim (`server.ts:1079`); no redaction rule before storage.
7. `POST /api/ai/generate` has no idempotency key, so caller retries can duplicate provider spend.
8. The Leantime probe sends no credential; the endpoint's own auth is not visible in this source.
9. 33 of 34 privacy classes are proposals, not sourced classifications.
10. The contract is `retired`, and the webhook and `/api/ai/*` routes are 410 in the archive. No live owner for inbound provider ingress is recorded.
11. Providers used outside the pinned sources (other cells) are out of scope for this map.

## Owner decision — PROPOSED, NOT ACCEPTED

Proposed for the owner to accept, amend or reject:

1. Accept this fixture as the provider/webhook inventory for the `integrations` system, within the scope above, including the proposed privacy classes:
   - `restricted`: LINE, Stripe, revenue, Gmail, Strava, Binance TH.
   - `public`: discovery directories.
   - `private`: personal-workspace providers and the AI provider.
   - `internal`: the rest.
2. Decide where signed provider ingress lives before any route is reactivated. Until decided, the gateway stays as it is and the routes stay retired.
   - (a) A gateway `signed-webhook` route class. This means:
     - a public `POST` route per provider;
     - raw-body HMAC verified at the gateway with the LINE/Stripe schemes above;
     - the Stripe 300 s tolerance, and a LINE timestamp window still to be chosen;
     - verified provider and event-id headers forwarded upstream.
   - (b) Direct delivery to the owning cell, with the gateway staying Bearer-only.
3. Whichever option is chosen, require these before reactivation:
   - a unique `(source, external_id)` constraint;
   - an `Idempotency-Key` retention window;
   - a redaction rule for stored Stripe payloads.

No status change, runtime move, production cutover or human acceptance is
claimed by this document.

## Re-running

```bash
bash scripts/check.sh
# with local checkouts, also verify the pinned snapshot against git:
ARCHITECTURE_DOCS_ROOT=../../../../bookchaowalit/private/architecture-docs \
SOLO_EMPIRE_ROOT=../../../../../../../../.. bash scripts/check.sh
```
