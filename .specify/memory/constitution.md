<!--
Sync Impact Report
- Version change: (template) → 1.0.0
- Modified principles: n/a (initial ratification)
- Added sections: Core Principles (I–VI), Additional Constraints & Scope Boundaries,
  Development Workflow & Quality Gates, Governance
- Removed sections: none
- Templates requiring updates:
  ✅ .specify/templates/plan-template.md — generic Constitution Check gate; no edit required
  ✅ .specify/templates/spec-template.md — no constitution-dependent sections; no edit required
  ✅ .specify/templates/tasks-template.md — no constitution-dependent sections; no edit required
- Follow-up TODOs: none
-->

# SpecGuard Constitution

## Core Principles

### I. Merge-Time Enforcement Is the Security Layer

The server-side merge check (GitHub/GitLab required status check) is the ONLY enforcement
layer that MUST be treated as a security boundary. All local layers (MCP server, pre-commit
hooks, CLI) are developer-experience layers: they MUST warn and explain, and MUST be assumed
bypassable (`--no-verify`, agents editing hook scripts, poisoned instruction files are
documented realities). No feature may rely on local enforcement for its security guarantee.

*Rationale: verified in market research — Claude Code Edit/Write tools can modify hook
scripts; deny rules have enforcement bugs; only branch protection cannot be bypassed.*

### II. Governance Overlay, Not a Framework

SpecGuard reads the file conventions of existing SDD frameworks (Spec Kit, OpenSpec, plain
markdown) and plugs into their public extension interfaces. SpecGuard MUST NOT define its own
spec format or proposal workflow, and MUST NOT fork, embed, or import code from Spec Kit or
OpenSpec — only their public file formats matter. Plain mode (raw CLAUDE.md / AGENTS.md /
arbitrary .md paths) MUST always work without any framework present.

*Rationale: the workflow war is over (Spec Kit 90k stars, OpenSpec 52k); interoperating
through files avoids license entanglement and survives their internal changes.*

### III. One Shared Validator Core

Exactly one validation module produces verdicts. Every surface (GitHub Action, CLI, pre-commit
hook, MCP server, future App) MUST call this same core and only differ in how the verdict is
formatted. A change classification rendered in CI MUST be identical to the one rendered
locally for the same inputs.

### IV. Zero Friction for Additive Changes

Additive, in-scope changes MUST auto-pass with at most a quiet log entry. Friction (blocking,
approval requirements, loud annotations) is permitted ONLY at genuine direction changes or
protected-file violations. Any feature that adds friction to the additive path violates this
constitution. False positives are treated as release-blocking defects, not tuning issues.

*Rationale: "blocked my Friday merge over a typo" = uninstalled by Monday. A probabilistic
gate on merges must earn trust before it may exercise power.*

### V. Deterministic Hard Blocks, Probabilistic Advice

Hard blocks (PROTECTED_VIOLATION) MUST be computed deterministically from path rules and
platform-verified identity — never from an LLM verdict. The LLM classifier decides only the
semantic question (ADDITIVE vs SCOPE_CHANGE), and its verdicts MUST always carry a confidence,
a one-line summary, and a human-readable explanation. Below the configured confidence
threshold, the system warns instead of blocking. Identity MUST be the server-side platform
account (GitHub/GitLab login), never locally-asserted git author data.

### VI. No Dashboard, No New UI

SpecGuard MUST NOT ship a web dashboard, separate website, or separate login. The host
platform's PR interface is the approval surface; the terminal is the configuration surface.
Approval paths are: native PR review, PR comment command, and CLI — all recorded identically.

*Rationale: developers do not leave their tools; every winning tool in this category
(pre-commit, Prettier, Dependabot) is CLI/git-native.*

## Additional Constraints & Scope Boundaries

- Language: Python ≥ 3.12. License: MIT. Classifier: independent Claude API call — never the
  same agent session being governed.
- The classifier prompt sends goal + scope lists in full; file content is diff-focused and
  truncatable, scope lists are not.
- Explicitly out of scope for the product (decided, not deferred): web dashboard; own spec
  format or proposal workflow; forking/embedding Spec Kit or OpenSpec code; code-vs-spec
  drift detection; SaaS subscription as the primary business model.
- `.specguard/**` configuration is itself protected by the role rules it defines
  (self-protecting lock).

## Development Workflow & Quality Gates

- CI tests MUST run without a live Claude API key (mocked client); classifier behavior is
  validated separately by a real-API eval harness run manually.
- Release gate: zero false BLOCKs on the ADDITIVE golden corpus at default thresholds. A
  prompt or threshold change MUST re-run the eval harness before merge.
- SpecGuard MUST dogfood itself: this repository's own spec files are guarded by the
  published action from the first working build onward.
- Configuration errors (malformed roles.yml/config.yml/lock.json) MUST fail loudly; vendor
  outages (Claude API unavailable) default to fail-open with a visible warning, configurable
  to fail-closed per repo.

## Governance

This constitution supersedes all other development practices in this repository. Amendments
are made by pull request that (a) updates this file, (b) bumps the version per semantic
versioning (MAJOR: principle removal/redefinition; MINOR: new principle or materially
expanded guidance; PATCH: clarification/wording), and (c) records the change in the Sync
Impact Report comment. All PRs and reviews MUST verify compliance with Principles I–VI;
deviations require explicit justification in the plan's Complexity Tracking section.

**Version**: 1.0.0 | **Ratified**: 2026-06-10 | **Last Amended**: 2026-06-10
