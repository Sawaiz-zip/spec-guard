# Tasks: Framework Adapters (Governance Overlay on Existing Specs)

**Input**: Design documents from `/specs/004-framework-adapters/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Feature**: Product-roadmap Phase 2 (Ecosystem Adapters), spec #004. Turns the log-only
`detect_framework()` seam into real governance derivation via one `resolve_lock(repo_root, base_ref)`
with fixed precedence: explicit `lock.json` > Spec Kit > OpenSpec > plain.

**Tests**: included — the contract defines a test contract and the constitution requires mocked-adapter
CI tests (no live LLM key). All test tasks use `FakeAdapter`.

**Conventions**: `[P]` = parallelizable (different files, no incomplete deps). `[US#]` = user story.

---

## Phase 1: Setup

- [X] T001 Create the new module skeleton in `src/specguard/governance.py`: `GovernanceSource` Literal
  (`"explicit-lock" | "spec-kit" | "openspec" | "plain"`), a `DerivationContext` dataclass
  (`repo_root`, `base_ref`, `changed_paths`), and a `resolve_lock(repo_root, base_ref, changed_paths)`
  stub returning `(None, "plain")` — so callers can be wired before adapters exist.
- [X] T002 [P] Add governance test fixtures under `tests/fixtures/governance/` (a sample Spec Kit
  `constitution.md` with an "Explicitly out of scope: …" line, two `specs/<feature>/spec.md` files, and
  an OpenSpec `proposal.md` with scope sections) for use by `tests/test_governance.py`.

## Phase 2: Foundational (blocking — the shared seam all stories build on)

**⚠️ Must complete before Phase 3+. Delivers the resolver + call-site wiring with explicit-lock and
plain branches working, leaving framework derivation as the per-story increments.**

- [X] T003 Add base-ref-aware detection `framework_at_ref(repo_root, base_ref)` in
  `src/specguard/config.py` (detect `.specify/` and `openspec/` via `git ls-tree`/`show` at the ref, not
  filesystem `is_dir()`); keep the existing `detect_framework()` for working-tree callers.
- [X] T004 Implement the explicit-lock and plain branches of `resolve_lock` in
  `src/specguard/governance.py`: read `LOCK_PATH` via `gitdiff.show_file(repo_root, base_ref, …)` →
  `(parsed_lock, "explicit-lock")`; else (no framework) → `(None, "plain")`. Explicit lock short-circuits
  before any framework read (FR-002).
- [X] T005 Thread the source through `src/specguard/localcheck.py`: add `source: GovernanceSource` to
  `BaselineGovernance`, and give `load_baseline_governance` a `changed_paths: list[str]` parameter that it
  forwards to `resolve_lock(repo_root, base_ref, changed_paths)`, replacing the direct `show_file(LOCK_PATH)`
  read (FR-005, FR-008).
- [X] T005a Fix CI↔local parity (analyze F1): the multi-feature Spec Kit rule keys on `changed_paths`, so
  the local surfaces MUST pass the same paths CI does, not `[]`. In `src/specguard/cli.py`, resolve the
  snapshot (compute the watched `changed_paths`) BEFORE calling `load_baseline_governance`, then pass those
  paths in; in `src/specguard/mcp_server.py`, pass the single proposed file path. Otherwise local derivation
  is constitution-only while CI is feature-aware, yielding different verdicts for the same inputs
  (violates constitution III / FR-005).
- [X] T006 Update `src/specguard/ci.py` to obtain the lock via `resolve_lock(repo_root, pr.base_sha,
  changed_paths=[c.path for c in changed])`, replacing the direct `show_file(pr.base_sha, LOCK_PATH)`
  read; keep config/roles reads unchanged.
- [X] T007 Regression checkpoint: run `pytest -q && ruff check src tests && mypy src`; confirm the
  existing 187 tests stay green with explicit-lock/plain routed through `resolve_lock` (FR-011, SC-003).

## Phase 3: User Story 1 — Govern a Spec Kit repo (Priority: P1) 🎯 MVP

**Goal**: Derive the locked goal/scope from `.specify/memory/constitution.md` + touched
`specs/<feature>/spec.md`, so a Spec Kit repo is governed with no hand-authored lock.

**Independent test**: In this repo (real Spec Kit, no `lock.json`), `specguard check --base HEAD~1`
reports `Governance source: spec-kit` and classifies a watched change. (quickstart Scenario 1)

- [X] T008 [US1] Add tolerant markdown scan helpers to `src/specguard/governance.py`: ATX heading and
  list-item extraction, and a `scope-marker` finder (case-insensitive `out of scope` / `in scope`,
  handling both heading-then-bullets and inline `… : a; b; c` forms) per research.md R2.
- [X] T009 [US1] Implement Spec Kit derivation in `src/specguard/governance.py` and wire it into the
  `resolve_lock` spec-kit branch: goal from constitution identity + first principle (refined by a touched
  feature spec title); `scope_out` = union(constitution out-of-scope, touched feature specs' out-of-scope);
  `scope_in` = union(touched feature specs' in-scope); multi-feature union keyed on `changed_paths`;
  constitution-only when no feature dir is touched (R2 multi-feature rule).
- [X] T010 [P] [US1] Tests in `tests/test_governance.py`: Spec Kit goal + `scope_out` parsing, two-feature
  scope union, and constitution-only derivation when no feature dir is touched. Include a **no-truncation**
  assertion (analyze G1): a derived `scope_out` with many/long items reaches the classifier prompt in full
  (FR-009 — scope lists are never truncatable).
- [X] T011 [P] [US1] Test in `tests/test_governance.py`: base-ref isolation — framework files altered only
  in the head commit do not change the derived lock (FR-008).
- [X] T012 [US1] Surface the governance source in the existing report surfaces: a `Governance source: …`
  line in the CI job summary (`src/specguard/report.py`), the local `check` output
  (`src/specguard/localreport.py` / `cli.py`), and a `governance_source` field in the MCP advisory payload
  (`src/specguard/mcp_server.py`) (FR-010, SC-005).
- [X] T013 [US1] Dogfood validation: run `specguard check --base HEAD~1 --head HEAD` on this repository and
  confirm `Governance source: spec-kit` with a non-empty derived goal and the constitution's out-of-scope
  items present (SC-004).

**Checkpoint**: A Spec Kit repo is fully governable with zero new scope files — the MVP is shippable.

## Phase 4: User Story 3 — Explicit lock & plain mode still win (Priority: P1)

**Goal**: Prove an explicit `lock.json` overrides framework derivation and that no-framework repos are
byte-identical to today.

**Independent test**: Adding a `lock.json` to this Spec Kit repo flips the source to `explicit-lock` and
the constitution is not consulted; a repo with neither framework behaves exactly as before.

- [X] T014 [P] [US3] Tests in `tests/test_governance.py`: explicit-lock short-circuit (use framework
  fixtures that, if read, would yield a different scope; assert the explicit lock's scope is used and
  source is `explicit-lock`); precedence explicit > spec-kit.
- [X] T015 [P] [US3] Tests in `tests/test_governance.py`: plain-mode unchanged when no framework present
  (`(None, "plain")`), and the SETUP_HINT/unconfigured path is preserved (FR-011).
- [X] T016 [US3] Parity test in `tests/test_governance.py`: a derived Spec Kit lock and an equivalent
  hand-authored `ScopeLock` produce an identical verdict through `engine.evaluate_pr` with a `FakeAdapter`
  (constitution III, SC-002). Cover **both** code paths: the CI route (`ci.py` → `resolve_lock` with the
  PR's changed paths) AND the local route (`load_baseline_governance` with the same changed paths), asserting
  they derive the same lock and emit the same verdict (analyze F1 regression guard).

**Checkpoint**: Backward compatibility and the override escape-hatch are guaranteed by tests.

## Phase 5: User Story 2 — Govern an OpenSpec repo (Priority: P2)

**Goal**: Derive goal/scope from `openspec/project.md` + touched `openspec/changes/<id>/proposal.md`
scope sections.

**Independent test**: In an OpenSpec fixture repo with no `lock.json`, a watched change contradicting a
proposal's out-of-scope list classifies SCOPE_CHANGE with source `openspec`.

- [ ] T017 [US2] Implement OpenSpec derivation in `src/specguard/governance.py` and wire it into the
  `resolve_lock` openspec branch: goal from `project.md`; `scope_in`/`scope_out` from touched proposals'
  scope sections; union across touched change dirs; deterministic tie-break by directory name (R3).
- [ ] T018 [P] [US2] Tests in `tests/test_governance.py`: OpenSpec derivation from a fixture proposal,
  multi-proposal union, and precedence Spec Kit > OpenSpec when both directories exist.
- [ ] T019 [US2] Record the honesty caveat (OpenSpec is documented-format, not live-validated this phase)
  in `specs/004-framework-adapters/quickstart.md` and the `README.md` frameworks note (R3).

**Checkpoint**: Both frameworks derive; OpenSpec flagged as best-effort pending live validation.

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T020 Degrade & error handling in `src/specguard/governance.py` + tests: detected framework with
  empty/missing scope sections ⇒ goal with empty lists (no crash); garbled required framework file ⇒
  `ConfigError` (exit 2 parity with malformed `lock.json`) (FR-007).
- [ ] T021 [P] Remove the obsolete `"adapter coming; using plain mode"` notice in `src/specguard/ci.py`
  (replaced by real source reporting from T012); confirm no surface still claims framework detection is a
  no-op (FR-010).
- [ ] T022 [P] Update `README.md` (frameworks/governance-overlay section: Spec Kit + OpenSpec auto-derive,
  explicit-lock override) and verify `CLAUDE.md` plan pointer is current.
- [ ] T023 Final gate: `pytest -q && ruff check src tests && mypy src` all green; record final test count
  and the "Spec Kit dogfooded / OpenSpec documented-only" status in this tasks file's notes.

---

## Dependencies & Execution Order

- **Setup (T001–T002)** → **Foundational (T003–T007, incl. T005a)** must finish before any user story.
  T005a (CI↔local parity) depends on T005 and must land with the local wiring, not after.
- **US1 (T008–T013)** depends only on Foundational. **This is the MVP** — ship after Phase 3.
- **US3 (T014–T016)** depends on Foundational + US1 (parity needs the Spec Kit derivation).
- **US2 (T017–T019)** depends on Foundational + the T008 markdown helpers; independent of US1's
  Spec-Kit-specific logic otherwise.
- **Polish (T020–T023)** last.

## Parallel Opportunities

- T002 ∥ T001 (different files).
- Within US1: T010 ∥ T011 (both add independent tests to `test_governance.py` — coordinate or split
  files if editing concurrently).
- US3 tests T014 ∥ T015. US2 T018 runs parallel to its own doc task T019.
- T021 ∥ T022 in Polish (different files).

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: a Spec Kit repo governed with zero hand-authored scope,
  dogfooded on this repository. Shippable on its own.
- **Increment 2 = US3**: lock in backward-compatibility + override guarantees (low risk, mostly tests).
- **Increment 3 = US2**: OpenSpec support, flagged best-effort until live-validated.
- Engine, classifier prompt, and verdict semantics remain untouched throughout (no eval re-run beyond the
  T016 parity test).

## Notes

- No new runtime dependency (research R1 — stdlib line scanning).
- Every framework read goes through `show_file(repo_root, base_ref, …)`; base-ref isolation is enforced by
  T011 (constitution I).
- Source-reporting (T012) is the visible end of the old "adapter coming" placeholder (FR-010).
