# Contract: Provider Adapters & Factory

Owner: `src/specguard/providers.py` (+ `AnthropicAdapter` in `classifier.py`). Extends the
`ClassifierAdapter` protocol from 002 contracts/adapter-protocol.md to multiple providers.

## Factory

```text
make_adapter(config: Config) -> ClassifierAdapter
```

Dispatches on `config.provider`: anthropic → `AnthropicAdapter`, openai → `OpenAIAdapter`,
openrouter → `OpenRouterAdapter`, gemini → `GeminiAdapter`.

## Every adapter MUST

1. Call `assert_model_allowed(config.model)` **before any SDK import or network call** — the
   Opus 4.8 guardrail is part of the contract on every provider (001 R2a).
2. Reuse `SYSTEM_PROMPT` and `build_user_message` — identical rubric and framing; scope lists
   never truncated; diff truncation noted in the explanation.
3. Return a schema-valid `Classification` or raise `ClassifierError` — no provider-specific
   verdict shapes, no partial results.
4. On a missing optional SDK, raise `ClassifierError` with the exact install hint
   (`pip install "specguard-ci[openai]"` / `[gemini]`) — never an unguarded `ImportError`.

## Provider specifics

| Provider | Structured output mechanism | Key env var |
|---|---|---|
| anthropic | `messages.parse(output_format=Classification)`; `thinking: adaptive` only if the model supports it | `ANTHROPIC_API_KEY` |
| openai | `beta.chat.completions.parse(response_format=Classification)` | `OPENAI_API_KEY` |
| openrouter | OpenAI mechanism with `base_url=https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |
| gemini | `generate_content(config=response_schema=Classification, response_mime_type=application/json)` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |

## Config validation

- Non-Anthropic provider with the Anthropic default model → ConfigError (explicit model
  required).
- Any provider with an Opus-4.8 model id (including OpenRouter's `anthropic/claude-opus-4-8`)
  → blocked at config validation AND at the adapter boundary.

## Calibration obligation

Only `anthropic` + `claude-sonnet-4-6` is live-verified against the golden corpus
(0 false BLOCKs, 100% recall). Other provider/model combinations are unvalidated until run
through `tests/eval/run_eval.py` and MUST NOT be made a documented default until they pass
(0 false BLOCKs, ≥90% recall). Haiku is a known opt-in below the recall gate (research.md R-H).

## Test doubles

`FakeAdapter` (tests/conftest.py) substitutes at the seam for engine/CLI/MCP tests. Provider
adapters are unit-tested for factory selection, config validation, env-var mapping, and
guardrail-before-SDK without any live key or installed provider SDK.
