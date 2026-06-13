"""Load and validate `.specguard/` configuration files.

Parsers take raw text so callers control WHERE config is read from. In CI the
governance config MUST come from the PR base commit (gitdiff.show_file) — the
checkout is the PR's own merge result, so reading it would let a PR rewrite
the rules it is judged by. The path-based loaders exist for trusted contexts
(tests, future local CLI on a clean working tree).

Missing lock → repo is unconfigured (caller decides: setup notice).
Missing config.yml → all defaults. Missing roles.yml → solo/warn mode.
Any parse or validation failure → ConfigError (the check fails loudly, exit 2).
"""

from __future__ import annotations

import json
import os
from fnmatch import fnmatchcase
from pathlib import Path

import yaml
from pydantic import ValidationError

from specguard.models import Config, RolesConfig, ScopeLock

SPECGUARD_DIR = ".specguard"
LOCK_FILE = "lock.json"
CONFIG_FILE = "config.yml"
ROLES_FILE = "roles.yml"

LOCK_PATH = f"{SPECGUARD_DIR}/{LOCK_FILE}"
CONFIG_PATH = f"{SPECGUARD_DIR}/{CONFIG_FILE}"
ROLES_PATH = f"{SPECGUARD_DIR}/{ROLES_FILE}"

MODEL_ENV_VAR = "SPECGUARD_MODEL"


class ConfigError(Exception):
    """Malformed or invalid .specguard configuration — always fails the check."""


def path_matches(path: str, pattern: str) -> bool:
    """fnmatch-style glob match for repo-relative paths.

    `*` crosses directory separators (so `.specguard/**` covers everything
    under the directory and `*.kilo` matches at any depth).
    """
    return fnmatchcase(path, pattern)


# ---------------------------------------------------------------------------
# Text-based parsers (source-agnostic)
# ---------------------------------------------------------------------------


def parse_lock(text: str, source: str = LOCK_PATH) -> ScopeLock:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{source}: invalid JSON — {exc}") from exc
    try:
        return ScopeLock.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{source}: {_first_error(exc)}") from exc


def parse_config(text: str | None, source: str = CONFIG_PATH) -> Config:
    raw: object = {}
    if text is not None:
        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{source}: invalid YAML — {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{source}: expected a mapping at the top level")
    try:
        config = Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{source}: {_first_error(exc)}") from exc

    model_override = os.environ.get(MODEL_ENV_VAR)
    if model_override:
        # Full re-validation (model_copy would skip the model guardrail).
        try:
            config = Config.model_validate(
                {**config.model_dump(), "model": model_override}
            )
        except ValidationError as exc:
            raise ConfigError(f"{MODEL_ENV_VAR}: {_first_error(exc)}") from exc
    return config


def parse_roles(text: str | None, source: str = ROLES_PATH) -> RolesConfig | None:
    """None when roles.yml is absent — that absence IS solo/warn mode."""
    if text is None:
        return None
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{source}: invalid YAML — {exc}") from exc
    try:
        roles_config = RolesConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{source}: {_first_error(exc)}") from exc

    known = set(roles_config.roles)
    for pattern, rule in roles_config.rules.items():
        referenced = [rule.edit] if rule.edit else []
        if rule.scope_changes and rule.scope_changes.approve:
            referenced.append(rule.scope_changes.approve)
        for role in referenced:
            if role not in known:
                raise ConfigError(
                    f"{source}: rule '{pattern}' references unknown role '{role}'"
                )
    return roles_config


# ---------------------------------------------------------------------------
# Path-based loaders (trusted working tree only)
# ---------------------------------------------------------------------------


def is_configured(repo_root: Path) -> bool:
    """True iff `.specguard/lock.json` exists — the activation switch."""
    return (repo_root / LOCK_PATH).is_file()


def load_lock(repo_root: Path) -> ScopeLock:
    lock_path = repo_root / LOCK_PATH
    try:
        text = lock_path.read_text()
    except FileNotFoundError as exc:
        raise ConfigError(f"{lock_path}: missing — run setup to create the scope lock") from exc
    return parse_lock(text, str(lock_path))


def load_config(repo_root: Path) -> Config:
    config_path = repo_root / CONFIG_PATH
    text = config_path.read_text() if config_path.is_file() else None
    return parse_config(text, str(config_path))


def load_roles(repo_root: Path) -> RolesConfig | None:
    roles_path = repo_root / ROLES_PATH
    text = roles_path.read_text() if roles_path.is_file() else None
    return parse_roles(text, str(roles_path))


def detect_framework(repo_root: Path) -> str | None:
    """Log-only seam for Phase 2 adapters (constitution II: no adapter behavior)."""
    if (repo_root / ".specify").is_dir():
        return "speckit"
    if (repo_root / "openspec").is_dir():
        return "openspec"
    return None


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    location = ".".join(str(part) for part in err["loc"]) or "(root)"
    return f"{location}: {err['msg']}"
