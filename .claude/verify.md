# Verify recipe (platform-api-gateway)

The `verify` skill follows this file. The checks are the ones CI runs.

## Checks

```bash
bash scripts/check.sh
# = python3 scripts/check.py && python3 scripts/check_schema_pin.py \
#   && PYTHONPATH=src python3 -m unittest discover -s tests -v && python3 -m compileall -q src tests
```

Standard library only; tests use loopback fixtures, no network or database. There is no coverage
gate: changed logic needs its own test.

## End to end

Run as one script. Fake test values only: the issuer is never contacted (no request here reaches
JWT key fetch), and with the edge on `/readyz` is 200 from the route table alone.

```bash
set -eu
export PYTHONPATH=src GATEWAY_PORT=8099
export GATEWAY_TRUSTED_ISSUERS='{"https://issuer.test.invalid":"https://issuer.test.invalid/jwks.json"}'
export GATEWAY_EDGE_SECRET=local-test-edge-secret-0123456789abcdef   # 32+ chars, not a real secret
python3 -m book_api_gateway.server & PID=$!
trap 'kill $PID 2>/dev/null' EXIT
for i in $(seq 50); do curl -fsS -o /dev/null localhost:8099/healthz 2>/dev/null && break; kill -0 $PID; sleep 0.2; done
curl -fsS localhost:8099/healthz && curl -fsS localhost:8099/readyz
E="X-Gateway-Edge: $GATEWAY_EDGE_SECRET"
curl -s -o /dev/null -w 'no edge secret %{http_code}\n' localhost:8099/v1/crm/contacts          # 403
curl -s -o /dev/null -w 'no token %{http_code}\n' -H "$E" localhost:8099/v1/crm/contacts         # 401
curl -s -o /dev/null -w 'bad JWT %{http_code}\n' -H "$E" -H 'Authorization: Bearer x.y.z' \
  localhost:8099/v1/crm/contacts                                                              # 401
curl -s -o /dev/null -w 'unknown route %{http_code}\n' -H "$E" localhost:8099/v1/no-such/x       # 404
```

`kill -0` stops the wait if the new process died (for example port 8099 already taken). For auth
or routing changes, show the refusal that matches the change and its status code; a 404 counts
only from this edge-enabled run (without `GATEWAY_TRUSTED_ISSUERS`, every `/v1/` path is 404).
For the pilot `/api/*` path, also set `BOOK_API_GATEWAY_TOKEN` and point `UPSTREAM_BASE_URL` at a
loopback server.

## Never

- `scripts/deploy.sh` (runs `railway up` against the production project).
- `scripts/smoke.py` without a URL (defaults to production).
- `scripts/assertion_key.py` (prints a service key).
