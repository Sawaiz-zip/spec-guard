# Tasks: Self-Documenting Configuration Templates

**Input**: Design documents from `specs/008-config-templates/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included — the spec's success criteria are assertions about generated file content and
parseability (SC-002/004/005), so marker/parse tests are the feature's proof, not optional extras.

All production change is localized to `src/specguard/cli.py` (template constants + the
`_offer_optional_files` flow). No engine/parser/model change (FR-008).

## Phase 1: Setup

- [x] T001 Record the current green baseline: run `pytest -q` and note the passing count, so
  Phase 6 can prove no regression (SC-006).

## Phase 2: Foundational (blocking prerequisites)

- [x] T002 In `tests/test_cli.py`, add a reusable helper that scaffolds a temp git repo and drives
  `specguard.cli._cmd_init` / `_offer_optional_files` non-interactively (feeding "yes" to each
  offer), returning the created file paths + contents — shared by the US1/US2/US3 test tasks.

## Phase 3: User Story 1 — roles.yml self-documenting (Priority: P1) 🎯 MVP

**Goal**: The generated `.specguard/roles.yml` explains every supported rule key inline, so a user
never leaves the file to understand it.

**Independent Test**: Run `init`, opt into roles, inspect `.specguard/roles.yml` — it documents
`edit` and `scope_changes.approve`, notes additive changes always pass, shows commented full-vocab
examples, references no `additive_changes` key, and parses via `parse_roles`.

- [x] T003 [US1] In `src/specguard/cli.py`, replace the inline `roles_text` built in
  `_offer_optional_files` with a documented template: keep the working `roles:`/`rules:` example,
  add inline comments defining `edit` (deterministic edit authority) and `scope_changes.approve`
  (which role's approval unblocks a SCOPE_CHANGE), a line stating additive changes always pass (no
  rule needed), and a commented-out block showing the full supported vocabulary. Do NOT reference
  `additive_changes` or any unsupported key (data-model.md rule table; FR-001/002/010).
- [x] T004 [US1] Ensure the generated roles.yml still round-trips: `parse_roles` runs on the active
  (uncommented) content before write, and the added comments do not break parsing (FR-007).
- [x] T005 [P] [US1] In `tests/test_cli.py`, add tests asserting the generated `.specguard/roles.yml`
  (a) parses via `parse_roles`, (b) contains documentation markers for `edit`, `scope_changes`,
  `approve`, and "additive", and (c) does NOT contain the string `additive_changes` (SC-001/002).

**Checkpoint**: US1 independently delivers the highest-value fix — the roles file is self-explanatory.

## Phase 4: User Story 2 — config.yml explains behavior (Priority: P2)

**Goal**: Each `config.yml` key documents what it *does*, not just its default value.

**Independent Test**: Run `init`, opt into settings, inspect `.specguard/config.yml` — every key has
a "what it does + allowed values" comment and the file parses via `parse_config`.

- [x] T006 [US2] In `src/specguard/cli.py`, rewrite `CONFIG_TEMPLATE` so every key (`watch`,
  `block_threshold`, `on_error`, `provider`, `model`, `max_diff_chars`) carries an inline
  explanation of its behavioral effect and allowed values/range per the data-model.md settings
  table; keep keys commented out (inert / pure-defaults) and verify the documented defaults match
  `models.Config` (FR-003/010; constitution IV — no behavior change).
- [x] T007 [P] [US2] In `tests/test_cli.py`, add tests asserting the generated `.specguard/config.yml`
  parses via `parse_config` and each documented key is accompanied by an explanatory comment marker
  (e.g. `on_error` mentions both `warn` and `fail`) (SC-002).

**Checkpoint**: US1 + US2 — the two required-to-understand files are both self-documenting.

## Phase 5: User Story 3 — regions.yml scaffold + lock.json demystified (Priority: P3)

**Goal**: Section locking is discoverable from `init`, and `lock.json` carries no mystery fields.

**Independent Test**: Run `init` — it offers `.specguard/regions.yml` (commented, parseable), and
the generated `.specguard/lock.json` contains only `goal`/`scope_in`/`scope_out`.

- [x] T008 [US3] In `src/specguard/cli.py`, import `REGIONS_PATH` from `specguard.config` and add a
  `REGIONS_TEMPLATE` constant: a commented `files:` example explaining the heading→regions mapping
  and how section locking narrows what is governed (FR-005; data-model.md).
- [x] T009 [US3] In `_offer_optional_files`, add a `regions.yml` offer mirroring the config/roles
  offers — interactive yes/no, skip-if-exists, skip in `--yes`, append to `created`/`skipped`, and
  round-trip through `parse_regions` before writing (FR-004/007/009).
- [x] T010 [US3] In `_cmd_init`, drop `locked_at`/`locked_by` from the generated `lock.json` dict
  (write only `goal`/`scope_in`/`scope_out`); keep the `parse_lock` round-trip. Leave the
  `ScopeLock` model unchanged — the fields stay for framework adapters (FR-006/008; research R1).
- [x] T011 [P] [US3] In `tests/test_cli.py`, add tests: (a) `regions.yml` is offered and, when
  accepted, written with the `files:` documentation and parses via `parse_regions`; (b) the
  generated `lock.json` contains no `locked_at`/`locked_by` and still parses via `parse_lock`
  (SC-003/005).

**Checkpoint**: all three stories complete; every generated file is self-explanatory.

## Phase 6: Polish & cross-cutting

- [x] T012 [P] Update the README **Configuration** section so it reflects that `init` now offers
  `regions.yml` and that generated `lock.json` omits the metadata fields — keep it consistent with
  the actual generated templates.
- [x] T013 [P] Fix pre-existing doc drift found during planning: `SPECGUARD_PRODUCT_SPEC.md` §9
  Phase 0 lists an `additive_changes` rule key the parser does not implement — correct it to
  `edit` / `scope_changes` only.
- [x] T014 Full gate: `ruff check .` + `mypy` clean; `pytest -q` green at the T001 baseline + the
  new tests; walk quickstart.md Q1–Q6.

## Dependencies & order

- **Setup (T001)** → **Foundational (T002)** → user stories.
- **US1 (T003–T005)**, **US2 (T006–T007)**, **US3 (T008–T011)** are mutually independent — they
  touch different template constants / different regions of `cli.py` and can be done in any order
  after T002. Recommended by priority: US1 → US2 → US3.
- Within a story, the `[P]` test task can run in parallel with (or immediately after) its
  implementation task since it only reads generated output.
- **Polish (T012–T014)** runs last; T012/T013 are `[P]` (different files), T014 gates everything.

## Parallel execution example

After T002, one developer can take US1 (T003–T005), another US2 (T006–T007), another US3
(T008–T011) concurrently — no shared file conflicts beyond `cli.py`'s distinct template constants
and the append-only test file.

## Implementation strategy

**MVP = User Story 1** (T001–T005): the roles file is the highest-consequence "guess-around" risk,
so shipping just US1 already delivers the core value. US2 and US3 are incremental additions on top.
