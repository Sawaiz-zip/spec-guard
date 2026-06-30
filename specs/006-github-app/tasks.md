# Tasks: GitHub App

**Input**: Design documents from `/specs/006-github-app/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

The testable core was implemented in one pass on `006-github-app`; the live deploy is a
user-gated runbook (quickstart V3/V4). 27 new tests; 251 total green on 3.11/3.12 (CI matrix
adds 3.10), ruff + strict mypy clean.

## Phase 1: Packaging

- [X] T001 `[app]` optional extra (`pyjwt[crypto]`) + `specguard-app` entry point in
  `pyproject.toml`; mypy override for `jwt.*`; CI installs `.[dev,mcp,app]`

## Phase 2: Auth & API clients (mocked-httpx tested)

- [X] T002 `app/auth.py` — `AppConfig.from_env`, RS256 `build_jwt`, `installation_token`
- [X] T003 `app/checks.py` — `upsert_check_run` (create vs. update-in-place), `find_check_run_id`
- [X] T004 `app/commits.py` — `attribute_author` (head-commit author, `[bot]` flag) for FR-005

## Phase 3: Orchestration (reuses the validator core)

- [X] T005 `app/repo.py` — shallow-clone base+head into a temp dir using the install token (D1)
- [X] T006 `app/events.py` — `parse_pr_webhook` + `evaluate`: config-at-base, governance
  overlay, `evaluate_pr`, fork classification (FR-001), neutral/fail-open mapping (FR-010)

## Phase 4: Webhook server

- [X] T007 `app/server.py` — stdlib receiver, `verify_signature` (HMAC-SHA256), `handle_delivery`
  (401/204/200), `specguard-app` main

## Phase 5: Tests & docs

- [X] T008 `tests/test_app_auth.py` — JWT, token exchange, signature verification
- [X] T009 `tests/test_app_checks.py` — create vs. update-in-place; handler 401/204/200
- [X] T010 `tests/test_app_events.py` — full pipeline on a temp repo: additive/scope/approved/
  fork/bot/classifier-error/unconfigured + webhook parsing + ci parity
- [X] T011 README roadmap row; quickstart runbook (V3/V4)

## Phase 6: Live (user-gated — needs App registration + a public endpoint)

- [ ] T012 Register the App, deploy `specguard-app` behind TLS, configure env secrets
- [ ] T013 Run quickstart V4 scenarios (fork block, approve-in-place, stale-after-push,
  bot-authored, classifier-outage); capture results
- [ ] T014 (follow-up) GitLab equivalent — separate spec

**Notes**: the core reuses `resolve_lock`/`watched_changes`/`evaluate_pr` verbatim against a
temp checkout (no core changes, no regression to the existing suite). Live verification needs
owner credentials and a public webhook endpoint, hence T012–T013 are gated like the Phase 0
sandbox E2E was.
