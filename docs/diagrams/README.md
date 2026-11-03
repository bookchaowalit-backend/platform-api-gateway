# Core 22 SDLC diagram pack — platform-api-gateway

ชุดภาพ Core 22 ตาม SDLC Diagram Catalog v2 วาดจากโค้ดและ config ใน repo นี้ (ณ `origin/main` `4c81817`, 2026-11-03)
repo นี้คือ **edge API gateway** ของ Book Platform: Python standard library บน Railway (Singapore) หลัง Cloudflare ที่ `https://gateway.bookchaowalit.com/v1/<system>/<path>` (SPEC-001) และเซ็น `X-Gateway-Assertion` ให้ service (SPEC-002); มี pilot `/api/*` เดิมที่ไม่ได้เปิดใน production

ทุกไฟล์มี `Sources:` ใต้ภาพ และ "Open questions" สำหรับสิ่งที่ยืนยันจากโค้ดไม่ได้

| # | Item | Status | File | Sources read |
|---|---|---|---|---|
| 01 | Business process As-Is / To-Be | done | [01-business-process.md](01-business-process.md) | `edge.py`, `server.py`, `contract.json`, SPEC-001/002, `docs/UPGRADE-PLAN.md`, `PRODUCT.md` |
| 02 | Use cases | done | [02-use-cases.md](02-use-cases.md) | `server.py` `ROUTE_ACCESS`, `edge.py`, scripts, `API.md` |
| 03 | User flows | done | [03-user-flows.md](03-user-flows.md) | `edge.py`, `server.py`, `config.py`, `API.md` |
| 04 | Traceability (RTM) | done | [04-traceability.md](04-traceability.md) | SPEC-001, SPEC-002, `src/`, `tests/`, `check.yml` |
| 05 | C4 Context | done | [05-c4-context.md](05-c4-context.md) | `routes.json`, `API.md`, `contract.json`, uptime-worker `targets.ts` |
| 06 | C4 Container | done | [06-c4-container.md](06-c4-container.md) | `Dockerfile`, `railway.toml`, `src/` |
| 07 | C4 Component | done | [07-c4-component.md](07-c4-component.md) | `src/book_api_gateway/*.py`, `scripts/` |
| 08 | ADRs | done (6) | [08-adr/](08-adr/) | `Dockerfile`, specs, `jwt_verify.py`, `routes.py`, `assertion.py`, `PRODUCT.md` |
| 09 | ERD | done (config + in-memory; no DB) | [09-erd.md](09-erd.md) | `routes.json`, `routes.py`, `jwt_verify.py`, `limiter.py`, `assertion.py` |
| 10 | Sequences | done (4) | [10-sequences.md](10-sequences.md) | `edge.py`, `jwt_verify.py`, `assertion.py` |
| 11 | State machines | done (4) | [11-state-machines.md](11-state-machines.md) | `jwt_verify.py`, `limiter.py`, SPEC-002, `contract.json` |
| 12 | API & integrations | reused + extended | [12-api-integration.md](12-api-integration.md) → [`API.md`](../../API.md), [BOO-147 gate](../gates/BOO-147-webhook-provider-map.md) | `API.md`, `contract.json`, `edge.py`, `server.py` |
| 13 | Threat model | done | [13-threat-model.md](13-threat-model.md) | `src/`, specs, architecture-docs `network-architecture.md` |
| 14 | Backup & DR | done (no data store) | [14-backup-dr.md](14-backup-dr.md) | `contract.json`, `railway.toml`, `UPGRADE-PLAN.md`, Railway deployments |
| 15 | CI/CD pipeline | done | [15-cicd-pipeline.md](15-cicd-pipeline.md) | `check.yml`, `scripts/check.sh`, platform-ci-workflows `ci-python.yml` @ `87dc5e1c`, `gh run` |
| 16 | Deployment | done | [16-deployment.md](16-deployment.md) | `railway.toml`, `Dockerfile`, `API.md`, Railway deployments |
| 17 | Test coverage matrix | done | [17-test-coverage-matrix.md](17-test-coverage-matrix.md) | `tests/*.py`, `scripts/check.sh` |
| 18 | Git & release workflow | done | [18-git-release-workflow.md](18-git-release-workflow.md) | `git log`, `gh pr list`, `check.yml` |
| 19 | Service dependency map | done | [19-service-dependency-map.md](19-service-dependency-map.md) | `routes.json`, `generate_routes.py`, consumer repos (grep) |
| 20 | Observability | done | [20-observability.md](20-observability.md) | `server.py`, `railway.toml`, `PRODUCT.md`, uptime-worker `targets.ts` |
| 21 | Incident response | done | [21-incident-response.md](21-incident-response.md) | uptime worker, `edge.py` errors, `contract.json` rollback |
| 22 | DORA | done (4/5 computed; recovery time not measurable in production) | [22-dora.md](22-dora.md) | `git log`, `gh run list`, Railway `list-deployments` |

## ADR list

- [ADR-0001](08-adr/ADR-0001-standard-library-only-runtime.md) Standard-library-only Python runtime
- [ADR-0002](08-adr/ADR-0002-railway-behind-cloudflare-origin-lock.md) Railway หลัง Cloudflare + origin-lock header
- [ADR-0003](08-adr/ADR-0003-pass-through-rs256-verification.md) ตรวจ RS256 ที่ edge แล้วส่ง token ต่อ
- [ADR-0004](08-adr/ADR-0004-committed-route-table-from-registry.md) Route table ที่ generate จาก registry แล้ว commit
- [ADR-0005](08-adr/ADR-0005-stdout-telemetry-no-sentry.md) Telemetry บน stdout แทน Sentry
- [ADR-0006](08-adr/ADR-0006-gateway-assertion-hmac.md) Gateway assertion HMAC ด้วย key ต่อ system

## Related docs (reused, not copied)

[`README.md`](../../README.md), [`PRODUCT.md`](../../PRODUCT.md), [`API.md`](../../API.md), [`docs/specs/001-edge-gateway.md`](../specs/001-edge-gateway.md), [`docs/specs/002-gateway-assertion.md`](../specs/002-gateway-assertion.md), [`docs/UPGRADE-PLAN.md`](../UPGRADE-PLAN.md), [`docs/gates/BOO-147-webhook-provider-map.md`](../gates/BOO-147-webhook-provider-map.md), central: [network-architecture.md](https://github.com/bookchaowalit/architecture-docs/blob/main/systems/architecture/network-architecture.md) (NET-04, NET-07)
