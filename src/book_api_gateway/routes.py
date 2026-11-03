"""Route table: `/v1/<system>/<path>` → the system's registry base URL (SPEC-001 R1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ID_RE = re.compile(r"[a-z][a-z0-9-]{1,62}")
DEFAULT_ROUTES = Path(__file__).resolve().parents[2] / "routes.json"


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class Route:
    system: str
    base_url: str
    host: str


def load_routes(path: Path = DEFAULT_ROUTES) -> dict[str, Route]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["routes"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RouteError(f"cannot read route table {path.name}") from exc
    routes = {}
    for system, base in raw.items():
        try:
            parts = urlsplit(base)
            parts.port  # noqa: B018 - raises ValueError for a port outside 0-65535 or not a number
        except (ValueError, TypeError, AttributeError) as exc:
            raise RouteError(f"invalid route {system!r}") from exc
        if (not ID_RE.fullmatch(system) or parts.scheme != "https" or not parts.hostname
                or parts.path not in ("", "/") or parts.query or parts.fragment or parts.username):
            raise RouteError(f"invalid route {system!r}")
        routes[system] = Route(system, f"https://{parts.netloc}", parts.hostname)
    if not routes:
        raise RouteError("route table is empty")
    return routes


def match(routes: dict[str, Route], path: str) -> tuple[Route, str] | None:
    """`/v1/<system>/<rest>` → (route, `/<rest>`); None when the system is unknown."""
    _, _, tail = path.partition("/v1/")
    system, slash, rest = tail.partition("/")
    route = routes.get(system)
    if route is None:
        return None
    return route, "/" + rest if slash else "/"
