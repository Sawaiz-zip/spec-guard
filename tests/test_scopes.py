"""Monorepo multi-scope: nearest-ancestor grouping, per-scope loading, rescoping."""

from __future__ import annotations

import json

import pytest

from specguard.config import ConfigError
from specguard.gitdiff import diff_from_contents
from specguard.scopes import rescope_changed_file, resolve_scopes

ROOT_LOCK = json.dumps({"goal": "Root goal", "scope_in": [], "scope_out": ["root-secret"]})
API_LOCK = json.dumps({"goal": "API service", "scope_in": [], "scope_out": ["billing"]})
WEB_LOCK = json.dumps({"goal": "Web app", "scope_in": [], "scope_out": ["payments"]})


def seed_monorepo(git_repo, root_lock: bool = True) -> str:
    if root_lock:
        git_repo.write(".specguard/lock.json", ROOT_LOCK)
    git_repo.write("packages/api/.specguard/lock.json", API_LOCK)
    git_repo.write("packages/web/.specguard/lock.json", WEB_LOCK)
    git_repo.write("packages/api/README.md", "API\n")
    git_repo.write("packages/web/README.md", "Web\n")
    git_repo.write("README.md", "Root\n")
    return git_repo.commit_all("seed")


class TestResolveScopes:
    def test_groups_by_nearest_ancestor_lock(self, git_repo):
        base = seed_monorepo(git_repo)
        changed = [
            diff_from_contents("packages/api/README.md", "API\n", "API v2\n"),
            diff_from_contents("packages/web/README.md", "Web\n", "Web v2\n"),
            diff_from_contents("README.md", "Root\n", "Root v2\n"),
        ]
        scopes = resolve_scopes(git_repo.root, base, changed)
        by_dir = {s.scope_dir: s for s in scopes}
        assert set(by_dir) == {"packages/api", "packages/web", ""}
        assert by_dir["packages/api"].lock.goal == "API service"
        assert by_dir["packages/web"].lock.goal == "Web app"
        assert by_dir[""].lock.goal == "Root goal"

    def test_each_scope_gets_only_its_own_files(self, git_repo):
        base = seed_monorepo(git_repo)
        changed = [
            diff_from_contents("packages/api/README.md", "API\n", "API v2\n"),
            diff_from_contents("packages/web/README.md", "Web\n", "Web v2\n"),
        ]
        scopes = resolve_scopes(git_repo.root, base, changed)
        by_dir = {s.scope_dir: [c.path for c in s.changed] for s in scopes}
        assert by_dir["packages/api"] == ["packages/api/README.md"]
        assert by_dir["packages/web"] == ["packages/web/README.md"]

    def test_no_subdirectory_scopes_is_single_repo_root_scope(self, git_repo):
        git_repo.write(".specguard/lock.json", ROOT_LOCK)
        git_repo.write("README.md", "v1\n")
        base = git_repo.commit_all("base")
        changed = [diff_from_contents("README.md", "v1\n", "v2\n")]
        scopes = resolve_scopes(git_repo.root, base, changed)
        assert len(scopes) == 1
        assert scopes[0].scope_dir == ""
        assert scopes[0].source == "explicit-lock"

    def test_file_outside_any_explicit_scope_falls_to_repo_root(self, git_repo):
        base = seed_monorepo(git_repo)
        changed = [diff_from_contents("docs/notes.md", "a\n", "b\n")]
        scopes = resolve_scopes(git_repo.root, base, changed)
        assert len(scopes) == 1
        assert scopes[0].scope_dir == ""

    def test_unconfigured_repo_root_with_no_subdirectory_scopes_yields_nothing(
        self, git_repo
    ):
        git_repo.write("README.md", "v1\n")
        base = git_repo.commit_all("base")
        changed = [diff_from_contents("README.md", "v1\n", "v2\n")]
        assert resolve_scopes(git_repo.root, base, changed) == []

    def test_malformed_scope_lock_raises_config_error(self, git_repo):
        git_repo.write("packages/api/.specguard/lock.json", "{not json")
        git_repo.write("packages/api/README.md", "v1\n")
        base = git_repo.commit_all("base")
        changed = [diff_from_contents("packages/api/README.md", "v1\n", "v2\n")]
        with pytest.raises(ConfigError):
            resolve_scopes(git_repo.root, base, changed)

    def test_scope_loads_its_own_config_and_roles(self, git_repo):
        git_repo.write("packages/api/.specguard/lock.json", API_LOCK)
        git_repo.write("packages/api/.specguard/config.yml", "block_threshold: 0.5\n")
        git_repo.write(
            "packages/api/.specguard/roles.yml",
            "roles:\n  api-team: [carol]\nrules:\n  README.md:\n"
            "    scope_changes: {approve: api-team}\n",
        )
        git_repo.write("packages/api/README.md", "v1\n")
        base = git_repo.commit_all("base")
        changed = [diff_from_contents("packages/api/README.md", "v1\n", "v2\n")]
        scopes = resolve_scopes(git_repo.root, base, changed)
        assert scopes[0].config.block_threshold == 0.5
        assert scopes[0].roles.roles["api-team"] == ["carol"]

    def test_scope_loads_its_own_regions(self, git_repo):
        git_repo.write("packages/api/.specguard/lock.json", API_LOCK)
        git_repo.write(
            "packages/api/.specguard/regions.yml",
            'files:\n  "README.md": ["Out of Scope"]\n',
        )
        git_repo.write("packages/api/README.md", "v1\n")
        base = git_repo.commit_all("base")
        changed = [diff_from_contents("packages/api/README.md", "v1\n", "v2\n")]
        scopes = resolve_scopes(git_repo.root, base, changed)
        assert scopes[0].regions.files == {"README.md": ["Out of Scope"]}

    def test_scope_with_no_own_config_uses_library_defaults(self, git_repo):
        base = seed_monorepo(git_repo)
        changed = [diff_from_contents("packages/api/README.md", "API\n", "API v2\n")]
        scopes = resolve_scopes(git_repo.root, base, changed)
        assert scopes[0].config.block_threshold == 0.75  # library default, not inherited


class TestRescopeChangedFile:
    def test_strips_scope_prefix(self):
        cf = diff_from_contents("packages/api/README.md", "a\n", "b\n")
        rescoped = rescope_changed_file(cf, "packages/api")
        assert rescoped.path == "README.md"

    def test_repo_root_scope_is_a_no_op(self):
        cf = diff_from_contents("README.md", "a\n", "b\n")
        rescoped = rescope_changed_file(cf, "")
        assert rescoped is cf

    def test_original_unaffected(self):
        cf = diff_from_contents("packages/api/README.md", "a\n", "b\n")
        rescope_changed_file(cf, "packages/api")
        assert cf.path == "packages/api/README.md"  # not mutated in place
