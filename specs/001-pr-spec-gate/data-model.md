# Data Model: PR Spec-File Governance Gate (Phase 0)

All models are Pydantic v2 classes in `src/specguard/models.py`. No persistence beyond the
governed repo's own files — these are in-memory shapes plus three on-disk config formats.

## On-disk configuration (in the governed repository)

### ScopeLock — `.specguard/lock.json`

| Field | Type | Rules |
|---|---|---|
| `goal` | str | required, non-empty — the locked project goal |
| `scope_in` | list[str] | required, may be empty — explicitly in-scope topics |
| `scope_out` | list[str] | required, may be empty — explicitly out-of-scope topics |
| `locked_at` | str (ISO-8601) \| null | informational |
| `locked_by` | str \| null | informational (git identity at lock time) |

Validation: parse error or missing `goal` → ConfigError (check fails loudly).
Mirrors product spec §6.5 lock shape (minus `locked_files`, which moved to Config.watch).

### Config — `.specguard/config.yml`

| Field | Type | Default |
|---|---|---|
| `watch` | list[glob] | `["README.md", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "*.kilo", ".specguard/**"]` |
| `block_threshold` | float 0–1 | `0.75` |
| `on_error` | `"warn"` \| `"fail"` | `"warn"` |
| `model` | str | `"claude-sonnet-4-6"` — Opus 4.8 is hard-blocked (guardrail) |
| `max_diff_chars` | int | `30000` |

Missing file → all defaults (lock.json alone is enough to activate plain mode).

### RolesConfig — `.specguard/roles.yml` (optional)

```yaml
roles:                       # role name → list of GitHub usernames; "*" = anyone
  architect: [alice]
  maintainers: [bob, charlie]
  agents: [my-bot[bot]]
rules:                       # path glob → rule; most-specific match wins
  ".specguard/**":
    edit: architect          # hard rule: only this role may touch these paths
  "ARCHITECTURE.md":
    scope_changes: {approve: architect}   # semantic rule: who unblocks SCOPE_CHANGE
```

| Entity | Field | Type | Rules |
|---|---|---|---|
| Role | name → members | dict[str, list[str]] | usernames; `"*"` wildcard member allowed |
| Rule | `edit` | role name \| null | violators → PROTECTED_VIOLATION (deterministic) |
| Rule | `scope_changes.approve` | role name \| null | role whose APPROVED review unblocks |

Validation: unknown role referenced in a rule → ConfigError. Absent file → solo/warn mode.
State: presence of roles.yml is the enforce-mode switch (see plan.md D2).

## In-memory models

### Classification (also the LLM output contract — see contracts/classifier.md)

| Field | Type | Rules |
|---|---|---|
| `classification` | `"ADDITIVE"` \| `"SCOPE_CHANGE"` | the semantic verdict |
| `confidence` | float | 0.0–1.0 |
| `risk_level` | `"LOW"` \| `"MEDIUM"` \| `"HIGH"` | display-only in Phase 0 |
| `out_of_scope_topics` | list[str] | scope_out entries (or novel topics) detected |
| `summary` | str | one line |
| `explanation` | str | human-readable reasoning |

### Verdict (engine output — the shared contract every surface formats)

| Field | Type |
|---|---|
| `file` | str (repo-relative path) |
| `outcome` | `"PASS"` \| `"WARN"` \| `"BLOCK"` |
| `reason` | `"additive"` \| `"scope_change_approved"` \| `"scope_change_unapproved"` \| `"scope_change_low_confidence"` \| `"protected_violation"` \| `"classifier_error"` \| `"not_configured"` |
| `classification` | Classification \| null (null for deterministic/skip reasons) |
| `required_approver_roles` | list[str] (empty unless blocking on approval) |

State transitions (per file): `BLOCK(scope_change_unapproved)` → `PASS(scope_change_approved)`
when a qualifying review appears and the check re-runs. No other transitions — verdicts are
recomputed from scratch each run (stateless).

### PRContext (assembled by ci.py from the event payload)

| Field | Type | Source |
|---|---|---|
| `pr_number` | int | event payload |
| `base_sha` / `head_sha` | str | event payload |
| `author_login` | str | `pull_request.user.login` |
| `is_fork` | bool | `pull_request.head.repo.fork` ≠ base repo |
| `repo` | str (`owner/name`) | `GITHUB_REPOSITORY` |

### Approval (from approvals.py)

| Field | Type | Rules |
|---|---|---|
| `reviewer_login` | str | latest review per reviewer only |
| `state` | str | counts iff `"APPROVED"` |

Relationship: an Approval *qualifies* for a Verdict iff `reviewer_login` ∈ members of any
role in `required_approver_roles`.

## Relationships overview

```
Config.watch ──selects──► changed files ──each──► Verdict
RolesConfig.rules ──edit──► deterministic gate (pre-classifier)
RolesConfig.rules ──scope_changes.approve──► required_approver_roles on BLOCK
ScopeLock ──frames──► Classification (goal + scope lists in every prompt)
Approval ⨯ RolesConfig.roles ──unblocks──► BLOCK → PASS on re-run
```
