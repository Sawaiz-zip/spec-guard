"""Checks API client: create vs. update-in-place, and the webhook handler shell."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from specguard.app.auth import AppConfig
from specguard.app.checks import CheckRunResult, upsert_check_run
from specguard.app.server import handle_delivery

RESULT = CheckRunResult(conclusion="failure", title="Changes requested", summary="...")


class TestUpsertCheckRun:
    def test_creates_when_none_exists(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.path.endswith("/check-runs") and request.method == "GET":
                return httpx.Response(200, content=json.dumps({"check_runs": []}))
            return httpx.Response(201, content=json.dumps({"id": 99}))

        run_id = upsert_check_run(
            "acme/widgets", "deadbeef", "tok", RESULT, transport=httpx.MockTransport(handler)
        )
        assert run_id == 99
        post = [r for r in seen if r.method == "POST"][0]
        assert post.url.path == "/repos/acme/widgets/check-runs"
        body = json.loads(post.content)
        assert body["head_sha"] == "deadbeef" and body["conclusion"] == "failure"
        assert body["name"] == "specguard"

    def test_updates_in_place_when_exists(self):
        # FR-002/003: an approval re-eval updates the SAME run, never a 2nd check.
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.method == "GET":
                return httpx.Response(200, content=json.dumps({"check_runs": [{"id": 7}]}))
            return httpx.Response(200, content=json.dumps({"id": 7}))

        run_id = upsert_check_run(
            "acme/widgets", "sha", "tok",
            CheckRunResult(conclusion="success", title="ok", summary="approved"),
            transport=httpx.MockTransport(handler),
        )
        assert run_id == 7
        patches = [r for r in seen if r.method == "PATCH"]
        assert len(patches) == 1
        assert patches[0].url.path == "/repos/acme/widgets/check-runs/7"
        assert not [r for r in seen if r.method == "POST"]  # no second check created


class TestHandleDelivery:
    CONFIG = AppConfig(app_id="1", private_key="pem", webhook_secret="shh")

    def _sign(self, body: bytes) -> str:
        return "sha256=" + hmac.new(b"shh", body, hashlib.sha256).hexdigest()

    def _pr_body(self) -> bytes:
        return json.dumps(
            {
                "installation": {"id": 5},
                "pull_request": {
                    "number": 7,
                    "user": {"login": "dev"},
                    "base": {"sha": "base", "repo": {"full_name": "acme/widgets"}},
                    "head": {"sha": "head", "repo": {"full_name": "acme/widgets"}},
                },
            }
        ).encode()

    def test_bad_signature_401_no_processing(self):
        called = []
        status, _ = handle_delivery(
            self.CONFIG, "pull_request", self._pr_body(), "sha256=wrong",
            token_provider=lambda *a: called.append(1) or "t",
            upsert=lambda *a: called.append(1),
        )
        assert status == 401
        assert not called  # rejected before any token/API work

    def test_unhandled_event_204(self):
        body = b"{}"
        status, _ = handle_delivery(
            self.CONFIG, "push", body, self._sign(body),
            token_provider=lambda *a: "t", upsert=lambda *a: None,
        )
        assert status == 204

    def test_valid_pr_delivery_upserts(self):
        body = self._pr_body()
        captured = {}

        def fake_upsert(repo, head_sha, token, result):
            captured["repo"] = repo
            captured["conclusion"] = result.conclusion

        def fake_evaluate(pr, token, **kw):
            return CheckRunResult(conclusion="success", title="ok", summary="s")

        # Patch evaluate via the events module the handler calls.
        import specguard.app.events as events_mod
        import specguard.app.server as server_mod
        orig = events_mod.evaluate
        events_mod.evaluate = fake_evaluate  # type: ignore[assignment]
        try:
            status, msg = handle_delivery(
                self.CONFIG, "pull_request", body, self._sign(body),
                token_provider=lambda *a: "tok", upsert=fake_upsert,
            )
        finally:
            events_mod.evaluate = orig  # type: ignore[assignment]
        assert status == 200
        assert captured == {"repo": "acme/widgets", "conclusion": "success"}
        assert "success" in msg
        _ = server_mod
