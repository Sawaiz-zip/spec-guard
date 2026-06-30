# Quickstart & Runbook: GitHub App

Contracts: [app-interface](contracts/app-interface.md). Entities: [data-model.md](data-model.md).

## V1. Unit suite (no credentials) — every merge

```bash
pip install -e ".[dev,app]"
pytest tests/test_app_*.py
```

**Expected**: green. Covers signature verification, JWT building, installation-token
exchange (mocked httpx), commit authorship, the full `evaluate_webhook` pipeline against a
temp git repo with `FakeAdapter`, and check-run create/update payloads. No live App, no
endpoint, no API key.

## V2. Verdict parity with the gate (SC-003)

```bash
pytest tests/test_app_events.py -k parity
```

**Expected**: for the same base/head and lock, `evaluate_webhook` yields the same
classification/outcome as `ci.py` — the App and the Action are the same core.

## V3. Live registration & deploy (user-gated runbook)

Requires owner credentials and a public endpoint — not runnable in CI.

1. **Register the App** (github.com → Settings → Developer settings → GitHub Apps → New):
   - Webhook URL: your deployed receiver; Webhook secret: a random string.
   - Permissions: Checks (read/write), Pull requests (read), Contents (read), Metadata (read).
   - Subscribe to events: Pull request, Pull request review, Check run.
   - Generate a private key (PEM).
2. **Configure the server** env: `SPECGUARD_APP_ID`, `SPECGUARD_APP_PRIVATE_KEY` (PEM),
   `SPECGUARD_WEBHOOK_SECRET`, and your classifier key (e.g. `ANTHROPIC_API_KEY`).
3. **Run**: `specguard-app` (or `python -m specguard.app.server`); put it behind TLS.
4. **Install** the App on a repo that has `.specguard/lock.json` (or a derivable Spec
   Kit/OpenSpec layout). Require the `specguard` check under branch protection.

## V4. Live scenarios (after V3)

| # | Action | Expected |
|---|--------|----------|
| 1 | Fork PR adds an out-of-scope topic to a watched file | check run **fails**, blocks merge — no secret exposed to the fork |
| 2 | Authorized role approves via native review | the **same** check run flips to passed; no second check; merge unblocks |
| 3 | New commit pushed after approval | fresh head SHA → new check run starts blocked again (no stale approval) |
| 4 | Bot-authored scope change, human opener | blocked pending human approval (propose-only agents rule) |
| 5 | Classifier key invalid | check run **neutral** "could not classify" (fail-open), never errors |

## Success-criteria traceability

| Scenario | Validates |
|---|---|
| V1 | FR-001/005/009/010 (logic), SC-005 |
| V2 | SC-003, constitution III |
| V4.1 | SC-001, FR-001 |
| V4.2–3 | SC-002, FR-002/003 |
| V4.4 | FR-005 |
| V4.5 | FR-010 |
| V3 install flow | SC-004, FR-006 |
