"""SPEC-001 AC1–AC6: /v1/<system>/… through a real gateway process to a recording upstream."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jwt_fixtures import TestKey, claims

from book_api_gateway.config import GatewayConfig
from book_api_gateway.edge import EdgeSettings
from book_api_gateway.jwt_verify import IssuerKeys, TokenVerifier
from book_api_gateway.routes import Route
from book_api_gateway.server import create_server

ISS = "https://issuer.test"
SECRET = "edge-secret-for-tests"


class Upstream(BaseHTTPRequestHandler):
    def _respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        self.server.records.append({"method": self.command, "path": self.path, "body": body,
                                    "headers": {k.lower(): v for k, v in self.headers.items()}})
        status = 404 if self.path.startswith("/missing") else 201 if self.command == "POST" else 200
        payload = json.dumps({"path": self.path, "status": status}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", '"v1"')
        self.send_header("Set-Cookie", "upstream=1")
        if self.path.startswith("/moved"):
            self.send_header("Location", "/items/2")
        elif self.path.startswith("/rel/"):
            self.send_header("Location", "next")  # relative to /rel/
        elif self.path.startswith("/away"):
            self.send_header("Location", "https://elsewhere.example/x")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self):
        self.server.records.append({"method": "HEAD", "path": self.path, "body": b"", "headers": {}})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "1234")
        self.end_headers()

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _respond

    def log_message(self, *_a):
        return


class Edge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = TestKey("k1")
        cls.other = TestKey("k1")
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        cls.upstream.records = []
        threading.Thread(target=cls.upstream.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()
        cls.upstream.server_close()

    def setUp(self):
        self.upstream.records.clear()
        self.events = []
        base = f"http://127.0.0.1:{self.upstream.server_port}"
        keys = IssuerKeys(ISS + "/jwks", fetch=lambda _u: {"keys": [self.key.jwk()]})
        edge = EdgeSettings(
            routes={"habits": Route("habits", base, "127.0.0.1")},
            verifier=TokenVerifier({ISS: keys}),
            edge_secret=SECRET,
            subject_limit_per_minute=5,
            failure_limit_per_minute=3,
            upstream_timeout_seconds=2.0,
        )
        self.gateway = create_server(GatewayConfig(), telemetry_sink=self.events.append, edge=edge)
        threading.Thread(target=self.gateway.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.gateway.server_port}"

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()

    def call(self, path, *, token=None, method="GET", body=None, edge=True, headers=None):
        h = dict(headers or {})
        if edge:
            h["X-Gateway-Edge"] = SECRET
        if token:
            h["Authorization"] = f"Bearer {token}"
        req = Request(self.base + path, method=method, data=body, headers=h)
        try:
            with urlopen(req, timeout=3) as r:
                return r.status, r.headers, r.read()
        except HTTPError as e:
            try:
                return e.code, e.headers, e.read()
            finally:
                e.close()

    def good(self, **kw):
        return self.key.sign(claims(issuer=ISS, **kw))

    def test_ac1_valid_token_reaches_upstream_unchanged(self):
        token = self.good()
        status, headers, body = self.call("/v1/habits/items?day=2026-11-03", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["path"], "/items?day=2026-11-03")
        [rec] = self.upstream.records
        self.assertEqual(rec["headers"]["authorization"], f"Bearer {token}")
        self.assertEqual(rec["headers"]["x-request-id"], headers["X-Request-ID"])
        self.assertNotIn("x-gateway-edge", rec["headers"])
        self.assertEqual(headers["ETag"], '"v1"')
        self.assertIsNone(headers.get("Set-Cookie"))

    def test_ac1_upstream_errors_and_bodies_pass_through(self):
        status, _, body = self.call("/v1/habits/missing", token=self.good())
        self.assertEqual((status, json.loads(body)["status"]), (404, 404))
        status, _, _ = self.call("/v1/habits/items", token=self.good(), method="POST", body=b'{"a":1}',
                                 headers={"Content-Type": "application/json", "Idempotency-Key": "k-1"})
        self.assertEqual(status, 201)
        rec = self.upstream.records[-1]
        self.assertEqual((rec["body"], rec["headers"]["idempotency-key"]), (b'{"a":1}', "k-1"))

    def test_location_is_rewritten_to_the_gateway_path(self):
        _, headers, _ = self.call("/v1/habits/moved", token=self.good())
        self.assertEqual(headers["Location"], "/v1/habits/items/2")
        _, headers, _ = self.call("/v1/habits/rel/item", token=self.good())
        self.assertEqual(headers["Location"], "/v1/habits/rel/next")
        _, headers, _ = self.call("/v1/habits/away", token=self.good())
        self.assertIsNone(headers.get("Location"))

    def test_head_keeps_the_upstream_length(self):
        status, headers, body = self.call("/v1/habits/items", token=self.good(), method="HEAD")
        self.assertEqual((status, headers["Content-Length"], body), (200, "1234", b""))

    def test_ac2_bad_tokens_never_reach_upstream(self):
        bad = (None, "junk", self.other.sign(claims(issuer=ISS)), self.key.sign(claims(issuer="https://evil")),
               self.good(exp=1))
        for i, token in enumerate(bad):  # one client IP each, so the failure lock stays out of the way
            with self.subTest(case=i):
                status, headers, _ = self.call("/v1/habits/items", token=token,
                                               headers={"CF-Connecting-IP": f"198.51.100.{i}"})
                self.assertEqual(status, 401)
                self.assertEqual(headers["WWW-Authenticate"], "Bearer")
        self.assertEqual(self.upstream.records, [])

    def test_ac3_direct_access_is_refused(self):
        status, _, body = self.call("/v1/habits/items", token=self.good(), edge=False)
        self.assertEqual((status, json.loads(body)["error"]), (403, "direct access not allowed"))
        status, _, _ = self.call("/v1/habits/items", token=self.good(), headers={"X-Gateway-Edge": "wrong"},
                                 edge=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.call("/healthz", edge=False)[0], 200)

    def test_ac4_unknown_system_and_unsafe_paths(self):
        self.assertEqual(self.call("/v1/nope/x", token=self.good())[0], 404)
        for path in ("/v1/habits/../admin", "/v1/habits/%2e%2e/admin", "/v1/habits/a%2fb", "/v1/habits/a%00"):
            with self.subTest(path):
                self.assertEqual(self.call(path, token=self.good())[0], 400)
        self.assertEqual(self.upstream.records, [])

    def test_ac5_failed_tokens_lock_the_ip(self):
        for _ in range(3):
            self.assertEqual(self.call("/v1/habits/x", token="junk")[0], 401)
        self.assertEqual(self.call("/v1/habits/x", token=self.good())[0], 429)

    def test_ac5_subject_limit(self):
        token = self.good()
        codes = [self.call("/v1/habits/x", token=token)[0] for _ in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])

    def test_ac5_client_ip_comes_from_cloudflare_only_with_the_edge_secret(self):
        for i in range(3):
            self.call("/v1/habits/x", token="junk", headers={"CF-Connecting-IP": f"203.0.113.{i}"})
        # three different client IPs: none of them is locked yet
        self.assertEqual(self.call("/v1/habits/x", token=self.good(),
                                   headers={"CF-Connecting-IP": "203.0.113.9"})[0], 200)

    def test_ac6_security_headers_everywhere(self):
        for path, token in (("/v1/habits/x", self.good()), ("/v1/habits/x", None), ("/v1/nope", self.good()),
                            ("/healthz", None)):
            with self.subTest(path):
                _, headers, _ = self.call(path, token=token)
                self.assertEqual(headers["Strict-Transport-Security"], "max-age=31536000")
                self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertTrue(headers["X-Request-ID"])

    def test_telemetry_never_carries_token_or_path_tail(self):
        token = self.good()
        self.call("/v1/habits/secret-path?q=private", token=token)
        event = self.events[-1]
        self.assertEqual((event["route"], event["system"], event["status"]), ("v1", "habits", 200))
        text = json.dumps(event)
        for leaked in (token, "secret-path", "private", "user-1"):
            self.assertNotIn(leaked, text)


if __name__ == "__main__":
    unittest.main()
