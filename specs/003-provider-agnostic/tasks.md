# Tasks: Provider-Agnostic Classifier & Python 3.10 Support

**Input**: Design documents from `/specs/003-provider-agnostic/`

**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅

All tasks complete — this feature was implemented in one pass on branch
`003-provider-agnostic`. Recorded here for traceability.

## Phase 1: Python floor

- [X] T001 `pyproject.toml`: `requires-python >= 3.10`, ruff `target-version = py310`, mypy
  `python_version = 3.10`; version bump to `0.3.0`
- [X] T002 `.github/workflows/tests.yml`: matrix `[3.10, 3.11, 3.12]`
- [X] T003 Verify: scan for 3.11+ syntax (none found); run full suite on a real 3.10 venv (green)

## Phase 2: Provider seam

- [X] T004 `models.py`: `Provider` literal + `DEFAULT_PROVIDER`; `Config.provider` field;
  `model_validator` requiring an explicit model for non-Anthropic providers
- [X] T005 `classifier.py`: `_supports_adaptive_thinking()`; send `thinking` only when
  supported (the Haiku fix, research.md R4)
- [X] T006 `providers.py`: `_OpenAICompatibleAdapter` (OpenAI + OpenRouter), `GeminiAdapter`,
  `make_adapter` factory, `required_env_var`, `PROVIDER_ENV_VAR`; guardrail before SDK import
- [X] T007 `pyproject.toml`: `openai` and `gemini` optional extras; mypy ignore for their imports

## Phase 3: Wiring & validation

- [X] T008 `ci.py` / `cli.py` / `mcp_server.py`: construct via `make_adapter(config)`;
  per-provider missing-key messages via `required_env_var`
- [X] T009 `tests/test_providers.py`: factory selection, config validation, env-var mapping,
  cross-provider Opus guardrail (config-level and adapter-level, no SDK needed)
- [X] T010 Run Haiku through the eval harness; record result (0 false BLOCKs / 83% recall →
  keep Sonnet default, Haiku opt-in) in research.md R-H

## Phase 4: Specfiles & docs

- [X] T011 Constitution → v1.1.0 (Python floor ≥3.10; provider-agnostic classifier; default
  must pass the eval gate)
- [X] T012 New `specs/003-provider-agnostic/` artifacts (this set)
- [X] T013 Forward-notes on superseded facts in 001/002 docs (Python version, single-provider,
  default model)
- [X] T014 `README.md`: providers section + extras + Python 3.10 note

## Phase 5: Release

- [X] T015 Commit, push branch, open PR into `001-pr-spec-gate`
- [X] T016 Publish `specguard-ci 0.3.0`; tag; push `ANTHROPIC_API_KEY` repo secret (user-directed)

**Notes**: 187 tests pass (3.10/3.11/3.12), ruff + strict mypy clean. The system prompt is
unchanged, so the Anthropic default needs no eval re-run; only the Haiku probe was run (R-H).
