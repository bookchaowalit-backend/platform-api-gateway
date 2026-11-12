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
(cd "$work" && railway up --ci -p "$GATEWAY_RAILWAY_PROJECT" -e "$GATEWAY_RAILWAY_ENVIRONMENT" \
  -s "$GATEWAY_RAILWAY_SERVICE" -m "$sha $(git log -1 --format=%s "$ref" | cut -c1-60)" | tail -1)
# `railway up --ci` returns after the build; the new deployment may still be starting. Retry the
# smoke test (it uses the routes of THIS checkout) for up to five minutes, 70 s apart so its three
# tokenless calls never add up to the failed-token limit (10 per minute per IP).
for attempt in 1 2 3 4 5; do
  if python3 "$root/scripts/smoke.py"; then
    echo "deployed $sha"
    exit 0
  fi
  echo "smoke attempt $attempt failed; retrying" >&2
  sleep 70
done
echo "deployed $sha but the smoke test still fails: roll back with REF=<previous sha>" >&2
exit 1
