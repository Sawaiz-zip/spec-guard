# Data Model: Self-Documenting Configuration Templates

No new persistent entities and no model changes. This feature edits the *text* `init` writes and
the set of files it offers. The relevant "entities" are the generated templates and the existing
models/parsers they must satisfy.

## Generated templates (string constants in `src/specguard/cli.py`)

| Constant | Target file | Parser it must round-trip | Change |
|---|---|---|---|
| (inline dict) | `.specguard/lock.json` | `parse_lock` | Drop `locked_at`/`locked_by` from the generated JSON (write `goal`/`scope_in`/`scope_out` only) |
| `CONFIG_TEMPLATE` | `.specguard/config.yml` | `parse_config` | Rewrite: per-key behavioral explanation + allowed values; keys stay commented (inert) |
| `ROLES_TEMPLATE` *(new; today built inline)* | `.specguard/roles.yml` | `parse_roles` | Add inline docs for `edit` + `scope_changes.approve`; commented full-vocabulary examples; note additive changes always pass |
| `REGIONS_TEMPLATE` *(new)* | `.specguard/regions.yml` | `parse_regions` | New commented template explaining the `files:` heading→regions mapping |

## Rule vocabulary (authoritative — from `models.py`)

The `roles.yml` template MUST document exactly these, and nothing else:

| Key | Location | Meaning | Allowed value |
|---|---|---|---|
| `edit` | `rules.<path>.edit` | Deterministic: only members of this role may edit the path (else PROTECTED_VIOLATION) | a role name |
| `scope_changes.approve` | `rules.<path>.scope_changes.approve` | Which role's approval unblocks a SCOPE_CHANGE verdict on this path | a role name |
| *(additive changes)* | — | Always pass silently; **no rule key exists** | n/a — document as "no configuration needed" |

> There is **no** `additive_changes` rule key. `Rule` = `{ edit?: str, scope_changes?: { approve?: str } }`.

## `config.yml` settings to document (authoritative — from `models.Config`)

| Key | Default | What it does |
|---|---|---|
| `watch` | `["README.md","CLAUDE.md","AGENTS.md","ARCHITECTURE.md","*.kilo",".specguard/**"]` | Glob set of files the gate classifies |
| `block_threshold` | `0.75` | Confidence at/above which a SCOPE_CHANGE blocks (below → warn); range 0.0–1.0 |
| `on_error` | `warn` | Classifier/vendor failure handling: `warn` = pass with a loud warning, `fail` = block |
| `provider` | `anthropic` | Backend: `anthropic` \| `openai` \| `gemini` \| `openrouter` |
| `model` | `claude-sonnet-4-6` | Model id (non-Anthropic providers require an explicit model; Opus 4.8 is guardrail-blocked) |
| `max_diff_chars` | `30000` | Diffs larger than this are truncated before classifying; must be > 0 |

## Unchanged models

`ScopeLock` keeps `locked_at: str | None = None` and `locked_by: str | None = None` — populated by
`governance.py` (framework derivation) and asserted in `tests/test_governance.py`. Only the
*generated file* omits them; the model and its behavior are unchanged.
