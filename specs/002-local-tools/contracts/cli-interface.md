# Contract: CLI Interface

Owner: `src/specguard/cli.py`. Entry point: `specguard` (`[project.scripts]`).

## `specguard init`

Interactive scaffolding. Prompts (in order): goal (required, re-prompted while empty),
in-scope topics (comma/newline separated, may be empty), out-of-scope topics (same),
then yes/no offers: config.yml, roles.yml (asks role name + usernames), CI workflow
snippet, plain git pre-commit hook.

| Flag | Effect |
|---|---|
| `--force` | allow overwriting an existing `.specguard/lock.json` |
| `--yes` | non-interactive: accept defaults, skip all optional files (scriptable) |

Guarantees:
- Refuses to overwrite an existing lock without `--force` (exit 2, names the file).
- Every written file round-trips through the existing loaders before success is reported.
- Final output lists created files, skipped offers, and the next command to run
  (`specguard check`).

Exit codes: `0` success · `1` aborted by user · `2` invalid state (existing lock without
`--force`, not a git repo, unwritable paths).

## `specguard check`

Evaluates watched-file changes for a snapshot and prints local verdicts.

| Flag | Effect |
|---|---|
| *(none)* | working tree vs `HEAD` |
| `--staged` | index vs `HEAD` (the hook's view) |
| `--base REF [--head REF]` | committed range `REF...HEAD-or-given` (reproduces CI verdicts) |
| `--hook` | hook mode: ALWAYS exit 0, silent when nothing watched changed, classifier timeout (30 s default, `SPECGUARD_HOOK_TIMEOUT` override) |
| `--json` | machine-readable verdict list (same shapes as data-model Verdict) |

Output (human mode):
```
specguard check — baseline HEAD (a1b2c3d) vs working tree

✅ README.md — ADDITIVE (97%): Fixed a typo in the usage section
❌ ARCHITECTURE.md — SCOPE CHANGE (94%): Added SaaS pricing section
   out-of-scope: [SaaS pricing]
   would block until architect approves (merge-time check)

⚠ advisory only — local results do not enforce anything; the merge-time
  check on your default branch is the only enforcing layer.
```
Invariants: additive files get exactly one quiet line (constitution IV); the baseline is
always named (FR-010); the advisory notice appears in 100% of outputs including `--json`
(as a field) and hook mode (SC-006).

Exit codes (mirror `ci.py`, FR-004): `0` nothing would block · `1` ≥1 verdict would
block · `2` configuration/environment error (malformed config at baseline, not a git
repo, missing `ANTHROPIC_API_KEY` in non-hook mode). `--hook` overrides all of these
to `0` unconditionally (FR-006).

## `specguard mcp`

Starts the stdio MCP server (see mcp-interface.md). Exit 2 with an actionable message
(`pip install "specguard-ci[mcp]"`) when the optional dependency is absent.

## Pre-commit framework hook (`.pre-commit-hooks.yaml`, repo root)

```yaml
- id: specguard-check
  name: SpecGuard (advisory scope check)
  entry: specguard check --staged --hook
  language: python
  pass_filenames: false
  always_run: true
```

Consumers add `repo: https://github.com/Sawaiz-zip/spec-guard` + `rev: v0.x.y` to their
`.pre-commit-config.yaml`. The plain-git variant written by `init` invokes the same
command and is therefore behaviorally identical.
