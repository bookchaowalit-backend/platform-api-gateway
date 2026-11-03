# Product

<!-- impeccable:product-schema 1 -->

## Platform

contract (Book Platform boundary, `book-platform.contract.v1`)

## Users

- The owner and the agents that change the Book Platform: they read this boundary before
  touching the `api-gateway` capability anywhere else.
- Other platform repositories and cells, which may depend on this boundary only through its
  versioned API or event contracts, never its database or private modules.

## Product Purpose

Own the `api-gateway` capability (routing, request identity, rate limiting, ingress policy) as a written, checked contract, so the capability can move
out of the `solo-empire` control plane later without consumers noticing.

Success: the contract stays valid against the pinned shared schema, the registry entry matches
it, and every gate in `fixtures/gates/` and the gateway tests pass in CI.

## Positioning

A boundary contract with offline evidence, not a running service. A dependency-free local HTTP pilot (`src/book_api_gateway/`): bearer-token checks with a per-client failure rate limit, route access rules and the webhook provider map (`fixtures/gates/`).

## Operating Context

- Status: contract `pilot`; the runtime is live since 2026-11-03 at `https://gateway.bookchaowalit.com`
  (Railway, Singapore, behind Cloudflare with the `X-Gateway-Edge` origin lock and a rate-limit rule;
  SPEC-001). Consumers move one at a time; rollback is pointing a consumer back at its direct URL.
- CI: shared `ci-python` (Ruff and `scripts/check.sh` on Python 3.11 and 3.12) and the shared
  security workflow, on GitHub-hosted runners (public repository). Deploys are Railway CLI uploads.

Sentry waiver: SPEC-001 R8 keeps the gateway standard-library only (no sentry-sdk) and R7 keeps exception text out of telemetry; every failure is a `request.completed` line on stdout with its status (500/502) and request id in the Railway logs, and the uptime worker checks the gateway hourly.
- The open `codex/shared-infrastructure-20261015` pull request (decision D8) is outside this
  document.

## Capabilities and Constraints

- `scripts/check.py`: validates `contract.json` against the vendored schema;
  `scripts/check_schema_pin.py`: the vendored schema matches the pinned canonical hash.
- No production provider integration, database writer, credential or customer payload.
- Out of scope: running the capability; it stays in its current implementation until parity
  and rollback evidence permit a cutover.

## Measures

- `scripts/check.sh` green on `main` (target: always).
- Drift between `contract.json` and the registry entry (target: 0).
- [ต้องยืนยัน] The cutover criteria for activating the runtime.
