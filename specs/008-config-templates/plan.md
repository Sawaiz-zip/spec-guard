# Implementation Plan: Self-Documenting Configuration Templates

**Branch**: `008-config-templates` | **Date**: 2026-07-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-config-templates/spec.md`

## Summary

Make every config file `specguard init` writes understandable without leaving the file:
richly-comment the generated `roles.yml` and `config.yml`, scaffold a commented `regions.yml`
(section locking, shipped in 007 but never offered by `init`), and stop the generated
`lock.json` from carrying unexplained `locked_at`/`locked_by` null fields. This is a
template-and-`init` change only — the governance engine, parsers, and models are untouched, and
every generated template must still round-trip through its existing parser before it is written.

## Technical Context

**Language/Version**: Python 3.10+ (existing floor)

**Primary Dependencies**: none new — stdlib + existing `pyyaml`/`pydantic`; templates are string
constants in `src/specguard/cli.py`

**Storage**: files under `.specguard/` (`lock.json`, `config.yml`, `roles.yml`, `regions.yml`)

**Testing**: pytest (existing suite); new assertions in `tests/test_cli.py` /
`tests/test_cli_init.py`

**Target Platform**: local developer machine (the CLI); no runtime/CI/App surface change

**Project Type**: single Python package (CLI + library)

**Performance Goals**: N/A — one-time scaffold at `init`

**Constraints**: every generated template MUST parse through its existing parser
(`parse_lock`/`parse_config`/`parse_roles`/`parse_regions`) before write (FR-007); no engine
behavior change (FR-008); never overwrite an existing file (FR-009)

**Scale/Scope**: 4 template constants + 1 new `init` prompt + tests + doc sync. No new modules.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Merge-time enforcement is the security layer** | ✅ Unaffected — `init` and its templates are a developer-experience layer; enforcement logic is untouched. |
| **II. Governance overlay, not a framework** | ✅ Unaffected — no new spec format; still plain files. |
| **III. One shared validator core** | ✅ Unaffected — FR-008 forbids any classification/enforcement change; templates only round-trip through existing parsers. |
| **IV. Zero friction for additive changes** | ✅ Reinforced — the `roles.yml` template documents that additive changes always pass (no rule needed). |
| **V. Deterministic hard blocks, probabilistic advice** | ✅ Unaffected. |
| **VI. No dashboard, no new UI** | ✅ Respected — output is commented text files, not UI. |
| **Quality gates** (config errors fail loudly; CI without live key; no default-model change) | ✅ Templates round-trip through parsers before write (loud failure preserved); tests are static-text assertions needing no API key; no provider/model default touched, so no golden-corpus re-run required. |

**Result**: PASS. No violations; Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/008-config-templates/
├── plan.md              # This file
├── research.md          # Phase 0 — design decisions
├── data-model.md        # Phase 1 — template + rule-vocabulary reference
├── quickstart.md        # Phase 1 — validation scenarios
├── contracts/
│   └── init-templates.md  # Phase 1 — the contract each generated template must satisfy
└── tasks.md             # Phase 2 (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
src/specguard/
├── cli.py         # CHANGE: WORKFLOW_SNIPPET stays; rewrite CONFIG_TEMPLATE, add
│                  #         ROLES_TEMPLATE + REGIONS_TEMPLATE constants; drop null
│                  #         locked_at/locked_by from the generated lock.json; add a
│                  #         regions.yml prompt in _offer_optional_files
├── config.py      # UNCHANGED — REGIONS_PATH + parse_regions already exist
└── models.py      # UNCHANGED — locked_at/locked_by stay on the model (used by adapters)

tests/
├── test_cli.py or test_cli_init.py   # CHANGE/ADD: assert each generated template parses;
│                                      #   assert documentation markers present; regions
│                                      #   offered + written; lock.json has no null metadata
└── (existing suites)                 # UNCHANGED — must stay green (FR-008)
```

**Structure Decision**: Single package. All production change is localized to `cli.py`'s
template constants and the `_offer_optional_files` flow; no new module, no model/parser change.

## Complexity Tracking

No constitution violations — section intentionally empty.
