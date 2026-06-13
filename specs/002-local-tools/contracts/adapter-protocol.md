# Contract: ClassifierAdapter Protocol

Owner: `src/specguard/classifier.py`. The provider seam reserved by 001 plan.md D5,
made concrete. Exactly one shipped implementation this phase: `AnthropicAdapter`.

## Protocol

```text
class ClassifierAdapter(Protocol):
    def classify(
        self, lock: ScopeLock, changed: ChangedFile, config: Config
    ) -> Classification: ...
```

## Obligations on every adapter (present and future)

1. **Guardrail first**: call `assert_model_allowed(config.model)` before any provider
   call. The Opus 4.8 block (001 research.md R2a) is part of this contract, not an
   Anthropic implementation detail. A blocked model raises `ValueError` — deliberately
   not `ClassifierError`, so no on_error policy can swallow it.
2. **Scope lists never truncated** in whatever prompt/request the adapter builds; only
   diff content is truncatable (001 contracts/classifier.md invariant).
3. **Output contract**: return a schema-valid `Classification` or raise
   `ClassifierError`. No partial results, no provider-specific verdict shapes.
4. **Calibration gate**: an adapter (or adapter+model combination) may not become a
   documented default until it passes the golden-corpus eval (SC-001/SC-002 of 001:
   0 false BLOCKs additive, ≥90% scope-change recall). `tests/eval/run_eval.py` grows an
   adapter parameter when a second provider lands — not this phase.

## Shipped implementation

`AnthropicAdapter`: wraps the existing byte-stable system prompt, `messages.parse`
structured output, ≤2K-chars-per-hunk context capping, one re-ask on schema failure,
`ClassifierError` on exhaustion — moved, not modified, so the 001 calibration results
remain valid without an eval re-run (constitution gate untouched).

## Test double

`FakeAdapter` replaces `FakeAnthropicClient` at the seam for engine/CLI/MCP tests:
canned `Classification`s keyed by path, scriptable errors, call counter. The existing
`FakeAnthropicClient` remains for `AnthropicAdapter`-internal tests (prompt assembly,
re-ask, SDK-shape concerns).

## Explicitly out of scope this phase

OpenAI/Gemini/local adapters; provider selection config keys; entry-point plugin
discovery. The seam exists so Phase 2+ can add these without touching `engine.py`.
