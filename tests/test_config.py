"""Config loading: defaults, validation failures, env overrides."""

from __future__ import annotations

import json

import pytest

from specguard.config import (
    ConfigError,
    detect_framework,
    is_configured,
    load_config,
    load_lock,
    path_matches,
)
from specguard.models import DEFAULT_WATCH


def write_specguard(tmp_path, name: str, content: str) -> None:
    (tmp_path / ".specguard").mkdir(exist_ok=True)
    (tmp_path / ".specguard" / name).write_text(content)


VALID_LOCK = json.dumps(
    {"goal": "Build a thing", "scope_in": ["a"], "scope_out": ["b"]}
)


class TestLock:
    def test_valid_lock_loads(self, tmp_path):
        write_specguard(tmp_path, "lock.json", VALID_LOCK)
        lock = load_lock(tmp_path)
        assert lock.goal == "Build a thing"
        assert lock.scope_out == ["b"]
        assert is_configured(tmp_path)

    def test_missing_lock_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="missing"):
            load_lock(tmp_path)
        assert not is_configured(tmp_path)

    def test_invalid_json_raises(self, tmp_path):
        write_specguard(tmp_path, "lock.json", "{nope")
        with pytest.raises(ConfigError, match="invalid JSON"):
            load_lock(tmp_path)

    def test_missing_goal_raises(self, tmp_path):
        write_specguard(
            tmp_path, "lock.json", json.dumps({"scope_in": [], "scope_out": []})
        )
        with pytest.raises(ConfigError, match="goal"):
            load_lock(tmp_path)

    def test_empty_goal_raises(self, tmp_path):
        write_specguard(
            tmp_path,
            "lock.json",
            json.dumps({"goal": "", "scope_in": [], "scope_out": []}),
        )
        with pytest.raises(ConfigError):
            load_lock(tmp_path)


class TestConfig:
    def test_missing_file_gives_all_defaults(self, tmp_path):
        config = load_config(tmp_path)
        assert config.watch == DEFAULT_WATCH
        assert config.block_threshold == 0.75
        assert config.on_error == "warn"
        assert config.model == "claude-opus-4-8"
        assert config.max_diff_chars == 30000

    def test_partial_config_fills_defaults(self, tmp_path):
        write_specguard(tmp_path, "config.yml", "block_threshold: 0.9\n")
        config = load_config(tmp_path)
        assert config.block_threshold == 0.9
        assert config.on_error == "warn"  # default preserved

    def test_malformed_yaml_raises(self, tmp_path):
        write_specguard(tmp_path, "config.yml", "watch: [unclosed\n")
        with pytest.raises(ConfigError, match="invalid YAML"):
            load_config(tmp_path)

    def test_non_mapping_yaml_raises(self, tmp_path):
        write_specguard(tmp_path, "config.yml", "- just\n- a list\n")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(tmp_path)

    def test_invalid_on_error_value_raises(self, tmp_path):
        write_specguard(tmp_path, "config.yml", "on_error: explode\n")
        with pytest.raises(ConfigError, match="on_error"):
            load_config(tmp_path)

    def test_model_env_override(self, tmp_path, monkeypatch):
        write_specguard(tmp_path, "config.yml", "model: claude-haiku-4-5-20251001\n")
        monkeypatch.setenv("SPECGUARD_MODEL", "claude-sonnet-4-6")
        assert load_config(tmp_path).model == "claude-sonnet-4-6"


class TestFrameworkDetection:
    def test_speckit(self, tmp_path):
        (tmp_path / ".specify").mkdir()
        assert detect_framework(tmp_path) == "speckit"

    def test_openspec(self, tmp_path):
        (tmp_path / "openspec").mkdir()
        assert detect_framework(tmp_path) == "openspec"

    def test_plain(self, tmp_path):
        assert detect_framework(tmp_path) is None


class TestPathMatching:
    @pytest.mark.parametrize(
        ("path", "pattern", "expected"),
        [
            ("README.md", "README.md", True),
            (".specguard/roles.yml", ".specguard/**", True),
            (".specguard/deep/nested.yml", ".specguard/**", True),
            ("notes.kilo", "*.kilo", True),
            ("docs/notes.kilo", "*.kilo", True),
            ("src/main.py", "README.md", False),
            ("README.md.bak", "README.md", False),
        ],
    )
    def test_patterns(self, path, pattern, expected):
        assert path_matches(path, pattern) is expected
