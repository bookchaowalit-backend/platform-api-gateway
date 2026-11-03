# ADR-0004 Committed route table generated from the hub registry

- Status: accepted (retro-documented)
- Date: 2026-11-03

## Decision
`routes.json` สร้างจาก `online-systems.yaml` ด้วย `scripts/generate_routes.py --registry` แล้ว commit; runtime ไม่อ่าน hub; รับเฉพาะ `https`, ไม่มี path/query/credential, id ตาม `[a-z][a-z0-9-]{1,62}`; route ผิด = gateway ไม่ start

## Evidence
- `scripts/generate_routes.py` (`SKIP_KINDS`, `SKIP_IDS`), `src/book_api_gateway/routes.py` (`load_routes`), `routes.json` (version 1, 44 routes), `tests/test_routes.py`, `Dockerfile` (`COPY routes.json`)

## Consequences
- เพิ่ม/ย้าย system = regenerate + commit + deploy ใหม่
- rollback ของ route = git revert + redeploy หรือ Railway rollback
