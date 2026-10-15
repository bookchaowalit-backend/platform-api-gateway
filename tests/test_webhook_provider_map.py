"""BOO-147 gate: external provider / webhook map stays in step with the code.

``fixtures/gates/webhook-provider-map.json`` maps every external provider and
inbound webhook route named by the integrations contract
(architecture-docs ``solo-empire-api-contract-v1.md#signed-and-authenticated-webhook-routes``)
to its signature check, idempotency key, replay window and privacy class, and
records how this gateway treats those routes today.

The tests fail when:

- a route class or path literal in ``server.py`` or an interface in
  ``contract.json`` is not mapped;
- a contract webhook/provider route has no provider entry, or an entry lacks a
  signature, idempotency, replay-window or privacy field;
- the recorded gateway behaviour (no signed-webhook route class, signature and
  ``Idempotency-Key`` headers not forwarded, bad bearer rejected) no longer
  matches what the real gateway does with synthetic credentials.

When an architecture-docs checkout is present (``ARCHITECTURE_DOCS_ROOT`` or
the Book Dev sibling path), the contract tables are also re-parsed so the
vendored route list cannot drift from the contract; CI skips that check.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from http.client import HTTPConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from book_api_gateway import server as gateway_server  # noqa: E402
from book_api_gateway.config import GatewayConfig  # noqa: E402
from book_api_gateway.server import FORWARD_HEADERS, PUBLIC, ROUTE_ACCESS, create_server  # noqa: E402
from test_gateway import RecordingUpstreamServer, start_server  # noqa: E402

FIXTURE_PATH = ROOT / "fixtures" / "gates" / "webhook-provider-map.json"
SERVER_SOURCE = ROOT / "src" / "book_api_gateway" / "server.py"
CONTRACT_SECTION = "### Signed and authenticated webhook routes"
READ_ROUTES_SECTION = "### Authenticated AI and read-only integration routes"
DEFAULT_ARCH_DOCS = ROOT.parents[3] / "bookchaowalit" / "private" / "architecture-docs"

# Synthetic credentials only; nothing here is a real provider secret.
GATEWAY_TOKEN = "boo147-synthetic-gateway-token"
WRONG_TOKEN = "boo147-synthetic-wrong-token"
SYNTHETIC_SIGNATURE_HEADERS = {
    "x-line-signature": "c3ludGhldGljLWxpbmUtc2lnbmF0dXJl",
    "stripe-signature": "t=1700000000,v1=00000000000000000000000000000000000000000000000000000000000000ff",
}
DIRECTIONS = {"inbound-webhook", "outbound-read-only", "local-script"}
WEBHOOK_AUTH_CLASSES = {"signed-webhook", "bearer"}
REPLAY_STATUSES = {"enforced", "missing", "not-applicable"}


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def mapped_routes(fixture: dict) -> dict[str, dict]:
    routes: dict[str, dict] = {}
    for provider in fixture["providers"]:
        for route in provider["routes"]:
            routes[route] = provider
    return routes


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


class FixtureCompletenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = load_fixture()

    def test_gate_and_contract_reference(self) -> None:
        self.assertEqual(
            self.fixture["next_gate"],
            "Map every external provider, signature check, idempotency key, and privacy class.",
        )
        contract = self.fixture["contract"]
        self.assertEqual(contract["path"], "systems/architecture/solo-empire-api-contract-v1.md")
        self.assertEqual(contract["anchor"], "#signed-and-authenticated-webhook-routes")

    def test_provider_ids_are_unique(self) -> None:
        ids = [provider["provider"] for provider in self.fixture["providers"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_provider_has_signature_idempotency_replay_and_privacy(self) -> None:
        vocabulary = set(self.fixture["privacy_classes"])
        self.assertEqual(vocabulary, {"public", "internal", "private", "restricted"})
        for provider in self.fixture["providers"]:
            name = provider["provider"]
            with self.subTest(provider=name):
                self.assertIn(provider["direction"], DIRECTIONS)
                self.assertTrue(_nonempty(provider["auth_class"]))
                signature = provider["signature"]
                for field in ("scheme", "header", "verification_location", "gateway_verification"):
                    self.assertTrue(_nonempty(signature.get(field)), f"signature.{field}")
                self.assertTrue(_nonempty(provider["idempotency"].get("key_source")), "idempotency.key_source")
                self.assertIsInstance(provider["idempotency"].get("gaps"), list)
                replay = provider["replay_window"]
                self.assertIn(replay.get("status"), REPLAY_STATUSES)
                self.assertTrue(_nonempty(replay.get("detail")))
                if replay["status"] == "enforced":
                    self.assertIsInstance(replay.get("seconds"), int)
                    self.assertGreater(replay["seconds"], 0)
                self.assertIn(provider["privacy_class"], vocabulary)
                self.assertIn(provider["privacy_class_basis"], {"cited", "proposed"})
                self.assertTrue(_nonempty(provider["privacy_evidence"]))
                self.assertTrue(provider["evidence"], "evidence citations")

    def test_inbound_webhooks_name_a_concrete_check_and_key(self) -> None:
        for provider in self.fixture["providers"]:
            if provider["direction"] != "inbound-webhook":
                continue
            with self.subTest(provider=provider["provider"]):
                self.assertIn(provider["auth_class"], WEBHOOK_AUTH_CLASSES)
                signature = provider["signature"]
                self.assertNotIn("not-applicable", signature["verification_location"])
                self.assertIsInstance(signature.get("failure_status"), int)
                self.assertIn("evidence", provider["idempotency"])
                self.assertNotIn("not-applicable", provider["idempotency"]["key_source"])
                if provider["auth_class"] == "signed-webhook":
                    self.assertIn(signature["header"].lower(), SYNTHETIC_SIGNATURE_HEADERS)
                    self.assertTrue(_nonempty(signature.get("secret_env")))
                    self.assertEqual(signature["gateway_verification"], "missing")
                    # A signed delivery carries third-party payloads; never below private.
                    self.assertIn(provider["privacy_class"], {"private", "restricted"})

    def test_integrations_directories_are_all_mapped(self) -> None:
        ids = {provider["provider"] for provider in self.fixture["providers"]}
        dirs = self.fixture["solo_empire_integrations_dirs"]
        self.assertEqual(sorted(dirs), sorted(self.fixture["integrations_dir_provider"]))
        for directory, provider in self.fixture["integrations_dir_provider"].items():
            with self.subTest(directory=directory):
                self.assertIn(provider, ids)


class ContractCoverageTests(unittest.TestCase):
    """Every contract webhook and provider route maps to a complete entry."""

    def setUp(self) -> None:
        self.fixture = load_fixture()
        self.routes = mapped_routes(self.fixture)

    def test_contract_webhook_routes_are_mapped(self) -> None:
        for route in self.fixture["contract"]["webhook_routes"]:
            with self.subTest(route=route):
                self.assertIn(route, sorted(self.routes))
                self.assertEqual(self.routes[route]["direction"], "inbound-webhook")

    def test_contract_provider_read_routes_are_mapped(self) -> None:
        for route in self.fixture["contract"]["provider_read_routes"]:
            with self.subTest(route=route):
                self.assertIn(route, sorted(self.routes))

    def test_no_mapped_route_is_outside_the_contract(self) -> None:
        contract_routes = set(self.fixture["contract"]["webhook_routes"]) | set(
            self.fixture["contract"]["provider_read_routes"]
        )
        self.assertEqual(set(self.routes) - contract_routes, set())

    def _architecture_docs(self) -> Path | None:
        configured = os.environ.get("ARCHITECTURE_DOCS_ROOT")
        candidate = Path(configured) if configured else DEFAULT_ARCH_DOCS
        contract = candidate / self.fixture["contract"]["path"]
        return contract if contract.is_file() else None

    @staticmethod
    def _section_rows(text: str, heading: str) -> list[str]:
        start = text.index(heading)
        following = text.find("\n#", start + len(heading))
        section = text[start : following if following != -1 else len(text)]
        rows = []
        for line in section.splitlines():
            match = re.match(r"\|\s*`(GET|POST)`\s*\|\s*`([^`]+)`", line)
            if match:
                rows.append(f"{match.group(1)} {match.group(2)}")
        return rows

    def test_vendored_routes_match_live_contract_when_available(self) -> None:
        contract = self._architecture_docs()
        if contract is None:
            self.skipTest("architecture-docs checkout not available (set ARCHITECTURE_DOCS_ROOT)")
        text = contract.read_text(encoding="utf-8")
        self.assertEqual(self._section_rows(text, CONTRACT_SECTION), self.fixture["contract"]["webhook_routes"])
        provider_rows = [
            row for row in self._section_rows(text, READ_ROUTES_SECTION) if row.startswith("GET /api/integrations/")
        ]
        provider_rows = [
            row
            for row in provider_rows
            if row not in {"GET /api/integrations/health", "GET /api/integrations/discovery"}
        ]
        self.assertEqual(provider_rows, self.fixture["contract"]["provider_read_routes"])
        signed = re.search(r"^\| Signed webhook \| (.+?) \|", text, re.MULTILINE)
        self.assertIsNotNone(signed)
        signed_paths = set(re.findall(r"`(/api/webhook/[a-z-]+)`", signed.group(1)))
        fixture_signed = {
            route.split(" ", 1)[1]
            for provider in self.fixture["providers"]
            if provider["auth_class"] == "signed-webhook"
            for route in provider["routes"]
        }
        self.assertEqual(signed_paths, fixture_signed)


class GatewaySourceCoverageTests(unittest.TestCase):
    """Every gateway route class, path literal and contract interface is mapped."""

    def setUp(self) -> None:
        self.fixture = load_fixture()
        self.gateway = self.fixture["gateway"]

    def test_route_access_classes_are_mapped(self) -> None:
        self.assertEqual(set(ROUTE_ACCESS), set(self.gateway["route_classes"]))
        for route, (access, methods) in ROUTE_ACCESS.items():
            with self.subTest(route=route):
                mapped = self.gateway["route_classes"][route]
                self.assertEqual(mapped["access"], access)
                self.assertEqual(set(mapped["methods"]), set(methods))
                self.assertIs(mapped["external_provider_ingress"], False)

    def test_path_literals_in_server_source_are_mapped(self) -> None:
        source = SERVER_SOURCE.read_text(encoding="utf-8")
        literals = set(re.findall(r"[\"'](/[A-Za-z][^\"'\s]*)[\"']", source))
        covered = set(self.gateway["route_classes"])
        for literal in sorted(literals):
            with self.subTest(literal=literal):
                normalized = "/api/*" if literal.rstrip("*").rstrip("/") == "/api" else literal
                self.assertIn(normalized, covered)

    def test_contract_json_interfaces_are_mapped(self) -> None:
        contract = json.loads((ROOT / "contract.json").read_text(encoding="utf-8"))
        ids = {interface["id"] for interface in contract["interfaces"]}
        self.assertEqual(ids, set(self.gateway["contract_interfaces"]))
        for interface_id, classification in self.gateway["contract_interfaces"].items():
            with self.subTest(interface=interface_id):
                self.assertTrue(_nonempty(classification))

    def test_signed_webhook_class_and_verification_are_recorded_as_missing(self) -> None:
        public_writes = [
            route
            for route, (access, methods) in ROUTE_ACCESS.items()
            if access == PUBLIC and methods - {"GET", "HEAD"}
        ]
        self.assertEqual(public_writes, [], "a public write route exists; map it as signed-webhook ingress")
        self.assertEqual(self.gateway["signed_webhook_route_class"], "missing")
        source = SERVER_SOURCE.read_text(encoding="utf-8").lower()
        for header in SYNTHETIC_SIGNATURE_HEADERS:
            self.assertNotIn(header, source, f"{header} appears in server.py; update the map")
        self.assertEqual(self.gateway["signature_verification"], "missing")

    def test_forwarded_header_allow_list_matches_source(self) -> None:
        self.assertEqual(list(FORWARD_HEADERS), self.gateway["forwarded_request_headers"])
        forwarded = {name.lower() for name in FORWARD_HEADERS}
        self.assertEqual(
            self.gateway["forwards_signature_headers"],
            bool(forwarded & set(SYNTHETIC_SIGNATURE_HEADERS)),
        )
        self.assertEqual(self.gateway["forwards_idempotency_key"], "idempotency-key" in forwarded)


class GatewayWebhookBehaviourTests(unittest.TestCase):
    """Drive the real gateway with synthetic secrets on each mapped webhook route."""

    def setUp(self) -> None:
        self.fixture = load_fixture()
        self.upstream = RecordingUpstreamServer()
        start_server(self.upstream)
        upstream_url = f"http://127.0.0.1:{self.upstream.server_port}"
        self.gateway = create_server(
            GatewayConfig(api_token=GATEWAY_TOKEN, upstream_base_url=upstream_url, rate_limit_per_minute=1000),
            telemetry_sink=lambda _event: None,
        )
        self.gateway.gateway_state.upstream_probe = lambda: True
        start_server(self.gateway)

    def tearDown(self) -> None:
        self.gateway.shutdown()
        self.gateway.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()

    def _post(self, path: str, headers: dict[str, str]) -> int:
        body = b'{"synthetic":true}'
        connection = HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=2)
        try:
            connection.request(
                "POST", path, body=body, headers={"Content-Type": "application/json", **headers}
            )
            response = connection.getresponse()
            response.read()
            return response.status
        finally:
            connection.close()

    def _webhooks(self) -> list[tuple[str, dict]]:
        return [
            (route.split(" ", 1)[1], provider)
            for provider in self.fixture["providers"]
            if provider["direction"] == "inbound-webhook"
            for route in provider["routes"]
        ]

    def test_provider_signed_delivery_without_bearer_is_rejected(self) -> None:
        for path, provider in self._webhooks():
            if provider["auth_class"] != "signed-webhook":
                continue
            header = provider["signature"]["header"].lower()
            with self.subTest(path=path):
                status = self._post(path, {header: SYNTHETIC_SIGNATURE_HEADERS[header]})
                self.assertEqual(status, 401)
        self.assertEqual(self.upstream.records, [])

    def test_bad_bearer_is_rejected_on_every_webhook_route(self) -> None:
        for path, _provider in self._webhooks():
            with self.subTest(path=path):
                status = self._post(path, {"Authorization": f"Bearer {WRONG_TOKEN}"})
                self.assertEqual(status, 401)
        self.assertEqual(self.upstream.records, [])

    def test_authenticated_passthrough_drops_signature_and_idempotency_headers(self) -> None:
        gateway = self.fixture["gateway"]
        for path, provider in self._webhooks():
            headers = {"Authorization": f"Bearer {GATEWAY_TOKEN}", "Idempotency-Key": "boo147-synthetic-key"}
            headers.update(SYNTHETIC_SIGNATURE_HEADERS)
            with self.subTest(path=path):
                before = len(self.upstream.records)
                self.assertEqual(self._post(path, headers), 200)
                record = self.upstream.records[before]
                self.assertEqual(record["path"], path)
                received = record["headers"]
                self.assertNotIn("authorization", received)
                for header in SYNTHETIC_SIGNATURE_HEADERS:
                    self.assertEqual(header in received, gateway["forwards_signature_headers"])
                self.assertEqual("idempotency-key" in received, gateway["forwards_idempotency_key"])
                if provider["idempotency"]["key_source"].startswith("Idempotency-Key") and not gateway[
                    "forwards_idempotency_key"
                ]:
                    self.assertTrue(
                        any("Idempotency-Key" in gap for gap in provider["idempotency"]["gaps"]),
                        "dropped Idempotency-Key must be listed as a gap",
                    )

    def test_gateway_module_has_no_signature_verifier(self) -> None:
        names = {name.lower() for name in dir(gateway_server)}
        self.assertFalse(any("signature" in name or "webhook" in name for name in names))


if __name__ == "__main__":
    unittest.main()
