"""BOO-147 gate: external provider / webhook map stays in step with its sources.

``fixtures/gates/webhook-provider-map.json`` maps external providers and
inbound webhook routes to direction, signature/auth mechanism, credential
reference names, idempotency key, replay window and privacy class, and records
how this gateway treats those routes today.

``fixtures/gates/webhook-provider-sources.json`` is a committed, pinned
snapshot (commit, git blob, sha256 and verbatim lines) of the sources the map
is derived from:

- the architecture-docs contract (auth classes, AI/integration routes, webhook
  routes);
- solo-empire ``integration_health.py`` (every ``check_*`` provider probe and
  the active probe list behind ``GET /api/integrations/health``);
- solo-empire ``discover_external_apps.py`` (``GET /api/integrations/discovery``
  sources);
- solo-empire ``ai_gateway.ts`` (``POST /api/ai/generate`` provider);
- the solo-empire ``integrations/`` tree.

"Every provider" is scoped to exactly those sources plus this gateway's own
routes. The tests below fail, in CI and without any sibling checkout, when a
route, probe, discovery source, AI provider or integrations directory in the
snapshot is not mapped, or when an entry lacks a required field. With local
checkouts (``ARCHITECTURE_DOCS_ROOT``, ``SOLO_EMPIRE_ROOT``) extra tests prove
the snapshot still matches git byte-for-byte.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
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
SOURCES_PATH = ROOT / "fixtures" / "gates" / "webhook-provider-sources.json"
GATE_DOC = ROOT / "docs" / "gates" / "BOO-147-webhook-provider-map.md"
SERVER_SOURCE = ROOT / "src" / "book_api_gateway" / "server.py"
CONTRACT_SECTION = "### Signed and authenticated webhook routes"
READ_ROUTES_SECTION = "### Authenticated AI and read-only integration routes"
DEFAULT_ARCH_DOCS = ROOT.parents[3] / "bookchaowalit" / "private" / "architecture-docs"
DEFAULT_SOLO_EMPIRE = ROOT.parents[8] if len(ROOT.parents) > 8 else None

# Synthetic credentials only; nothing here is a real provider secret.
GATEWAY_TOKEN = "boo147-synthetic-gateway-token"
WRONG_TOKEN = "boo147-synthetic-wrong-token"
SYNTHETIC_SIGNATURE_HEADERS = {
    "x-line-signature": "c3ludGhldGljLWxpbmUtc2lnbmF0dXJl",
    "stripe-signature": "t=1700000000,v1=00000000000000000000000000000000000000000000000000000000000000ff",
}
DIRECTIONS = {"inbound-webhook", "outbound-read-only", "local-script"}
DIRECTION_FLAGS = {"inbound", "outbound", "local"}
WEBHOOK_AUTH_CLASSES = {"signed-webhook", "bearer"}
REPLAY_STATUSES = {"enforced", "missing", "not-applicable"}
CREDENTIAL_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
ROUTE_ROW = re.compile(r"\|\s*`(GET|POST)`\s*\|\s*`([^`]+)`")


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def load_sources() -> dict:
    return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))


def source(key: str) -> dict:
    return next(entry for entry in load_sources()["sources"] if entry["key"] == key)


def mapped_routes(fixture: dict) -> dict[str, dict]:
    routes: dict[str, dict] = {}
    for provider in fixture["providers"]:
        for route in provider["routes"]:
            routes[route] = provider
    return routes


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def contract_rows(lines: dict[str, str], heading: str) -> list[str]:
    """Route rows (``METHOD /path``) of one contract section from snapshot lines."""

    ordered = [lines[key] for key in sorted(lines, key=int)]
    rows: list[str] = []
    inside = False
    for line in ordered:
        if line.startswith("#"):
            inside = line.strip() == heading
            continue
        match = ROUTE_ROW.match(line)
        if inside and match:
            rows.append(f"{match.group(1)} {match.group(2)}")
    return rows


def health_probes() -> tuple[set[str], set[str]]:
    """(all check_* functions, check_* called in the live probe list)."""

    lines = source("integration_health")["lines"]
    defined = {m.group(1) for line in lines.values() if (m := re.match(r"def (check_\w+)\(", line))}
    active = {m.group(1) for line in lines.values() if (m := re.match(r"\s+(check_\w+)\(\),", line))}
    return defined, active


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
        self.assertEqual(contract["revision"], source("contract")["commit"])

    def test_provider_ids_are_unique(self) -> None:
        ids = [provider["provider"] for provider in self.fixture["providers"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_provider_has_direction_auth_idempotency_replay_and_privacy(self) -> None:
        vocabulary = set(self.fixture["privacy_classes"])
        self.assertEqual(vocabulary, {"public", "internal", "private", "restricted"})
        for provider in self.fixture["providers"]:
            name = provider["provider"]
            with self.subTest(provider=name):
                self.assertIn(provider["direction"], DIRECTIONS)
                self.assertTrue(provider["directions"])
                self.assertLessEqual(set(provider["directions"]), DIRECTION_FLAGS)
                self.assertEqual("inbound" in provider["directions"], provider["direction"] == "inbound-webhook")
                self.assertEqual(
                    "outbound" in provider["directions"],
                    provider["direction"] == "outbound-read-only" or bool(provider["outbound_calls"]),
                )
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

    def test_outbound_calls_name_credentials_by_reference_only(self) -> None:
        for provider in self.fixture["providers"]:
            with self.subTest(provider=provider["provider"]):
                self.assertIsInstance(provider["credential_refs"], list)
                for name in provider["credential_refs"]:
                    self.assertRegex(name, CREDENTIAL_NAME)
                for call in provider["outbound_calls"]:
                    self.assertTrue(_nonempty(call["via"]))
                    self.assertTrue(_nonempty(call["call"]))
                    self.assertTrue(_nonempty(call["evidence"]))
                    self.assertLessEqual(set(call["credential_refs"]), set(provider["credential_refs"]))
                if provider["direction"] == "outbound-read-only":
                    self.assertTrue(provider["outbound_calls"] or provider["routes"])

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
                    self.assertIn(signature["secret_env"], provider["credential_refs"])
                    self.assertEqual(signature["gateway_verification"], "missing")
                    # A signed delivery carries third-party payloads; never below private.
                    self.assertIn(provider["privacy_class"], {"private", "restricted"})

    def test_finance_and_health_data_providers_are_restricted(self) -> None:
        by_id = {provider["provider"]: provider for provider in self.fixture["providers"]}
        for provider_id in ("binance-th", "stripe", "internal-revenue-push", "strava", "gmail"):
            with self.subTest(provider=provider_id):
                self.assertEqual(by_id[provider_id]["privacy_class"], "restricted")

    def test_architecture_docs_citations_resolve_to_the_pinned_commit(self) -> None:
        revision = self.fixture["contract"]["revision"]
        texts = {
            "fixture": FIXTURE_PATH.read_text(encoding="utf-8"),
            "doc": GATE_DOC.read_text(encoding="utf-8"),
        }
        for label, text in texts.items():
            shas = set(re.findall(r"architecture-docs@([0-9a-f]+)", text))
            with self.subTest(document=label):
                self.assertTrue(shas, "no architecture-docs citation found")
                for sha in shas:
                    self.assertTrue(revision.startswith(sha), f"architecture-docs@{sha} is not {revision}")


class SourceSnapshotCoverageTests(unittest.TestCase):
    """The map covers everything in the pinned source snapshot (runs in CI)."""

    def setUp(self) -> None:
        self.fixture = load_fixture()
        self.providers = self.fixture["providers"]
        self.routes = mapped_routes(self.fixture)

    def test_snapshot_entries_are_well_formed(self) -> None:
        sources = load_sources()
        self.assertEqual(self.fixture["sources_snapshot"], "fixtures/gates/webhook-provider-sources.json")
        keys = {entry["key"] for entry in sources["sources"]}
        self.assertEqual(keys, {"contract", "integration_health", "discovery", "ai_gateway"})
        for entry in sources["sources"]:
            with self.subTest(source=entry["key"]):
                self.assertRegex(entry["commit"], r"^[0-9a-f]{40}$")
                self.assertRegex(entry["git_blob"], r"^[0-9a-f]{40}$")
                self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                self.assertTrue(entry["lines"])

    def test_contract_webhook_section_matches_snapshot(self) -> None:
        rows = contract_rows(source("contract")["lines"], CONTRACT_SECTION)
        self.assertEqual(rows, self.fixture["contract"]["webhook_routes"])
        for route in rows:
            with self.subTest(route=route):
                self.assertIn(route, sorted(self.routes))
                self.assertEqual(self.routes[route]["direction"], "inbound-webhook")

    def test_every_contract_ai_and_integration_route_is_mapped(self) -> None:
        rows = contract_rows(source("contract")["lines"], READ_ROUTES_SECTION)
        self.assertTrue(rows)
        aggregates = self.fixture["contract"]["aggregate_routes"]
        for route in rows:
            with self.subTest(route=route):
                if route in aggregates:
                    field = aggregates[route]
                    self.assertTrue(
                        any(provider.get(field) for provider in self.providers),
                        f"{route} aggregates {field} but no provider declares one",
                    )
                else:
                    self.assertIn(route, sorted(self.routes))
        self.assertEqual(
            [row for row in rows if row not in aggregates], self.fixture["contract"]["provider_read_routes"]
        )

    def test_signed_webhook_auth_class_matches_snapshot(self) -> None:
        lines = source("contract")["lines"].values()
        signed = next(line for line in lines if line.startswith("| Signed webhook |"))
        signed_paths = set(re.findall(r"`(/api/webhook/[a-z-]+)`", signed))
        fixture_signed = {
            route.split(" ", 1)[1]
            for provider in self.providers
            if provider["auth_class"] == "signed-webhook"
            for route in provider["routes"]
        }
        self.assertEqual(signed_paths, fixture_signed)

    def test_no_mapped_route_is_outside_the_contract(self) -> None:
        contract = self.fixture["contract"]
        allowed = set(contract["webhook_routes"]) | set(contract["provider_read_routes"])
        self.assertEqual(set(self.routes) - allowed, set())

    def test_every_health_probe_is_mapped(self) -> None:
        defined, active = health_probes()
        internal = set(self.fixture["internal_health_checks"])
        external = defined - internal
        self.assertGreaterEqual(len(external), 28)
        by_check = {provider["health_check"]: provider for provider in self.providers if provider["health_check"]}
        self.assertEqual(set(by_check), external, "integration_health.py probes vs fixture health_check")
        self.assertLessEqual(active, external)
        for check, provider in by_check.items():
            with self.subTest(check=check):
                expected = "active" if check in active else "paused"
                self.assertEqual(provider["health_status"], expected)
                self.assertIn("outbound", provider["directions"])
                self.assertTrue(
                    any(call["via"] == "GET /api/integrations/health" for call in provider["outbound_calls"])
                )

    def test_every_discovery_source_is_mapped(self) -> None:
        lines = source("discovery")["lines"].values()
        constants = dict(
            m.groups() for line in lines if (m := re.match(r'([A-Z_]+_URL) = "(https://[^"]+)"', line))
        )
        self.assertEqual(set(constants), {"APIS_GURU_URL", "MCP_REGISTRY_URL"})
        by_source = {p["discovery_source"]: p for p in self.providers if p["discovery_source"]}
        self.assertEqual(set(by_source), set(constants))
        for name, url in constants.items():
            with self.subTest(source=name):
                calls = by_source[name]["outbound_calls"]
                self.assertIn(url, [call["call"] for call in calls])

    def test_every_ai_gateway_provider_is_mapped(self) -> None:
        lines = source("ai_gateway")["lines"].values()
        text = "\n".join(lines)
        kinds = set(re.findall(r"provider !== '([a-z-]+)'", text))
        env_names = set(re.findall(r"env\.(AI_GATEWAY_[A-Z_]+)", text))
        self.assertEqual(kinds, {"openai-compatible"})
        by_kind = {p["ai_provider"]: p for p in self.providers if p["ai_provider"]}
        self.assertEqual(set(by_kind), kinds)
        provider = by_kind["openai-compatible"]
        self.assertLessEqual(env_names, set(provider["credential_refs"]))
        self.assertIn("POST /api/ai/generate", [call["via"] for call in provider["outbound_calls"]])

    def test_every_integrations_directory_is_mapped(self) -> None:
        tree = next(t for t in load_sources()["trees"] if t["key"] == "integrations_dir")
        dirs = sorted({path.split("/")[1] for path in tree["files"] if path.count("/") >= 2})
        self.assertEqual(dirs, sorted(self.fixture["solo_empire_integrations_dirs"]))
        self.assertEqual(dirs, sorted(self.fixture["integrations_dir_provider"]))
        ids = {provider["provider"] for provider in self.providers}
        for directory, provider in self.fixture["integrations_dir_provider"].items():
            with self.subTest(directory=directory):
                self.assertIn(provider, ids)


class LiveSourceDriftTests(unittest.TestCase):
    """Optional: with local checkouts, prove the snapshot still matches git."""

    @staticmethod
    def _repo_root(key: str) -> Path | None:
        if key == "contract":
            candidate = Path(os.environ.get("ARCHITECTURE_DOCS_ROOT") or DEFAULT_ARCH_DOCS)
        else:
            configured = os.environ.get("SOLO_EMPIRE_ROOT")
            if not configured and DEFAULT_SOLO_EMPIRE is None:
                return None
            candidate = Path(configured) if configured else DEFAULT_SOLO_EMPIRE
        return candidate if (candidate / ".git").exists() else None

    @staticmethod
    def _git_show(repo: Path, commit: str, path: str) -> bytes | None:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True, check=False
        )
        return result.stdout if result.returncode == 0 else None

    def test_snapshot_lines_and_hashes_match_git(self) -> None:
        checked = 0
        for entry in load_sources()["sources"]:
            repo = self._repo_root(entry["key"])
            if repo is None:
                continue
            raw = self._git_show(repo, entry["commit"], entry["path"])
            if raw is None:
                continue
            with self.subTest(source=entry["key"]):
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
                lines = raw.decode("utf-8").split("\n")
                for number, text in entry["lines"].items():
                    self.assertEqual(lines[int(number) - 1], text, f"{entry['path']}:{number}")
            checked += 1
        if checked == 0:
            self.skipTest("no architecture-docs / solo-empire checkout (set ARCHITECTURE_DOCS_ROOT, SOLO_EMPIRE_ROOT)")

    def test_snapshot_tree_matches_git(self) -> None:
        tree = next(t for t in load_sources()["trees"] if t["key"] == "integrations_dir")
        repo = self._repo_root("solo-empire")
        if repo is None:
            self.skipTest("no solo-empire checkout (set SOLO_EMPIRE_ROOT)")
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-r", "--name-only", tree["commit"], "--", tree["path"]],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.skipTest("pinned solo-empire commit not available locally")
        self.assertEqual(result.stdout.split(), tree["files"])

    def test_live_contract_still_matches_snapshot(self) -> None:
        repo = self._repo_root("contract")
        entry = source("contract")
        if repo is None or not (repo / entry["path"]).is_file():
            self.skipTest("architecture-docs checkout not available (set ARCHITECTURE_DOCS_ROOT)")
        raw = (repo / entry["path"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            entry["sha256"],
            "working-tree contract differs from the pinned snapshot; re-pin and re-map",
        )


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
        # The only HMAC use is the constant-time Bearer compare; computing a
        # digest over a request body would be a verifier that must be mapped.
        source = SERVER_SOURCE.read_text(encoding="utf-8")
        self.assertNotIn("hmac.new(", source)
        self.assertNotIn("hmac.digest(", source)


if __name__ == "__main__":
    unittest.main()
