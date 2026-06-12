"""Changed watched files and their diffs via the git CLI.

Diffs use `base...head` (merge-base form) so verdicts reflect only what the PR
introduces, matching what GitHub shows on the Files tab.
"""

from __future__ import annotations

import difflib
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from specguard.config import path_matches

ChangeKind = Literal["modified", "added", "deleted"]


@dataclass
class ChangedFile:
    path: str
    change: ChangeKind
    diff: str
    old_content: str
    new_content: str


class GitError(Exception):
    """git CLI failure — surfaced as a configuration/environment problem."""


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def show_file(repo_root: Path, sha: str, path: str) -> str | None:
    """File content at a commit, or None when the file doesn't exist there.

    Security note: governance config (.specguard/*) MUST be read at the PR
    base via this function, never from the checkout — the checkout contains
    the PR's own (attacker-controlled) version of the rules.
    """
    result = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def watched_changes(
    repo_root: Path, base_sha: str, head_sha: str, watch: list[str]
) -> list[ChangedFile]:
    """All files changed in base...head that match a watch glob."""
    name_status = _git(
        repo_root, "diff", "--name-status", "-M", f"{base_sha}...{head_sha}"
    )
    changes: list[ChangedFile] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        status = parts[0]
        # Renames/copies (R100, C75) list old and new path; govern the new one.
        path = parts[-1]
        if not any(path_matches(path, pattern) for pattern in watch):
            continue
        if status.startswith("A"):
            change: ChangeKind = "added"
        elif status.startswith("D"):
            change = "deleted"
        else:
            change = "modified"
        old_content = (
            "" if change == "added" else (show_file(repo_root, base_sha, path) or "")
        )
        new_content = (
            "" if change == "deleted" else (show_file(repo_root, head_sha, path) or "")
        )
        diff = _git(repo_root, "diff", f"{base_sha}...{head_sha}", "--", path)
        changes.append(
            ChangedFile(
                path=path,
                change=change,
                diff=diff,
                old_content=old_content,
                new_content=new_content,
            )
        )
    return changes


def _changes_from_name_status(
    repo_root: Path,
    name_status: str,
    watch: list[str],
    base_ref: str,
    new_content: Callable[[str], str],
) -> list[ChangedFile]:
    changes: list[ChangedFile] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        if not any(path_matches(path, pattern) for pattern in watch):
            continue
        old = "" if status.startswith("A") else (show_file(repo_root, base_ref, path) or "")
        new = "" if status.startswith("D") else new_content(path)
        changed = diff_from_contents(path, old, new)
        if status.startswith("A"):
            changed.change = "added"
        elif status.startswith("D"):
            changed.change = "deleted"
        else:
            changed.change = "modified"
        changes.append(changed)
    return changes


def staged_changes(repo_root: Path, watch: list[str]) -> list[ChangedFile]:
    """Watched files changed in the index vs HEAD (the pre-commit hook's view)."""
    name_status = _git(repo_root, "diff", "--cached", "--name-status", "-M", "HEAD")

    def index_content(path: str) -> str:
        result = subprocess.run(
            ["git", "show", f":{path}"], cwd=repo_root, capture_output=True, text=True
        )
        return result.stdout if result.returncode == 0 else ""

    return _changes_from_name_status(repo_root, name_status, watch, "HEAD", index_content)


def worktree_changes(repo_root: Path, watch: list[str]) -> list[ChangedFile]:
    """Watched files changed in the working tree vs HEAD (what you'd push)."""
    name_status = _git(repo_root, "diff", "--name-status", "-M", "HEAD")

    def filesystem_content(path: str) -> str:
        file_path = repo_root / path
        return file_path.read_text() if file_path.is_file() else ""

    return _changes_from_name_status(
        repo_root, name_status, watch, "HEAD", filesystem_content
    )


def diff_from_contents(path: str, old: str, new: str) -> ChangedFile:
    """Build a ChangedFile from raw contents (corpus/eval cases, tests)."""
    if old and not new:
        change: ChangeKind = "deleted"
    elif new and not old:
        change = "added"
    else:
        change = "modified"
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return ChangedFile(
        path=path, change=change, diff=diff, old_content=old, new_content=new
    )
