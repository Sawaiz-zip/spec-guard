# Quickstart / Validation: Framework Adapters

Runnable scenarios that prove the feature works end to end. Assumes the dev install
(`pip install -e ".[dev]"`) and a FakeAdapter for tests (no live LLM key).

## Prerequisites

- Python ≥ 3.10, repo installed editable with dev extras.
- `pytest`, `ruff`, `mypy` available (already in `[dev]`).

## Scenario 1 — Dogfood: govern THIS repo with the Spec Kit adapter (SC-001, SC-004)

This repository is a real Spec Kit project (`.specify/memory/constitution.md` exists) and currently has
no `.specguard/lock.json`.

```bash
# From repo root, with the Spec Kit adapter active:
specguard check --base HEAD~1 --head HEAD
```

**Expected**: output states `Governance source: spec-kit`, the goal is derived from the constitution,
and watched spec-file changes are classified — with NO hand-authored `lock.json` present. (Before this
feature, the same repo fell back to plain mode and reported "unconfigured".)

## Scenario 2 — Explicit lock overrides the framework (FR-002, SC-003)

```bash
# Add an explicit lock whose scope differs from the constitution, then check:
specguard init --yes        # writes a placeholder .specguard/lock.json
specguard check
```

**Expected**: output states `Governance source: explicit-lock`; the constitution is NOT consulted for
scope. Removing the lock returns the source to `spec-kit`.

## Scenario 3 — Plain mode unchanged when no framework (FR-011)

In a repo with neither `.specify/` nor `openspec/` and no lock, `specguard check` reports the same
"unconfigured" SETUP_HINT as today. (Validated by the unchanged plain-mode tests.)

## Scenario 4 — Base-ref isolation: a PR can't rewrite its own scope (FR-008)

```bash
pytest tests/test_governance.py -k base_ref_isolation -q
```

**Expected**: green. The test alters framework files only in the head commit and asserts the derived
lock is unchanged (derivation reads the base ref).

## Full gate (the release bar)

```bash
pytest -q && ruff check src tests && mypy src
```

**Expected**: all green, including:
- the existing 187 tests still pass (backward compatibility, SC-003),
- new `tests/test_governance.py` (precedence, Spec Kit/OpenSpec derivation, base-ref isolation,
  malformed, degrade, parity),
- the parity test: derived lock and equivalent hand-authored lock ⇒ identical verdict (SC-002).

## What is NOT validated this phase

OpenSpec derivation is implemented against the documented format but not run against a live OpenSpec repo
(research.md R3). Spec Kit is the dogfooded, live path. The classifier prompt and engine are unchanged,
so no eval re-run is required for the Anthropic default beyond the parity test.
