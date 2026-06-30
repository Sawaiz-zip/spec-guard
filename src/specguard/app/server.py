"""Stdlib webhook receiver: verify signature → evaluate → upsert the check run.

The HTTP layer is deliberately thin (constitution: no framework dependency for a
single endpoint); the real logic lives in `events.evaluate` and is unit-tested
without a server. `python -m specguard.app.server` / `specguard-app` runs it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from specguard.app import checks, events
from specguard.app.auth import AppAuthError, AppConfig, installation_token

SIGNATURE_HEADER = "X-Hub-Signature-256"
EVENT_HEADER = "X-GitHub-Event"


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Constant-time HMAC-SHA256 check of the raw body against the webhook secret."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def handle_delivery(
    config: AppConfig,
    event_name: str,
    body: bytes,
    signature_header: str | None,
    *,
    token_provider: Any = installation_token,
    upsert: Any = checks.upsert_check_run,
) -> tuple[int, str]:
    """Process one delivery; return (http_status, message). Pure and testable.

    401 on a bad signature; 204 for events/payloads we ignore; 200 once a check
    run has been upserted. Collaborators are injectable for tests.
    """
    if not verify_signature(config.webhook_secret, body, signature_header):
        return 401, "invalid signature"

    payload = json.loads(body)
    pr = events.parse_pr_webhook(event_name, payload)
    if pr is None:
        return 204, "ignored"

    token = token_provider(config.app_id, config.private_key, pr.installation_id)
    result = events.evaluate(pr, token)
    upsert(pr.repo, pr.head_sha, token, result)
    return 200, f"{pr.repo}#{pr.pr_number}: {result.conclusion}"


def _make_handler(config: AppConfig) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 (stdlib naming)
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                status, message = handle_delivery(
                    config,
                    self.headers.get(EVENT_HEADER, ""),
                    body,
                    self.headers.get(SIGNATURE_HEADER),
                )
            except Exception as exc:  # never crash the server on one bad delivery
                status, message = 500, f"error: {exc}"
            self.send_response(status)
            self.end_headers()
            self.wfile.write(message.encode())

        def log_message(self, *args: Any) -> None:  # quiet default logging
            pass

    return Handler


def main(argv: list[str] | None = None) -> int:
    try:
        config = AppConfig.from_env()
    except AppAuthError as exc:
        print(f"specguard-app: {exc}", file=sys.stderr)
        return 2
    port = int((argv or sys.argv[1:] or ["8080"])[0]) if (argv or sys.argv[1:]) else 8080
    server = HTTPServer(("0.0.0.0", port), _make_handler(config))
    print(f"specguard-app: listening on :{port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
