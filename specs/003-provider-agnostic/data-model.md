# Data Model: Provider-Agnostic Classifier & Python 3.10

No new on-disk formats (constitution II). One new config field and one new type.

## Changed: Config (`.specguard/config.yml`)

| Field | Type | Default | Rules |
|---|---|---|---|
| `provider` | `anthropic` \| `openai` \| `gemini` \| `openrouter` | `anthropic` | NEW |
| `model` | str | `claude-sonnet-4-6` | unchanged default; Opus 4.8 blocked (field validator) |

New cross-field validation (`model_validator`, mode=after): if `provider != "anthropic"` and
`model` is still the Anthropic default, raise (ConfigError at load) — non-default providers
require an explicit model. All other fields (`watch`, `block_threshold`, `on_error`,
`max_diff_chars`) unchanged.

## New type: Provider

`Provider = Literal["anthropic", "openai", "gemini", "openrouter"]` in `models.py`.
`DEFAULT_PROVIDER = "anthropic"`, `DEFAULT_MODEL = "claude-sonnet-4-6"` (unchanged).

## ClassifierAdapter implementations (`classifier.py` + `providers.py`)

| Adapter | Module | SDK | Env var | Notes |
|---|---|---|---|---|
| `AnthropicAdapter` | classifier.py | anthropic (core) | `ANTHROPIC_API_KEY` | calibrated default; adaptive thinking only when model supports it |
| `OpenAIAdapter` | providers.py | openai (extra) | `OPENAI_API_KEY` | `beta.chat.completions.parse(response_format=Classification)` |
| `OpenRouterAdapter` | providers.py | openai (extra) | `OPENROUTER_API_KEY` | OpenAI adapter with `base_url=https://openrouter.ai/api/v1` |
| `GeminiAdapter` | providers.py | google-genai (extra) | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `generate_content(response_schema=Classification)` |

All implement `classify(lock, changed, config) -> Classification`, call
`assert_model_allowed` first, reuse `SYSTEM_PROMPT` + `build_user_message` (scope never
truncated), and raise `ClassifierError` on failure or missing SDK.

## Factory & helpers (`providers.py`)

- `make_adapter(config) -> ClassifierAdapter` — dispatch on `config.provider`.
- `required_env_var(provider) -> str` — env var name, for missing-key messages in cli/ci/mcp.
- `PROVIDER_ENV_VAR: dict[Provider, str]` — the mapping.

## Relationships

```text
Config.provider ──make_adapter──► ClassifierAdapter ──classify──► Classification ──► engine
Config.model ──assert_model_allowed──► (Opus 4.8 blocked on every provider path)
required_env_var(provider) ──► cli/ci/mcp missing-key message
```
