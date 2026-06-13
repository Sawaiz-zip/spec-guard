# Research & Decisions: Provider-Agnostic Classifier & Python 3.10

## R1. Provider set and SDK strategy

- **Decision**: Ship adapters for Anthropic (core dep), OpenAI and OpenRouter (one
  `openai`-SDK adapter, base-URL/env differ), and Gemini (`google-genai`). OpenAI/Gemini are
  optional extras; OpenRouter reuses the openai extra.
- **Rationale**: OpenRouter is OpenAI-wire-compatible, so one implementation covers two
  providers. Keeping provider SDKs as extras preserves the lean base install the CI Action
  ships on every run.
- **Alternatives**: a single multi-provider client lib (LiteLLM) — rejected: heavy dependency,
  and we only need a thin structured-output call per provider. Entry-point plugin discovery —
  deferred: no third-party adapters to justify the machinery yet.

## R2. Guardrail placement

- **Decision**: `assert_model_allowed` runs first in every adapter, before the SDK import.
  Config validation also rejects blocked models. Two layers.
- **Rationale**: switching providers must not become an Opus-4.8 bypass (001 R2a). Running it
  before the import means the guardrail test needs no provider SDK installed.

## R3. Non-Anthropic providers require an explicit model

- **Decision**: a `model_validator` rejects config where `provider != anthropic` and `model`
  is still the Anthropic default.
- **Rationale**: there is no sensible cross-provider default model; silently sending a Claude
  model id to OpenAI would fail confusingly at call time. Fail loud at config load instead.

## R4. Capability-aware request parameters

- **Decision**: send `thinking: adaptive` only to models that support it
  (`_supports_adaptive_thinking`, false for Haiku).
- **Rationale**: Haiku returns HTTP 400 "adaptive thinking is not supported on this model".
  Discovered when running the Haiku eval. The same pattern generalizes to any
  model-specific parameter.

## R5. Python floor 3.12 → 3.10

- **Decision**: `requires-python >= 3.10`; ruff `py310`; mypy `3.10`; CI matrix
  `[3.10, 3.11, 3.12]`.
- **Rationale**: a source scan found no PEP 695 generics/`type` statements, no `tomllib`,
  no `datetime.UTC`, no `itertools.batched` — nothing 3.11+. `from __future__ import
  annotations` makes `X | Y` and `list[str]` annotations valid on 3.10. The floor was a plan
  choice, not a code constraint. Verified by running the full suite on a real 3.10 venv.
- **Note**: the merge gate was never affected — the composite Action provisions its own Python
  on the runner. The floor only ever constrained the local tools (CLI/hook/MCP).

## R-H. Haiku calibration (the requested default change)

- **Run** (2026-06-12, golden corpus, threshold 0.75, thinking omitted):

  | Model | False BLOCKs (gate: 0) | Recall (gate: ≥90%) | Cost |
  |---|---|---|---|
  | `claude-sonnet-4-6` (default) | 0 | 100% (12/12) | ~$0.19 |
  | `claude-haiku-4-5-20251001` | 0 | **83% (10/12)** | ~$0.06 |

- **Decision**: keep `claude-sonnet-4-6` as the default; ship Haiku as a documented opt-in.
- **Rationale**: Haiku preserves the zero-false-block promise (constitution IV) but misses 2
  of 12 real scope changes — below the SC-002 recall gate. The constitution forbids a
  below-gate model as the documented default. The user was presented this tradeoff and chose
  Sonnet-default / Haiku-opt-in.
- **Note**: Haiku's miss is false *negatives* (drift slips through), not false positives, so
  it never adds friction — it just under-enforces. Fine for cost-first teams who accept that.
