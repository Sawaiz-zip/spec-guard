# Feature Specification: Advanced Governance (Section Locking, Monorepo, Audit Export)

**Feature Branch**: `007-advanced`

**Created**: 2026-06-13

**Status**: Draft

**Input**: Phase 3 from the roadmap — finer-grained and larger-scale governance:
section-level locking within a file, monorepo multi-scope (per-directory `.specguard/`), and
audit export. Per the product spec, Phase 3 is pursued only once Phases 0–2 show traction;
this spec scopes it so the work is ready when that bar is met.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Lock a section, let the rest of the file float (Priority: P1)

A maintainer wants the **goal paragraph** and the **out-of-scope list** of a large spec file
locked tightly, while the FAQ and examples below them can change freely. Today the whole
watched file is governed as one unit, so a trivial FAQ edit gets classified against the same
bar as a goal rewrite. Section-level locking lets a region of a file be governed
independently of the rest.

**Why this priority**: It is the most-requested refinement and the one with real product
risk — the spec itself flags "no prior art; prototype in Phase 3." Getting the region model
right unblocks the rest of the phase.

**Independent Test**: Mark a heading region as locked; edit text *inside* it with an
out-of-scope addition → SCOPE_CHANGE; edit text *outside* any locked region → passes as
ungoverned/additive.

**Acceptance Scenarios**:

1. **Given** a file with a locked region defined, **When** a change falls entirely outside
   that region, **Then** it is not classified as a scope change (the rest of the file floats).
2. **Given** a change inside a locked region adds an out-of-scope topic, **When** the gate
   runs, **Then** it is blocked exactly as a whole-file lock would block today.
3. **Given** a change that straddles the region boundary, **When** the gate runs, **Then**
   the governed portion is evaluated and the verdict explains which region triggered it.
4. **Given** the region anchor can no longer be located (heading renamed/removed), **When**
   the gate runs, **Then** it fails loudly (config-error style) rather than silently
   un-governing the section.

---

### User Story 2 - Govern a monorepo with per-area scopes (Priority: P2)

A monorepo has several packages, each with its own goal and scope. A maintainer places a
`.specguard/` in each package directory; a change under `packages/api/` is judged against
`packages/api/.specguard/lock.json`, while a change under `packages/web/` is judged against
its own — independently, in one PR.

**Why this priority**: Monorepos are common and currently unsupported (single repo-root
scope). It is additive over the existing resolution and lower-risk than section locking.

**Independent Test**: In a repo with two package-level `.specguard/` dirs, open a PR touching
watched files in both; confirm each file is judged against its nearest-ancestor lock, with
independent verdicts in the same run.

**Acceptance Scenarios**:

1. **Given** per-directory `.specguard/` configs, **When** a watched file changes, **Then**
   it is governed by its nearest-ancestor `.specguard/` (most-specific wins).
2. **Given** a PR touching files under two different scopes, **When** the gate runs, **Then**
   each file gets its own scope's verdict and the report attributes each to its scope.
3. **Given** a file under no package scope, **When** it changes, **Then** the repo-root
   scope governs it (or plain mode if none), unchanged from today.

---

### User Story 3 - Export an audit trail of governance decisions (Priority: P3)

A compliance owner needs a record of what SpecGuard decided over time — which scope changes
were flagged, who approved them, and when. They export a machine-readable audit log of
verdicts and approvals without standing up any new system.

**Why this priority**: Required for regulated/enterprise adoption but depends on nothing
above it; it reads from data the gate already produces.

**Independent Test**: After a series of PRs, export the audit record and confirm each
blocked/approved scope change appears with file, classification, approver identity, and
timestamp.

**Acceptance Scenarios**:

1. **Given** a history of governed PRs, **When** the audit export runs, **Then** it emits a
   machine-readable record of verdicts and qualifying approvals with identities and times.
2. **Given** the export, **When** inspected, **Then** it contains no secrets or raw API
   keys and is derivable from platform-recorded data (no new datastore required).

---

### Edge Cases

- Overlapping or nested locked regions in one file — define precedence (most-specific
  region wins; document the rule).
- A monorepo PR that edits a package's *own* `.specguard/` — the protected-path rule applies
  per-scope (a scope's lock is protected by that scope's roles).
- Region anchors that drift (content edited around the heading) vs. disappear (heading
  deleted) — the former re-locates, the latter fails loudly (US1 scenario 4).
- Audit export volume on a long-lived repo — must paginate/stream, not assume bounded size.
- Section locking + governance overlay (derived locks): regions are only meaningful with an
  explicit lock; derived-lock repos get whole-file behavior with a documented notice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A lock MUST be able to scope governance to a region of a file (e.g. a heading
  region), so changes outside any locked region in that file are not classified as scope
  changes.
- **FR-002**: Region anchoring MUST tolerate surrounding edits but MUST fail loudly when an
  anchor can no longer be resolved — never silently leave a declared region ungoverned
  (constitution: config errors fail loudly).
- **FR-003**: Governance MUST support multiple scopes in one repository via per-directory
  `.specguard/`, with each changed file judged against its nearest-ancestor scope
  (most-specific wins); repo-root scope is the fallback.
- **FR-004**: A single PR spanning multiple scopes MUST produce independent per-file verdicts
  attributed to their respective scopes, through the one shared validator core
  (constitution III) with verdict semantics unchanged.
- **FR-005**: Each scope's `.specguard/` MUST be self-protected by that scope's role rules
  (the self-protecting-lock property, applied per scope).
- **FR-006**: SpecGuard MUST be able to export a machine-readable audit trail of verdicts and
  qualifying approvals (file, classification, confidence, approver identity, timestamp),
  derived from platform-recorded data with no new datastore and no secrets in the output.
- **FR-007**: All Phase 3 capabilities MUST preserve the existing guarantees — zero friction
  for additive changes, deterministic hard blocks, merge-time as the only security boundary,
  no new UI/login.

### Key Entities

- **Locked Region**: a named, anchored region within a watched file that is governed
  independently of the rest of the file.
- **Scope**: a `.specguard/` configuration governing a directory subtree; a repo may have
  many, resolved most-specific-first.
- **Audit Record**: a verdict + approval event in exportable form (no secrets), keyed by
  repo, PR, file, and time.

## Success Criteria *(mandatory)*

- **SC-001**: For a file with a locked region, changes outside the region never produce a
  scope-change verdict, and changes inside it match whole-file behavior (verified on a
  region-aware extension of the golden corpus).
- **SC-002**: In a monorepo with N package scopes, a PR touching M of them yields M
  independent verdicts each attributed to the correct scope.
- **SC-003**: A region whose anchor cannot be resolved fails the check loudly (config-error
  exit), never silently un-governs.
- **SC-004**: The audit export reproduces every blocked/approved scope change over a test
  history with correct identities and timestamps, and contains no secrets.
- **SC-005**: All existing Phase 0–2 success criteria still pass unchanged (no regression in
  the whole-file / single-scope / additive paths).
- **SC-006**: Section locking (SC-001) and monorepo multi-scope (SC-002) behave identically
  on every surface that runs the shared validator core — the CI merge gate, the local
  `specguard check`, and the MCP write-time tools — never CI-only (constitution III).
  *(Recorded post-implementation: both features were initially wired into the CI gate only;
  parity on the local-check and MCP surfaces was restored in 0.4.2–0.4.4. When adding a new
  governance behavior, verify it reaches all three surfaces, not just `ci.py`.)*

## Assumptions

- Region anchoring uses the spec files' existing structure (markdown headings) rather than a
  new annotation syntax where possible — exact mechanism (heading regions vs. anchor
  comments) is a planning-time decision the product spec flags as needing a prototype.
- Section locking is meaningful only with an explicit lock; framework-derived locks
  (Spec Kit/OpenSpec) keep whole-file behavior with a documented notice.
- Monorepo resolution extends the existing config/governance loading (nearest-ancestor),
  reusing the same parse/validate path; no change to the lock/roles/config formats beyond
  the optional region field.
- Audit export reads from platform-recorded verdict/approval data (e.g. check runs, reviews,
  comments) — it introduces no SpecGuard-side datastore, honoring the no-SaaS / no-new-UI
  posture.
- **Enterprise self-host** from the roadmap is treated as a deployment concern of the
  GitHub App (006) plus this audit export, not a separate product surface in this spec.
- Phase 3 is gated on Phase 0–2 traction (product spec §11); this spec exists so the work is
  ready, not as a commitment to build immediately.
