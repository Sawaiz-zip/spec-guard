# Research: Framework Adapters

Resolves the "NEEDS CLARIFICATION" items the spec deferred to planning: the exact files/headings each
adapter reads, the multi-feature/multi-proposal resolution rule, and the dependency choice.

## R1. No markdown library — tolerant line scanning

**Decision**: Parse framework files with stdlib line scanning, not a markdown parser.

**Rationale**: Adds zero dependencies (constitution favors a lean install; 003 kept the base install
SDK-free). The signals we need — a heading match and the bullet/line block that follows — are trivially
extracted by scanning lines for ATX headings (`#`/`##`) and list markers (`-`/`*`/`1.`). A full AST is
overkill and would make derivation harder to reason about and test deterministically.

**Alternatives considered**: `markdown-it-py` / `mistune` (AST) — rejected: new dependency, nondeterministic
across versions, no real benefit for "find a section, read its bullets."

## R2. Spec Kit derivation — what is read and how

**Files** (all read at the base ref via `show_file`):
- `.specify/memory/constitution.md` — the project-wide, stable lock source.
- `specs/<feature>/spec.md` — per-feature refinement, only for features touched by the PR diff.

**Decision — goal**: take the project identity + first principle from the constitution. Concretely: the
first `#` H1 title and the first `### ` principle heading + its opening sentence form the goal string;
if a touched feature spec has a "Feature Specification: <name>" title, that name refines the goal for
that feature's changes.

**Decision — scope_out**: scan (case-insensitive) for any line containing `out of scope` (heading OR
bullet). Collect the items that follow:
- If the marker is a heading, collect subsequent bullet lines until the next heading.
- If the marker is an inline bullet with a trailing list (this repo's constitution:
  `Explicitly out of scope … : web dashboard; own spec format; …`), split the post-colon remainder on
  `;` into items.
Union the constitution's scope_out with each touched feature spec's scope_out.

**Decision — scope_in**: scan for `in scope` / `in-scope` markers in the touched feature specs and the
constitution's "Additional Constraints & Scope Boundaries" allowed items; if none are expressed, leave
empty (an empty `scope_in` is valid and means "judge against goal + scope_out only", exactly like a plain
lock with `scope_in: []`).

**Decision — multi-feature rule**: the constitution is always included (project goal + project scope_out).
Feature specs contribute scope only for the `specs/<feature>/` directories whose files appear in the PR
diff (the `ChangedFile` paths the engine already computes). Multiple touched features → union their lists.
No touched feature dir → constitution alone. This is deterministic, order-independent, and matches intent:
you are judged against the project's locked frame plus the scope of exactly the feature you are editing.

**Validation source**: dogfooded live against *this* repository (a real Spec Kit project) — SC-004.

## R3. OpenSpec derivation — what is read and how

**Files** (base ref): `openspec/project.md` (goal), `openspec/specs/**` (source-of-truth specs),
`openspec/changes/<id>/proposal.md` (per-change scope).

**Decision — goal**: `openspec/project.md` purpose/overview section; fall back to the first spec's stated
purpose if `project.md` is absent.

**Decision — scope**: parse the proposal's scope-bearing sections. OpenSpec proposals conventionally use
`## Why` / `## What Changes`; explicit "out of scope" / "non-goals" lines are collected into `scope_out`,
and the "What Changes" items into `scope_in`. When multiple change directories exist, the ones touched by
the PR diff govern (same union rule as R2); deterministic tie-break by directory name when the diff
touches none.

**Status**: built against the **documented** OpenSpec format; not live-validated this phase (no OpenSpec
sample repo nor a live corpus at build time). This mirrors how 003 shipped the OpenAI/Gemini/OpenRouter
adapters against SDK docs without live keys. Spec Kit is the calibrated, dogfooded path; OpenSpec is
best-effort-correct with the explicit-lock override as the escape hatch (D5). Recorded honestly so it is
never presented as live-verified. Follow-up: validate against a real OpenSpec repo before documenting it
as a first-class default.

## R4. Precedence order

**Decision**: explicit `.specguard/lock.json` > Spec Kit > OpenSpec > plain (None).

**Rationale**: An explicit lock is the user's deliberate override and must always win (FR-002) — checked
first so no framework file is even read when it is present. Spec Kit before OpenSpec because it is the
dogfooded, live-validated path; the order only matters in the rare repo containing both `.specify/` and
`openspec/`, and the choice is logged so it is never silent. Plain (None) is the terminal fallback,
preserving today's behavior exactly (FR-011).

**Alternatives considered**: framework-wins-over-lock (rejected — removes the user's escape hatch and
would silently override an intentional pin); config key to force an adapter (deferred — not needed now;
auto-detection + explicit-lock override covers the cases, and a `governance_source:` config key can be
added later without breaking this design).

## R5. Where derivation hooks in (single seam)

**Decision**: introduce `governance.resolve_lock(repo_root, base_ref)` and call it from both
`load_baseline_governance` (localcheck.py — serves CLI + MCP) and `ci.py`, replacing the direct
`show_file(..., LOCK_PATH)` lock read. `config`/`roles` reads are unchanged.

**Rationale**: One dispatch point keeps the Action and local tools identical (constitution III) and means
detection/derivation are tested once. The base-ref signature makes the trusted-base rule structural, not
optional (D2).

## R6. Reporting the governance source

**Decision**: thread the `GovernanceSource` value into the existing report surfaces — the Action job
summary line and the MCP/CLI advisory payload — as a short label (`explicit-lock` | `spec-kit` |
`openspec` | `plain`). No new UI (constitution VI). Satisfies FR-010/SC-005 so users always know which
source produced a verdict.
