"""Provider factory selection, config validation, and the cross-provider guardrail."""

from __future__ import annotations

import pytest

from specguard.classifier import AnthropicAdapter, ClassifierError
from specguard.config import ConfigError, parse_config
from specguard.gitdiff import diff_from_contents
from specguard.models import Config
from specguard.providers import (
    GeminiAdapter,
    OpenAIAdapter,
    OpenRouterAdapter,
    make_adapter,
    required_env_var,
)

CHANGED = diff_from_contents("README.md", "a\n", "b\n")
LOCK_GOAL = "A CLI tool"


def lock():
    from specguard.models import ScopeLock

    return ScopeLock(goal=LOCK_GOAL, scope_in=[], scope_out=["SaaS"])


class TestFactory:
    def test_anthropic_default(self):
        assert isinstance(make_adapter(Config()), AnthropicAdapter)

    def test_openai(self):
        cfg = Config(provider="openai", model="gpt-4o-2024-11-20")
        assert isinstance(make_adapter(cfg), OpenAIAdapter)

    def test_openrouter(self):
        cfg = Config(provider="openrouter", model="anthropic/claude-3.5-sonnet")
        assert isinstance(make_adapter(cfg), OpenRouterAdapter)

    def test_gemini(self):
        cfg = Config(provider="gemini", model="gemini-2.0-flash")
        assert isinstance(make_adapter(cfg), GeminiAdapter)


class TestEnvVarMapping:
    @pytest.mark.parametrize(
        ("provider", "expected"),
        [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("gemini", "GEMINI_API_KEY"),
            ("openrouter", "OPENROUTER_API_KEY"),
        ],
    )
    def test_required_env_var(self, provider, expected):
        assert required_env_var(provider) == expected


class TestConfigValidation:
    def test_non_anthropic_provider_needs_explicit_model(self):
        # Leaving the Anthropic default model on another provider is rejected.
        with pytest.raises(ConfigError, match="requires an explicit"):
            parse_config("provider: openai\n")

    def test_non_anthropic_with_model_ok(self):
        cfg = parse_config("provider: openai\nmodel: gpt-4o-2024-11-20\n")
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o-2024-11-20"

    def test_unknown_provider_rejected(self):
        with pytest.raises(ConfigError):
            parse_config("provider: cohere\nmodel: command-r\n")

    def test_anthropic_default_unchanged(self):
        cfg = parse_config(None)
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-sonnet-4-6"


class TestGuardrailAcrossProviders:
    """Opus 4.8 stays blocked no matter which provider routes to it (R2a)."""

    def test_config_blocks_opus_even_via_openrouter(self):
        # First line of defense: config validation rejects an Opus-4.8 routing.
        with pytest.raises(ConfigError, match="blocked by project guardrail"):
            parse_config("provider: openrouter\nmodel: anthropic/claude-opus-4-8\n")

    def test_adapter_blocks_opus_before_sdk(self):
        # Second line: even a config built WITHOUT validation (model_copy
        # bypasses validators) is caught at the adapter boundary, before any
        # SDK import — so no openai dep is needed to prove it.
        cfg = Config(provider="openrouter", model="anthropic/claude-3.5-sonnet")
        cfg = cfg.model_copy(update={"model": "anthropic/claude-opus-4-8"})
        with pytest.raises(ValueError, match="blocked by project guardrail"):
            OpenRouterAdapter().classify(lock(), CHANGED, cfg)

    def test_openai_guardrail_fires_without_sdk(self, monkeypatch):
        # Even if the model is allowed, a missing SDK yields ClassifierError —
        # never a crash — proving the import is guarded.
        cfg = Config(provider="openai", model="gpt-4o-2024-11-20")
        import builtins

        real_import = builtins.__import__

        def no_openai(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("no openai")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_openai)
        with pytest.raises(ClassifierError, match=r"specguard-ci\[openai\]"):
            OpenAIAdapter().classify(lock(), CHANGED, cfg)
