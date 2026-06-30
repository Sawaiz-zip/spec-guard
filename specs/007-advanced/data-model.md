# Data Model: Advanced Governance

No existing on-disk format changes (constitution II) — one new optional file
(`.specguard/regions.yml`), reusing the existing `.specguard/lock.json` /
`config.yml` / `roles.yml` *names* at additional locations for multi-scope.

## New on-disk: RegionsConfig — `.specguard/regions.yml` (optional)

```yaml
files:
  "ARCHITECTURE.md": ["Goal", "Out of Scope"]
```

| Field | Type | Rules |
|---|---|---|
| `files` | `dict[str, list[str]]` | path (relative to this `.specguard/`'s own scope) → list of exact heading-text anchors |

Absence → no file is region-restricted (today's whole-file behavior, unchanged).

## Changed: Verdict (`models.py`)

| Field | Type | Change |
|---|---|---|
| `scope` | `str` | **NEW**, default `""` (repo root) — which scope this verdict belongs to |

New `VerdictReason` member: `"region_ungoverned"` — a quiet `PASS`, no `Classification`,
emitted when a region-restricted file's change falls entirely outside every declared region.

`Verdict.file` for a region sub-verdict is `"{path}#{anchor}"` (e.g.
`"ARCHITECTURE.md#Out of Scope"`); for a multi-scope verdict it is prefixed with the scope
directory (e.g. `"packages/api/README.md"`) — both composable, so a region inside a scoped
package reads as `"packages/api/ARCHITECTURE.md#Out of Scope"`.

## New in-memory: Scope (`scopes.py`)

| Field | Type | Notes |
|---|---|---|
| `scope_dir` | str | `""` = repo root |
| `lock` | ScopeLock | loaded at base ref |
| `config` | Config | loaded at base ref; library defaults if this scope has no own `config.yml` |
| `roles` | RolesConfig \| None | loaded at base ref |
| `regions` | RegionsConfig \| None | loaded at base ref |
| `source` | GovernanceSource | `"explicit-lock"` for any non-root scope; full precedence for the root scope |
| `changed` | list[ChangedFile] | the subset of changed files nearest to this scope |

## New in-memory: AuditEntry (`audit.py`)

| Field | Type |
|---|---|
| `repo`, `pr_number`, `head_sha` | str / int |
| `file`, `scope`, `outcome`, `reason` | str (mirrors the `Verdict`) |
| `classification`, `confidence` | str \| None, float \| None |
| `required_approver_roles` | list[str] |
| `approvals` | list of `{login, state, source}` (no `at` — see research.md R6) |
| `as_of` | str \| None — the PR head commit's time, one value per export batch |

No secrets, no API keys, no new datastore — `export_audit_json` serializes a `list[AuditEntry]`
straight to a string.

## Relationships

```text
.specguard/regions.yml (per scope) ──parse_regions──► RegionsConfig
ChangedFile + RegionsConfig.files[path] ──regions.split_into_regions──► region ChangedFiles
                                                                       + has_outside_change

changed files ──scopes.resolve_scopes──► list[Scope] (nearest-ancestor explicit lock, or
                                                        the existing repo-root resolve_lock)
Scope ──rescope_changed_file──► scope-relative ChangedFile ──evaluate_pr──► list[Verdict]
                                                                              (scope, file
                                                                               re-prefixed)

list[Verdict] + approvals + PRContext ──audit.build_audit_entries──► list[AuditEntry]
                                                                    ──export_audit_json──► str
```
