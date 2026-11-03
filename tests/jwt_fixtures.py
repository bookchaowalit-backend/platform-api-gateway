"""Test-only RS256 keys and tokens, made with the openssl binary at run time (no key is committed)."""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class TestKey:
    def __init__(self, kid: str = "k1") -> None:
        self.kid = kid
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "key.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", self.path],
            check=True,
            capture_output=True,
        )
        out = subprocess.run(
            ["openssl", "rsa", "-in", self.path, "-noout", "-modulus"], check=True, capture_output=True, text=True
        ).stdout
        self.n = int(out.strip().split("=", 1)[1], 16)

    def jwk(self) -> dict[str, str]:
        n = self.n.to_bytes((self.n.bit_length() + 7) // 8, "big")
        return {"kty": "RSA", "alg": "RS256", "use": "sig", "kid": self.kid, "n": b64url(n), "e": "AQAB"}

    def sign(self, claims: dict, header: dict | None = None) -> str:
        head = {"alg": "RS256", "typ": "JWT", "kid": self.kid, **(header or {})}
        signing_input = f"{b64url(json.dumps(head).encode())}.{b64url(json.dumps(claims).encode())}"
        sig = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", self.path],
            input=signing_input.encode(),
            check=True,
            capture_output=True,
        ).stdout
        return f"{signing_input}.{b64url(sig)}"


def claims(issuer: str = "https://issuer.test", **overrides) -> dict:
    now = int(time.time())
    base = {"iss": issuer, "sub": "user-1", "aud": "habits-api", "iat": now, "exp": now + 300, "jti": uuid.uuid4().hex}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}
