"""Changed watched files and their diffs via the git CLI.

Diffs use `base...head` (merge-base form) so verdicts reflect only what the PR
introduces, matching what GitHub shows on the Files tab.
"""

from __future__ import annotations

import difflib
import subprocess
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


def _show_file(repo_root: Path, sha: str, path: str) -> str:
    """File content at a commit; empty string when absent (added/deleted side)."""
    result = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


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
        old_content = "" if change == "added" else _show_file(repo_root, base_sha, path)
        new_content = "" if change == "deleted" else _show_file(repo_root, head_sha, path)
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
