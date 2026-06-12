# Tasks: Local Tools (CLI, Pre-commit Hook, MCP Server)

**Input**: Design documents from `/specs/002-local-tools/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

**Organization**: Tasks grouped by user story — each story is an independently testable
increment. Tests are included per story (the spec's success criteria are test-shaped:
SC-001 parity, SC-003 never-blocks, SC-006 disclosure coverage).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US4 from spec.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Packaging surface for the new entry points — must complete first.

- [ ] T001 Add `[project.scripts] specguard = "specguard.cli:main"` and `[project.optional-dependencies] mcp = ["mcp>=1.0"]` to `pyproject.toml`; bump version to `0.2.0.dev0`; reinstall editable and confirm `specguard --help` resolves once T009 lands
- [ ] T002 [P] Create `.pre-commit-hooks.yaml` at repo root per `contracts/cli-interface.md` (id `specguard-check`, entry `specguard check --staged --hook`, `pass_filenames: false`, `always_run: true`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The adapter seam and snapshot plumbing every story depends on.

**⚠️ CRITICAL**: No user story work can begin until T003–T007 are done.

- [ ] T003 Add `ClassifierAdapter` protocol + `AnthropicAdapter` to `src/specguard/classifier.py` per `contracts/adapter-protocol.md`: protocol method `classify(lock, changed, config)`; AnthropicAdapter wraps the existing prompt/parse/re-ask logic byte-for-byte (no eval re-run); `assert_model_allowed` enforced at the adapter boundary
- [ ] T004 Switch `src/specguard/engine.py` `evaluate_pr` to take `adapter: ClassifierAdapter`; update `src/specguard/ci.py` to construct `AnthropicAdapter`; all existing Phase 0 tests must stay green with mechanical-only updates
- [ ] T005 Add `FakeAdapter` to `tests/conftest.py` (canned Classifications keyed by path, scriptable errors, call counter) alongside the kept `FakeAnthropicClient`
- [ ] T006 [P] Add `staged_changes()` and `worktree_changes()` to `src/specguard/gitdiff.py` (index content via `git show :path`, worktree via filesystem; reuse the watch-glob filter and ChangedFile shape)
- [ ] T007 Implement `src/specguard/localcheck.py`: `CheckSnapshot` resolution for worktree/staged/range per `data-model.md`; governance config loaded at `base_ref` via `show_file` + `parse_*` (FR-010); clear errors for non-repo / no-commits states

**Checkpoint**: adapter seam live, snapshots resolvable, fakes ready.

---

## Phase 3: User Story 1 — Preview verdicts locally (Priority: P1) 🎯 MVP

**Goal**: `specguard check` prints the merge gate's verdicts for local changes, exit
codes mirror ci.py, every output carries the advisory disclosure and baseline.

**Independent Test**: stage an out-of-scope edit → `specguard check --staged` names the
same classification/outcome CI would, exits 1; typo fix → one quiet line, exit 0.

- [ ] T008 [US1] Implement `src/specguard/localreport.py`: terminal renderer per `contracts/cli-interface.md` output spec — quiet additive lines, would-block-until-{role} rendering (FR-011), baseline line, advisory notice constant, `--json` shape
- [ ] T009 [US1] Implement `src/specguard/cli.py`: argparse entry with `check` subcommand (`--staged`, `--base/--head`, `--json`, `--hook` flag parsed but wired in T015); compose localcheck → engine(FakeAdapter-able) → localreport; exit codes 0/1/2 mirroring ci.py (FR-004); missing `ANTHROPIC_API_KEY` → exit 2 with actionable message
- [ ] T010 [P] [US1] Write `tests/test_localcheck.py`: staged vs worktree vs range resolution in tmp git repos; baseline config wins over locally-edited `.specguard/` (FR-010 regression, local mirror of the Phase 0 E2E finding)
- [ ] T011 [P] [US1] Write `tests/test_cli.py` check scenarios: exit codes, quiet additive output, disclosure present in human AND json modes (SC-006), no-watched-changes message, non-repo error
- [ ] T012 [US1] Write `tests/test_parity.py`: corpus-driven — for all 27 golden cases, verdicts via the local path equal verdicts via the ci path for identical ChangedFiles + lock (SC-001, constitution III enforcement test)

**Checkpoint**: MVP — local verdict preview with proven gate parity.

---

## Phase 4: User Story 2 — specguard init (Priority: P2)

**Goal**: guided scaffolding from nothing to a working check in under 5 minutes.

**Independent Test**: in an unconfigured repo, run `specguard init`, answer prompts,
confirm files validate and `specguard check` runs.

- [ ] T013 [US2] Implement `init` in `src/specguard/cli.py` per `contracts/cli-interface.md`: prompts (goal required, scope lists, optional config/roles/workflow/hook offers), `--force`, `--yes`; every written file round-trips through `config.parse_*` before success; refuse existing lock without `--force` (exit 2)
- [ ] T014 [P] [US2] Write `tests/test_cli.py` init scenarios: scripted prompts via monkeypatched stdin, generated files load cleanly, overwrite refusal, `--yes` non-interactive path, declined offers reported

**Checkpoint**: US1 + US2 — the five-minute onboarding loop is real.

---

## Phase 5: User Story 3 — Pre-commit hook, never blocks (Priority: P3)

**Goal**: warn at commit time; the commit ALWAYS succeeds.

**Independent Test**: hook installed, commit an out-of-scope edit → warning shown,
commit lands; unset the API key → "could not classify" notice, commit lands.

- [ ] T015 [US3] Wire `--hook` mode in `src/specguard/cli.py`: unconditional exit 0 (verdicts, ConfigError, missing key, GitError — everything), silent when no watched files staged, classifier timeout default 30s via `SPECGUARD_HOOK_TIMEOUT` (FR-006)
- [ ] T016 [US3] Add the `init` hook offer: write executable `.git/hooks/pre-commit` invoking `specguard check --staged --hook`; refuse to clobber an existing hook file (append-with-comment or skip+explain)
- [ ] T017 [P] [US3] Write hook never-blocks matrix in `tests/test_cli.py`: BLOCK verdict→0, ConfigError→0, missing key→0, timeout→0, nothing-staged→silent 0 (SC-003)

**Checkpoint**: US1–US3 — commit-time advisory loop closed.

---

## Phase 6: User Story 4 — MCP write-time warnings (Priority: P4)

**Goal**: agents get the verdict for proposed content before any commit exists.

**Independent Test**: invoke `check_proposed_change` with out-of-scope content → full
SCOPE_CHANGE verdict + advisory flag; non-watched path → `watched: false`, no API call.

- [ ] T018 [US4] Implement `src/specguard/mcp_server.py` per `contracts/mcp-interface.md`: tools `check_proposed_change` (baseline content vs proposed via `diff_from_contents`), `get_scope_lock`, `list_watched_paths`; import-guarded `mcp` SDK with `pip install "specguard-ci[mcp]"` hint; unconfigured/missing-key/ClassifierError → warn-shaped results, blocked model → hard error
- [ ] T019 [US4] Add `mcp` subcommand to `src/specguard/cli.py` + `__main__` block in `mcp_server.py` (stdio run); exit 2 with install hint when extra absent
- [ ] T020 [P] [US4] Write `tests/test_mcp_server.py`: tool functions called directly with FakeAdapter in tmp repos — verdict shape, `watched: false` short-circuit (zero adapter calls), `configured: false` hint, advisory field on every result (SC-006)

**Checkpoint**: all four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T021 [P] Update `README.md`: Local Tools section (check/init usage, pre-commit snippet, MCP client config example), roadmap Phase 1 status flip; keep positive framing
- [ ] T022 [P] Update `docs/quickstart.md` with local-tools validation scenarios mirroring `specs/002-local-tools/quickstart.md` V1–V6
- [ ] T023 Run validation: V1 (full suite, mocked), V2 (parity suite), V3 init-to-check in a throwaway dir, V4 hook matrix live, V6 baseline-trust live; V5 MCP with a real client if available — record results in quickstart or PR notes
- [ ] T024 Release: bump to `0.2.0`, `uv build`, publish `specguard-ci`, tag `v0.2.0` + move/retag action line if needed, update `.pre-commit-hooks.yaml` consumer `rev` reference in README

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → Phase 3 (US1)**: strictly sequential gates
- **US2 (P2)**: needs T009 (cli.py exists); independent of US3/US4
- **US3 (P3)**: needs T009; T016 also needs T013 (init exists)
- **US4 (P4)**: needs T007 + T005 only — can run parallel with US2/US3 after Phase 3
- **Phase 7**: after US1–US4 code-complete

### Parallel opportunities

```
Phase 2: T006 ∥ (T003→T004→T005); T007 after T006
Phase 3: T010 ∥ T011 once T008/T009 exist; T012 after both
Post-US1: US2 (T013–T014) ∥ US3 (T015–T017) ∥ US4 (T018–T020)
Phase 7: T021 ∥ T022
```

## Implementation Strategy

MVP = Phases 1–3 (T001–T012): the parity-proven `specguard check`. Each later story is
an independent increment on top of it. The eval harness is NOT re-run this feature —
the classifier prompt moves verbatim (adapter-protocol.md); any prompt edit during
implementation re-triggers the 001 T036 gate per the constitution.

**24 tasks total**: 2 setup + 5 foundational + 5 US1 + 2 US2 + 3 US3 + 3 US4 + 4 polish.
