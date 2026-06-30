"""GitHub App authentication: App JWT (RS256) → installation access token.

The classifier credential is read from the server environment elsewhere; this
module only handles the App's own GitHub identity. Contract:
specs/006-github-app/contracts/app-interface.md.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

API_BASE = "https://api.github.com"

ENV_APP_ID = "SPECGUARD_APP_ID"
ENV_PRIVATE_KEY = "SPECGUARD_APP_PRIVATE_KEY"
ENV_WEBHOOK_SECRET = "SPECGUARD_WEBHOOK_SECRET"

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class AppAuthError(Exception):
    """App credentials missing/invalid, or the token exchange failed."""


@dataclass
class AppConfig:
    app_id: str
    private_key: str
    webhook_secret: str

    @classmethod
    def from_env(cls) -> AppConfig:
        missing = [
            name
            for name in (ENV_APP_ID, ENV_PRIVATE_KEY, ENV_WEBHOOK_SECRET)
            if not os.environ.get(name)
        ]
        if missing:
            raise AppAuthError(
                f"missing required App env vars: {', '.join(missing)}"
            )
        return cls(
            app_id=os.environ[ENV_APP_ID],
            private_key=os.environ[ENV_PRIVATE_KEY],
            webhook_secret=os.environ[ENV_WEBHOOK_SECRET],
        )


def build_jwt(app_id: str, private_key: str, *, now: int | None = None) -> str:
    """A short-lived RS256 App JWT. `now` is injectable for deterministic tests."""
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - exercised via server entry
        raise AppAuthError(
            'the GitHub App needs the optional extra — pip install "specguard-ci[app]"'
        ) from exc
    issued = now if now is not None else int(time.time())
    payload = {
        "iat": issued - 60,  # backdate to tolerate clock skew
        "exp": issued + 9 * 60,  # GitHub caps App JWTs at 10 minutes
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def installation_token(
    app_id: str,
    private_key: str,
    installation_id: int,
    *,
    transport: httpx.BaseTransport | None = None,
    now: int | None = None,
) -> str:
    """Exchange the App JWT for an installation access token."""
    app_jwt = build_jwt(app_id, private_key, now=now)
    url = f"{API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {"Authorization": f"Bearer {app_jwt}", **_HEADERS}
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            response = client.post(url, headers=headers)
            response.raise_for_status()
            return str(response.json()["token"])
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise AppAuthError(f"could not get installation token: {exc}") from exc
