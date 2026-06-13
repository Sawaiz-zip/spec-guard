# Data Model: Local Tools (Phase 1)

Phase 0 models (`ScopeLock`, `Config`, `RolesConfig`, `Classification`, `Verdict`,
`PRContext`, `Approval`) are unchanged. Phase 1 adds in-memory shapes only — no new
on-disk formats (constitution II).

## New in-memory models

### CheckSnapshot (`src/specguard/localcheck.py`)

What `specguard check` resolved to evaluate.

| Field | Type | Rules |
|---|---|---|
| `mode` | `"worktree"` \| `"staged"` \| `"range"` | worktree is the CLI default; staged is the hook's mode |
| `base_ref` | str | resolved baseline (default `HEAD`); governance config is read HERE (FR-010) |
| `head_desc` | str | human label for the compared side: `"working tree"`, `"index"`, or a ref |
| `changes` | list[ChangedFile] | watched-filtered, built with existing gitdiff plumbing |

Derivation: `worktree` → `git diff HEAD` paths + worktree contents; `staged` →
`git diff --cached` + index contents (`git show :path`); `range` → existing
`watched_changes(base, head)`.

### LocalReport (`src/specguard/localreport.py`)

The rendered result every local surface shows.

| Field | Type | Rules |
|---|---|---|
| `verdicts` | list[Verdict] | unchanged engine output |
| `baseline` | str | the `base_ref` used, always displayed (FR-010 disclosure) |
| `advisory_notice` | str | constant text; MUST appear in 100% of outputs (SC-006) |
| `would_block` | bool | drives CLI exit code (mirrors ci.py semantics) |

Rendering rules: additive → one quiet line (constitution IV); `scope_change_unapproved`
→ "would block until {role} approves" (FR-011, never implies live approval state);
`classifier_error` → "could not classify — advisory check skipped".

### InitAnswers (`src/specguard/cli.py`)

Collected before any file is written; `init` is transactional per file.

| Field | Type | Rules |
|---|---|---|
| `goal` | str | required, non-empty |
| `scope_in` | list[str] | may be empty |
| `scope_out` | list[str] | may be empty |
| `write_config` | bool | optional `.specguard/config.yml` from defaults |
| `write_roles` | bool | optional `.specguard/roles.yml` template |
| `write_workflow` | bool | optional `.github/workflows/specguard.yml` consumer snippet |
| `write_hook` | bool | optional plain `.git/hooks/pre-commit` script |

Validation: produced files MUST round-trip through the existing `config.parse_*` loaders
before being reported as created. Existing `lock.json` → refuse unless `--force`.

## Changed interfaces (no semantic change)

### ClassifierAdapter (protocol, `src/specguard/classifier.py`)

```text
classify(lock: ScopeLock, changed: ChangedFile, config: Config) -> Classification
```

- MUST call `assert_model_allowed(config.model)` before any provider call (001 R2a —
  guardrail is part of the protocol contract, see contracts/adapter-protocol.md).
- MUST return a schema-valid `Classification` or raise `ClassifierError`.
- `AnthropicAdapter`: existing prompt/parse/re-ask logic, byte-stable prompt (no eval
  re-run needed). `FakeAdapter` (tests): canned Classifications keyed by path.

### engine.evaluate_pr

Takes `adapter: ClassifierAdapter` where it previously took a raw client. Callers:
`ci.py` (constructs `AnthropicAdapter`), `cli.py`, `mcp_server.py`, tests. Verdict
pipeline unchanged — D2 of 001 still holds.

## Relationships

```text
cli check / hook / MCP tool ──builds──► CheckSnapshot
CheckSnapshot.base_ref ──show_file+parse_*──► ScopeLock/Config/RolesConfig   (FR-010)
CheckSnapshot.changes ──evaluate_pr(adapter, approvals=[])──► list[Verdict]
list[Verdict] ──localreport──► LocalReport (terminal / hook / MCP rendering)
ci.py ──unchanged path──► report.py (GitHub rendering)
```
