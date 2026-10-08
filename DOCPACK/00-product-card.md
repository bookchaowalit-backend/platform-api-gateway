---
title: Book API Gateway — Product Card
doc_id: CARD-book-api-gateway
doc_type: product-card
verdict: showcase
version: 0.1
date: 2026-10-08
status: ร่างเพื่อพิจารณา
owner: Product owner (Book Dev)
---

# Book API Gateway — Product Card

## 1. สรุปคุณค่าในหนึ่งประโยค

pilot HTTP gateway แบบไม่มี dependency ที่ยืนยันตัวตนด้วย bearer token, จำกัด rate, กัน path อันตราย และ proxy ไปยัง upstream ที่อยู่ใน allow-list

## 2. ปัญหาและผู้ใช้เป้าหมาย

- ปัญหา: ผลิตภัณฑ์ภายในต้องมีจุดเข้าเดียวที่บังคับ authentication, rate limit และ ingress policy ก่อนถึง backend
- ผู้ใช้เป้าหมาย: platform ภายในของ Book Platform; ยังไม่มี consumer ที่ใช้งานจริง **[ต้องยืนยัน]**

## 3. สิ่งที่ทำได้จริงตอนนี้

- `src/book_api_gateway/server.py` (`ThreadingHTTPServer`): `GET /healthz`, `GET /readyz` (TCP probe ไปยัง upstream), `GET`/`POST /api/*` ที่ต้องมี `Authorization: Bearer`
- `limiter.py` จำกัด rate; `_unsafe_api_path` กัน path traversal; ปิดการ follow redirect; telemetry ที่ redact ข้อมูล
- config ผ่าน `BOOK_API_GATEWAY_TOKEN`, `UPSTREAM_BASE_URL`, `UPSTREAM_ALLOWED_HOSTS` (ชื่อตัวแปรเท่านั้น)
- test 4 ไฟล์รวม `test_gateway.py` และ `test_route_access.py` ที่ pin ทุก route; ใช้ loopback fixture เท่านั้น
- `API.md` และ `contract.json` (status `pilot`) ตรวจความสอดคล้องกันใน CI

## 4. หลักฐานสถานะ

- Stack: Python 3.11 standard library (`http.server`), `unittest`, GitHub Actions
- Commits: 9 (แรก 2026-09-17 / ล่าสุด 2026-10-01), branch `main`
- Source: 11 ไฟล์ / 2077 บรรทัด; test files: 4
- CI workflows: 1; deploy config: ไม่มี
- Live URL: ไม่มี
- README: 65 บรรทัด ("book-api-gateway"); template family size: 1

## 5. คุณค่าและจุดต่าง

- standard library ล้วน, hardening ที่ทดสอบได้ และเอกสาร API ที่ตรวจด้วยเครื่อง — หลักฐาน backend engineering ที่ดี
- **[สมมติฐาน]** ไม่มีมุมรายได้; gateway สำเร็จรูป (Caddy, Kong, Cloudflare) ทำงานนี้ได้ครบกว่า

## 6. ช่องว่างสำคัญ

- ไม่มี deploy และไม่มี consumer; README ระบุว่า runtime ยังไม่เปิดใช้
- token เป็น credential ชั่วคราว รอ identity platform ที่ยังเป็น scaffold
- ยังไม่มีเหตุผลที่ต้องเขียน gateway เองแทนเครื่องมือมาตรฐาน **[ต้องยืนยัน]**

## 7. คำตัดสิน

**showcase** — โค้ดจริงที่ทดสอบและ harden แล้ว แต่ไม่มีผู้ใช้และมีทางเลือกสำเร็จรูป เงื่อนไขที่จะเปลี่ยนคำตัดสิน: มีผลิตภัณฑ์ภายในที่ต้องวาง gateway นี้หน้า `infra/api/server.ts` จริงพร้อมหลักฐาน parity

## 8. ขั้นต่อไป

1. บันทึก ADR ว่าทำไมไม่ใช้ gateway สำเร็จรูป หรือหยุดพัฒนาเพิ่ม
2. ถ้าเดินต่อ ให้ทำ shadow traffic กับ `infra/api/server.ts` ในเครื่องก่อน

## การอนุมัติ

| บทบาท | การตัดสินใจ | วันที่ |
|---|---|---|
| Product owner (Book Dev) | [ต้องยืนยัน] verdict `showcase` | — |

## แหล่งข้อมูล

- `bookchaowalit-backend/book-backend/book-api-gateway/README.md`
- `bookchaowalit-backend/book-backend/book-api-gateway/API.md`
- `bookchaowalit-backend/book-backend/book-api-gateway/src/book_api_gateway/server.py`
- `bookchaowalit-backend/book-backend/book-api-gateway/contract.json`
