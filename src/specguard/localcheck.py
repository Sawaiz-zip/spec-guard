"""Local check snapshots: what `specguard check` evaluates and against what.

Three modes (research.md 002 R4): worktree (default — what you'd push), staged
(the hook's view), and an explicit ref range (reproduces CI verdicts).

Governance config is ALWAYS read at the snapshot's baseline ref, never the
working tree (FR-010) — the local mirror of the merge gate's trusted-base rule:
editing your own lock must not change the verdict your PR would actually get.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from specguard.config import (
    CONFIG_PATH,
    LOCK_PATH,
    ROLES_PATH,
    parse_config,
    parse_lock,
    parse_roles,
)
from specguard.gitdiff import (
    ChangedFile,
    GitError,
    show_file,
    staged_changes,
    watched_changes,
    worktree_changes,
)
from specguard.models import Config, RolesConfig, ScopeLock

SnapshotMode = Literal["worktree", "staged", "range"]


@dataclass
class CheckSnapshot:
    mode: SnapshotMode
    base_ref: str
    base_sha: str  # short sha for display
    head_desc: str  # "working tree", "index", or a ref name
    changes: list[ChangedFile]


@dataclass
class BaselineGovernance:
    """Config loaded at the snapshot baseline; lock is None when unconfigured."""

    lock: ScopeLock | None
    config: Config
    roles: RolesConfig | None


def require_repo_with_head(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "not a git repository" in stderr:
            raise GitError(f"{repo_root} is not a git repository")
        raise GitError(
            "repository has no commits yet — commit your initial state first "
            "(SpecGuard compares against a committed baseline)"
        )
    return result.stdout.strip()


def _short_sha(repo_root: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"unknown ref '{ref}': {result.stderr.strip()}")
    return result.stdout.strip()


def resolve_snapshot(
    repo_root: Path,
    *,
    staged: bool = False,
    base: str | None = None,
    head: str | None = None,
    watch: list[str],
) -> CheckSnapshot:
    """Build the ChangedFile list for the selected snapshot mode."""
    require_repo_with_head(repo_root)

    if base is not None:
        head_ref = head or "HEAD"
        return CheckSnapshot(
            mode="range",
            base_ref=base,
            base_sha=_short_sha(repo_root, base),
            head_desc=head_ref,
            changes=watched_changes(repo_root, base, head_ref, watch),
        )
    if staged:
        return CheckSnapshot(
            mode="staged",
            base_ref="HEAD",
            base_sha=_short_sha(repo_root, "HEAD"),
            head_desc="index (staged changes)",
            changes=staged_changes(repo_root, watch),
        )
    return CheckSnapshot(
        mode="worktree",
        base_ref="HEAD",
        base_sha=_short_sha(repo_root, "HEAD"),
        head_desc="working tree",
        changes=worktree_changes(repo_root, watch),
    )


def load_baseline_governance(repo_root: Path, base_ref: str) -> BaselineGovernance:
    """Lock/config/roles parsed from the baseline commit (FR-010)."""
    source = f"{base_ref}:{{path}}"
    lock_text = show_file(repo_root, base_ref, LOCK_PATH)
    lock = (
        parse_lock(lock_text, source.format(path=LOCK_PATH))
        if lock_text is not None
        else None
    )
    config = parse_config(
        show_file(repo_root, base_ref, CONFIG_PATH), source.format(path=CONFIG_PATH)
    )
    roles = parse_roles(
        show_file(repo_root, base_ref, ROLES_PATH), source.format(path=ROLES_PATH)
    )
    return BaselineGovernance(lock=lock, config=config, roles=roles)
