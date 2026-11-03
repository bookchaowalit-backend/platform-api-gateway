# platform-api-gateway

`API Gateway` platform boundary for the Book Platform portfolio.

## Scope

This repository owns the `api-gateway` capability: routing, request identity, rate limiting, ingress policy.
The current source implementation is recorded as `infra/api/server.ts` in the
parent registry. This checkout contains a dependency-free local HTTP pilot; it
does not contain production provider integration, a database writer, or a
customer payload.

## Edge gateway (SPEC-001)

`/v1/<system>/<path>` is the production ingress for the registry's services:
`https://gateway.bookchaowalit.com`, proxied by Cloudflare, on Railway (Singapore). It
rejects requests that did not come through Cloudflare (`X-Gateway-Edge`), verifies RS256
tokens from the trusted issuers (platform-identity, empire-platform) against their JWKS,
limits failed tokens per client IP and requests per subject, adds `X-Request-ID`, HSTS and
`nosniff`, and passes the caller's token through so each service keeps its own audience and
scope checks. Routes come from `routes.json`, generated from the hub registry with
`scripts/generate_routes.py --registry <online-systems.yaml>` and committed; the gateway never
reads the hub. Requirements and acceptance criteria:
[docs/specs/001-edge-gateway.md](docs/specs/001-edge-gateway.md); surface: [API.md](API.md).
Consumers move one at a time; the direct service URLs keep working until a cutover is recorded.

## Boundary

- Owner: `bookchaowalit-backend`
- Repository: `platform-api-gateway`
- Target remote: `https://github.com/bookchaowalit-backend/platform-api-gateway.git` (Railway project `platform-api-gateway`, service `gateway`, CLI deploy of `git archive main`)
- Contract: `book-platform.contract.v1`
- Status: `pilot` (contract stage, as for the other live Book Platform services; the edge `/v1/` has been live since 2026-11-03 at `https://gateway.bookchaowalit.com`, and the pilot `/api/*` is unset in production)
- Data owner: the platform boundary identified in `contract.json`

The platform communicates through versioned API or event contracts. Consumers
must not import another platform's database, migration, or private runtime
module. `solo-empire` remains the control plane and compatibility adapter until
parity and rollback evidence permit a cutover.

## Local verification

Run from this repository:

```bash
bash scripts/check.sh
```

The check validates `contract.json` against
[`schema/book-platform.contract.v1.schema.json`](schema/book-platform.contract.v1.schema.json),
confirms that the README and [`API.md`](API.md) agree with the contract, and
runs the unit tests: routing/authentication behavior, path and request-body
hardening, rate limiting, upstream timeout handling, and telemetry redaction.
GitHub Actions runs the same command on every push and pull request
(`.github/workflows/check.yml`). Planned work is tracked in
[`docs/UPGRADE-PLAN.md`](docs/UPGRADE-PLAN.md).
It uses only loopback fixtures and does not claim deployment, provider
connectivity, data migration, or production readiness.

Gate evidence for BOO-147 (external providers, webhook signatures, idempotency
keys and privacy classes) is in
[`docs/gates/BOO-147-webhook-provider-map.md`](docs/gates/BOO-147-webhook-provider-map.md).
The map is `fixtures/gates/webhook-provider-map.json`, derived from the pinned
source snapshot `fixtures/gates/webhook-provider-sources.json` and enforced by
`tests/test_webhook_provider_map.py`.

`scripts/check_schema_pin.py` fails when the vendored schema no longer
matches the sha256 pinned in `schema/book-platform.contract.v1.schema.json.sha256`
(the canonical copy lives in `bookchaowalit-backend-core/contracts/`; change it
there first, then copy the schema and its pin here). Pass
`--canonical ../platform-backend-core` to also compare with a local
checkout. `python3 scripts/check_registry_alignment.py --solo-empire ../solo-empire`
compares this contract with the parent platform registry (local only; read-only).

The pilot exposes `GET /healthz` and authenticated `GET`/`POST /api/*` routes.
Set `BOOK_API_GATEWAY_TOKEN`, `UPSTREAM_BASE_URL`, and (when the upstream is
not loopback) `UPSTREAM_ALLOWED_HOSTS` before starting
`PYTHONPATH=src python3 -m book_api_gateway.server`.
The complete endpoint and security inventory is in [`API.md`](API.md).

## Migration gate

Before activating a remote or changing a consumer, add sanitized fixtures for
success, duplicate delivery, timeout and provider failure; prove tenant/privacy
isolation; compare the old and new contract; and rehearse rollback on a
disposable state store. Record the evidence in the parent platform registry.
