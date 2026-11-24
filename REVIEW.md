# Review guide (platform-api-gateway)

The Codex Stop-hook review reads this file from the default branch, never from the change under
review. Owner-written; keep it under 16 KiB.

## What failure looks like here

Treat these as `[P0]`/`[P1]`:

- **Edge lock bypassed**: trusting `CF-Connecting-IP` or any client header without the edge secret
  (`docs/specs/001-edge-gateway.md`, `src/book_api_gateway/edge.py`).
- **JWT verification weakened**: an algorithm other than RS256, an untrusted `iss`, exp/nbf skew
  widened, `sub`/`aud` not required, or a JWKS outage turning into a pass instead of 503
  (`jwt_verify.py`, spec 001 AC2).
- **Assertion forged**: a caller-supplied `X-Gateway-Assertion` forwarded, or the HMAC input changed
  without the services changing with it (`docs/specs/002-gateway-assertion.md`).
- **Routing to the wrong place**: a route to a non-https or non-allowlisted host, or back to the
  gateway itself (spec 001 AC7). Check every host change in `routes.json`, generated or not.
- **Request smuggling / traversal**: `..`, encoded slashes, chunked bodies, conflicting
  Content-Length (`API.md`, spec 001 AC4).
- **Telemetry leaking** a token, path tail, query or body (spec 001, `003-production-standard.md`).
- **Header allowlist drift** in what is forwarded upstream.

## Severity

- `[P0]` edge or auth bypass, forged assertion, traffic routed to an untrusted host, token in logs.
- `[P1]` a route or a service broken for real callers (wrong status, lost header, 503 where 200 is right).
- `[P2]` edge case, or changed behaviour without a test.
- `[P3]` nit. **At most 3 nits.**

## Skip

- `__pycache__/`, `.ruff_cache/`, `DOCPACK/pdf/`.
- `routes.json` and `fixtures/gates/webhook-provider-*.json` are generated: skim them, but any host
  change in `routes.json` is reviewed as a routing change.

## Evidence

Every finding gives `file:line` and input -> wrong result. No finding without evidence from the diff
or the code it calls. Start the summary with the count, e.g. `2 findings (1 P1, 1 P3)`.
