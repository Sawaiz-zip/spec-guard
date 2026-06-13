"""Snapshot resolution and baseline-trusted governance loading."""

from __future__ import annotations

import json

import pytest

from specguard.config import ConfigError
from specguard.gitdiff import GitError
from specguard.localcheck import load_baseline_governance, resolve_snapshot

WATCH = ["README.md", ".specguard/**"]

LOCK = json.dumps(
    {"goal": "A CLI tool", "scope_in": ["tasks"], "scope_out": ["SaaS pricing"]}
)


def seeded(git_repo):
    git_repo.write("README.md", "v1\n")
    git_repo.write(".specguard/lock.json", LOCK)
    git_repo.commit_all("base")
    return git_repo


class TestSnapshots:
    def test_worktree_mode_sees_unstaged_edits(self, git_repo):
        repo = seeded(git_repo)
        repo.write("README.md", "v2 unstaged\n")
        snapshot = resolve_snapshot(repo.root, watch=WATCH)
        assert snapshot.mode == "worktree"
        assert snapshot.base_ref == "HEAD"
        assert [c.path for c in snapshot.changes] == ["README.md"]
        assert snapshot.changes[0].new_content == "v2 unstaged\n"

    def test_staged_mode_sees_only_the_index(self, git_repo):
        repo = seeded(git_repo)
        repo.write("README.md", "v2 staged\n")
        repo.git("add", "README.md")
        repo.write("README.md", "v3 unstaged on top\n")
        snapshot = resolve_snapshot(repo.root, staged=True, watch=WATCH)
        assert snapshot.mode == "staged"
        assert snapshot.changes[0].new_content == "v2 staged\n"  # index, not worktree

    def test_staged_mode_empty_when_nothing_staged(self, git_repo):
        repo = seeded(git_repo)
        repo.write("README.md", "v2 unstaged\n")
        snapshot = resolve_snapshot(repo.root, staged=True, watch=WATCH)
        assert snapshot.changes == []

    def test_range_mode_reproduces_committed_diffs(self, git_repo):
        repo = seeded(git_repo)
        base = repo.git("rev-parse", "HEAD")
        repo.write("README.md", "v2 committed\n")
        repo.commit_all("edit")
        snapshot = resolve_snapshot(repo.root, base=base, watch=WATCH)
        assert snapshot.mode == "range"
        assert snapshot.base_ref == base
        assert snapshot.changes[0].new_content == "v2 committed\n"

    def test_added_and_deleted_in_worktree(self, git_repo):
        repo = seeded(git_repo)
        repo.write(".specguard/roles.yml", "roles: {architect: [a]}\n")
        repo.git("add", "-A")  # adds must be staged to appear in git diff HEAD
        repo.delete("README.md")
        snapshot = resolve_snapshot(repo.root, watch=WATCH)
        by_path = {c.path: c for c in snapshot.changes}
        assert by_path[".specguard/roles.yml"].change == "added"
        assert by_path["README.md"].change == "deleted"

    def test_not_a_repo_raises_clear_error(self, tmp_path):
        with pytest.raises(GitError, match="not a git repository"):
            resolve_snapshot(tmp_path, watch=WATCH)

    def test_no_commits_raises_clear_error(self, git_repo):
        with pytest.raises(GitError, match="no commits"):
            resolve_snapshot(git_repo.root, watch=WATCH)

    def test_unknown_base_ref_raises(self, git_repo):
        repo = seeded(git_repo)
        with pytest.raises(GitError, match="unknown ref"):
            resolve_snapshot(repo.root, base="no-such-ref", watch=WATCH)


class TestBaselineGovernance:
    def test_loads_lock_config_roles_from_baseline(self, git_repo):
        repo = seeded(git_repo)
        governance = load_baseline_governance(repo.root, "HEAD")
        assert governance.lock is not None
        assert governance.lock.goal == "A CLI tool"
        assert governance.roles is None  # solo mode

    def test_unconfigured_baseline_gives_none_lock(self, git_repo):
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        governance = load_baseline_governance(git_repo.root, "HEAD")
        assert governance.lock is None

    def test_locally_edited_lock_does_not_change_baseline_read(self, git_repo):
        """FR-010 — the local mirror of the Phase 0 E2E security finding."""
        repo = seeded(git_repo)
        repo.write(
            ".specguard/lock.json",
            json.dumps({"goal": "totally different", "scope_in": [], "scope_out": []}),
        )
        governance = load_baseline_governance(repo.root, "HEAD")
        assert governance.lock is not None
        assert governance.lock.goal == "A CLI tool"  # committed baseline wins

    def test_malformed_baseline_lock_raises_config_error(self, git_repo):
        git_repo.write(".specguard/lock.json", "{nope")
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        with pytest.raises(ConfigError, match="invalid JSON"):
            load_baseline_governance(git_repo.root, "HEAD")
