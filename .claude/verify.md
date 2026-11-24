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

```bash
PYTHONPATH=src GATEWAY_PORT=8099 python3 -m book_api_gateway.server &
curl -fsS localhost:8099/healthz && curl -fsS localhost:8099/readyz
```

For auth or routing changes, also show one request that must be refused (no edge secret, bad JWT,
unknown route) and its status code.

## Never

- `scripts/deploy.sh` (runs `railway up` against the production project).
- `scripts/smoke.py` without a URL (defaults to production).
- `scripts/assertion_key.py` (prints a service key).
