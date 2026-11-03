"""SPEC-001 R1 / AC4 / AC7: generated route table and matching."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from book_api_gateway.routes import RouteError, load_routes, match

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("generate_routes", ROOT / "scripts" / "generate_routes.py")
generate_routes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_routes)


class Generate(unittest.TestCase):  # AC7
    def test_only_online_https_services(self):
        systems = [
            {"id": "habits", "status": "online", "kind": "cell", "url": "https://habits-api.up.railway.app"},
            {"id": "owner-web", "status": "online", "kind": "web", "url": "https://owner.example"},
            {"id": "staged", "status": "staged", "kind": "service", "url": "https://s.example"},
            {"id": "plain", "status": "online", "kind": "cell", "url": "http://plain.example"},
            {"id": "pathy", "status": "online", "kind": "cell", "url": "https://p.example/api"},
            {"id": "api-gateway", "status": "online", "kind": "platform", "url": "https://gateway.example"},
            {"id": "identity", "status": "online", "kind": "service", "url": "https://id.example"},
            {"id": "ai-gateway", "status": "online", "kind": "service", "url": "https://ai.example"},
            {"id": "cron", "status": "online", "kind": "cron"},
        ]
        self.assertEqual(generate_routes.routes_from(systems), {"habits": "https://habits-api.up.railway.app"})

    def test_committed_table_is_valid(self):
        routes = load_routes()
        self.assertGreater(len(routes), 30)
        for skipped in ("api-gateway", "identity", "ai-gateway"):
            self.assertNotIn(skipped, routes)
        self.assertTrue(all(r.base_url.startswith("https://") for r in routes.values()))


class Load(unittest.TestCase):
    def write(self, routes):
        path = Path(tempfile.mkdtemp()) / "routes.json"
        path.write_text(json.dumps({"routes": routes}))
        return path

    def test_rejects_unsafe_entries(self):
        for bad in ({"x": "https://a.example"}, {"ok-id": "http://a.example"}, {"ok-id": "https://u@a.example"},
                    {"ok-id": "https://a.example/path"}, {}):
            with self.subTest(bad), self.assertRaises(RouteError):
                load_routes(self.write(bad))


class Match(unittest.TestCase):  # AC4 (unknown system)
    def setUp(self):
        self.routes = load_routes(self.write({"habits": "https://h.example"}))

    write = Load.write

    def test_match(self):
        route, rest = match(self.routes, "/v1/habits/v1/habits/today")
        self.assertEqual((route.system, rest), ("habits", "/v1/habits/today"))
        self.assertEqual(match(self.routes, "/v1/habits")[1], "/")
        self.assertIsNone(match(self.routes, "/v1/unknown/x"))


if __name__ == "__main__":
    unittest.main()
