# Implementation Plan: Local Tools (CLI, Pre-commit Hook, MCP Server)

**Branch**: `002-local-tools` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-local-tools/spec.md`

## Summary

Expose the existing Phase 0 validator core (`engine.evaluate_pr`) on three advisory local
surfaces — a `specguard` CLI (`init`, `check`), a never-blocking pre-commit hook, and a
stdio MCP server for coding agents — plus a `ClassifierAdapter` protocol that formalizes
the provider seam (Anthropic remains the only shipped adapter). No verdict logic is
duplicated: local surfaces build `ChangedFile` lists from staged/worktree/ref-range
snapshots, read governance config from the committed baseline (same trust rule the merge
gate uses), call the same engine, and differ only in rendering. Every local output carries
an advisory disclosure; the Opus 4.8 guardrail applies unchanged.

## Technical Context

**Language/Version**: Python 3.12 (unchanged from Phase 0) *(superseded by
003-provider-agnostic: floor lowered to Python ≥ 3.10)*

**Primary Dependencies**: Existing: `anthropic`, `pydantic` v2, `pyyaml`, `httpx`. New:
`mcp` (official MCP Python SDK) as an **optional extra** `specguard-ci[mcp]` — the base
install stays lean. CLI uses stdlib `argparse` + `input()` prompts: zero new required deps.

**Storage**: Files in the governed repository only (`.specguard/*`), unchanged. No new
state; `init` writes config files, everything else is read-only.

**Testing**: `pytest` with the existing `FakeAnthropicClient`/fixtures; new surfaces get
a `FakeAdapter` (same canned-Classification idea one level up). CI runs with no API key.
MCP server tested by invoking tool functions directly (no live transport needed).

**Target Platform**: Developer machines (Linux/macOS; Windows via standard Python) and
editor/agent hosts speaking MCP over stdio. No hosted component.

**Project Type**: Existing single library + new CLI entry point (`[project.scripts]
specguard = specguard.cli:main`) + pre-commit metadata (`.pre-commit-hooks.yaml`).

**Performance Goals**: `specguard check` ≤ 60 s for ≤ 5 changed watched files (SC-005);
MCP single-file verdict ≤ 30 s (SC-004); hook adds no perceptible delay when nothing is
watched-changed (SC-003 path) and respects a hard timeout otherwise.

**Constraints**: Local surfaces are advisory only and must say so (constitution I);
`claude-opus-4-8` stays hard-blocked on every path (research.md 001 R2a); governance
config read from the committed baseline, never the dirty working tree (Phase 0 E2E
security finding, FR-010); pre-commit hook must exit 0 unconditionally.

**Scale/Scope**: Same single-repo scale as Phase 0. Four new modules + one protocol
refactor inside `classifier.py`; no changes to verdict semantics.

## Constitution Check

*GATE: evaluated against constitution v1.0.0 — all pass, no Complexity Tracking entries.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time enforcement is the security layer | ✅ | All three new surfaces are explicitly advisory: hook exits 0 unconditionally, CLI/MCP outputs carry a bypassability disclosure (FR-005/SC-006). Nothing local gates anything. |
| II. Governance overlay, not a framework | ✅ | No new formats; `init` writes the existing `.specguard/*` shapes. MCP server reads, never defines, spec conventions. |
| III. One shared validator core | ✅ | CLI, hook, and MCP all call `engine.evaluate_pr()` with locally-built `ChangedFile` lists; new code is snapshot assembly + rendering only. SC-001 (100% corpus parity) is the enforcement test. |
| IV. Zero friction for additive changes | ✅ | Local additive verdicts render as one quiet line; hook prints nothing on non-watched commits. |
| V. Deterministic hard blocks, probabilistic advice | ✅ | Unchanged — same engine. Locally, would-block verdicts display as "would block until {role} approves" (FR-011) without inventing approval state. |
| VI. No dashboard, no new UI | ✅ | Terminal output and stdio MCP only; no listener, no web anything. |

*Re-check after Phase 1 design: still ✅ — contracts add no new surfaces beyond CLI/stdio.*

## Project Structure

### Documentation (this feature)

```text
specs/002-local-tools/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions D1–D8
├── data-model.md        # Phase 1 output — new entities, adapter protocol
├── quickstart.md        # Phase 1 output — runnable validation guide
├── contracts/
│   ├── cli-interface.md     # specguard init/check commands, flags, exit codes, output
│   ├── mcp-interface.md     # MCP tools, inputs, result shapes
│   └── adapter-protocol.md  # ClassifierAdapter contract
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
.pre-commit-hooks.yaml      # pre-commit framework hook definition (repo root)
pyproject.toml              # + [project.scripts] specguard; + [project.optional-dependencies] mcp

src/specguard/
├── cli.py                  # argparse entry: `specguard init|check|mcp`; exit codes mirror ci.py
├── localcheck.py           # snapshot resolution: staged / worktree / ref-range →
│                           #   (ChangedFile list, baseline ref, baseline-loaded config)
├── localreport.py          # terminal renderer + advisory disclosure (formatting only)
├── mcp_server.py           # stdio MCP server (import-guarded; needs the [mcp] extra)
├── classifier.py           # + ClassifierAdapter protocol + AnthropicAdapter (refactor)
├── engine.py               # signature takes an adapter (ci.py updated; semantics unchanged)
└── gitdiff.py              # + staged_changes() / worktree_changes() helpers

tests/
├── test_cli.py             # init prompts, check snapshots, exit codes, disclosure
├── test_localcheck.py      # staged vs worktree vs ref-range; baseline config reads
├── test_mcp_server.py      # tool functions invoked directly with FakeAdapter
└── test_classifier.py      # + adapter-protocol conformance tests (extended)
```

**Structure Decision**: Everything stays in the single `src/specguard` package — the
constitution's one-core rule makes a separate CLI/MCP package counterproductive. The MCP
SDK is the only new dependency and is isolated behind an extra so the composite action's
`pip install specguard-ci` payload is unchanged.

## Core Design Decisions

### D1. CLI: stdlib argparse, no framework

`init`/`check` need subcommands, a handful of flags, and interactive prompts — argparse +
`input()` covers it with zero new required dependencies. Click/typer rejected: dependency
weight buys nothing at this surface area. Entry point `specguard` via `[project.scripts]`.

### D2. Snapshot model for `specguard check`

Default = working tree vs `HEAD` (what you'd push). `--staged` = index vs `HEAD` (what
you'd commit; the hook's mode). `--base REF [--head REF]` = committed range (what a PR
would contain). `localcheck.py` resolves each to a `ChangedFile` list using existing
gitdiff plumbing (`git diff --name-status`, `show_file`; index content via `git show
:path`). The resolved baseline ref is carried into the report (FR-010 disclosure).

### D3. Baseline-trusted governance config (FR-010)

Lock/config/roles are read at the snapshot's baseline ref via `gitdiff.show_file` +
`config.parse_*` — exactly the merge gate's rule. A locally-edited lock therefore does not
change the verdict its own PR would get, and the output names the baseline used.

### D4. ClassifierAdapter protocol (the D5 seam from 001, now real)

`classifier.py` gains a `ClassifierAdapter` protocol (`classify(lock, changed, config) ->
Classification`) and `AnthropicAdapter`, which wraps the existing prompt/parse/re-ask
logic unchanged. `engine.evaluate_pr` accepts the adapter; `ci.py` constructs
`AnthropicAdapter`. The Opus guardrail check moves into the adapter boundary so EVERY
adapter inherits it (`assert_model_allowed` stays mandatory — documented in the protocol
contract). Tests get a `FakeAdapter`. No other provider ships this phase.

### D5. Pre-commit hook: `specguard check --staged --hook` and exit 0, always

Distribution both ways: `.pre-commit-hooks.yaml` for the pre-commit framework, and
`specguard init` offers to write a plain `.git/hooks/pre-commit` script. `--hook` mode:
always exits 0 (even on config errors), silent when no watched files are staged, applies
a hard classifier timeout (default 30 s, `SPECGUARD_HOOK_TIMEOUT` to tune) after which it
prints "could not classify — advisory check skipped".

### D6. MCP server: stdio, three tools, optional extra

`specguard mcp` (and module entry `python -m specguard.mcp_server`) starts a stdio server
exposing: `check_proposed_change(path, proposed_content)` — builds a `ChangedFile` from
baseline content vs proposed content and returns the full verdict; `get_scope_lock()`;
`list_watched_paths()`. Import of the `mcp` SDK is guarded with an actionable message
naming `pip install "specguard-ci[mcp]"`. Every tool result embeds the advisory notice
and the unconfigured-repo hint when applicable.

### D7. Rendering split

`localreport.py` renders verdicts for terminals/hook/MCP (plain text, no workflow
commands); `report.py` remains the GitHub renderer. Both consume the same `Verdict` list
— formatting-only divergence per constitution III, asserted by parity tests (SC-001).

### D8. No approvals lookup locally

Local surfaces pass an empty approvals supplier; `BLOCK(scope_change_unapproved)` renders
as "would block until {role} approves" (FR-011). Querying the Reviews API locally is
wrong twice: there is no PR yet, and advisory surfaces must not imply enforcement state.

## Complexity Tracking

> No constitution violations — table intentionally empty.
