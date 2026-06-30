# Contract: Monorepo Multi-Scope

Owner: `src/specguard/scopes.py`.

## `resolve_scopes(repo_root, base_ref, changed: list[ChangedFile]) -> list[Scope]`

1. Group `changed` by the **nearest ancestor directory** (walking from the file's parent up
   to repo root) that contains an explicit `{dir}/.specguard/lock.json` at `base_ref`.
2. A file under no such subdirectory falls into the **repo-root scope** (`scope_dir=""`),
   which alone uses the full `governance.resolve_lock` precedence (explicit > Spec Kit >
   OpenSpec > plain) — unaffected by this feature when no subdirectory scope exists.
3. For a non-root scope: load `{dir}/.specguard/{lock.json,config.yml,roles.yml,regions.yml}`
   directly (no framework derivation at subdirectory level — explicit locks only).
4. A scope whose `lock.json` fails to parse raises `ConfigError` — failing the **whole**
   check loudly, same as any other malformed config (never silently skips that scope).
5. A scope with no lock found and not the repo root cannot occur (a directory is only
   classified as a scope because its lock.json exists).

## `rescope_changed_file(changed: ChangedFile, scope_dir: str) -> ChangedFile`

Strips the `{scope_dir}/` prefix from `changed.path` before the file is handed to
`evaluate_pr`, so a scope's own `roles.yml`/`config.yml` glob patterns are written as if
that `.specguard/` were the repo root (`"README.md"`, not `"packages/api/README.md"`) — the
whole `.specguard/` directory is then copy-paste portable between packages.

## Caller contract (ci.py / app/events.py)

```python
config = parse_config(show_file(repo_root, base_sha, CONFIG_PATH), ...)  # watch globs only
changed = watched_changes(repo_root, base_sha, head_sha, config.watch)
scopes = resolve_scopes(repo_root, base_sha, changed)
if not scopes:
    # no scope at all resolved (unconfigured repo root, no subdirectory scopes) -> setup hint
    ...
all_verdicts = []
for scope in scopes:
    rescoped = [rescope_changed_file(c, scope.scope_dir) for c in scope.changed]
    verdicts = evaluate_pr(rescoped, scope.lock, scope.config, scope.roles, pr,
                            make_adapter(scope.config), get_approvals,
                            regions_config=scope.regions, scope=scope.scope_dir)
    all_verdicts.extend(verdicts)
```

`get_approvals` (PR-level reviews/comments) is the SAME callable across every scope — there
is one set of GitHub reviews per PR, not one per scope.

Watch globs (`config.watch`) are resolved ONCE from the **repo-root** `config.yml` only —
a deliberate phase-1 simplification (research.md R4 family); everything else
(`block_threshold`, `on_error`, `model`, `provider`, `max_diff_chars`, roles, regions) is
fully independent per scope.

## Guarantees

- **Backward compatible**: a repo with no subdirectory `.specguard/` produces exactly one
  scope (`scope_dir=""`) behaving byte-identical to the pre-multi-scope pipeline
  (acceptance scenario 3, SC-005).
- A PR touching files in N scopes produces verdicts independently attributed to each
  (`Verdict.scope`), through the one shared `evaluate_pr` (constitution III, FR-004).
- A scope's `.specguard/**` is protected by that scope's OWN role rules (FR-005) — the
  edit-rule check inside `evaluate_pr` runs against the rescoped (scope-relative) path
  against that scope's `roles_config`.
