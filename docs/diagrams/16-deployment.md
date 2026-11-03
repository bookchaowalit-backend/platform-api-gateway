# 16 — Deployment

```mermaid
flowchart LR
  subgraph Dev["Operator machine"]
    GA["git archive main"] --> RU["railway up --path-as-root --ci"]
  end
  subgraph CFZ["Cloudflare zone bookchaowalit.com"]
    DNS["CNAME gateway, proxied"]
    TR["Transform Rule http_request_late_transform: set X-Gateway-Edge"]
    CR["Configuration Rule http_config_settings: bic false"]
    RL["Rate-limit rule 60 per 10 s per IP"]
  end
  subgraph RWP["Railway project platform-api-gateway, env production"]
    SVC["Service gateway, Singapore asia-southeast1, serverless"]
    IMG["Image: python 3.12-slim, user gateway uid 10001, src and routes.json"]
    HC["Healthcheck /healthz, timeout 30 s, restart ON_FAILURE max 3"]
    VARS["Variables: GATEWAY_TRUSTED_ISSUERS, GATEWAY_EDGE_SECRET, GATEWAY_ASSERTION_MASTER_KEY"]
  end
  INF["Infisical /platform-api-gateway"] --> VARS
  RU --> IMG --> SVC
  HC --> SVC
  VARS --> SVC
  U["Clients"] --> DNS --> TR --> CR --> RL --> SVC
  SVC --> UP["Registry services on up.railway.app"]
```

| Fact | Value | Source |
|---|---|---|
| Host | `https://gateway.bookchaowalit.com` | `README.md`, `API.md` |
| Builder | Dockerfile | `railway.toml` |
| Start command | `python -c "from book_api_gateway.server import main; ..."`, bind `0.0.0.0`, port from `PORT` | `Dockerfile`, `server.py` `main` |
| Region | `asia-southeast1-eqsg3a` | Railway `list-deployments` (2026-11-03) |
| Railway domain | none (`*.up.railway.app` → 404) | ops record: api-gateway-edge (2026-11-03) |
| Deployments | 14, all on 2026-11-03, latest `e2bd3ba7` SUCCESS 16:21 UTC | Railway `list-deployments` |
| Pilot `/api/*` | unset in production | `README.md` |

Sources: `railway.toml`, `Dockerfile`, `README.md`, `API.md`, `src/book_api_gateway/server.py`, `src/book_api_gateway/edge.py` (`from_env`), Railway `list-deployments` project `platform-api-gateway`, ops record: api-gateway-edge (2026-11-03)

## Open questions

- deployment แต่ละครั้งตรงกับ commit ไหน — Railway upload ไม่บันทึก SHA (การจับคู่ใน [22](22-dora.md) ใช้เวลาเป็นหลัก)
