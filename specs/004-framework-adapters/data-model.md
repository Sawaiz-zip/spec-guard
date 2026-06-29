# Data Model: Framework Adapters

No persisted storage. These are in-memory entities produced during a run. The output entity
(`ScopeLock`) is the **existing** model — derivation reuses it unchanged, which is what guarantees the
engine and verdict semantics are untouched.

## ScopeLock (existing — `models.py`, unchanged)

The contract every governance source produces.

| Field | Type | Notes |
|---|---|---|
| `goal` | `str` (min_length=1) | The locked project goal. Derivation must always produce a non-empty goal. |
| `scope_in` | `list[str]` | In-scope topics. May be empty (means "judge against goal + scope_out"). |
| `scope_out` | `list[str]` | Out-of-scope topics. May be empty. |
| `locked_at` | `str \| None` | Unused by derivation (no human lock event). |
| `locked_by` | `str \| None` | Derivation may set a provenance hint (e.g. `"spec-kit:constitution.md"`), optional. |

A **Derived Lock** is just a `ScopeLock` instance whose values were computed by an adapter rather than
read from JSON. It is consumed identically by `engine.evaluate_pr`.

## GovernanceSource (new — `Literal` in `governance.py`)

```
GovernanceSource = Literal["explicit-lock", "spec-kit", "openspec", "plain"]
```

Reports which source produced the active lock. `"plain"` is paired with a `None` lock (unconfigured /
no framework / explicit-lock absent). Surfaced in the Action summary and MCP/CLI payload (FR-010).

## resolve_lock — signature & return shape

```
resolve_lock(
    repo_root: Path,
    base_ref: str,
    changed_paths: list[str] = [],   # PR/diff file paths; drives the multi-feature/-proposal union (R2/R3)
) -> tuple[ScopeLock | None, GovernanceSource]
```

`changed_paths` is required for parity: CI passes the PR's changed paths and the local surfaces
(`load_baseline_governance` via `cli.py`/`mcp_server.py`) MUST pass the same paths, or Spec Kit derivation
would be constitution-only locally while feature-aware in CI — different verdicts for the same inputs
(constitution III / FR-005). Empty `changed_paths` means whole-repo/constitution-only derivation.

| Outcome | lock | source |
|---|---|---|
| `.specguard/lock.json` present at base_ref | parsed `ScopeLock` | `"explicit-lock"` |
| `.specify/` present, no explicit lock | derived `ScopeLock` | `"spec-kit"` |
| `openspec/` present, no explicit lock, no Spec Kit | derived `ScopeLock` | `"openspec"` |
| none of the above | `None` | `"plain"` |

`None` lock + `"plain"` reproduces today's "unconfigured" behavior (the SETUP_HINT path in ci.py /
cli.py). Validation rules: a derived lock MUST satisfy the existing `ScopeLock` model (non-empty goal);
if derivation cannot produce a non-empty goal, it degrades to `None`/`"plain"` rather than constructing
an invalid model.

## DerivationContext (new — internal helper input)

What an adapter needs to derive. Not persisted; constructed inside `resolve_lock`.

| Field | Type | Notes |
|---|---|---|
| `repo_root` | `Path` | Repo root. |
| `base_ref` | `str` | The trusted base revision; ALL reads use `show_file(repo_root, base_ref, …)`. |
| `changed_paths` | `list[str]` | PR/diff file paths, used by the multi-feature/multi-proposal union rule (R2/R3). Empty for whole-repo derivation. |

## Error model (reuses existing `ConfigError`)

- Missing/empty scope sections → not an error; empty `scope_in`/`scope_out`.
- Unparseable framework file (e.g. truncated/garbled markdown that breaks a required read) →
  `ConfigError`, identical handling to a malformed `lock.json` (loud, exit 2 in CI). FR-007.