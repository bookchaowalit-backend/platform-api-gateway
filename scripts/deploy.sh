#!/usr/bin/env bash
# SPEC-003 deploy: checks, then `railway up` of a clean `git archive` of REF (default origin/main), then
# the smoke test from THIS checkout (so a rollback to a ref without it is still checked), retried until
# the new deployment answers. Needs RAILWAY_API_TOKEN (e.g. `infisical run --path=/railway --
# scripts/deploy.sh`). Rollback: REF=<previous good commit> scripts/deploy.sh
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
ref="${REF:-origin/main}"
git fetch -q origin
sha="$(git rev-parse --short "$ref")"
# Some tests resolve sibling checkouts relative to the repository (ROOT.parents[3]), so the archive
# needs a few parent directories: <tmp>/a/b/c/platform-api-gateway.
base="$(mktemp -d)"
trap 'rm -rf "$base"' EXIT
work="$base/a/b/c/platform-api-gateway"
mkdir -p "$work"
git archive "$ref" | tar -x -C "$work"
if [ -f "$work/scripts/check.sh" ]; then
  (cd "$work" && bash scripts/check.sh >/dev/null) || { echo "checks failed on $sha; not deployed" >&2; exit 1; }
fi
: "${GATEWAY_RAILWAY_PROJECT:=451cd409-8aa1-437f-b2d3-2f2da7627209}"
: "${GATEWAY_RAILWAY_ENVIRONMENT:=c96ce799-05d0-417e-a1d9-573d9dde0b67}"
: "${GATEWAY_RAILWAY_SERVICE:=a2c21011-3e2d-4af6-9366-2c4b2ae6306b}"
export GATEWAY_RAILWAY_PROJECT GATEWAY_RAILWAY_ENVIRONMENT GATEWAY_RAILWAY_SERVICE
started="$(date -u +%Y-%m-%dT%H:%M:%S)"
(cd "$work" && railway up --ci -p "$GATEWAY_RAILWAY_PROJECT" -e "$GATEWAY_RAILWAY_ENVIRONMENT" \
  -s "$GATEWAY_RAILWAY_SERVICE" -m "$sha $(git log -1 --format=%s "$ref" | cut -c1-60)" | tail -1)
# `railway up --ci` returns after the build. Wait until the deployment created by this upload is
# SUCCESS (the one serving traffic), then smoke-test it.
python3 - "$started" <<'PY' || { echo "the new deployment did not become SUCCESS; roll back with REF=<previous sha>" >&2; exit 1; }
import json, os, sys, time, urllib.request
since = sys.argv[1]
q = ("query($p:String!,$e:String!,$s:String!){ deployments(first:1, input:{projectId:$p, environmentId:$e,"
     " serviceId:$s}){ edges { node { status createdAt } } } }")
v = {"p": os.environ["GATEWAY_RAILWAY_PROJECT"], "e": os.environ["GATEWAY_RAILWAY_ENVIRONMENT"],
     "s": os.environ["GATEWAY_RAILWAY_SERVICE"]}
for _ in range(60):
    req = urllib.request.Request("https://backboard.railway.com/graphql/v2", json.dumps({"query": q, "variables": v}).encode(),
                                 headers={"Authorization": "Bearer " + os.environ["RAILWAY_API_TOKEN"], "Content-Type": "application/json"})
    node = json.load(urllib.request.urlopen(req, timeout=30))["data"]["deployments"]["edges"][0]["node"]
    if node["createdAt"] >= since and node["status"] == "SUCCESS":
        sys.exit(0)
    if node["createdAt"] >= since and node["status"] in ("FAILED", "CRASHED", "REMOVED"):
        sys.exit(1)
    time.sleep(10)
sys.exit(1)
PY
# Smoke the deployed ref's own route table, at GATEWAY_URL (default production), from THIS checkout's
# script (a rollback ref may predate it). Retried 70 s apart: three tokenless calls per run stay under
# the failed-token limit (10 per minute per IP).
routes="$work/routes.json"
for attempt in 1 2 3; do
  if python3 "$root/scripts/smoke.py" "${GATEWAY_URL:-https://gateway.bookchaowalit.com}" --routes "$routes"; then
    echo "deployed $sha"
    exit 0
  fi
  echo "smoke attempt $attempt failed; retrying" >&2
  sleep 70
done
echo "deployed $sha but the smoke test still fails: roll back with REF=<previous sha>" >&2
exit 1
