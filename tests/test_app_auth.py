"""App JWT building, installation-token exchange, and signature verification."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from specguard.app.auth import AppAuthError, AppConfig, build_jwt, installation_token
from specguard.app.server import verify_signature


def _real_key() -> str:
    """Generate a real test RSA key at runtime (cryptography ships with pyjwt[crypto])."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


class TestJwt:
    def test_build_jwt_roundtrips_claims(self):
        import jwt
        from cryptography.hazmat.primitives import serialization

        key_pem = _real_key()
        token = build_jwt("12345", key_pem, now=1_000_000)
        public = serialization.load_pem_private_key(key_pem.encode(), password=None).public_key()
        # now=1_000_000 is 1970, so skip exp validation against the real clock.
        claims = jwt.decode(token, public, algorithms=["RS256"], options={"verify_exp": False})
        assert claims["iss"] == "12345"
        assert claims["iat"] == 1_000_000 - 60
        assert claims["exp"] == 1_000_000 + 9 * 60


class TestInstallationToken:
    def test_exchanges_jwt_for_token(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(201, content=json.dumps({"token": "ghs_install_xyz"}))

        token = installation_token(
            "12345", _real_key(), 42,
            transport=httpx.MockTransport(handler), now=1_000_000,
        )
        assert token == "ghs_install_xyz"
        assert seen[0].url.path == "/app/installations/42/access_tokens"
        assert seen[0].headers["Authorization"].startswith("Bearer ")

    def test_api_failure_raises(self):
        transport = httpx.MockTransport(lambda r: httpx.Response(404))
        with pytest.raises(AppAuthError):
            installation_token("1", _real_key(), 42, transport=transport, now=1)


class TestAppConfigFromEnv:
    def test_missing_vars_raise(self, monkeypatch):
        for var in ("SPECGUARD_APP_ID", "SPECGUARD_APP_PRIVATE_KEY", "SPECGUARD_WEBHOOK_SECRET"):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(AppAuthError, match="missing required App env vars"):
            AppConfig.from_env()

    def test_loads_when_present(self, monkeypatch):
        monkeypatch.setenv("SPECGUARD_APP_ID", "1")
        monkeypatch.setenv("SPECGUARD_APP_PRIVATE_KEY", "pem")
        monkeypatch.setenv("SPECGUARD_WEBHOOK_SECRET", "shh")
        config = AppConfig.from_env()
        assert config.app_id == "1" and config.webhook_secret == "shh"


class TestSignatureVerification:
    SECRET = "topsecret"

    def _sign(self, body: bytes) -> str:
        return "sha256=" + hmac.new(self.SECRET.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_signature_accepted(self):
        body = b'{"action":"opened"}'
        assert verify_signature(self.SECRET, body, self._sign(body))

    def test_tampered_body_rejected(self):
        good = self._sign(b'{"action":"opened"}')
        assert not verify_signature(self.SECRET, b'{"action":"closed"}', good)

    def test_wrong_secret_rejected(self):
        body = b"x"
        bad = "sha256=" + hmac.new(b"other", body, hashlib.sha256).hexdigest()
        assert not verify_signature(self.SECRET, body, bad)

    def test_missing_or_malformed_header_rejected(self):
        assert not verify_signature(self.SECRET, b"x", None)
        assert not verify_signature(self.SECRET, b"x", "garbage")
