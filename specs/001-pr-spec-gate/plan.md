# Implementation Plan: PR Spec-File Governance Gate (Phase 0 MVP)

**Branch**: `001-pr-spec-gate` | **Date**: 2026-06-10 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-pr-spec-gate/spec.md`

## Summary

Build a Python package (`specguard`) plus a composite GitHub Action that runs as a required
status check on PRs. It diffs watched spec files against the PR base, classifies each change
with an independent Claude API call (ADDITIVE vs SCOPE_CHANGE, structured output), applies
deterministic role rules for protected paths, detects qualifying PR-review approvals, and
emits pass/warn/block verdicts as annotations + job summary + exit code. Branch protection
turns the exit code into an unbypassable merge gate. Classifier calibration is treated as the
primary product risk: a golden diff corpus and a real-API eval harness are first-class
deliverables with a zero-false-block release gate.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: `anthropic` (Claude API SDK), `pydantic` v2 (models + structured
output), `pyyaml` (roles/config parsing), `httpx` (GitHub REST API). Git CLI assumed present
(Actions runners have it).

**Storage**: Files in the governed repository only — `.specguard/config.yml`,
`.specguard/lock.json`, `.specguard/roles.yml`. No database, no service-side state
(constitution VI: no dashboard).

**Testing**: `pytest` with a fake Anthropic client (CI, no API key) + `tests/eval/run_eval.py`
real-API calibration harness (manual). `act` for local Action runs.

**Target Platform**: GitHub Actions (ubuntu-latest); package published to PyPI; composite
action tagged `v0`.

**Project Type**: Library + CLI entrypoint (`python -m specguard.ci`) wrapped by a composite
GitHub Action.

**Performance Goals**: Check completes < 90 s for ≤ 5 watched files (SC-005); one classifier
call per changed watched file, ~3–5K input / ~500 output tokens each.

**Constraints**: CI tests must run without API credentials; classifier cost ≈ $0.03–0.05 per
file per push on `claude-opus-4-8` (model configurable); fork PRs cannot access secrets
(skip-with-notice).

**Scale/Scope**: Single-repo governance; ≤ ~20 watched files typical; roles files of ≤ ~50
identities. Monorepo multi-scope is out of scope (product spec §10.7, later phase).

## Constitution Check

*GATE: evaluated against constitution v1.0.0 — all pass, no Complexity Tracking entries.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time enforcement is the security layer | ✅ | The only enforcement built in Phase 0 IS the merge-time check (required status + branch protection). No local layer exists yet to be mistaken for security. |
| II. Governance overlay, not a framework | ✅ | Plain mode only; `detect_framework()` recognizes Spec Kit/OpenSpec dirs but only logs; no code imported from either project. |
| III. One shared validator core | ✅ | `engine.py` produces `Verdict`s; `ci.py`/`report.py` only format them. Phase 1 surfaces (CLI/hook/MCP) will call the same engine. |
| IV. Zero friction for additive changes | ✅ | ADDITIVE → PASS always; sole output is a quiet summary line. Release gate: 0 false blocks on additive corpus. |
| V. Deterministic hard blocks, probabilistic advice | ✅ | PROTECTED_VIOLATION computed from path rules + PR-author login only — no LLM in that path. Classifier verdicts carry confidence/summary/explanation; sub-threshold → warn. |
| VI. No dashboard, no new UI | ✅ | Surfaces: GitHub annotations, job summary, PR reviews. Nothing else. |

*Re-check after Phase 1 design: still ✅ — data model and contracts introduce no new surfaces
or frameworks.*

## Project Structure

### Documentation (this feature)

```text
specs/001-pr-spec-gate/
├── plan.md              # This file
├── research.md          # Phase 0 output — decisions on model, thresholds, error policy
├── data-model.md        # Phase 1 output — entities and validation rules
├── quickstart.md        # Phase 1 output — runnable end-to-end validation guide
├── contracts/           # Phase 1 output — classifier I/O, config schemas, action interface
└── tasks.md             # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
pyproject.toml              # deps: anthropic, pyyaml, pydantic, httpx; dev: pytest
LICENSE                     # MIT
README.md                   # positioning one-liner + 5-minute quickstart
action.yml                  # composite action: setup-python → pip install → python -m specguard.ci
.github/workflows/
├── tests.yml               # pytest (mocked) on push/PR
└── specguard.yml           # dogfood: guard this repo's own spec files

src/specguard/
├── __init__.py
├── models.py               # ScopeLock, Classification, Verdict, RolesConfig (Pydantic)
├── config.py               # load/validate .specguard/{config.yml,lock.json}; detect_framework()
├── gitdiff.py              # changed files + unified diffs via `git diff base...head` / `git show`
├── classifier.py           # Claude call: messages.parse → Classification
├── roles.py                # roles.yml parse; glob rules; permission resolution
├── approvals.py            # GitHub Reviews API; latest-review-per-user; role-qualified approvals
├── engine.py               # orchestration: deterministic checks → classify → threshold → verdict
├── report.py               # ::error/::warning annotations + GITHUB_STEP_SUMMARY markdown
└── ci.py                   # __main__: parse event payload, drive engine, exit code

tests/
├── conftest.py             # FakeAnthropicClient, sample configs, event payload fixtures
├── fixtures/
│   ├── corpus/             # golden diffs: NN_name/{old.md,new.md,scope.json,expected.json}
│   └── events/             # pull_request / pull_request_review payload fixtures
├── test_config.py
├── test_gitdiff.py
├── test_classifier.py
├── test_roles.py
├── test_approvals.py
├── test_engine.py
└── eval/run_eval.py        # real-API calibration: confusion matrix, FP rate, cost

docs/quickstart.md
```

**Structure Decision**: Single Python package under `src/` (library-style layout) because
every future surface (CLI, hook, MCP server — product-spec Phase 1) must import the same
engine (constitution III). The GitHub Action is a thin composite wrapper, not a separate
codebase. Module dependency order is acyclic: `models` → `config`/`gitdiff` →
`classifier`/`roles`/`approvals` → `engine` → `report`/`ci`.

## Core Design Decisions

### D1. PROTECTED_VIOLATION is deterministic (refines product spec §F2)

The product spec lists PROTECTED_VIOLATION as classifier output. Here it is computed from
(path matches `edit` rule) ∧ (PR author not in required role) — before any API call. The
hard-block path must never depend on a probabilistic verdict (constitution V). The LLM
answers only ADDITIVE vs SCOPE_CHANGE.

### D2. Verdict pipeline per watched changed file

```
roles edit-rule check ──unauthorized──► BLOCK (protected_violation)   [no API call]
        │ authorized / no rule
        ▼
classifier (Claude) ──ADDITIVE──► PASS (quiet log)
        │ SCOPE_CHANGE
        ├─ confidence < block_threshold ──► WARN (annotation, never blocks)
        └─ confidence ≥ block_threshold
                ├─ no roles.yml (solo mode) ──► WARN
                ├─ qualifying approval found ──► PASS (recorded in summary)
                └─ none ──► BLOCK (lists required role(s))
```

### D3. Approval re-evaluation without a GitHub App

Workflow triggers on both `pull_request` and `pull_request_review`. An authorized approving
review re-runs the job, which queries `GET /repos/{o}/{r}/pulls/{n}/reviews`, takes each
reviewer's latest review, and counts APPROVED states from identities in the authorizing role.
This is what flips the check green with zero new UI.

### D4. Identity = PR author GitHub login

Available in every event payload, server-verified, matches what the Reviews API returns.
Commit-author identity and bot propose-only enforcement are deferred to the App phase
(documented limitation). Logins ending `[bot]` map to an `agents` role when defined.

### D5. Classifier call shape

- Model `claude-opus-4-8` (config override: `model:` in config.yml / `SPECGUARD_MODEL`).
- `client.messages.parse(..., output_format=Classification)` — Pydantic-validated structured
  output, no hand-rolled JSON parsing. Adaptive thinking, `max_tokens=4000`, non-streaming.
- System prompt is byte-stable with `cache_control: {"type": "ephemeral"}` — a PR touching
  N spec files pays the system-prompt tokens once (5-min TTL spans a CI run).
- User content: goal + full scope_in/scope_out (never truncated) + file path + unified diff
  + ≤ 2K chars of context around hunks. Files < 4K chars are sent whole.
- Calibration instruction in the system prompt: "when uncertain, prefer ADDITIVE; reserve
  SCOPE_CHANGE for changes that alter goals, add out-of-scope topics, or shift direction."
- Failure path: SDK retries (2× on 429/5xx) → one re-ask on schema-validation failure →
  `ClassifierError` → engine applies `on_error` policy.

### D6. Thresholds (full table in research.md)

ADDITIVE always passes. SCOPE_CHANGE blocks at confidence ≥ 0.75 (`block_threshold`,
configurable), warns below. `risk_level` is display-only in Phase 0.

### D7. Error policy

Vendor outage → `on_error: warn` default (pass + loud "could not classify" annotation),
`fail` opt-in. Config parse errors → always fail the check. Fork PRs → skip with notice.
Deleted watched files → classified with empty new content. Rationale and alternatives in
research.md.

## Complexity Tracking

> No constitution violations — table intentionally empty.
