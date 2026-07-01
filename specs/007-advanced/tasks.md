# Tasks: Advanced Governance (Section Locking, Monorepo, Audit Export)

**Input**: Design documents from `/specs/007-advanced/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

All tasks complete — implemented in one pass on branch `007-advanced`.

## Phase 1: Foundation — models, config, regions

- [X] T001 `models.py`: `RegionsConfig`; `Verdict.scope` (default `""`); `"region_ungoverned"`
  VerdictReason
- [X] T002 `config.py`: `REGIONS_PATH` (`.specguard/regions.yml`); `parse_regions()`
- [X] T003 `regions.py`: tolerant heading scan (`_locate`), `split_into_regions()`,
  `RegionAnchorError(ConfigError)`; only modified files are split (D1); both old AND new
  content must resolve the anchor (D2)

## Phase 2: US1 — Section-level locking (P1)

- [X] T004 `engine.py`: `evaluate_pr` gains optional `regions_config`/`scope` params;
  `_evaluate_changed_file` returns `list[Verdict]`; region sub-verdicts use the ORIGINAL
  file path for role-rule lookups (`role_path`), the region path (`path#anchor`) for
  classification and display
- [X] T005 `report.py`: `_summary_block` branch for `region_ungoverned`
- [X] T006 `tests/test_regions.py` — 16 cases: span location, multi-anchor, anchor-missing
  (both sides), subsections, engine integration, role-lookup-uses-original-path, added-file
  fallback

**Checkpoint**: a file with `regions.yml` declared governs only its named sections; the rest
passes without ever reaching the classifier. 251 pre-existing tests still green (no regression).

## Phase 3: US2 — Monorepo multi-scope (P2)

- [X] T007 `scopes.py`: `Scope` dataclass, `_nearest_explicit_scope` (walks ancestors for
  `{dir}/.specguard/lock.json`), `resolve_scopes()`, `rescope_changed_file()`
- [X] T008 `ci.py`: `_run` groups changed files via `resolve_scopes`, evaluates per scope
  with that scope's own lock/config/roles/regions, aggregates verdicts + `scope_roles` for
  reporting
- [X] T009 `app/events.py`: same per-scope refactor as ci.py; `_summary` reports each
  scope's governance source
- [X] T010 `tests/test_scopes.py` — 12 cases: nearest-ancestor grouping, per-scope
  config/roles/regions loading, repo-root fallback, malformed-scope-lock propagation,
  rescoping
- [X] T011 `test_ci.py`/`test_app_events.py`: end-to-end multi-scope cases (independent
  verdicts per package; a scope's own roles protect that scope's own `.specguard/`)

**Checkpoint**: a monorepo with N package locks gets N independent verdict sets in one PR;
a single-scope repo is provably unaffected (existing test suites pass unchanged).

## Phase 4: US3 — Audit export (P3)

- [X] T012 `audit.py`: `AuditEntry`/`AuditApproval`, `build_audit_entries()` (timestamped
  once via the PR's head commit time, not per-approval — research.md R6),
  `export_audit_json()`
- [X] T013 `ci.py`: opt-in `SPECGUARD_AUDIT_PATH` env var, memoized approvals fetch (no
  duplicate API call when a scope-change verdict already triggered it)
- [X] T014 `tests/test_audit.py` — 8 cases: entry building, scope propagation, JSON
  round-trip, no-secrets assertion
- [X] T015 `test_ci.py`: end-to-end audit-file-written / no-env-var-no-file cases

**Checkpoint**: `SPECGUARD_AUDIT_PATH` set → one JSON record per verdict, no secrets; unset →
zero behavior change, zero extra API calls.

## Phase 5: Docs & release

- [X] T016 README: roadmap row flipped to shipped; new "Advanced Governance" section
  (regions, monorepo, audit export usage)
- [X] T017 Full gate: ruff + strict mypy clean; 292 tests green on Python 3.11 and 3.12
  (the floor, 3.10, is covered by the existing CI matrix)
- [ ] T018 Commit, push branch, open PR into `main`
- [ ] T019 (follow-up, deferred per research.md R7) embed audit JSON into the GitHub App's
  check-run output, so App deployments get the same compliance trail with zero extra config

**Notes**: no golden-corpus cases were added (research.md R8) — regions/scopes change which
diff and which `ScopeLock` reach `classify()`, never `classify()`'s own behavior, so the
existing 27-case corpus and its calibration remain the relevant signal.
