#!/usr/bin/env python3
"""Print one service's SPEC-002 key (64 hex) from GATEWAY_ASSERTION_MASTER_KEY in the environment.

    infisical run --path /platform-api-gateway -- python3 scripts/assertion_key.py habits \\
      | railway variables --service habits-api --set-from-stdin GATEWAY_ASSERTION_KEY

Pipe it straight into the service's variable; it is a secret, so do not print it to a terminal log.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from book_api_gateway.assertion import parse_master, system_key  # noqa: E402
from book_api_gateway.routes import load_routes  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: assertion_key.py <system>", file=sys.stderr)
        return 2
    system = argv[0]
    if system not in load_routes():
        print(f"unknown system {system!r} (not in routes.json)", file=sys.stderr)
        return 2
    master = parse_master(os.environ.get("GATEWAY_ASSERTION_MASTER_KEY", ""))
    if master is None:
        print("GATEWAY_ASSERTION_MASTER_KEY is not set", file=sys.stderr)
        return 2
    sys.stdout.write(system_key(master, system).hex())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
