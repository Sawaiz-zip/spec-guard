# Implementation Plan: GitHub App

**Branch**: `006-github-app` | **Date**: 2026-06-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/006-github-app/spec.md`

## Summary

A self-hostable GitHub App that governs pull requests — including **fork PRs** — by posting a
native **Checks-API** check run, reusing the existing validator core verbatim. The App holds
the classifier credential server-side (so forks never see a secret), authenticates as a
GitHub App (JWT → installation token), and on each relevant webhook **shallow-clones the PR's
base+head into a temp dir** and runs the same `resolve_lock` → `watched_changes` →
`evaluate_pr` pipeline `ci.py` uses. An authorized approval updates the *same* check run in
place (Checks API is commit-anchored), retiring the Actions-era `reevaluate` re-run job and
the forgeable-timestamp comment staleness. Per-commit authorship enables the propose-only
`agents` role. Configuration stays in-repo; no SpecGuard-hosted UI or login (constitution VI).

## Technical Context

**Language/Version**: Python ≥ 3.10 (unchanged).

**Primary Dependencies**: core unchanged (anthropic, pydantic, pyyaml, httpx). New **optional
extra** `specguard-ci[app]`: `pyjwt[crypto]>=2.8` for the App JWT (RS256). The webhook
receiver uses the standard library (`http.server` + `hmac`) — no web framework dependency.
Git CLI is used for the per-event shallow clone (already assumed present, as in the gate).

**Storage**: none. All verdict state is recomputed per webhook from the commit (idempotent,
FR-009). No datastore, no session state (constitution VI).

**Testing**: pytest with mocked `httpx` transports (the established `approvals.py` pattern)
for auth/Checks/commits API, a temp `git_repo` for the clone step (the `test_ci.py` pattern),
and the existing `FakeAdapter`. No live App credentials, webhook endpoint, or API key needed
for CI.

**Target Platform**: a long-running webhook receiver the installing org self-hosts; bring
your own classifier key (FR-008). Reuses GitHub's native install screen — no SpecGuard site.

**Project Type**: a new *surface* — `src/specguard/app/` subpackage + a `specguard-app`
entry point — over the unchanged engine. Not new verdict logic.

**Performance Goals / Constraints**: a check run posted well within GitHub's check timing;
merge-time check is still the only security boundary (I); fork PRs classified without
exposing secrets (FR-001); webhook handling idempotent (FR-009); `on_error` policy honored
(FR-010).

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — all pass.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time is the security layer | ✅ | The App's check run, gated by branch protection, IS the boundary. The webhook server adds no bypassable "security" layer. |
| II. Governance overlay | ✅ | Reuses `.specguard/` + the governance overlay unchanged; no new format. |
| III. One shared validator core | ✅ | The App clones base+head and calls the SAME `resolve_lock`/`watched_changes`/`evaluate_pr` as `ci.py`. Parity is a test (SC-003). |
| IV. Zero friction for additive | ✅ | Additive PRs → passing check, no annotations, across all origins. |
| V. Deterministic blocks, probabilistic advice | ✅ | Engine unchanged; Opus guardrail intact via the reused adapters. |
| VI. No dashboard, no new UI | ✅ | Surface = GitHub Checks UI + PR; config = in-repo files + GitHub's native install screen. No SpecGuard-hosted UI/login. The webhook server is headless infra, not a UI. |

*The App is the first server-side component; constitution VI forbids a dashboard/login, NOT a
headless webhook receiver. Recorded explicitly so the boundary is clear.*

## Project Structure

```text
specs/006-github-app/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/app-interface.md
└── tasks.md

src/specguard/app/
├── __init__.py
├── auth.py        # App JWT (RS256, pyjwt) -> installation access token
├── checks.py      # Checks API client: create / update a check run (httpx)
├── commits.py     # per-commit authorship (human / [bot]) for the agents role
├── repo.py        # shallow-clone base+head into a temp dir using the install token
├── events.py      # webhook payload -> verdicts (reused core) -> CheckRunResult
└── server.py      # stdlib webhook receiver + HMAC signature verification; __main__

tests/
├── test_app_auth.py · test_app_checks.py · test_app_events.py · test_app_server.py
└── (reuses conftest git_repo + FakeAdapter)

pyproject.toml      # [app] extra (pyjwt[crypto]); [project.scripts] specguard-app
```

**Structure Decision**: an `app/` subpackage isolates the server surface; the optional `[app]`
extra keeps the CI Action's install lean. The core package is untouched — the App is a caller.

## Core Design Decisions

### D1. Clone-and-reuse, don't refactor the core

The validator core reads files via `git show base_ref:path` against a local checkout. Rather
than introduce a file-reader abstraction across `governance.py`/`localcheck.py` (invasive,
risks 224 tests), the App **shallow-clones base+head into a temp dir per event** and reuses
`resolve_lock`/`watched_changes`/`evaluate_pr` verbatim. Highest fidelity (the trusted-base
rule and overlay work identically) and lowest risk. Clone cost is a documented later
optimization (caching / partial clone).

### D2. Fork PRs (FR-001)

The App clones with its own installation token and classifies regardless of origin — the
credential is server-side and never reaches fork-controlled code. This is the headline gap
the Actions gate cannot close.

### D3. Native check run, approval updates it in place (FR-002/FR-003)

The App creates one check run keyed to the head SHA. On `pull_request_review` (approved) or
`check_run` re-request, it re-evaluates and **updates that same check run** — no second
check, no workflow re-run. Staleness is the platform's native commit↔check association, not a
client timestamp, which closes the comment-staleness gap from the review of 005.

### D4. Authorship for the agents role (FR-005)

`commits.py` reads `GET /pulls/{n}/commits` and attributes the change to the head commit's
author with a bot flag (`[bot]` / App-authored). The App passes that login as
`PRContext.author_login`, so the existing role logic enforces "agent proposes, human
approves" per actual commit author rather than the PR opener. Full multi-author policy is a
documented refinement.

### D5. Headless server, no new dependency for HTTP (FR-006/FR-008)

The receiver is stdlib `http.server`; webhook authenticity is HMAC-SHA256 over the raw body
with the App webhook secret (`hmac.compare_digest`). Only `pyjwt[crypto]` (RS256 signing) is
new, behind `[app]`. Self-hostable; bring-your-own classifier key.

### D6. Idempotency & errors (FR-009/FR-010)

Every handler recomputes all state from the commit, so duplicate deliveries converge. A
classifier failure yields a neutral check conclusion per the `on_error` policy (fail-open
default), never a hard error or a silently-passed scope change.

## Complexity Tracking

> No constitution violations — table intentionally empty.
