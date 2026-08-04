"""Monorepo multi-scope resolution (007 US2): group changed files by the
nearest-ancestor directory that declares an EXPLICIT `.specguard/lock.json`,
and load that scope's own lock/config/roles/regions independently. A repo
with no subdirectory scope behaves exactly as before — the existing
repo-root `resolve_lock` precedence (explicit lock > Spec Kit > OpenSpec >
plain) is the fallback scope (FR-003, fully backward compatible).

Spec Kit / OpenSpec derivation is intentionally repo-root-only — multi-scope
recognizes only explicit per-directory locks, avoiding the combinatorial
complexity of multi-framework derivation per subdirectory (research.md R4).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from specguard.config import (
    CONFIG_PATH,
    LOCK_PATH,
    REGIONS_PATH,
    ROLES_PATH,
    parse_config,
    parse_lock,
    parse_regions,
    parse_roles,
)
from specguard.gitdiff import ChangedFile, ref_has_path, show_file
from specguard.governance import GovernanceSource, resolve_lock
from specguard.models import Config, RegionsConfig, RolesConfig, ScopeLock


@dataclass
class Scope:
    """One governed area of the repo and the changed files nearest to it."""

    scope_dir: str  # "" = repo root
    lock: ScopeLock
    config: Config
    roles: RolesConfig | None
    regions: RegionsConfig | None
    source: GovernanceSource
    changed: list[ChangedFile] = field(default_factory=list)


def _ancestor_dirs(path: str) -> list[str]:
    """Repo-relative ancestor directories of `path`, nearest first, "" last."""
    parts = PurePosixPath(path).parts[:-1]
    dirs = ["/".join(parts[:depth]) for depth in range(len(parts), 0, -1)]
    dirs.append("")
    return dirs


def _nearest_explicit_scope(repo_root: Path, base_ref: str, file_path: str) -> str:
    for candidate in _ancestor_dirs(file_path):
        if not candidate:
            return ""  # repo root is always a valid fallback scope
        if ref_has_path(repo_root, base_ref, f"{candidate}/{LOCK_PATH}"):
            return candidate
    return ""


def _scoped(scope_dir: str, path: str) -> str:
    return f"{scope_dir}/{path}" if scope_dir else path


def rescope_changed_file(changed: ChangedFile, scope_dir: str) -> ChangedFile:
    """Strip the scope-dir prefix from a changed file's path before handing it
    to `evaluate_pr`, so a scope's own roles.yml/config.yml glob patterns are
    written as if that `.specguard/` were the repo root — the whole
    `.specguard/` directory becomes copy-paste portable between packages
    (FR-005, research.md R5)."""
    if not scope_dir:
        return changed
    prefix = f"{scope_dir}/"
    if not changed.path.startswith(prefix):
        return changed
    return dataclasses.replace(changed, path=changed.path[len(prefix) :])


def _load_scope(
    repo_root: Path, base_ref: str, scope_dir: str, changed_paths: list[str]
) -> Scope | None:
    """Load one scope's full governance (lock/config/roles/regions) at `base_ref`.

    `changed_paths` drives Spec Kit/OpenSpec derivation for the repo-root scope
    only. Returns None when the scope has no lock (unconfigured). A malformed
    lock raises ConfigError (propagated) — loud, never silently skipped.
    """
    lock: ScopeLock | None
    if scope_dir:
        lock_path = f"{scope_dir}/{LOCK_PATH}"
        lock = parse_lock(
            show_file(repo_root, base_ref, lock_path) or "", f"{base_ref}:{lock_path}"
        )
        source: GovernanceSource = "explicit-lock"
    else:
        lock, source = resolve_lock(repo_root, base_ref, changed_paths)
    if lock is None:
        return None

    config = parse_config(
        show_file(repo_root, base_ref, _scoped(scope_dir, CONFIG_PATH)),
        f"{base_ref}:{_scoped(scope_dir, CONFIG_PATH)}",
    )
    roles = parse_roles(
        show_file(repo_root, base_ref, _scoped(scope_dir, ROLES_PATH)),
        f"{base_ref}:{_scoped(scope_dir, ROLES_PATH)}",
    )
    regions = parse_regions(
        show_file(repo_root, base_ref, _scoped(scope_dir, REGIONS_PATH)),
        f"{base_ref}:{_scoped(scope_dir, REGIONS_PATH)}",
    )
    return Scope(scope_dir, lock, config, roles, regions, source, [])


def resolve_scope_for_path(
    repo_root: Path, base_ref: str, path: str
) -> Scope | None:
    """The single governing scope for one path — nearest-ancestor explicit lock,
    else the repo-root overlay. Lets the path-oriented MCP tools judge a change
    against its package's own lock instead of only the repo root (007 US2)."""
    scope_dir = _nearest_explicit_scope(repo_root, base_ref, path)
    return _load_scope(repo_root, base_ref, scope_dir, [path])


def resolve_scopes(
    repo_root: Path, base_ref: str, changed: list[ChangedFile]
) -> list[Scope]:
    """Group `changed` by nearest-ancestor explicit-lock scope and load each
    scope's full governance independently.

    A scope whose lock fails to parse raises ConfigError (propagated, not
    caught) — a malformed lock anywhere fails the WHOLE check loudly, never
    silently skips that scope.
    """
    grouped: dict[str, list[ChangedFile]] = {}
    for changed_file in changed:
        scope_dir = _nearest_explicit_scope(repo_root, base_ref, changed_file.path)
        grouped.setdefault(scope_dir, []).append(changed_file)

    scopes: list[Scope] = []
    for scope_dir, scope_changed in grouped.items():
        scope = _load_scope(
            repo_root, base_ref, scope_dir, [c.path for c in scope_changed]
        )
        if scope is None:
            continue  # unconfigured repo-root scope — caller emits the setup hint
        scopes.append(dataclasses.replace(scope, changed=scope_changed))
    return scopes
