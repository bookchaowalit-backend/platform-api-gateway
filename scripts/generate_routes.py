#!/usr/bin/env python3
"""Write routes.json from the hub registry (SPEC-001 R1). Run when a system is added or moved:

    python3 scripts/generate_routes.py --registry ../../../../bookchaowalit/.../online-systems.yaml

The registry is read only here, never by the running gateway. Only online systems with an
https URL become routes; web frontends and SKIP_IDS are skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SKIP_KINDS = {"web"}
# Not behind the JWT check: the gateway itself; identity (its /v1/token takes no bearer token,
# it issues them); ai-gateway (callers use its own static API keys, not platform JWTs).
SKIP_IDS = {"api-gateway", "identity", "ai-gateway"}
ID_RE = re.compile(r"[a-z][a-z0-9-]{1,62}")


def routes_from(systems: list[dict]) -> dict[str, str]:
    routes = {}
    for s in systems:
        url = s.get("url")
        if s.get("status") != "online" or s.get("kind") in SKIP_KINDS or s.get("id") in SKIP_IDS or not url:
            continue
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query:
            continue
        if not ID_RE.fullmatch(s["id"]):
            continue
        routes[s["id"]] = f"https://{parts.netloc}"
    return dict(sorted(routes.items()))


def load_registry(path: Path) -> list[dict]:
    try:
        import yaml  # local tooling only; the gateway runtime stays dependency-free
    except ImportError:
        sys.exit("PyYAML is needed to read the registry (pip install pyyaml)")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--registry", type=Path, required=True)
    p.add_argument("--out", type=Path, default=ROOT / "routes.json")
    args = p.parse_args(argv)
    routes = routes_from(load_registry(args.registry))
    args.out.write_text(json.dumps({"version": 1, "routes": routes}, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(routes)} routes to {args.out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
