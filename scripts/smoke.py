#!/usr/bin/env python3
"""Post-deploy smoke test of the public edge (SPEC-003). No token is used or needed.

    python3 scripts/smoke.py [https://gateway.bookchaowalit.com]

Checks: /healthz 200; every route's tokenless /openapi.json (the one tokenless path) reaches its
service (not the gateway's own 404, not 5xx);
three sample routes answer a tokenless call with 401 (the token check is on; more would trip the
failed-token limit of 10 per minute per IP); an unknown route is 404. Exit 1 on any miss.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ("habits", "knowledge", "crm")  # 3 tokenless failures per run; the lock is 10 per minute per IP
BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://gateway.bookchaowalit.com").rstrip("/")


def status(path: str) -> int:
    """HTTP status; -404 marks the gateway's own "route not found" (an upstream 404 stays 404)."""
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "gateway-smoke/1"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", "replace")
        return -404 if exc.code == 404 and '"error":"route not found"' in body.replace('": "', '":"') else exc.code
    except OSError:
        return 0


def main() -> int:
    routes = json.loads((ROOT / "routes.json").read_text())["routes"]
    failures = []
    if (code := status("/healthz")) != 200:
        failures.append(f"/healthz {code}")
    for system in sorted(routes):
        code = status(f"/v1/{system}/openapi.json")
        # An upstream may hide its docs (its own 404); the route must exist (not the gateway's -404),
        # be answered (not 0 or 5xx) and not be the gateway's own rate limit (429 never reached it).
        if code in (-404, 0, 429) or code >= 500:
            failures.append(f"/v1/{system}/openapi.json {code}")
        time.sleep(0.25)  # under the 60 req / 10 s edge rule and the public per-IP limit
    for system in SAMPLE:
        if system in routes and (code := status(f"/v1/{system}/health")) != 401:
            failures.append(f"/v1/{system} tokenless {code}")
    if (code := status("/v1/no-such-route-smoke/health")) != -404:
        failures.append(f"unknown route {code}")
    print(json.dumps({"base": BASE, "routes": len(routes), "failures": failures}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
