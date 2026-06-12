"""Load and validate `.specguard/` configuration files.

`lock.json` missing → repo is unconfigured (caller decides: setup notice).
`config.yml` missing → all defaults. `roles.yml` missing → solo/warn mode.
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

MODEL_ENV_VAR = "SPECGUARD_MODEL"


class ConfigError(Exception):
    """Malformed or invalid .specguard configuration — always fails the check."""


def path_matches(path: str, pattern: str) -> bool:
    """fnmatch-style glob match for repo-relative paths.

    `*` crosses directory separators (so `.specguard/**` covers everything
    under the directory and `*.kilo` matches at any depth).
    """
    return fnmatchcase(path, pattern)


def is_configured(repo_root: Path) -> bool:
    """True iff `.specguard/lock.json` exists — the activation switch."""
    return (repo_root / SPECGUARD_DIR / LOCK_FILE).is_file()


def load_lock(repo_root: Path) -> ScopeLock:
    lock_path = repo_root / SPECGUARD_DIR / LOCK_FILE
    try:
        raw = json.loads(lock_path.read_text())
    except FileNotFoundError as exc:
        raise ConfigError(f"{lock_path}: missing — run setup to create the scope lock") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{lock_path}: invalid JSON — {exc}") from exc
    try:
        return ScopeLock.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{lock_path}: {_first_error(exc)}") from exc


def load_config(repo_root: Path) -> Config:
    config_path = repo_root / SPECGUARD_DIR / CONFIG_FILE
    raw: object = {}
    if config_path.is_file():
        try:
            raw = yaml.safe_load(config_path.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{config_path}: invalid YAML — {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"{config_path}: expected a mapping at the top level")
    try:
        config = Config.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{config_path}: {_first_error(exc)}") from exc

    model_override = os.environ.get(MODEL_ENV_VAR)
    if model_override:
        config = config.model_copy(update={"model": model_override})
    return config


def load_roles(repo_root: Path) -> RolesConfig | None:
    """None when roles.yml is absent — that absence IS solo/warn mode."""
    roles_path = repo_root / SPECGUARD_DIR / ROLES_FILE
    if not roles_path.is_file():
        return None
    try:
        raw = yaml.safe_load(roles_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{roles_path}: invalid YAML — {exc}") from exc
    try:
        roles_config = RolesConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{roles_path}: {_first_error(exc)}") from exc

    known = set(roles_config.roles)
    for pattern, rule in roles_config.rules.items():
        referenced = [rule.edit] if rule.edit else []
        if rule.scope_changes and rule.scope_changes.approve:
            referenced.append(rule.scope_changes.approve)
        for role in referenced:
            if role not in known:
                raise ConfigError(
                    f"{roles_path}: rule '{pattern}' references unknown role '{role}'"
                )
    return roles_config


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
