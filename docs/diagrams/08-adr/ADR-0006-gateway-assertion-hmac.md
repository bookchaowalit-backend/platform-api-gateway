# ADR-0006 HMAC gateway assertion with per-system derived keys

- Status: accepted (retro-documented; SPEC-002 accepted 2026-11-03)

## Decision
เมื่อมี `GATEWAY_ASSERTION_MASTER_KEY` gateway ใส่ `X-Gateway-Assertion: v1.<iat>.<b64 rid>.<b64 HMAC>` ในทุก request ที่ forward; key ต่อ system = `HMAC(master, "gateway-assertion/v1/<system>")`; signed: system, method, target, iat, request id, SHA-256 ของ Authorization, Content-Type, body; window 60 s, ไม่มี replay cache; service copy `verify` เอง (cells own their code)

## Evidence
- `src/book_api_gateway/assertion.py`, `src/book_api_gateway/edge.py` `_proxy`, `scripts/assertion_key.py`, `tests/test_assertion.py` (pinned vectors), `docs/specs/002-gateway-assertion.md`, `contract.json` `migration.cutover`

## Consequences
- test vectors ต้องเปลี่ยนพร้อม habits `test_gateway_assertion.py`
- master key รั่ว = ปลอม assertion ได้ทุก system
