# Feature Specification: Local Tools (CLI, Pre-commit Hook, MCP Server)

**Feature Branch**: `002-local-tools`

**Created**: 2026-06-12

**Status**: Draft

**Input**: User description: "Phase 1 — Local Tools. Bring SpecGuard's existing merge-time verdict pipeline to the developer's machine as advisory (never security-boundary) surfaces: a CLI (`specguard init`, `specguard check`), a pre-commit hook that warns and never blocks, an MCP server that warns coding agents at write time, and a provider-adapter seam for non-Anthropic classifiers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preview verdicts locally before opening a PR (Priority: P1)

A developer (or an AI agent operating a terminal) has edited watched spec files and wants
to know what the merge gate will say *before* pushing. They run `specguard check` in the
repository and see the same per-file verdicts the CI check would produce — additive changes
listed quietly, scope changes called out with classification, confidence, matched
out-of-scope topics, and which role's approval the merge gate would require.

**Why this priority**: This is the validator-parity slice everything else builds on. It
converts the merge gate from a surprise at PR time into a feedback loop at edit time, and
the hook (P3) and MCP server (P4) are thin wrappers around it.

**Independent Test**: In a configured repository, edit a watched file to add an
out-of-scope topic, run `specguard check`, and confirm the output names the same
classification and outcome the CI gate produces for the identical diff; revert, make a typo
fix, re-run, and confirm a quiet pass.

**Acceptance Scenarios**:

1. **Given** a configured repo with an out-of-scope addition staged, **When** the developer
   runs `specguard check`, **Then** the output shows a SCOPE CHANGE verdict with
   classification, confidence, matched topics, and the approver role the merge gate would
   demand, and the command exits non-zero.
2. **Given** only a typo fix in a watched file, **When** `specguard check` runs, **Then**
   the output is one quiet additive line per file and the command exits zero.
3. **Given** the same diff and the same locked scope, **When** verdicts from `specguard
   check` and the CI gate are compared, **Then** classification and outcome are identical.
4. **Given** changes only to non-watched files, **When** `specguard check` runs, **Then**
   it reports nothing to evaluate and exits zero.
5. **Given** any local verdict output, **Then** it includes a notice that local results are
   advisory and only the merge-time check is enforcing.

---

### User Story 2 - Set up SpecGuard from nothing (Priority: P2)

A maintainer who has never used SpecGuard runs `specguard init` in their repository. They
are prompted for their project goal, in-scope topics, and out-of-scope topics; the tool
writes the scope lock and offers optional configuration and roles templates plus the CI
workflow snippet, leaving the repository ready for both local checks and the merge gate.

**Why this priority**: Onboarding friction is the adoption gate. Today users hand-author
JSON from README examples; guided scaffolding makes the five-minute-setup promise real.

**Independent Test**: In a repository with no SpecGuard configuration, run `specguard
init`, answer the prompts, and confirm the generated files validate and a subsequent
`specguard check` runs successfully.

**Acceptance Scenarios**:

1. **Given** an unconfigured repository, **When** the maintainer completes `specguard
   init` prompts, **Then** a valid scope lock exists and `specguard check` immediately
   works against it.
2. **Given** a repository that already has a scope lock, **When** `specguard init` runs,
   **Then** it refuses to overwrite the existing lock unless explicitly told to.
3. **Given** the maintainer declines optional items (roles, config, workflow snippet),
   **Then** only the scope lock is created and the tool explains what was skipped and why
   they might want each later.

---

### User Story 3 - Be warned at commit time, never blocked (Priority: P3)

A developer has the SpecGuard pre-commit hook installed (via the pre-commit framework or a
plain git hook). When they commit staged changes to watched spec files, the hook shows the
verdicts; if a scope change is detected they see the warning inline — but the commit always
completes. The enforcement story stays exclusively at merge time.

**Why this priority**: Catches drift one step earlier than the PR with zero workflow risk.
It is deliberately advisory: a local hook that blocks would violate the project's
constitution (only the merge-time check is a security boundary) and would train users to
bypass it.

**Independent Test**: Install the hook, commit an out-of-scope spec edit, and confirm the
warning appears AND the commit succeeds; commit a typo fix and confirm minimal output.

**Acceptance Scenarios**:

1. **Given** the hook is installed and a staged watched-file change is a high-confidence
   scope change, **When** the developer commits, **Then** the warning with full
   classification is printed and the commit still succeeds.
2. **Given** the classifier is unreachable (no key, no network), **When** the developer
   commits, **Then** the hook notes it could not classify and the commit succeeds without
   delay beyond a stated timeout.
3. **Given** staged changes touch no watched files, **When** the developer commits,
   **Then** the hook adds no visible output and no perceptible delay.

---

### User Story 4 - Warn coding agents at write time (Priority: P4)

An AI coding agent (e.g., Claude Code) connected to the SpecGuard MCP server is about to
write a change to a watched spec file. Through the server, the agent submits the proposed
file content (before any commit exists) and receives the verdict the merge gate would
later produce. The agent can self-correct mid-draft instead of burning a PR cycle on a
blocked check.

**Why this priority**: This is the differentiating surface for the AI-agent story — drift
prevention moves from "blocked PR" to "agent self-corrects before writing" — but it
depends on the same validator the CLI exposes, so it lands last.

**Independent Test**: Connect an MCP client to the server in a configured repository,
submit a proposed README edit containing an out-of-scope topic, and confirm the response
contains a SCOPE CHANGE verdict with explanation; submit a typo-level edit and confirm an
additive verdict.

**Acceptance Scenarios**:

1. **Given** a connected agent and a configured repository, **When** the agent submits
   proposed content for a watched file that adds an out-of-scope topic, **Then** the
   response identifies SCOPE CHANGE with confidence, topics, and explanation, and states
   the result is advisory.
2. **Given** proposed content for a non-watched file, **When** submitted, **Then** the
   response says the file is not governed and no classification is performed.
3. **Given** the repository has no SpecGuard configuration, **When** any tool is invoked,
   **Then** the response explains the repository is unconfigured and how to set it up.

---

### Edge Cases

- Running `specguard check` outside a git repository, or in a repo with no commits yet —
  clear error naming the problem, no traceback.
- No classifier API key available locally — `specguard check` fails with a clear message
  naming the variable to set; the pre-commit hook and MCP server degrade to a "could not
  classify — advisory check skipped" notice and never block or crash.
- Working tree has both staged and unstaged edits to the same watched file — the surface
  states which snapshot (staged vs. working tree) it evaluated.
- The locked scope or governance files are themselves modified locally — local surfaces
  evaluate against the committed baseline (matching the merge gate's trusted-base rule) and
  say so, so a user editing their own lock sees the verdict a PR would actually get.
- Roles are configured but no PR (and therefore no approvals) exists locally — verdicts
  that would block pending approval are shown as "would block until {role} approves" rather
  than pretending an approval state.
- Very large diffs — same truncation disclosure behavior as the merge gate.
- A blocked model (e.g., the Opus 4.8 family) configured anywhere — every local surface
  refuses identically to the merge gate; advisory mode is not a guardrail bypass.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `specguard init` MUST scaffold SpecGuard configuration interactively —
  goal, in-scope topics, out-of-scope topics — producing a valid scope lock, with optional
  generation of the settings file, roles file, and CI workflow snippet; it MUST NOT
  overwrite an existing scope lock without explicit confirmation.
- **FR-002**: `specguard check` MUST evaluate watched-file changes for a user-selected
  snapshot: staged changes (default for hook use), the working tree, or an explicit
  ref-to-ref range.
- **FR-003**: For identical inputs (diff, scope lock, settings), local verdicts MUST be
  identical in classification and outcome to the merge gate's verdicts — one shared
  validator, surfaces differ only in formatting (constitution III).
- **FR-004**: `specguard check` exit codes MUST mirror the CI gate: zero when nothing
  blocks, non-zero when at least one verdict would block, a distinct code for
  configuration errors.
- **FR-005**: Every local surface MUST disclose in its output that it is advisory and
  bypassable, and that only the merge-time check enforces (constitution I).
- **FR-006**: The pre-commit hook MUST never prevent a commit — regardless of verdicts,
  classifier failures, missing keys, or timeouts — and MUST be installable both via the
  pre-commit framework and as a plain git hook script.
- **FR-007**: The MCP server MUST let a connected agent submit proposed content for a path
  (before any commit exists) and receive the full verdict — classification, confidence,
  topics, explanation, would-be outcome — plus tools to read the locked scope and list
  watched paths, so agents can avoid drafting out-of-scope content in the first place.
- **FR-008**: Classification MUST go through a provider-adapter seam such that alternative
  providers can be added without touching the validator core; the Anthropic adapter is the
  only one shipped in this phase, and all adapters MUST honor the same output contract,
  calibration corpus, and eval gate before becoming a default.
- **FR-009**: The Opus 4.8 model guardrail MUST apply unchanged on every local surface and
  on every adapter path (research.md R2a) — advisory mode never weakens it.
- **FR-010**: Local surfaces MUST read governance configuration (lock, settings, roles)
  from the committed baseline being compared against — not the (possibly dirty) working
  tree — and disclose which baseline was used, preserving the merge gate's
  trusted-base security property in what they preview.
- **FR-011**: Verdicts that the merge gate would block pending role approval MUST be
  presented locally as blocked-pending-approval with the role named; local surfaces MUST
  NOT invent or assume approval state.
- **FR-012**: CI tests for all new surfaces MUST run without live classifier credentials
  (mocked), consistent with the existing constitution constraint.

### Key Entities

- **Check Snapshot**: what `specguard check` evaluates — staged changes, working tree, or
  an explicit ref range; carries the resolved baseline used for both diffing and
  governance config.
- **Local Verdict Report**: the per-file verdicts plus the advisory disclosure and the
  baseline used; the same underlying verdict shape the merge gate produces, rendered for
  terminal / hook / MCP consumers.
- **Init Answers**: goal, in-scope list, out-of-scope list, optional role assignments
  collected by `specguard init` before any file is written.
- **Provider Adapter**: a named classification backend honoring the existing
  classification output contract; exactly one (Anthropic) ships in this phase.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For every case in the golden corpus, the local check and the merge gate
  produce identical classification and outcome (100% parity).
- **SC-002**: A maintainer with no prior SpecGuard exposure goes from `specguard init` to
  a completed first `specguard check` in under 5 minutes.
- **SC-003**: Zero commits are ever prevented by the pre-commit hook across the entire
  test matrix, including classifier-failure and missing-key scenarios.
- **SC-004**: A connected coding agent drafting an out-of-scope spec change receives a
  scope-change warning before any commit exists, in under 30 seconds for a typical file.
- **SC-005**: `specguard check` on a repository with ≤5 changed watched files completes in
  under 60 seconds.
- **SC-006**: 100% of local-surface outputs include the advisory/bypassable disclosure
  (verified across the test matrix).

## Assumptions

- The existing Phase 0 package is the foundation; local surfaces reuse its validator,
  models, and configuration loading rather than reimplementing any verdict logic.
- Local users supply the same classifier API key via environment variable (or a standard
  local env file) — no new credential storage is introduced.
- `specguard check` requires the key to classify; the hook and MCP server degrade
  gracefully without it (warn-and-continue), because they must never block work.
- Default baseline for staged/working-tree checks is the current HEAD; ref-range checks
  name their own baseline. Governance config is read from that baseline (FR-010).
- The MCP server is local-only (stdio transport for editor/agent integration); no hosted
  service, no network listener beyond the local machine, no UI (constitution VI).
- The pre-commit hook's classifier calls respect a short timeout so commits are never
  noticeably delayed; on timeout it behaves as "could not classify".
- Multi-provider adapters beyond Anthropic, and any change of default provider, are out of
  scope for this phase (Phase 1 ships the seam, not the providers).
- Section-level locking, monorepo multi-scope, and the GitHub App remain out of scope
  (later phases).
