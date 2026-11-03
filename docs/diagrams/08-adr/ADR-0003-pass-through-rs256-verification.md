# ADR-0003 Verify RS256 at the edge, pass the token through

- Status: accepted (retro-documented)
- Date: 2026-11-03

## Context
ทุก service ตรวจ token เอง; token ขยะจำนวนมากกระทบทุก service และ DB pool

## Decision
gateway ตรวจ signature/iss/exp/nbf/iat/sub/aud กับ JWKS ของ trusted issuers (`GATEWAY_TRUSTED_ISSUERS`), token ไม่มี `kid` (empire-platform) ลองทีละ key สูงสุด 8, JWKS cache 10 นาที, refetch ไม่เกินครั้งละ 1 นาที, keys โหลดไม่ได้ = 503 (fail closed); แล้ว **forward token เดิม** ให้ service ตรวจ audience/scope เอง

## Evidence
- `src/book_api_gateway/jwt_verify.py` (`KEYS_TTL_SECONDS`, `REFETCH_MIN_SECONDS`, `MAX_KEYS_WITHOUT_KID`, `KeysUnavailable`)
- `src/book_api_gateway/edge.py` (`FORWARD_REQUEST` includes `Authorization`)
- `docs/specs/001-edge-gateway.md` R3; `tests/test_jwt_verify.py`
- `scripts/generate_routes.py` `SKIP_IDS` (identity และ ai-gateway ไม่อยู่หลัง JWT check)

## Consequences
- gateway ไม่มี authorization ต่อ consumer; consumer ที่ใช้ token อื่น (CRM owner token, solo-web service key) ยังเรียก direct
