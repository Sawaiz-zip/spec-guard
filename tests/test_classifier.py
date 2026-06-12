"""Classifier prompt assembly, structured-output handling, and failure paths."""

from __future__ import annotations

import pytest

from conftest import FakeAnthropicClient, make_classification
from specguard.classifier import (
    SYSTEM_PROMPT,
    TRUNCATION_MARKER,
    ClassifierError,
    build_user_message,
    classify,
)
from specguard.gitdiff import diff_from_contents
from specguard.models import ScopeLock


def big_lock() -> ScopeLock:
    return ScopeLock(
        goal="A focused project goal",
        scope_in=[f"in-scope topic number {i}" for i in range(40)],
        scope_out=[f"out-of-scope topic number {i}" for i in range(40)],
    )


class TestPromptAssembly:
    def test_scope_lock_never_truncated_even_when_diff_is(self):
        lock = big_lock()
        old = "line\n" * 2000
        new = "line\n" * 2000 + "EXTRA CONTENT " * 500 + "\n"
        changed = diff_from_contents("README.md", old, new)
        message, truncated = build_user_message(lock, changed, max_diff_chars=500)
        assert truncated
        assert TRUNCATION_MARKER in message
        # Every scope entry survives even though the diff was cut to 500 chars.
        for i in range(40):
            assert f"in-scope topic number {i}" in message
            assert f"out-of-scope topic number {i}" in message

    def test_small_files_sent_whole(self, sample_lock):
        changed = diff_from_contents("README.md", "old text\n", "new text\n")
        message, truncated = build_user_message(sample_lock, changed, 30000)
        assert not truncated
        assert "OLD FILE CONTENT:" in message
        assert "NEW FILE CONTENT:" in message

    def test_large_files_use_diff_with_capped_context(self, sample_lock):
        # >4K total content forces the diff path; unchanged context is capped.
        context = "".join(f"context line {i}\n" for i in range(400))
        old = context + "OLD SENTENCE\n"
        new = context + "NEW SENTENCE\n"
        changed = diff_from_contents("README.md", old, new)
        message, _ = build_user_message(sample_lock, changed, 30000)
        assert "OLD FILE CONTENT:" not in message
        assert "-OLD SENTENCE" in message
        assert "+NEW SENTENCE" in message

    def test_message_carries_path_and_change_kind(self, sample_lock):
        changed = diff_from_contents("AGENTS.md", "", "born\n")
        message, _ = build_user_message(sample_lock, changed, 30000)
        assert '<file path="AGENTS.md" change="added">' in message

    def test_system_prompt_calibration_is_byte_stable(self):
        # The eval harness calibrates against this exact wording; changing it
        # requires re-running tests/eval/run_eval.py (constitution gate).
        assert "When uncertain, prefer ADDITIVE." in SYSTEM_PROMPT
        assert "merely mentions an excluded topic" in SYSTEM_PROMPT


class TestClassify:
    def test_returns_schema_valid_classification(self, sample_lock, sample_config):
        client = FakeAnthropicClient(
            responses={"README.md": make_classification("ADDITIVE", 0.9)}
        )
        changed = diff_from_contents("README.md", "a\n", "b\n")
        result = classify(client, sample_lock, changed, sample_config)
        assert result.classification == "ADDITIVE"
        assert 0.0 <= result.confidence <= 1.0
        assert client.call_count == 1

    def test_request_shape_matches_contract(self, sample_lock, sample_config):
        client = FakeAnthropicClient()
        changed = diff_from_contents("README.md", "a\n", "b\n")
        classify(client, sample_lock, changed, sample_config)
        kwargs = client.calls[0].kwargs
        assert kwargs["model"] == sample_config.model
        assert kwargs["max_tokens"] == 4000
        assert kwargs["thinking"] == {"type": "adaptive"}
        system = kwargs["system"]
        assert system[0]["text"] == SYSTEM_PROMPT
        assert system[0]["cache_control"] == {"type": "ephemeral"}

    def test_reask_once_on_schema_failure(self, sample_lock, sample_config):
        good = make_classification("ADDITIVE", 0.9)
        client = FakeAnthropicClient(responses={"README.md": ["not valid json", good]})
        changed = diff_from_contents("README.md", "a\n", "b\n")
        result = classify(client, sample_lock, changed, sample_config)
        assert result.confidence == 0.9
        assert client.call_count == 2
        # The re-ask appends the validation error for the model to fix.
        reask = client.calls[1].kwargs["messages"]
        assert any("failed schema validation" in str(m.get("content")) for m in reask)

    def test_classifier_error_after_reask_exhaustion(self, sample_lock, sample_config):
        client = FakeAnthropicClient(responses={"README.md": ["bad", "still bad"]})
        changed = diff_from_contents("README.md", "a\n", "b\n")
        with pytest.raises(ClassifierError):
            classify(client, sample_lock, changed, sample_config)
        assert client.call_count == 2

    def test_api_error_wrapped_as_classifier_error(self, sample_lock, sample_config):
        client = FakeAnthropicClient(
            responses={"README.md": RuntimeError("api exploded")}
        )
        changed = diff_from_contents("README.md", "a\n", "b\n")
        with pytest.raises(ClassifierError):
            classify(client, sample_lock, changed, sample_config)

    def test_truncation_noted_in_explanation(self, sample_config):
        lock = big_lock()
        old = "line\n" * 2000
        new = "line\n" * 2000 + "EXTRA CONTENT\n" * 50
        changed = diff_from_contents("README.md", old, new)
        config = sample_config.model_copy(update={"max_diff_chars": 200})
        client = FakeAnthropicClient(
            responses={"README.md": make_classification("ADDITIVE", 0.8)}
        )
        result = classify(client, lock, changed, config)
        assert "truncated" in result.explanation
