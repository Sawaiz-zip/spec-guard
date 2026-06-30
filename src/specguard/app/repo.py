"""Shallow checkout of a PR's base+head into a temp dir using the install token.

The App has no local checkout, but the validator core reads files via `git show
base:path`. Cloning base+head lets the App reuse `resolve_lock`/`watched_changes`/
`evaluate_pr` verbatim (plan.md D1) — the trusted-base rule and governance overlay
hold identically. The token is used only for the clone URL and never written to disk.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class CheckoutError(Exception):
    """Could not materialize the PR's base+head locally."""


def _git(repo_root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True
    )
    if result.returncode != 0:
        # Redact a token that may appear in a remote URL in the error text.
        stderr = result.stderr.replace("x-access-token:", "x-access-token:***@").strip()
        raise CheckoutError(f"git {args[0]}: {stderr}")


@contextmanager
def checkout(repo: str, base_sha: str, head_sha: str, token: str) -> Iterator[Path]:
    """Yield a temp repo root containing both `base_sha` and `head_sha`.

    Fetched by SHA so the working tree need not be checked out to any branch;
    the core reads both revisions via `git show`. The temp dir is always removed.
    """
    tmp = Path(tempfile.mkdtemp(prefix="specguard-app-"))
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    try:
        _git(tmp, "init", "-q")
        _git(tmp, "remote", "add", "origin", url)
        # Depth 1 per SHA: enough for `git show base:path` and base...head diffs.
        _git(tmp, "fetch", "-q", "--depth", "1", "origin", base_sha, head_sha)
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
