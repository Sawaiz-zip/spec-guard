# Contract: GitHub App Interface

Owner: `src/specguard/app/`. The App is a webhook receiver that posts Checks-API verdicts,
reusing the validator core. No persisted state; every verdict recomputed from the commit.

## Webhook events consumed

| Event | Action(s) | Behavior |
|---|---|---|
| `pull_request` | opened, synchronize, reopened | clone base+head, evaluate, create/update the head-SHA check run |
| `pull_request_review` | submitted (approved) | re-evaluate (approvals now include the review), update the same check run |
| `check_run` | rerequested | re-evaluate, update the check run |
| `installation` / `installation_repositories` | added | no-op verdict; logged |

All other events: 204, ignored.

## Authenticity

- `X-Hub-Signature-256` MUST verify as HMAC-SHA256 over the raw body with the webhook secret,
  compared via `hmac.compare_digest`. Mismatch → `401`, no processing.
- Missing/unknown event → `204`.

## Auth flow

1. Sign an RS256 JWT (`iss=app_id`, `iat`, short `exp`) with the App private key.
2. `POST /app/installations/{installation_id}/access_tokens` → installation token.
3. Use the token for: clone (`https://x-access-token:{token}@github.com/{repo}.git`), Checks
   API, and `GET /pulls/{n}/commits`.

The classifier key is read from the server's environment and is NEVER passed to clone or to
fork-controlled code (FR-001).

## Check run

| Field | Value |
|---|---|
| `name` | `specguard` (the branch-protection required-check name — parity with the Action) |
| `head_sha` | the PR head SHA (commit anchor; the approval-update target) |
| `status` | `completed` |
| `conclusion` | `success` (no block) · `failure` (≥1 BLOCK) · `neutral` (could-not-classify / unconfigured) |
| `output.title` / `output.summary` | reused §F4 verdict formatting |

An authorized approval or a `check_run` re-request updates the run **for the same head_sha**
in place — never a second check run (FR-002/FR-003).

## Outputs / guarantees

- Fork PRs are classified identically to internal PRs; no secret reaches fork code (FR-001).
- For identical inputs, App verdicts == Actions-gate verdicts (constitution III, SC-003).
- Duplicate webhook deliveries converge to one check-run state (idempotent, FR-009).
- Classifier unavailable → `neutral` conclusion per `on_error` (fail-open default), never a
  hard error or a silently-passed scope change (FR-010).
- Config/install flow only through repo files + GitHub's native screens — no SpecGuard UI
  (FR-006, SC-004).

## Entry point

`specguard-app` (and `python -m specguard.app.server`) starts the stdlib webhook receiver.
Requires the `[app]` extra; exits with an actionable hint if `pyjwt` is absent. Required env:
`SPECGUARD_APP_ID`, `SPECGUARD_APP_PRIVATE_KEY`, `SPECGUARD_WEBHOOK_SECRET`, and the
provider's classifier key.

## Testing

Pure functions (`verify_signature`, `build_jwt`, `attribute_author`, `evaluate_webhook`) are
unit-tested with mocked `httpx` transports and a temp `git_repo`; no live App, endpoint, or
API key. Live registration + deploy + fork-PR demo is the runbook in quickstart.md
(user-gated).
