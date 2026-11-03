"""SPEC-001 R3 / AC2: RS256 bearer tokens from trusted issuers only."""

from __future__ import annotations

import time
import unittest

from jwt_fixtures import TestKey, claims

from book_api_gateway.jwt_verify import (
    IssuerKeys,
    KeysUnavailable,
    TokenError,
    TokenVerifier,
)

ISS = "https://issuer.test"


class StaticKeys(IssuerKeys):
    def __init__(self, keys, *, fail=False):
        super().__init__(ISS + "/.well-known/jwks.json", fetch=self._fetch)
        self.keys, self.fail, self.fetches = keys, fail, 0

    def _fetch(self, _url):
        self.fetches += 1
        if self.fail:
            raise OSError("down")
        return {"keys": [k.jwk() for k in self.keys]}


class Verify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = TestKey("k1")
        cls.other = TestKey("k1")  # same kid, different key: a forged signature

    def verifier(self, keys=None, **kw):
        return TokenVerifier({ISS: StaticKeys(keys if keys is not None else [self.key], **kw)})

    def test_valid_token_returns_issuer_and_subject(self):
        principal = self.verifier().verify(self.key.sign(claims()))
        self.assertEqual((principal.issuer, principal.subject), (ISS, "user-1"))

    def test_rejections(self):
        v = self.verifier()
        now = int(time.time())
        cases = {
            "forged": self.other.sign(claims()),
            "untrusted issuer": self.key.sign(claims(issuer="https://evil.test")),
            "expired": self.key.sign(claims(exp=now - 120)),
            "not yet valid": self.key.sign(claims(nbf=now + 600)),
            "issued in the future": self.key.sign(claims(iat=now + 600)),
            "no sub": self.key.sign(claims(sub=None)),
            "no aud": self.key.sign(claims(aud=None)),
            "no exp": self.key.sign(claims(exp=None)),
            "alg none": self.key.sign(claims(), header={"alg": "none"}),
            "alg HS256": self.key.sign(claims(), header={"alg": "HS256"}),
            "unknown kid": self.key.sign(claims(), header={"kid": "nope"}),
            "two parts": "a.b",
            "garbage": "not-a-token",
            "bad base64": "###.###.###",
        }
        for name, token in cases.items():
            with self.subTest(name), self.assertRaises(TokenError):
                v.verify(token)

    def test_token_without_kid_tries_each_issuer_key(self):
        # empire-platform tokens carry no kid; cells try their rollover keys in turn.
        second = TestKey("k2")
        v = self.verifier(keys=[second, self.key])
        principal = v.verify(self.key.sign(claims(), header={"kid": None}))
        self.assertEqual(principal.subject, "user-1")
        with self.assertRaises(TokenError):
            v.verify(self.other.sign(claims(), header={"kid": None}))

    def test_tampered_payload_fails(self):
        token = self.key.sign(claims())
        head, _, sig = token.split(".")
        other_payload = self.key.sign(claims(sub="admin")).split(".")[1]
        with self.assertRaises(TokenError):
            self.verifier().verify(f"{head}.{other_payload}.{sig}")

    def test_skew_allows_sixty_seconds(self):
        now = int(time.time())
        self.verifier().verify(self.key.sign(claims(iat=now + 30, nbf=now + 30)))

    def test_keys_unavailable_is_not_a_pass(self):
        with self.assertRaises(KeysUnavailable):
            self.verifier(fail=True).verify(self.key.sign(claims()))

    def test_keys_are_cached_and_unknown_kid_refetch_is_throttled(self):
        keys = StaticKeys([self.key])
        v = TokenVerifier({ISS: keys})
        v.verify(self.key.sign(claims()))
        v.verify(self.key.sign(claims()))
        self.assertEqual(keys.fetches, 1)
        with self.assertRaises(TokenError):  # just loaded: no refetch inside the minute
            v.verify(self.key.sign(claims(), header={"kid": "rotated"}))
        self.assertEqual(keys.fetches, 1)
        keys._attempted_at -= 61
        for _ in range(3):
            with self.assertRaises(TokenError):
                v.verify(self.key.sign(claims(), header={"kid": "rotated"}))
        self.assertEqual(keys.fetches, 2)  # one refetch per minute at most


if __name__ == "__main__":
    unittest.main()
