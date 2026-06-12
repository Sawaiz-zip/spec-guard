# Tasks: PR Spec-File Governance Gate (Phase 0 MVP)

**Input**: Design documents from `/specs/001-pr-spec-gate/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

**Organization**: Tasks grouped by user story — each story is an independently testable
increment. No tests column (not requested in spec); each phase has an Independent Test
criteria instead.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4 from spec.md)
- Every task includes an exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization — must complete before any other phase.

- [X] T001 Create project structure: `pyproject.toml`, `src/specguard/__init__.py`, `tests/conftest.py` skeleton, empty fixture dirs `tests/fixtures/corpus/` and `tests/fixtures/events/`
- [X] T002 [P] Scaffold GitHub Actions workflows: `.github/workflows/tests.yml` (pytest on push/PR) and `.github/workflows/specguard.yml` (dogfood — placeholder, wired up in T035)
- [X] T003 [P] Add `ruff` + `mypy` config to `pyproject.toml`; confirm `pytest` discovers `tests/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core shared modules that ALL user stories depend on. Nothing in Phase 3+ can
start until this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until T004–T007 are done.

- [X] T004 Implement all Pydantic models in `src/specguard/models.py`: `ScopeLock`, `Config`, `RolesConfig`, `Classification`, `Verdict`, `PRContext`, `Approval` — exact field shapes from `data-model.md`
- [X] T005 [P] Implement `src/specguard/config.py`: load and validate `.specguard/config.yml` (with all defaults from `data-model.md`) and `.specguard/lock.json`; raise `ConfigError` on parse failures; implement `detect_framework()` (checks for `.specify/`, `openspec/`, logs only)
- [X] T006 [P] Implement `src/specguard/gitdiff.py`: run `git diff --name-only {base}...{head}`, filter by watch-list globs, then `git show` per file for old/new content and unified diff; handle added/deleted/renamed cases
- [X] T007 Populate `tests/conftest.py`: `FakeAnthropicClient` that returns canned `Classification` objects keyed by file path and raises configurable errors; sample `ScopeLock`, `Config`, `RolesConfig` fixtures; `pr_event` and `pr_review_event` payload fixtures pointing at `tests/fixtures/events/`

**Checkpoint**: Foundation ready — all four modules importable, fixtures usable. User story implementation can begin.

---

## Phase 3: User Story 1 — Scope Change Blocked Until Authorized Approval (Priority: P1) 🎯 MVP

**Goal**: A PR adding an out-of-scope topic to a watched file is blocked with a full explanation;
an authorized review flips the check green without any new commits.

**Independent Test**: In a repo with scope lock + roles configured, open a PR adding an
out-of-scope topic → check exit code 1, `::error` annotation shows classification +
confidence + matched topics + required role; submit approving review from authorized account
→ re-run → exit code 0.

### Implementation for User Story 1

- [X] T008 [US1] Implement `src/specguard/classifier.py`: build byte-stable system prompt per `contracts/classifier.md` with `cache_control: {"type": "ephemeral"}`; call `client.messages.parse(output_format=Classification, thinking={"type":"adaptive"}, max_tokens=4000)`; truncate diff context to ≤2000 chars/hunk but never truncate scope lists; one re-ask on schema validation failure; raise `ClassifierError` on exhaustion
- [X] T009 [US1] Build additive golden corpus: create ≥15 cases under `tests/fixtures/corpus/NN_name/{old.md,new.md,scope.json,expected.json}` — typo fix, wording clarification, in-scope detail expansion, adversarial (out-of-scope topic mentioned only to exclude it), non-watched file only
- [X] T010 [US1] Build scope-change golden corpus: create ≥12 cases under `tests/fixtures/corpus/` — verbatim scope_out topic added, semantically out-of-scope novel topic, goal sentence rewritten, domain shift, mixed diff (typo + scope add in one file)
- [X] T011 [P] [US1] Implement `tests/eval/run_eval.py`: load all corpus cases, call real `classifier.py` (requires `ANTHROPIC_API_KEY`), print confusion matrix, per-case confidence, false-positive rate, total cost — exit non-zero if any additive case produces BLOCK at default threshold
- [X] T012 [US1] Implement `src/specguard/roles.py`: parse `roles.yml`; `fnmatch`-style glob matching, most-specific rule wins; resolve PR-author login → role membership; expose `is_edit_authorized(login, path)` and `required_approver_roles(path)` → raise `ConfigError` on unknown role reference
- [X] T013 [US1] Implement `src/specguard/approvals.py`: `GET /repos/{owner}/{repo}/pulls/{n}/reviews` with `httpx`; deduplicate to latest review per reviewer; expose `has_qualified_approval(required_roles, roles_config)` → `True` iff an APPROVED reviewer is in an authorizing role
- [X] T014 [US1] Implement `src/specguard/engine.py`: per-file pipeline per `plan.md D2` — edit-rule check (deterministic, no API) → `classifier.py` → threshold table from `research.md R3` → `approvals.py` → produce `Verdict`; apply `on_error` policy on `ClassifierError`; return list of `Verdict` objects
- [X] T015 [US1] Implement `src/specguard/report.py`: emit `::error file={path}::` per BLOCK, `::warning file={path}::` per WARN, `::notice::` for setup hints; write verdict table to `$GITHUB_STEP_SUMMARY` in the §F4 format from `contracts/action-interface.md`; additive files get one quiet summary line only
- [X] T016 [US1] Implement `src/specguard/ci.py` as `__main__`: parse `GITHUB_EVENT_PATH` → `PRContext`; detect fork (`is_fork=True`) → emit notice + exit 0; call `gitdiff.py`, `config.py`, `engine.py` per file; call `report.py`; exit 1 iff any BLOCK, exit 2 on `ConfigError`, exit 0 otherwise
- [X] T017 [US1] Write `action.yml`: composite action — `actions/setup-python@v5` (python 3.12) → `pip install specguard==${VERSION}` → `python -m specguard.ci`; inputs `anthropic-api-key` (required) and `github-token` (default `${{ github.token }}`); export both as env vars

**Checkpoint**: US1 fully functional — blocked PR + authorized approval → green is the demo and the thesis test.

---

## Phase 4: User Story 2 — Additive Changes Pass Silently (Priority: P2)

**Goal**: Typo fixes and in-scope elaborations produce exit 0 with no annotations and one
quiet log line per file.

**Independent Test**: Open a PR that only fixes a typo in a watched file → `exit 0`, PR shows
zero warning/error annotations, step summary contains exactly one line per watched-changed
file with "ADDITIVE" and no block/warn icons.

### Implementation for User Story 2

- [X] T018 [US2] Add `tests/fixtures/events/pr_typo_fix.json` and `pr_scope_change.json` event payloads (pull_request and pull_request_review variants for each)
- [X] T019 [P] [US2] Write `tests/test_engine.py` ADDITIVE scenarios: FakeAnthropicClient returns ADDITIVE/0.95 → Verdict outcome=PASS reason=additive; non-watched changed files → skipped; ADDITIVE with confidence < 0.60 → PASS with notice
- [X] T020 [P] [US2] Write `tests/test_classifier.py`: prompt assembly covers scope_lock never truncated; diff hunk context capped; test FakeAnthropicClient returns schema-valid Classification; test re-ask on schema failure; test ClassifierError on exhaustion
- [X] T021 [US2] Write `tests/test_ci.py`: point `GITHUB_EVENT_PATH` at `pr_typo_fix.json` fixture → exit 0 and empty annotation list; point at fork-event fixture → exit 0 + skip notice

**Checkpoint**: US1 and US2 both pass. Additive path confirmed friction-free.

---

## Phase 5: User Story 3 — Protected File Edited by Unauthorized Identity (Priority: P3)

**Goal**: PRs touching protected paths (e.g., `.specguard/**`) from non-authorized authors are
hard-blocked deterministically — no classifier call made.

**Independent Test**: Rule `".specguard/**": edit: architect`; non-architect PR modifies
`roles.yml` → exit 1, `::error` with protected-violation reason, no Classification in Verdict;
architect PR → edit-rule passes, proceeds to classify normally.

### Implementation for User Story 3

- [X] T022 [US3] Extend `src/specguard/engine.py` protected-violation branch: before any API call, if `is_edit_authorized(author_login, path)` is False → produce `Verdict(outcome=BLOCK, reason=protected_violation, classification=None)`; confirm no `classifier.py` call occurs in this path (verifiable via FakeAnthropicClient call counter)
- [X] T023 [P] [US3] Write `tests/test_engine.py` protected-violation scenarios: unauthorized author + protected path → BLOCK/protected_violation, FakeAnthropicClient called 0 times; authorized author + protected path → proceeds to classification
- [X] T024 [P] [US3] Write `tests/test_roles.py`: glob matching (exact, wildcard, most-specific); `"*"` wildcard membership; unknown role reference → ConfigError; missing roles.yml → solo mode flag

**Checkpoint**: US1 + US2 + US3 all pass. Self-protecting governance config working.

---

## Phase 6: User Story 4 — Solo Developer Warn Mode (Priority: P4)

**Goal**: No roles.yml → SCOPE_CHANGE becomes a warning, never a block. No `.specguard/` at
all → single setup notice, check passes.

**Independent Test**: Repo with lock.json, no roles.yml; PR adds out-of-scope topic → exit 0,
one `::warning` annotation with full classification; repo with no `.specguard/` → exit 0,
one `::notice` with setup instructions.

### Implementation for User Story 4

- [X] T025 [US4] Extend `src/specguard/engine.py` solo-mode path: when `roles_config` is None (no roles.yml), any SCOPE_CHANGE verdict ≥ block_threshold → `Verdict(outcome=WARN, reason=scope_change_low_confidence)` instead of BLOCK; SCOPE_CHANGE < threshold stays WARN unchanged
- [X] T026 [US4] Extend `src/specguard/ci.py` no-config path: if `.specguard/` absent or `lock.json` missing → single `::notice::` with setup URL, exit 0, no file evaluation
- [X] T027 [US4] Write `tests/test_engine.py` solo-mode + no-config scenarios: no roles.yml + SCOPE_CHANGE/0.90 → WARN not BLOCK; no lock.json → not_configured verdict

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, edge cases, documentation, evaluation, and release. Spans all stories.

- [ ] T028 [P] Error handling in `src/specguard/engine.py` + `src/specguard/ci.py`: `ClassifierError` → `on_error: warn` → PASS + `::warning::` "could not classify"; `on_error: fail` → BLOCK; `ConfigError` anywhere → exit 2 + `::error::` naming file and parse problem
- [ ] T029 [P] Fork PR detection in `src/specguard/ci.py`: `pull_request.head.repo.fork != base repo` → emit `::warning::` "SpecGuard skipped: secrets unavailable on fork PRs" → exit 0; write `tests/fixtures/events/pr_fork.json`
- [ ] T030 [P] Large-diff handling in `src/specguard/classifier.py`: diffs > `max_diff_chars` (default 30K) truncated with a `[TRUNCATED]` marker; scope lists never touched; truncation noted in Verdict explanation
- [ ] T031 [P] Write `tests/test_config.py`: valid config.yml with all defaults; missing keys → defaults applied; malformed YAML → ConfigError; missing lock.json → ConfigError; missing config.yml → defaults only
- [ ] T032 [P] Write `tests/test_approvals.py`: Reviews API mocked with `httpx`; multiple reviews from same reviewer → latest wins; APPROVED from role member → qualified; APPROVED from non-member → not qualified; CHANGES_REQUESTED → not qualified
- [ ] T033 Write `README.md`: one-liner positioning, 5-minute install quickstart (config templates + workflow YAML + branch-protection steps), blocked-PR screenshot placeholder, cost disclosure (~$0.03–0.05/file/push), MIT badge
- [ ] T034 [P] Write `docs/quickstart.md`: mirror of `specs/001-pr-spec-gate/quickstart.md` but user-facing; links to README config templates; covers V1–V5 scenarios from the spec quickstart
- [ ] T035 Complete `.github/workflows/specguard.yml`: dogfood — watch `SPECGUARD_PRODUCT_SPEC.md`, `README.md`, and `specs/**/*.md`; reference the published action once T017 + T038 are done
- [ ] T036 Run `tests/eval/run_eval.py` against real API; tune system prompt and/or `block_threshold` until SC-001 (0 false BLOCKs on additive corpus) and SC-002 (≥90% recall on scope-change corpus) both pass; document final threshold in `research.md`
- [ ] T037 Sandbox E2E: create throwaway GitHub repo with config from README templates; execute all 6 scenarios from `quickstart.md V4`; confirm blocked-then-approved-then-green flow works; save blocked-PR screenshot for README
- [ ] T038 [P] PyPI publish: bump version in `pyproject.toml`; `python -m build && twine upload dist/*`; tag action repo `v0`; pin version in `action.yml`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user stories**
- **Phase 3 (US1)**: Depends on Phase 2 — the bulk of the work; delivers the full thesis test
- **Phase 4 (US2)**: Depends on Phase 3 — additive path fixtures + integration tests
- **Phase 5 (US3)**: Depends on Phase 3 (`engine.py` and `roles.py` exist) — deterministic extension
- **Phase 6 (US4)**: Depends on Phase 3 (`engine.py` exists) — solo-mode branch
- **Phase 7 (Polish)**: Depends on Phases 3–6 being code-complete

### User Story Dependencies

| Story | Depends on | Can run in parallel with |
|---|---|---|
| US1 (P1) | Phase 2 complete | — |
| US2 (P2) | Phase 3 complete (needs engine + ci) | US3, US4 |
| US3 (P3) | T012 + T014 (roles.py + engine.py) | US2, US4 |
| US4 (P4) | T014 (engine.py) | US2, US3 |

### Within Each User Story

- Corpus (T009/T010) can be built in parallel with classifier code (T008) — different files
- T011 (eval harness) depends on T008 (classifier) but not on T009/T010 existing yet
- T014 (engine) depends on T008 (classifier), T012 (roles), T013 (approvals)
- T015 (report) and T016 (ci) can be written in parallel once T014 exists
- T017 (action.yml) can be written any time after T001

---

## Parallel Opportunities

### Phase 2 (run all together after T001)

```
T004 models.py
T005 config.py     ← parallel with T004 once models.py has stubs
T006 gitdiff.py    ← parallel with T004/T005
T007 conftest.py   ← parallel once T004 complete (needs models)
```

### Phase 3 US1 (run after T007)

```
T008 classifier.py ─┐
T009 additive corpus ─┤ all parallel
T010 scope corpus   ─┤
T011 eval harness  ─┘ (needs T008)

T012 roles.py      ─┐
T013 approvals.py  ─┘ parallel (different files)

T014 engine.py     (needs T008 + T012 + T013)
T015 report.py     ─┐ parallel once T014 done
T016 ci.py         ─┘
T017 action.yml    ← can be written any time
```

---

## Implementation Strategy

### MVP First (US1 only — the thesis test) — ~8 tasks to first blocked PR

1. Complete Phase 1 (T001–T003)
2. Complete Phase 2 (T004–T007)
3. Implement classifier + corpus (T008–T010)
4. Implement engine + roles + approvals (T012–T014)
5. Implement ci + report + action (T015–T017)
6. **STOP and VALIDATE**: sandbox E2E — blocked PR + authorized approval → green
7. This is the demo; this is the launch artifact

### Incremental Delivery

| After completing | Deliverable |
|---|---|
| Phase 1 + 2 | Project builds, models importable, test rig works |
| Phase 3 (US1) | MVP: scope-change governance, end-to-end, ready to launch |
| Phase 4 (US2) | Additive path fully tested, adoption safe |
| Phase 5 (US3) | Self-protecting config (governance config can't be edited by non-architects) |
| Phase 6 (US4) | Solo-dev persona covered — no deadlock on teams of one |
| Phase 7 (Polish) | Eval gate passed, README live, PyPI published, `v0` tagged |

---

## Notes

- **38 tasks total**: 3 setup + 4 foundational + 10 US1 + 4 US2 + 3 US3 + 3 US4 + 11 polish
- **MVP = Phases 1–3 (17 tasks)** — delivers the full thesis test
- `[P]` tasks have different files and no incomplete-task dependencies; safe to parallelize
- `tests/eval/run_eval.py` (T036) requires `ANTHROPIC_API_KEY` — manual run, not CI
- Commit after each phase checkpoint; dogfood check (T035) will validate commits once wired up
- Constitution gate: any prompt change requires re-running T036 before merge
