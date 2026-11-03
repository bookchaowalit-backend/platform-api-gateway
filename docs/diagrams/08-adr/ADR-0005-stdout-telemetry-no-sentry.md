# ADR-0005 Redacted stdout telemetry instead of Sentry

- Status: accepted (retro-documented)
- Date: 2026-11-03 (`c998368`, PRODUCT.md waiver `8f9775a`)

## Decision
หนึ่งบรรทัด JSON `request.completed` ต่อ request บน **stdout** (method, route class, system, status, latency_ms, request_id, subject_hash); ไม่มี token, path tail, query, body; ไม่ใช้ sentry-sdk (ADR-0001); stdout เพราะ Railway ทำเครื่องหมาย stderr เป็น error

## Evidence
- `src/book_api_gateway/server.py` `_default_telemetry`, `_handle_request`, `log_message` (ปิด default access log)
- `PRODUCT.md` (Sentry waiver), `tests/test_edge.py` `test_telemetry_never_carries_token_or_path_tail`

## Consequences
- ไม่มี alert อัตโนมัติจาก 5xx; มีแค่ uptime probe รายชั่วโมง (ดู [20](../20-observability.md))
