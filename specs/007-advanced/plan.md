# Implementation Plan: Advanced Governance (Section Locking, Monorepo, Audit Export)

**Branch**: `007-advanced` | **Date**: 2026-06-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-advanced/spec.md`

## Summary

Three additive capabilities over the unchanged validator core: (US1) **section-level
locking** — an optional `.specguard/regions.yml` restricts governance on a file to named
heading regions, leaving the rest of the file ungoverned; (US2) **monorepo multi-scope** —
changed files are grouped by the nearest-ancestor directory declaring an explicit
`.specguard/lock.json`, each scope loading its own lock/config/roles/regions independently,
falling back to the existing repo-root resolution when no subdirectory scope applies; (US3)
**audit export** — an opt-in JSON dump of verdicts + approvals, timestamped by the PR's head
commit, with no new datastore. All three are optional-by-absence: a repo with no
`regions.yml` and a single `.specguard/` behaves byte-identical to today.

## Technical Context

**Language/Version**: Python ≥ 3.10 (unchanged).

**Primary Dependencies**: none added — pure extensions of the existing stdlib/pydantic/httpx
stack (regions parsing reuses the same hand-rolled heading scan pattern as
`governance.py`; audit export is `json` from the stdlib).

**Testing**: pytest; the new logic is deterministic plumbing (which diff reaches the
classifier, which lock governs a path) rather than classifier behavior, so it is covered by
focused unit tests, not new golden-corpus cases — the existing 27-case corpus and
calibration are unaffected because `classify()` itself never changes.

**Target Platform**: unchanged (Actions gate + GitHub App, both already built).

**Project Type**: extensions to the existing single package — two new modules
(`regions.py`, `scopes.py`) plus one new module (`audit.py`); small, additive changes to
`models.py`, `engine.py`, `report.py`, `ci.py`, `app/events.py`.

**Performance Goals / Constraints**: zero behavior change for repos without `regions.yml`
or subdirectory `.specguard/` dirs (FR-007, SC-005); a malformed region anchor or scope lock
fails the whole check loudly (exit 2 / `ConfigError` family), never silently un-governs.

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — all pass.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time is the security layer | ✅ | No new enforcement surface; scopes/regions still resolve at the trusted base ref. |
| II. Governance overlay | ✅ | `regions.yml` is one more optional file in the existing `.specguard/` convention; multi-scope reuses the existing lock/config/roles file *names*, just at more locations. |
| III. One shared validator core | ✅ | `evaluate_pr` is the only place a `Classification` is turned into a `Verdict`; regions/scopes only change which `ChangedFile`s and which `ScopeLock`/`Config`/`RolesConfig` are handed to it. Both ci.py and app/events.py call the same new `resolve_scopes` helper. |
| IV. Zero friction for additive | ✅ | Content outside a locked region is never classified at all (deterministic PASS, no API call) — strictly less friction than today, never more. |
| V. Deterministic blocks, probabilistic advice | ✅ | The protected-path edit-rule check stays first and unconditional, per scope; an unresolvable region anchor is a deterministic `ConfigError`-family failure, never an LLM verdict. |
| VI. No dashboard | ✅ | Audit export is a file or check-run text field; no UI, no login. |

## Project Structure

```text
specs/007-advanced/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/{regions,scopes,audit}.md
└── tasks.md

src/specguard/
├── regions.py    # NEW: heading-anchor location, ChangedFile region splitting, RegionAnchorError
├── scopes.py     # NEW: nearest-ancestor scope grouping, per-scope lock/config/roles/regions loading
├── audit.py      # NEW: AuditEntry, build_audit_entries, export_audit_json
├── models.py     # + RegionsConfig; + Verdict.scope; + "region_ungoverned" VerdictReason
├── engine.py     # evaluate_pr gains optional regions_config + scope params; per-file
│                 #   evaluation now returns a list[Verdict] (0..N) instead of exactly one
├── report.py     # emit_annotations/write_summary gain optional scope_roles param
├── ci.py         # _run groups changed files via resolve_scopes, evaluates per scope,
│                 #   optional SPECGUARD_AUDIT_PATH export
└── app/events.py # same per-scope refactor as ci.py (audit export deferred — see research.md)

tests/
├── test_regions.py · test_scopes.py · test_audit.py   (new)
└── test_engine.py, test_ci.py, test_app_events.py     (extended, existing cases untouched)
```

**Structure Decision**: three small, independent modules rather than growing `governance.py`
or `engine.py` into a monolith — `regions.py` and `scopes.py` only ever IMPORT from
`config.py`/`gitdiff.py`/`governance.py`/`models.py`, never from `engine.py`, so there is no
import cycle and each is unit-testable in isolation.

## Core Design Decisions

### D1. Region locking only applies to *modified* files

A newly **added** watched file has no prior heading to defend, so region rules are skipped
for it (governed as a whole file, today's behavior, unchanged). This sidesteps a large
amount of edge-case complexity (what does "the anchor doesn't exist yet" mean for a brand
new file?) for a case the user stories don't actually require.

### D2. Anchor resolution must succeed on BOTH sides of a modification

Each declared anchor heading must be locatable in **both** the old and new content of a
modified file. If it is missing from either side, `RegionAnchorError` (a `ConfigError`
subclass) is raised — it propagates through the *exact same* exit-2 path every other
malformed-config error already takes in `ci.py`'s `main()`, with zero new exception
handling needed there (FR-002, SC-003).

### D3. Content outside every declared region is deterministically ungoverned

After extracting each anchor's span from old/new content, the remainder (content with all
declared spans removed) is diffed too: if it changed, one quiet `PASS` verdict
(`reason="region_ungoverned"`) is emitted — no classifier call. This is *stricter* friction
reduction than today, never weaker (constitution IV).

### D4. Multi-scope recognizes only explicit locks, not derived ones

A subdirectory is a "scope" only if `{dir}/.specguard/lock.json` exists explicitly. Spec
Kit/OpenSpec derivation (`governance.resolve_lock`) remains repo-root-only — avoiding the
combinatorial complexity of multi-framework derivation per subdirectory in one feature. The
repo-root scope still gets full precedence (explicit > Spec Kit > OpenSpec > plain),
preserving 100% backward compatibility for every existing single-scope repo (FR-003,
acceptance scenario 3).

### D5. Per-scope files use scope-relative paths

A scope's own `roles.yml`/`config.yml` write glob patterns as if their `.specguard/` were
at the repo root (e.g. `README.md`, not `packages/api/README.md`) — `scopes.py` strips the
scope-dir prefix from each `ChangedFile.path` before calling `evaluate_pr`, and the engine
re-adds it when building `Verdict.file`. This makes a scope's `.specguard/` directory
self-contained and copyable between packages (FR-005).

### D6. Audit timestamp = the PR's head commit time, not a per-approval stamp

Rather than extend the `Approval` model with a new timestamp field (which would require
updating several existing exact-equality test assertions for no real audit-fidelity gain),
each audit batch is timestamped once via the already-existing `fetch_commit_time` — "this is
the state of governance as of commit X, observed at time Y." Approver identity and state are
still fully captured per entry (FR-006).

### D7. Audit export ships for the CI gate only this phase

`SPECGUARD_AUDIT_PATH` (ci.py) writes a JSON file an Actions workflow can upload as an
artifact. Embedding the same data into the App's check-run output is the natural next step
(no new datastore needed there either — the check run *is* GitHub's own record) but is
deferred to keep this feature's surface area reviewable, the same way GitLab parity was
deferred out of 006.

## Complexity Tracking

> No constitution violations — table intentionally empty.
