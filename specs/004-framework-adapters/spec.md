# Feature Specification: Framework Adapters (Governance Overlay on Existing Specs)

**Feature Branch**: `004-framework-adapters`

**Created**: 2026-06-29

**Status**: Draft

**Input**: User description: "Framework adapters so SpecGuard governs the spec structure a repo already uses
instead of requiring a hand-authored `.specguard/lock.json`. A Spec Kit adapter reads
`.specify/memory/constitution.md` plus `specs/<feature>/spec.md` to derive the locked goal and in/out
scope; an OpenSpec adapter reads `openspec/specs/**` and `openspec/changes/<id>/proposal.md`
scope-in/out sections; plain mode (explicit lock.json / configured .md paths) remains the fallback and
is auto-selected when no framework is detected. Both the GitHub Action and the MCP server consume the
same derived governance through the existing engine. SpecGuard must not fork or import Spec Kit /
OpenSpec code — only parse their public file formats. A hand-authored lock.json, when present, overrides
framework derivation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Govern a Spec Kit repo without hand-authoring a lock (Priority: P1)

A team already runs Spec Kit: their project goal and scope live in `.specify/memory/constitution.md`
and in each feature's `specs/<feature>/spec.md`. Today, to use SpecGuard, they must duplicate that into
a hand-written `.specguard/lock.json` — a second source of truth that immediately drifts. They want
SpecGuard to read the Spec Kit files they already maintain and govern PR changes against them directly.

**Why this priority**: This is the product's core differentiator (governance overlay, not a new format)
and its biggest adoption-friction remover. Until this exists, SpecGuard "detects" Spec Kit and then
prints *"adapter coming; using plain mode"* — visibly unfinished in exactly the repos it targets. It is
also dogfoodable in SpecGuard's own repository on day one.

**Independent Test**: In a Spec Kit repo with no `.specguard/lock.json`, open a PR that adds an
out-of-scope topic to a watched spec file; confirm the gate derives the goal/scope from the constitution
and feature spec and classifies SCOPE_CHANGE with the same verdict shape the plain-mode lock produces.

**Acceptance Scenarios**:

1. **Given** a repo with `.specify/memory/constitution.md` and no `.specguard/lock.json`, **When** the
   gate runs, **Then** the locked goal and in/out scope are derived from the Spec Kit files and a watched
   change is classified exactly as an equivalent hand-written lock would classify it.
2. **Given** the same repo, **When** a PR introduces a topic the constitution lists as out of scope,
   **Then** the verdict is SCOPE_CHANGE with the same fields (classification, confidence, summary,
   explanation) the plain-mode path produces, and enforcement behaves identically.
3. **Given** the same repo, **When** the MCP server's write-time check runs on a proposed change,
   **Then** it consults the same derived governance and returns an advisory verdict consistent with the
   merge gate.

---

### User Story 2 - Govern an OpenSpec repo from its proposal scope sections (Priority: P2)

A team uses OpenSpec: their source-of-truth specs live in `openspec/specs/**` and changes are proposed
in `openspec/changes/<id>/proposal.md` with explicit in-scope / out-of-scope sections. They want
SpecGuard to treat those proposal scope sections as the lock source and gate edits to the specs against
them, without writing a separate lock.

**Why this priority**: OpenSpec is the second-largest SDD framework and its proposal files already encode
exactly the scope-in/out lists SpecGuard needs. Supporting it doubles the addressable framework surface,
but Spec Kit is dogfoodable here first, so this is P2.

**Independent Test**: In an OpenSpec repo with no `.specguard/lock.json`, open a PR editing a file under
`openspec/specs/**` that contradicts the active proposal's out-of-scope list; confirm SCOPE_CHANGE with
the standard verdict shape.

**Acceptance Scenarios**:

1. **Given** a repo with `openspec/` and a proposal that declares out-of-scope topics, **When** a watched
   spec file gains one of those topics, **Then** the verdict is SCOPE_CHANGE derived from the proposal's
   scope sections.
2. **Given** an OpenSpec repo with multiple change proposals, **When** governance is derived, **Then** the
   adapter resolves which scope source applies in a defined, predictable way (documented in Assumptions),
   never silently picking an arbitrary one.

---

### User Story 3 - Explicit lock and plain mode still win when chosen (Priority: P1)

A team wants to override what a framework's files say — or has no framework at all — and pin the locked
goal/scope explicitly. A hand-authored `.specguard/lock.json` must take precedence over any framework
derivation, and a repo with no recognized framework must keep working exactly as it does today.

**Why this priority**: Backward compatibility is non-negotiable — every shipped install relies on the
plain-mode lock, and an explicit lock is the documented escape hatch when a framework's files are wrong
or incomplete. Breaking it would regress all three existing features.

**Independent Test**: (a) In a Spec Kit repo, add a `.specguard/lock.json`; confirm its goal/scope are
used and the framework files are ignored. (b) In a repo with neither `.specify/` nor `openspec/`, confirm
behavior is byte-identical to today's plain mode.

**Acceptance Scenarios**:

1. **Given** both `.specguard/lock.json` and `.specify/` exist, **When** governance is resolved, **Then**
   the explicit lock is used and the framework files are not consulted for scope.
2. **Given** neither framework directory exists, **When** the gate runs, **Then** governance resolution
   and verdicts are unchanged from the current plain-mode behavior.
3. **Given** a framework is detected but its scope-bearing files are missing or unreadable, **When**
   governance is resolved, **Then** the system falls back to plain mode (or fails loudly per the
   configured policy) rather than crashing.

---

### Edge Cases

- **Framework files present but no scope is expressed** (constitution states a goal but lists no
  in/out scope; a Spec Kit feature spec has no scope section) → governance derives the goal with empty
  scope lists, matching how a plain lock with empty lists behaves; never a crash.
- **Multiple feature specs in `specs/`** → the adapter must define which feature(s) contribute to the
  derived scope and not silently average or pick one at random.
- **Both `.specify/` and `openspec/` present** → a deterministic precedence order decides which adapter
  drives derivation; the choice is logged.
- **Malformed framework files** (unparseable constitution/proposal) → a loud configuration error
  consistent with how malformed `lock.json` is handled today, never a silent pass.
- **Framework files change between base and head of a PR** → governance is derived from the PR base (as
  the existing gate already reads config/lock at base), so a PR cannot rewrite the scope it is judged by.
- **Scope lists derived from framework files must never be truncated** when sent to the classifier, same
  as the plain lock (constitution constraint).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST resolve locked governance (goal + in-scope + out-of-scope) from one of three
  sources, selected in a defined precedence order: an explicit `.specguard/lock.json`, a detected Spec Kit
  layout, or a detected OpenSpec layout; with plain mode as the fallback when none of the above yields a
  lock.
- **FR-002**: A hand-authored `.specguard/lock.json`, when present, MUST take precedence over any
  framework derivation; the framework files MUST NOT be consulted for scope in that case.
- **FR-003**: The Spec Kit adapter MUST derive the locked goal and in/out scope by parsing
  `.specify/memory/constitution.md` and the relevant `specs/<feature>/spec.md` file(s), reading only their
  public markdown structure.
- **FR-004**: The OpenSpec adapter MUST derive the locked goal and in/out scope by parsing
  `openspec/specs/**` and the scope-in/out sections of `openspec/changes/<id>/proposal.md`, reading only
  their public file formats.
- **FR-005**: Derived governance MUST flow through the existing single validator core unchanged, so that
  the GitHub Action and the MCP server produce identical verdict semantics for the same inputs regardless
  of governance source (constitution III).
- **FR-006**: The system MUST NOT fork, embed, or import Spec Kit or OpenSpec code; only their public
  file/markdown formats may be parsed (constitution II).
- **FR-007**: When a framework is detected but its scope-bearing files are missing, empty, or unreadable,
  the system MUST degrade predictably — falling back to plain mode or failing loudly per the configured
  error policy — and MUST NOT crash.
- **FR-008**: Governance MUST be derived from the PR base revision (not the PR's own checkout), preserving
  the existing guarantee that a PR cannot rewrite the rules it is judged by.
- **FR-009**: Scope lists derived from framework files MUST be sent to the classifier in full (never
  truncated), matching the existing lock behavior.
- **FR-010**: The current placeholder behavior — detecting a framework and then printing "adapter coming;
  using plain mode" while ignoring it — MUST be replaced by actual derivation; the detection result MUST
  drive governance, and the active governance source MUST be reported to the user (in the Action summary
  and the MCP/CLI output).
- **FR-011**: Existing repos that rely on a hand-authored lock or on plain mode MUST observe no change in
  verdicts or behavior (backward compatibility).

### Key Entities *(include if feature involves data)*

- **Governance Source**: where the locked goal/scope came from — explicit lock, Spec Kit, OpenSpec, or
  plain mode. Surfaced to the user so it's never ambiguous which source is in effect.
- **Derived Lock**: the goal + in-scope + out-of-scope produced by an adapter from framework files,
  semantically equivalent to a hand-authored lock and consumed identically by the engine.
- **Framework Adapter**: a reader that maps a specific framework's public files to a Derived Lock without
  importing that framework's code; one per supported framework (Spec Kit, OpenSpec), plus the plain
  fallback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Spec Kit repo with no hand-authored lock can be governed end to end (PR classified,
  scope change blocked) using only files the team already maintains — zero new scope files required.
- **SC-002**: For the same change, a verdict produced from a derived lock is identical in shape and
  semantics (classification, confidence, summary, explanation, enforcement) to the verdict produced from
  an equivalent hand-authored lock.
- **SC-003**: An explicit `.specguard/lock.json` overrides framework derivation 100% of the time when
  present, and repos with no recognized framework behave identically to today (no verdict regressions
  across the existing test corpus).
- **SC-004**: SpecGuard governs its own repository (a Spec Kit project) via the Spec Kit adapter rather
  than a hand-authored lock — dogfooding the differentiator.
- **SC-005**: Every governed run states which governance source is in effect, so a user can always tell
  whether a verdict came from an explicit lock, a framework adapter, or plain mode.

## Assumptions

- **Spec Kit scope location**: the locked goal comes from the constitution's stated purpose/scope
  boundaries, and per-feature in/out scope comes from the feature spec's scope-bearing sections; the exact
  headings to read are settled during planning by inspecting the real Spec Kit templates already in this
  repo. Where a framework file doesn't express in/out lists, the corresponding list is empty.
- **OpenSpec scope location**: the in/out scope comes from the proposal's scope sections; when multiple
  proposals exist, the active/most-recent change directory governs, with the precedence rule documented in
  the plan.
- **Multi-feature Spec Kit repos**: which `specs/<feature>/` contributes scope is resolved by a defined
  rule (e.g., the feature touched by the PR, or all watched features) decided during planning; the rule is
  deterministic and reported, never arbitrary.
- **Precedence order is fixed**: explicit lock > Spec Kit > OpenSpec > plain. This is a policy choice for
  predictability; framework auto-derivation never silently overrides an explicit lock.
- **No new config format**: framework selection is automatic from repository layout (with the explicit
  lock as override); a config key to force a specific adapter may be added later but is not required here.
- **Calibration unchanged**: the classifier prompt and the engine are untouched; because derived locks
  feed the same prompt, no eval re-run is required for the Anthropic default beyond confirming derived and
  hand-authored locks yield equivalent verdicts.
- **Reuse existing detection**: `detect_framework()` already recognizes `.specify/` and `openspec/`;
  this feature turns that recognition into derivation rather than adding new detection logic.