"""RS256 bearer-token verification against trusted issuers' JWKS (SPEC-001 R3, R8).

Standard library only. RS256 verification is the RSA public-key operation on the JWKS
modulus and exponent, then a byte comparison with the PKCS#1 v1.5 encoding of the SHA-256
digest. Every input is public (token, keys), so timing reveals nothing secret.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

SKEW_SECONDS = 60
KEYS_TTL_SECONDS = 600
REFETCH_MIN_SECONDS = 60
MAX_TOKEN_CHARS = 8192
# A token without kid (empire-platform) is tried against each published key, like the cells' rollover keys.
MAX_KEYS_WITHOUT_KID = 8
# DER prefix of DigestInfo for SHA-256 (RFC 8017 §9.2, note 1).
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


class TokenError(Exception):
    """The token is not acceptable (401)."""


class KeysUnavailable(Exception):
    """The issuer's keys could not be loaded, so no verdict is possible (503)."""


def _timestamp(value: Any) -> bool:
    """A NumericDate: a finite number, never a bool (json accepts NaN and Infinity)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class Principal:
    issuer: str
    subject: str


def _b64decode(part: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except (binascii.Error, ValueError) as exc:
        raise TokenError("malformed token") from exc


def _json_part(part: str) -> dict[str, Any]:
    try:
        value = json.loads(_b64decode(part))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:  # deep nesting is junk, not a 500
        raise TokenError("malformed token") from exc
    if not isinstance(value, dict):
        raise TokenError("malformed token")
    return value


def rs256_valid(signing_input: bytes, signature: bytes, n: int, e: int) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, "big")
    digest_info = SHA256_PREFIX + hashlib.sha256(signing_input).digest()
    padding = k - len(digest_info) - 3
    if padding < 8:
        return False
    return em == b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info


def _default_fetch(url: str) -> dict[str, Any]:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=10) as response:
        return json.loads(response.read(65536))


class IssuerKeys:
    """One issuer's RSA keys by kid, cached for 10 minutes; an unknown kid refetches at most once a minute."""

    def __init__(self, jwks_url: str, *, fetch: Callable[[str], dict[str, Any]] = _default_fetch) -> None:
        self.jwks_url = jwks_url
        self._fetch = fetch
        self._keys: dict[str, tuple[int, int]] = {}
        # Keys published without a kid: only kid-less tokens are tried against them.
        self._unnamed: list[tuple[int, int]] = []
        self._loaded_at = 0.0
        self._attempted_at = 0.0
        self._lock = threading.Lock()

    def _due(self, now: float, kid: str | None = None) -> bool:
        """Fetch only when keys are missing, stale or lack this kid, and never twice within a minute.

        A down issuer would otherwise be fetched on every request (latency plus load on it).
        """
        if self._attempted_at and now - self._attempted_at <= REFETCH_MIN_SECONDS:
            return False
        stale = not (self._keys or self._unnamed) or now - self._loaded_at > KEYS_TTL_SECONDS
        return stale or (kid is not None and kid not in self._keys)

    def _load(self, now: float) -> None:
        self._attempted_at = now
        try:
            document = self._fetch(self.jwks_url)
            keys: dict[str, tuple[int, int]] = {}
            unnamed: list[tuple[int, int]] = []
            for jwk in document.get("keys", []):
                if jwk.get("kty") == "RSA" and jwk.get("alg", "RS256") == "RS256":
                    n = int.from_bytes(_b64decode(jwk["n"]), "big")
                    e = int.from_bytes(_b64decode(jwk["e"]), "big")
                    if n.bit_length() < 2048:
                        continue
                    if jwk.get("kid"):
                        keys[str(jwk["kid"])] = (n, e)
                    else:
                        unnamed.append((n, e))
        except Exception as exc:
            if not (self._keys or self._unnamed):
                raise KeysUnavailable("issuer keys unavailable") from exc
            return  # keep the last good keys
        # A successful answer is the issuer's current key set, even when empty: an issuer that
        # withdraws every key must not keep being trusted with the old ones. Only a failed fetch
        # (above) keeps the last good keys.
        self._keys, self._unnamed, self._loaded_at = keys, unnamed, now

    def all_keys(self) -> list[tuple[int, int]]:
        with self._lock:
            now = time.monotonic()
            if self._due(now):
                self._load(now)
            if not (self._keys or self._unnamed):
                raise KeysUnavailable("issuer keys unavailable")
            return [*self._keys.values(), *self._unnamed][:MAX_KEYS_WITHOUT_KID]

    def key(self, kid: str) -> tuple[int, int] | None:
        with self._lock:
            now = time.monotonic()
            if self._due(now, kid):
                self._load(now)
            if not (self._keys or self._unnamed):
                raise KeysUnavailable("issuer keys unavailable")
            return self._keys.get(kid)


class TokenVerifier:
    def __init__(self, issuers: dict[str, IssuerKeys]) -> None:
        self.issuers = issuers

    def verify(self, token: str, now: float | None = None) -> Principal:
        if len(token) > MAX_TOKEN_CHARS or token.count(".") != 2:
            raise TokenError("malformed token")
        head_part, claims_part, sig_part = token.split(".")
        header = _json_part(head_part)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or (kid is not None and not isinstance(kid, str)):
            raise TokenError("unsupported token")
        claims = _json_part(claims_part)
        issuer = claims.get("iss")
        keys = self.issuers.get(issuer) if isinstance(issuer, str) else None
        if keys is None:
            raise TokenError("untrusted issuer")
        candidates = keys.all_keys() if kid is None else [k for k in [keys.key(kid)] if k is not None]
        if not candidates:
            raise TokenError("unknown key")
        signing_input, signature = f"{head_part}.{claims_part}".encode("ascii"), _b64decode(sig_part)
        if not any(rs256_valid(signing_input, signature, *key) for key in candidates):
            raise TokenError("bad signature")
        now = time.time() if now is None else now
        exp, nbf, iat = claims.get("exp"), claims.get("nbf"), claims.get("iat")
        if not _timestamp(exp) or exp <= now - SKEW_SECONDS:
            raise TokenError("expired")
        for value in (nbf, iat):
            if value is not None and (not _timestamp(value) or value > now + SKEW_SECONDS):
                raise TokenError("not yet valid")
        subject, audience = claims.get("sub"), claims.get("aud")
        if not isinstance(subject, str) or not subject or not audience:
            raise TokenError("missing claims")
        return Principal(issuer, subject)
