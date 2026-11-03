"""SPEC-002: X-Gateway-Assertion signing (gateway) and the reference check services copy."""

from __future__ import annotations

import time
import unittest

from test_edge import Edge

from book_api_gateway import assertion
from book_api_gateway.config import ConfigError
from book_api_gateway.edge import EdgeSettings

MASTER = bytes(range(32))


class Reference(unittest.TestCase):
    def setUp(self):
        self.key = assertion.system_key(MASTER, "habits")
        self.now = int(time.time())
        self.args = ("GET", "/v1/habits?status=active", "Bearer t")
        self.header = assertion.sign(self.key, "habits", "GET", "/v1/habits?status=active", self.now,
                                     "rid-1", "Bearer t")

    def check(self, header=None, key=None, system="habits", method="GET", target="/v1/habits?status=active",
              authorization="Bearer t", now=None):
        return assertion.verify(key or self.key, system, self.header if header is None else header, method,
                                target, authorization, self.now if now is None else now)

    def test_ac1_valid_and_bound_to_the_system_key(self):
        self.assertEqual(self.check(), "valid")
        self.assertEqual(self.check(key=assertion.system_key(MASTER, "goals")), "invalid")
        self.assertEqual(self.check(system="goals"), "invalid")

    def test_ac2_every_signed_field_matters(self):
        for name, kw in {"method": {"method": "POST"}, "target": {"target": "/v1/habits"},
                         "query": {"target": "/v1/habits?status=paused"},
                         "authorization": {"authorization": "Bearer other"},
                         "no authorization": {"authorization": ""}}.items():
            with self.subTest(name):
                self.assertEqual(self.check(**kw), "invalid")
        other_rid = assertion.sign(self.key, "habits", "GET", "/v1/habits?status=active", self.now, "rid-2",
                                   "Bearer t")
        forged = ".".join(other_rid.split(".")[:3] + [self.header.split(".")[3]])
        self.assertEqual(self.check(header=forged), "invalid")

    def test_ac2_sixty_second_window(self):
        self.assertEqual(self.check(now=self.now + 60), "valid")
        self.assertEqual(self.check(now=self.now - 60), "valid")
        self.assertEqual(self.check(now=self.now + 61), "invalid")
        self.assertEqual(self.check(now=self.now - 61), "invalid")

    def test_missing_and_malformed(self):
        self.assertEqual(self.check(header=""), "missing")
        for bad in ("v1", "v2." + self.header[3:], self.header + "x", "v1.abc.cmlk.x", "v1.1.!!.x" + "a" * 42):
            with self.subTest(bad):
                self.assertEqual(self.check(header=bad), "invalid")

    def test_request_id_with_dots_and_colons(self):
        h = assertion.sign(self.key, "habits", "GET", "/x", self.now, "req.1:a", "")
        self.assertEqual(assertion.verify(self.key, "habits", h, "GET", "/x", "", self.now), "valid")

    def test_master_key_parsing(self):
        self.assertIsNone(assertion.parse_master(""))
        self.assertEqual(assertion.parse_master(MASTER.hex()), MASTER)
        for bad in ("ab" * 31, "zz" * 32, "abc" * 23):
            with self.subTest(bad), self.assertRaises(ValueError):
                assertion.parse_master(bad)

    def test_bad_master_key_stops_the_gateway(self):
        env = {"GATEWAY_TRUSTED_ISSUERS": '{"https://i.test": "https://i.test/jwks"}',
               "GATEWAY_EDGE_SECRET": "s" * 32, "GATEWAY_ASSERTION_MASTER_KEY": "short"}
        with self.assertRaises(ConfigError):
            EdgeSettings.from_env(env)
        env["GATEWAY_ASSERTION_MASTER_KEY"] = MASTER.hex()
        self.assertEqual(EdgeSettings.from_env(env).assertion_master, MASTER)


class SignedEdge(Edge):
    """Every SPEC-001 edge test again with signing on, plus the SPEC-002 gateway criteria."""

    MASTER = MASTER

    def test_ac1_forwarded_request_carries_a_valid_assertion(self):
        token = self.good()
        status, _, _ = self.call("/v1/habits/items?x=1", token=token)
        self.assertEqual(status, 200)
        rec = self.upstream.records[-1]
        key = assertion.system_key(MASTER, "habits")
        result = assertion.verify(key, "habits", rec["headers"].get("x-gateway-assertion"), "GET",
                                  "/items?x=1", f"Bearer {token}", time.time())
        self.assertEqual(result, "valid")

    def test_ac3_caller_assertion_is_replaced(self):
        self.call("/v1/habits/items", token=self.good(), headers={"X-Gateway-Assertion": "v1.1.YQ.forged"})
        self.assertNotEqual(self.upstream.records[-1]["headers"].get("x-gateway-assertion"), "v1.1.YQ.forged")


if __name__ == "__main__":
    unittest.main()
