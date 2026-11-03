# ADR-0001 Standard-library-only Python runtime

- Status: accepted (retro-documented)
- Date: 2026-11-03 (decision visible since the pilot; restated as SPEC-001 R8)

## Context
gateway อยู่หน้า service ทุกตัวของ registry; dependency ทุกตัวเพิ่ม supply-chain risk และขนาด image

## Decision
ใช้ Python standard library เท่านั้น (`http.server.ThreadingHTTPServer`, `urllib`, `hmac`, `hashlib`); RS256 verify เขียนเองด้วย RSA public-key operation + PKCS#1 v1.5 (public data เท่านั้น)

## Evidence
- `Dockerfile`: "Standard library only: no dependency install step (SPEC-001 R8)"; ไม่มี `pip install`
- `.github/workflows/check.yml`: `install-command: "true"`
- `src/book_api_gateway/jwt_verify.py` (`rs256_valid`, `SHA256_PREFIX`)
- `docs/specs/001-edge-gateway.md` R8; `PRODUCT.md` (Sentry waiver: no sentry-sdk)

## Consequences
- ไม่มี Sentry SDK → error ดูจาก stdout telemetry ใน Railway logs (ดู ADR-0005)
- `scripts/generate_routes.py` ต้องใช้ PyYAML เฉพาะ local tooling
