# Research & Decisions: Local Tools (Phase 1)

No NEEDS CLARIFICATION markers existed in the Technical Context; this file records the
decisions behind plan.md D1–D8 with rationale and alternatives.

## R1. CLI framework: stdlib argparse

- **Decision**: `argparse` subcommands + stdlib `input()` for `init` prompts; entry point
  `specguard = specguard.cli:main` via `[project.scripts]`.
- **Rationale**: Two subcommands and ~6 flags don't justify a dependency. Phase 0
  deliberately kept the install surface to four runtime deps; the composite action
  installs this same package on every CI run, so dependency weight is a real cost.
- **Alternatives considered**: `typer`/`click` (nicer prompts/completion — rejected for
  dependency weight); `rich` for output (rejected: plain text matches the no-UI posture
  and renders identically in hooks/CI logs).

## R2. MCP server: official `mcp` SDK, stdio transport, optional extra

- **Decision**: Use the official MCP Python SDK (`mcp` on PyPI, FastMCP server API) over
  stdio only, packaged as the `specguard-ci[mcp]` extra; import-guarded with an
  actionable install hint. Exact SDK version pin to be confirmed at implementation time
  against the current release.
- **Rationale**: stdio is what editor/agent hosts (Claude Code, etc.) spawn locally — no
  listener, no network surface, consistent with constitution VI. An extra keeps the CI
  install payload unchanged.
- **Alternatives considered**: hand-rolled JSON-RPC over stdio (rejected: protocol drift
  risk for zero benefit); HTTP/SSE transport (rejected: introduces a network listener —
  constitution VI smell, and unneeded for local agents); making `mcp` a required dep
  (rejected: CI never needs it).

## R3. Pre-commit hook semantics: warn-only, hard timeout, dual distribution

- **Decision**: Hook = `specguard check --staged --hook`. `--hook` mode always exits 0
  (verdicts, config errors, missing key, timeout — everything), prints nothing when no
  watched files are staged, and enforces a classifier timeout (default 30 s,
  `SPECGUARD_HOOK_TIMEOUT` env override). Distributed via `.pre-commit-hooks.yaml` (id
  `specguard-check`) and an `init`-offered plain `.git/hooks/pre-commit` script.
- **Rationale**: Constitution I makes local blocking a defect, not a feature: a blocking
  hook trains `--no-verify` habits and falsely implies a security boundary. 30 s bounds
  the worst-case commit delay while allowing one classifier round-trip.
- **Alternatives considered**: exit non-zero on BLOCK verdicts (rejected: violates
  constitution I and spec FR-006); skipping classification entirely in hooks and only
  pattern-matching (rejected: violates one-core rule III).

## R4. Snapshot model and defaults

- **Decision**: `check` defaults to working-tree-vs-HEAD; `--staged` for index-vs-HEAD;
  `--base REF [--head REF]` for committed ranges. Baseline ref is always reported.
- **Rationale**: "What will the gate say about what I'd push?" is the P1 question — the
  working tree is what you'd push. The hook needs exactly the staged view. Ref ranges
  reproduce CI verdicts for existing branches (and power SC-001 parity testing).
- **Alternatives considered**: staged-by-default (rejected: surprising for the primary
  interactive use; the hook passes `--staged` explicitly); diffing against the remote
  default branch by default (rejected: requires network/fetch state assumptions).

## R5. Governance config provenance locally (FR-010)

- **Decision**: Read lock/config/roles at the snapshot baseline via `gitdiff.show_file`
  + `config.parse_*` — never from the working tree — and name the baseline in output.
- **Rationale**: Inherits the merge gate's trusted-base rule (Phase 0 E2E security
  finding). A user editing their own lock locally sees the verdict their PR would
  actually get, not a self-approved preview.
- **Alternatives considered**: working-tree config for convenience (rejected: previews
  would diverge from the gate exactly when it matters most); a `--trust-worktree` escape
  hatch (deferred: add only if real usage demands it).

## R6. ClassifierAdapter protocol shape

- **Decision**: `ClassifierAdapter` protocol with a single method
  `classify(lock: ScopeLock, changed: ChangedFile, config: Config) -> Classification`;
  `AnthropicAdapter` wraps the existing prompt/parse/re-ask logic verbatim;
  `engine.evaluate_pr` takes an adapter; the Opus 4.8 guardrail
  (`assert_model_allowed`) is enforced at the adapter boundary so every present and
  future adapter inherits it (001 R2a is non-negotiable).
- **Rationale**: The protocol is the narrowest seam that keeps the engine
  provider-agnostic. Wrapping (not rewriting) the Anthropic path keeps the calibrated
  prompt byte-stable — no eval re-run required (constitution gate untouched).
- **Alternatives considered**: provider plug-ins via entry points (rejected for now:
  packaging machinery without a second provider to justify it); LiteLLM-style
  multi-provider client (rejected: heavy dependency, and Phase 1 ships no second
  provider anyway).

## R7. Local rendering

- **Decision**: New `localreport.py` (plain-text renderer + advisory disclosure);
  `report.py` stays GitHub-only. MCP tools return structured verdict objects plus the
  same disclosure text.
- **Rationale**: Constitution III says surfaces differ only in formatting — so formatting
  lives in per-surface renderers over the shared `Verdict` list, asserted by parity tests.
- **Alternatives considered**: teaching `report.py` both formats behind flags (rejected:
  two unrelated output grammars in one module invites drift).

## R8. Approvals in local context

- **Decision**: Local surfaces always supply zero approvals; would-block verdicts render
  as "would block until {role} approves".
- **Rationale**: No PR exists; querying the Reviews API would require network + token and
  would imply enforcement state on an advisory surface (FR-011).
- **Alternatives considered**: optional `--pr N` flag to fetch real approval state
  (deferred to demand; trivially addable since the engine already takes a supplier).
