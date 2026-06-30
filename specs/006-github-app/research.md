# Research & Decisions: GitHub App

## R1. Clone-and-reuse vs. file-reader refactor

- **Decision**: per webhook, shallow-clone the PR base+head into a temp dir with the
  installation token; reuse `resolve_lock`/`watched_changes`/`evaluate_pr` unchanged.
- **Rationale**: the core reads via `git show base:path`; a checkout makes every existing
  guarantee (trusted-base config, governance overlay, protected paths) hold verbatim with
  zero core changes and zero regression risk to the 224 tests. Constitution III parity is
  then trivially true because it is literally the same code.
- **Alternatives**: a `RefReader` protocol threaded through governance/localcheck (cleaner
  long-term, but invasive now and live-untestable this phase — deferred); fetching each file
  via the contents API and faking a tree (reimplements git, drift risk).

## R2. Auth: App JWT → installation token

- **Decision**: `pyjwt[crypto]` signs an RS256 JWT (`iss=app_id`, short `exp`) with the App
  private key; exchange at `POST /app/installations/{id}/access_tokens` for an installation
  token used for clone + Checks + commits.
- **Rationale**: the standard GitHub App flow. `pyjwt[crypto]` is the minimal dependency and
  lives behind the `[app]` extra so CI/base installs are unaffected.
- **Alternatives**: hand-rolled RS256 with `cryptography` (more code, same dep weight);
  OAuth/user tokens (wrong model — the App needs its own identity to reach forks).

## R3. HTTP receiver: stdlib, not a framework

- **Decision**: `http.server` + `hmac` for signature verification; the event logic is a pure
  function so the HTTP layer stays a thin, swappable shell.
- **Rationale**: keeps dependencies at zero for the transport, matches the project's lean
  ethos, and makes the meaningful logic unit-testable without booting a server. A production
  deployer can put it behind any WSGI/ASGI server later.
- **Alternatives**: FastAPI/Flask (a real dependency for a thin endpoint — rejected now).

## R4. Webhook authenticity

- **Decision**: verify `X-Hub-Signature-256` as HMAC-SHA256 over the raw request body with
  the configured webhook secret, compared with `hmac.compare_digest`; reject mismatches with
  401 before any processing.
- **Rationale**: standard, constant-time, prevents forged events from triggering clones/API
  calls.

## R5. Approval re-evaluation & staleness

- **Decision**: one check run per head SHA; `pull_request_review` (approved) and `check_run`
  re-requests re-run evaluation and **update that run**. Staleness is GitHub's native
  commit↔check association (a new commit = a new head SHA = a fresh check), not a timestamp.
- **Rationale**: removes both Actions-era workarounds and closes the forgeable-committer-date
  gap flagged in the 005 review. Native reviews are already commit-anchored by GitHub.

## R6. Authorship for the agents role

- **Decision**: attribute the change to the head commit's author (login + `[bot]`/App flag)
  via `GET /pulls/{n}/commits`; pass that as `PRContext.author_login` so existing role rules
  apply per actual author.
- **Rationale**: lets "agent proposes, human approves" work even when a human opened the PR —
  the gap the Actions gate (keyed on the opener) cannot close. Multi-author precedence is a
  documented refinement, not blocking.

## R7. Hosting model

- **Decision**: self-hostable App, bring-your-own classifier key; managed instance optional
  and out of scope.
- **Rationale**: matches the existing no-SaaS / no-new-login posture (constitution VI, product
  spec §10). The operational tradeoff (if your instance is down, the required check waits) is
  documented in the runbook.

## R8. What is NOT live-validated this phase

- **Decision**: build and unit-test the full logic with mocked transports + temp repos;
  registering the real App, deploying the receiver, and a live fork-PR demo are a documented
  runbook (user-gated, like the Phase 0 sandbox E2E and PyPI publish).
- **Rationale**: live verification needs a GitHub App registration (App ID, private key,
  webhook secret) and a public endpoint — credentials/infra only the owner can provide.
