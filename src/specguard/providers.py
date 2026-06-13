"""Provider-agnostic classifier backends behind one output contract.

The engine speaks only `ClassifierAdapter.classify(...) -> Classification`
(contracts/adapter-protocol.md). This module adds OpenAI, Gemini, and
OpenRouter adapters alongside the shipped Anthropic one and a `make_adapter`
factory that selects by `Config.provider`.

Every adapter, present and future:
  1. calls `assert_model_allowed(config.model)` BEFORE any provider call — the
     Opus 4.8 guardrail (001 research.md R2a) is part of the contract, enforced
     here so it cannot be bypassed by switching providers;
  2. reuses the byte-stable SYSTEM_PROMPT and `build_user_message` so the scope
     lock is never truncated and the rubric is identical across providers;
  3. returns a schema-valid `Classification` or raises `ClassifierError`.

Calibration caveat: only Anthropic + Sonnet 4.6 has passed the golden-corpus
gate (SC-001/SC-002). Other provider/model combinations are unvalidated until
run through `tests/eval/run_eval.py`; they are opt-in, never defaults.
"""

from __future__ import annotations

import os

from specguard.classifier import (
    SYSTEM_PROMPT,
    AnthropicAdapter,
    ClassifierAdapter,
    ClassifierError,
    build_user_message,
)
from specguard.gitdiff import ChangedFile
from specguard.models import (
    Classification,
    Config,
    Provider,
    ScopeLock,
    assert_model_allowed,
)

# Env var holding each provider's API key (used for actionable error messages).
PROVIDER_ENV_VAR: dict[Provider, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def required_env_var(provider: Provider) -> str:
    return PROVIDER_ENV_VAR[provider]


class _OpenAICompatibleAdapter:
    """OpenAI Chat Completions structured output (also serves OpenRouter).

    OpenRouter speaks the OpenAI wire protocol, so the only differences are the
    base URL and which env var holds the key.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        env_var: str = "OPENAI_API_KEY",
        provider_label: str = "openai",
    ) -> None:
        self._base_url = base_url
        self._env_var = env_var
        self._label = provider_label

    def classify(
        self, lock: ScopeLock, changed: ChangedFile, config: Config
    ) -> Classification:
        assert_model_allowed(config.model)  # guardrail before any network/import
        user_message, truncated = build_user_message(
            lock, changed, config.max_diff_chars
        )
        try:
            import openai
        except ImportError as exc:
            raise ClassifierError(
                f"the {self._label} provider needs the optional extra — "
                'pip install "specguard-ci[openai]"'
            ) from exc

        api_key = os.environ.get(self._env_var)
        client = openai.OpenAI(api_key=api_key, base_url=self._base_url, max_retries=2)
        try:
            completion = client.beta.chat.completions.parse(
                model=config.model,
                max_tokens=4000,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                response_format=Classification,
            )
        except Exception as exc:
            raise ClassifierError(f"{self._label} call failed: {exc}") from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ClassifierError(f"{self._label} returned no parsable output")
        return _note_truncation(parsed, truncated, config)


class OpenAIAdapter(_OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(env_var="OPENAI_API_KEY", provider_label="openai")


class OpenRouterAdapter(_OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(
            base_url=OPENROUTER_BASE_URL,
            env_var="OPENROUTER_API_KEY",
            provider_label="openrouter",
        )


class GeminiAdapter:
    """Google Gemini structured output via the google-genai SDK."""

    def classify(
        self, lock: ScopeLock, changed: ChangedFile, config: Config
    ) -> Classification:
        assert_model_allowed(config.model)
        user_message, truncated = build_user_message(
            lock, changed, config.max_diff_chars
        )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ClassifierError(
                "the gemini provider needs the optional extra — "
                'pip install "specguard-ci[gemini]"'
            ) from exc

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model=config.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=Classification,
                ),
            )
        except Exception as exc:
            raise ClassifierError(f"gemini call failed: {exc}") from exc

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, Classification):
            return _note_truncation(parsed, truncated, config)
        text = getattr(response, "text", None)
        if text:
            try:
                return _note_truncation(
                    Classification.model_validate_json(text), truncated, config
                )
            except Exception as exc:
                raise ClassifierError(
                    f"gemini output failed schema validation: {exc}"
                ) from exc
        raise ClassifierError("gemini returned no parsable output")


def _note_truncation(
    classification: Classification, truncated: bool, config: Config
) -> Classification:
    if not truncated:
        return classification
    return classification.model_copy(
        update={
            "explanation": classification.explanation
            + f" [Note: the diff was truncated at {config.max_diff_chars} chars.]"
        }
    )


def make_adapter(config: Config) -> ClassifierAdapter:
    """Select the classifier backend declared by `config.provider`."""
    if config.provider == "anthropic":
        return AnthropicAdapter()
    if config.provider == "openai":
        return OpenAIAdapter()
    if config.provider == "openrouter":
        return OpenRouterAdapter()
    if config.provider == "gemini":
        return GeminiAdapter()
    raise ClassifierError(f"unknown provider '{config.provider}'")  # pragma: no cover

