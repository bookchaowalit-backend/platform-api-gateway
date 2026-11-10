# 18 — Git and release workflow

จาก history จริง: เกือบทุก commit push ตรงเข้า `main` (48 commits ใน 90 วัน มี merge commit เดียว `db27ca3`); PR มี 3 รายการ (#1, #2 BOO-147; #3 `docs/product-live-sentry-waiver`) merged แบบไม่มี merge commit
Release = Railway CLI upload ของ `git archive main` ทำโดย operator; ไม่มี tag หรือ release notes

```mermaid
gitGraph
  commit id: "pilot 2026-09"
  branch claude/untitled-session-bhlj06
  commit id: "session work"
  checkout main
  merge claude/untitled-session-bhlj06 id: "db27ca3"
  branch boo-147-webhook-provider-map
  commit id: "PR 1 BOO-147 map"
  checkout main
  merge boo-147-webhook-provider-map id: "PR 1 merged 10-15"
  commit id: "ac89703 IP failure limit"
  commit id: "04c1fcd shared CI v1.1.1"
  commit id: "eeceedc SPEC-001 edge"
  branch docs/product-live-sentry-waiver
  commit id: "PR 3 waiver"
  checkout main
  merge docs/product-live-sentry-waiver id: "PR 3 merged 11-03"
  commit id: "e653535 SPEC-002"
  commit id: "4c81817 HEAD"
```

```mermaid
flowchart LR
  A["Commit, usually direct to main"] --> B["git push origin main"]
  B --> C["check.yml: contract 3.11, 3.12 and security"]
  B --> D["Operator: git archive main then railway up --path-as-root --ci"]
  D --> E["Railway build Dockerfile, healthcheck /healthz"]
  E --> F["New deployment live, previous REMOVED"]
  C -.->|"result not checked by deploy"| D
  F --> G["Record consumer cutover or parity in contract.json"]
```

หมายเหตุ: gitGraph ด้านบนย่อเฉพาะจุดสำคัญ (ไม่ใช่ทุก commit); ลำดับ PR #2 (`boo-147-owner-decision`, merged 2026-10-16) ไม่ได้แสดง

Sources: `git log origin/main`, `git branch -r`, `gh pr list -R bookchaowalit-backend/platform-api-gateway --state all`, `.github/workflows/check.yml`, `.railway/railway.ts`, `README.md` (Boundary: "CLI deploy of git archive main"), ops record: api-gateway-edge (2026-11-03)

## Open questions

- branch protection / ruleset บน `main` มีหรือไม่ (ไม่พบใน repo; ประวัติแสดง direct push)
- ควรมี tag ต่อ deploy เพื่อผูก Railway deployment กับ SHA หรือไม่
