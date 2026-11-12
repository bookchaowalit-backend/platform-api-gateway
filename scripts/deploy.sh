#!/usr/bin/env bash
# SPEC-003 deploy: checks, then `railway up` of a clean `git archive` of origin/main, then the smoke test.
# Needs RAILWAY_API_TOKEN (e.g. `infisical run --path=/railway -- scripts/deploy.sh`). Rollback:
# run it with REF=<previous good commit>.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
ref="${REF:-origin/main}"
git fetch -q origin
sha="$(git rev-parse --short "$ref")"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git archive "$ref" | tar -x -C "$work"
(cd "$work" && bash scripts/check.sh >/dev/null) || { echo "checks failed on $sha; not deployed" >&2; exit 1; }
: "${GATEWAY_RAILWAY_PROJECT:=451cd409-8aa1-437f-b2d3-2f2da7627209}"
: "${GATEWAY_RAILWAY_ENVIRONMENT:=c96ce799-05d0-417e-a1d9-573d9dde0b67}"
: "${GATEWAY_RAILWAY_SERVICE:=a2c21011-3e2d-4af6-9366-2c4b2ae6306b}"
(cd "$work" && railway up --ci -p "$GATEWAY_RAILWAY_PROJECT" -e "$GATEWAY_RAILWAY_ENVIRONMENT" \
  -s "$GATEWAY_RAILWAY_SERVICE" -m "$sha $(git log -1 --format=%s "$ref" | cut -c1-60)" | tail -1)
sleep 20
python3 "$work/scripts/smoke.py"
echo "deployed $sha"
