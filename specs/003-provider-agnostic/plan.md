# Implementation Plan: Provider-Agnostic Classifier & Python 3.10 Support

**Branch**: `003-provider-agnostic` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-provider-agnostic/spec.md`

## Summary

Realize the multi-provider half of the `ClassifierAdapter` seam (001 plan.md D5, 002
adapter-protocol) by adding OpenAI, Gemini, and OpenRouter adapters beside the shipped
Anthropic one, selected by a new `Config.provider` field via a `make_adapter` factory. Each
adapter reuses the byte-stable prompt and `build_user_message`, enforces the Opus 4.8
guardrail before any call, and returns the same `Classification`. Separately, drop the Python
floor from 3.12 to 3.10 (a policy choice — the code carries no 3.11+ syntax). The Anthropic
default + Sonnet 4.6 stays the calibrated default; Haiku is wired and works (request now omits
adaptive thinking where unsupported) but stays opt-in because it fails the recall gate.

## Technical Context

**Language/Version**: Python ≥ 3.10 (was 3.12). No code change needed — scan confirmed no
PEP 695 / 3.11+ syntax; `from __future__ import annotations` keeps `X | Y` annotations valid.

**Primary Dependencies**: unchanged core (anthropic, pydantic, pyyaml, httpx). New optional
extras: `openai>=1.50` (serves OpenAI and OpenRouter), `google-genai>=0.3` (Gemini). Both
import-guarded; absent in the base install and CI.

**Testing**: pytest with `FakeAdapter`; provider adapters tested for factory selection, config
validation, env-var mapping, and guardrail-before-SDK (no live keys/SDKs needed). CI matrix
adds 3.10 and 3.11.

**Target Platform**: unchanged. The composite Action still provisions its own Python on the
runner, so the gate is unaffected by the floor change; the floor matters only for local tools.

**Project Type**: same single package; one new module (`providers.py`) and a `Config` field.

**Performance Goals / Constraints**: unchanged. Opus 4.8 guardrail on every provider path
(R2a); scope lists never truncated; non-Anthropic providers require an explicit model.

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — all pass.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time is the security layer | ✅ | No change to enforcement surfaces. |
| II. Governance overlay | ✅ | No new formats; provider is a config key. |
| III. One shared validator core | ✅ | All adapters feed the same `engine.evaluate_pr`; only the API call differs. Engine-parity tests unchanged. |
| IV. Zero friction for additive | ✅ | Verdict semantics untouched. |
| V. Deterministic hard blocks, probabilistic advice | ✅ | Opus guardrail enforced at every adapter boundary AND at config validation. |
| VI. No dashboard | ✅ | Config + terminal only. |

*Constitution v1.1.0 itself was amended by this feature (Python floor, multi-provider
phrasing, default-must-pass-eval). No new violations.*

## Project Structure

```text
specs/003-provider-agnostic/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/provider-adapters.md
└── tasks.md

src/specguard/
├── providers.py      # NEW: OpenAI/Gemini/OpenRouter adapters + make_adapter factory
├── classifier.py     # + _supports_adaptive_thinking(); thinking sent only where supported
├── models.py         # + Config.provider; non-anthropic-needs-model validator
├── ci.py / cli.py / mcp_server.py   # construct via make_adapter; per-provider key messages
└── ...

tests/test_providers.py   # NEW: factory, config validation, env-var map, cross-provider guardrail
pyproject.toml            # requires-python>=3.10; ruff py310; mypy 3.10; openai/gemini extras
.github/workflows/tests.yml  # matrix [3.10, 3.11, 3.12]
```

**Structure Decision**: Anthropic-specific prompt/parse logic stays in `classifier.py`
(`AnthropicAdapter` wraps it); cross-provider adapters live in `providers.py` and import the
shared prompt helpers. The factory is the single dispatch point the surfaces call.

## Core Design Decisions

### D1. Adapter set and the OpenAI/OpenRouter share

OpenRouter speaks the OpenAI wire protocol, so a single `_OpenAICompatibleAdapter` serves both
— differing only in base URL and env var. Gemini uses `google-genai` structured output
(`response_schema=Classification`). Anthropic is unchanged. Factory dispatches on
`config.provider`.

### D2. Guardrail before SDK import

Every adapter calls `assert_model_allowed(config.model)` as its first line — before importing
the provider SDK — so the Opus 4.8 block fires regardless of which providers are installed,
and the cross-provider guardrail test needs no SDK.

### D3. Capability-aware requests (the Haiku fix)

`thinking={"type":"adaptive"}` is sent only when `_supports_adaptive_thinking(model)` (false
for the Haiku tier). This unblocked the Haiku eval and is the general pattern for
model-specific parameters.

### D4. Default stays Sonnet (calibration gate)

Haiku was run through the eval at the user's request: 0 false BLOCKs but 83% recall (< 90%
gate). Per the constitution, a model below the gate cannot be the documented default, so
Sonnet 4.6 remains default and Haiku is a documented opt-in. Recorded in research.md R-H.

### D5. Python floor

`requires-python >= 3.10`; ruff `py310`; mypy `3.10`; CI matrix `[3.10, 3.11, 3.12]`.
Verified by running the full suite on a real 3.10 interpreter.

## Complexity Tracking

> No constitution violations — table intentionally empty.
