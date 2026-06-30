# Data Model: GitHub App

No new on-disk formats and no persisted state (constitution VI / FR-009). New in-memory
shapes only; all existing models (`ScopeLock`, `Config`, `Verdict`, `PRContext`, `Approval`,
…) are reused unchanged.

## New in-memory models (`src/specguard/app/`)

### AppConfig (`auth.py`) — from environment, never from a watched repo

| Field | Source env var | Use |
|---|---|---|
| `app_id` | `SPECGUARD_APP_ID` | JWT issuer |
| `private_key` | `SPECGUARD_APP_PRIVATE_KEY` (PEM) | RS256 signing |
| `webhook_secret` | `SPECGUARD_WEBHOOK_SECRET` | HMAC verification |
| classifier key | provider env var (e.g. `ANTHROPIC_API_KEY`) | server-side, never sent to forks |

### PRWebhook (`events.py`) — parsed from the webhook payload

| Field | Type | Notes |
|---|---|---|
| `repo` | str (`owner/name`) | target repo |
| `pr_number` | int | |
| `base_sha` / `head_sha` | str | clone targets; head anchors the check run |
| `installation_id` | int | for the installation token |
| `is_fork` | bool | head repo ≠ base repo (classified anyway, FR-001) |
| `opener_login` | str | fallback author when commit attribution is unavailable |

Maps onto the existing `PRContext` for the engine call (author_login is the attributed
commit author from `commits.py`, not necessarily the opener — D4).

### CommitAuthor (`commits.py`)

| Field | Type | Rules |
|---|---|---|
| `login` | str | per-commit author login |
| `is_bot` | bool | `[bot]` suffix or App-authored — drives the propose-only agents rule |

### CheckRunResult (`events.py` → `checks.py`)

| Field | Type | Maps to Checks API |
|---|---|---|
| `conclusion` | `success` \| `failure` \| `neutral` | `success` (no block), `failure` (≥1 block), `neutral` (could-not-classify / unconfigured) |
| `title` / `summary` | str | check-run output, reusing the §F4 verdict formatting |
| `head_sha` | str | the check run's commit anchor |

## Reused, unchanged

`evaluate_pr(changed, lock, config, roles_config, pr, adapter, get_approvals)` is called
exactly as `ci.py` calls it, against the temp checkout. `resolve_lock`, `watched_changes`,
`make_adapter`, `fetch_approvals`/`fetch_comment_approvals`, and the report formatting are all
reused. The App contributes only: auth, clone, commit-authorship, the Checks client, and the
webhook shell.

## Relationships

```text
webhook → PRWebhook → installation token (auth) → shallow clone base+head (repo)
  → resolve_lock + watched_changes (reused, on the temp checkout)
  → commits.py attributes author → PRContext
  → evaluate_pr (reused core) → verdicts → CheckRunResult → checks.create/update
approval/re-request webhook → same pipeline → UPDATE the same head-SHA check run
```
