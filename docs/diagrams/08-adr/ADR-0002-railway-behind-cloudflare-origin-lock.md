# ADR-0002 Railway (Singapore) behind Cloudflare with an origin-lock header

- Status: accepted (retro-documented)
- Date: 2026-11-03

## Context
Network review (NET-04) พบว่า API ถูกเรียกตรงบน `*.up.railway.app` ไม่มี WAF/rate limit ที่ edge

## Decision
host บน Railway project `platform-api-gateway` service `gateway` (Singapore, serverless) ใต้ custom domain `gateway.bookchaowalit.com` ที่ proxied โดย Cloudflare; Cloudflare Transform Rule ใส่ `X-Gateway-Edge` และ gateway ตอบ 403 ถ้า header ไม่ตรง `GATEWAY_EDGE_SECRET`; `CF-Connecting-IP` เชื่อถือได้หลังผ่าน lock เท่านั้น

## Evidence
- `railway.toml` (DOCKERFILE builder, healthcheck `/healthz`)
- `src/book_api_gateway/edge.py` `handle_v1` (`EDGE_HEADER`, `hmac.compare_digest`)
- `API.md` (Edge routes: zone rules, BIC off, 60 req / 10 s rule)
- `docs/specs/001-edge-gateway.md` R2; architecture-docs `systems/architecture/network-architecture.md` NET-04
- ops record: api-gateway-edge (2026-11-03): service has no Railway domain (`*.up.railway.app` → 404)

## Consequences
- `/healthz` และ `/readyz` ไม่ผ่าน edge lock (เพื่อ platform probe)
- Cloudflare Free plan: rate-limit rule ได้ 1 rule
