# Feature Specification: Provider-Agnostic Classifier & Python 3.10 Support

**Feature Branch**: `003-provider-agnostic`

**Created**: 2026-06-12

**Status**: Draft

**Input**: User description: "Relax the Python restriction so it works for 3.10. Make the LLM
provider agnostic — work for Gemini, OpenAI, Anthropic, and OpenRouter. Change the default
model away from Opus 4.8 toward Haiku."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose your LLM provider (Priority: P1)

A team already pays for OpenAI (or Gemini, or routes everything through OpenRouter) and does
not want a second vendor relationship just to run SpecGuard. They set `provider:` and `model:`
in `.specguard/config.yml`, supply that provider's API key as the repo secret, and the gate
classifies with their chosen backend — producing the same ADDITIVE/SCOPE_CHANGE verdicts,
through the same engine, as the Anthropic default.

**Why this priority**: Provider lock-in is an adoption blocker. The validator core was built
provider-agnostic from the start (the `ClassifierAdapter` seam); this story makes that real.

**Independent Test**: In a configured repo, set `provider: openai` + a model, supply
`OPENAI_API_KEY`, and confirm a scope-change edit is classified and reported exactly as the
Anthropic path would shape it; switch to `gemini`/`openrouter` and confirm the same.

**Acceptance Scenarios**:

1. **Given** `provider: openai` and an explicit model, **When** a watched file gains an
   out-of-scope topic, **Then** the verdict is SCOPE_CHANGE with the same fields the
   Anthropic backend produces, and enforcement behaves identically.
2. **Given** a provider is selected but no model is set, **When** config loads, **Then** it
   fails loudly explaining that non-default providers require an explicit model.
3. **Given** any provider routes to an Opus 4.8 model (e.g. `anthropic/claude-opus-4-8` via
   OpenRouter), **When** config loads or the adapter runs, **Then** it is hard-blocked by the
   guardrail before any API call.
4. **Given** the selected provider's optional dependency is not installed, **When**
   classification is attempted, **Then** the user gets an actionable "install the extra"
   message, never a crash.

---

### User Story 2 - Install on Python 3.10+ (Priority: P2)

A team's CI images and developer machines run Python 3.10 or 3.11. They install
`specguard-ci` and the local tools without being forced to upgrade their interpreter.

**Why this priority**: The 3.12 floor was a policy choice, not a code necessity, and it
blocked the local tools (CLI/hook/MCP) for a large share of real environments. The CI gate
was never affected (the Action provisions its own Python), so this is about local reach.

**Independent Test**: Create a Python 3.10 virtualenv, `pip install specguard-ci[dev]`, and
run the full test suite to green.

**Acceptance Scenarios**:

1. **Given** Python 3.10, **When** `pip install specguard-ci` runs, **Then** it installs
   successfully (no `requires-python` rejection).
2. **Given** Python 3.10/3.11/3.12, **When** the test suite runs, **Then** it passes on all
   three.

---

### User Story 3 - Pick a cheaper Anthropic model (Priority: P3)

A cost-sensitive team wants the cheapest viable Anthropic model. They can select Haiku, and
it must actually work (not error on unsupported request parameters) — with the project being
honest about whether it meets the quality bar.

**Why this priority**: Directly requested. Surfaces a real portability issue (adaptive
thinking is not universal) and the calibration discipline (a model below the recall gate must
not silently become the default).

**Independent Test**: Run the eval harness against Haiku and confirm it completes (no
unsupported-parameter error) and reports its confusion matrix.

**Acceptance Scenarios**:

1. **Given** `model: claude-haiku-4-5-20251001`, **When** classification runs, **Then** it
   succeeds (the request omits parameters Haiku does not support).
2. **Given** a model that fails the recall gate, **When** choosing the shipped default,
   **Then** that model is NOT made the default; it remains an opt-in with the gap documented.

---

### Edge Cases

- A provider's structured-output call returns unparseable content → `ClassifierError`,
  handled by the existing `on_error` policy (never a crash).
- `GEMINI_API_KEY` vs `GOOGLE_API_KEY` — the Gemini adapter accepts either.
- OpenRouter model ids namespace the vendor (`anthropic/...`, `google/...`); the Opus
  guardrail still matches the `opus-4-8` substring within them.
- A model that rejects the `thinking` parameter (Haiku tier) must not error — the parameter
  is sent only to models that support it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The classifier backend MUST be selectable via `provider:` in
  `.specguard/config.yml` — one of `anthropic` (default), `openai`, `gemini`, `openrouter` —
  with the engine and verdict semantics unchanged across providers (constitution III).
- **FR-002**: Each provider adapter MUST honor the same output contract (a schema-valid
  `Classification` or `ClassifierError`), reuse the byte-stable system prompt and scope-lock
  framing (scope lists never truncated), and enforce the Opus 4.8 guardrail before any
  provider call (constitution V, research.md 001 R2a).
- **FR-003**: Non-Anthropic providers MUST require an explicit `model:`; leaving the Anthropic
  default model on another provider MUST fail loudly at config load.
- **FR-004**: Provider SDKs beyond Anthropic MUST be optional install extras; the base package
  and CI test run MUST not require them, and a missing SDK MUST produce an actionable install
  message, not a crash.
- **FR-005**: The package MUST install and pass its full test suite on Python 3.10, 3.11, and
  3.12.
- **FR-006**: Provider/model combinations other than the calibrated default MUST be treated as
  unvalidated until run through the eval harness; only a combination that passes the gate
  (0 false BLOCKs, ≥90% recall) may be a documented default.
- **FR-007**: Requests MUST adapt to model capability — parameters a model does not support
  (e.g. adaptive thinking on Haiku) MUST be omitted rather than sent and failed.

### Key Entities

- **Provider**: the selected classifier backend — anthropic | openai | gemini | openrouter.
- **ClassifierAdapter**: one backend implementation behind the shared `classify(...)`
  contract; the factory `make_adapter(config)` returns the one for `config.provider`.

## Success Criteria *(mandatory)*

- **SC-001**: The full test suite passes on Python 3.10, 3.11, and 3.12.
- **SC-002**: A repo can switch provider with two config lines plus a key, and get verdicts
  identical in shape and semantics to the Anthropic default (verified by adapter-selection and
  engine-parity tests).
- **SC-003**: The Opus 4.8 guardrail holds on 100% of provider paths, including OpenRouter
  vendor-namespaced model ids (verified across the test matrix).
- **SC-004**: The shipped default provider/model has passed the golden-corpus gate; any model
  that has not (e.g. Haiku at 83% recall) is documented as opt-in with its gap stated.

## Assumptions

- Anthropic remains the default and the only provider with a live-verified calibration; the
  OpenAI/Gemini/OpenRouter adapters are implemented against documented SDK contracts but were
  not run live in this phase (no keys for them available at build time).
- One API key per provider via the conventional env var (`ANTHROPIC_API_KEY`,
  `OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`).
- The system prompt is reused verbatim across providers, so no eval re-run is required for the
  Anthropic default; new provider/model defaults would require their own eval run.
- Entry-point plugin discovery and a configurable `classifier-provider` Action input remain
  future work; this phase ships the providers and the config switch.
