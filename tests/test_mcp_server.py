"""MCP tool functions invoked directly with FakeAdapter — no transport, no key."""

from __future__ import annotations

import json

import pytest

from conftest import FakeAdapter, make_classification
from specguard import mcp_server
from specguard.gitdiff import GitError
from specguard.localreport import ADVISORY_NOTICE

LOCK = json.dumps(
    {"goal": "A CLI tool", "scope_in": ["tasks"], "scope_out": ["SaaS pricing"]}
)


@pytest.fixture
def configured_repo(git_repo):
    git_repo.write("README.md", "v1\n")
    git_repo.write(".specguard/lock.json", LOCK)
    git_repo.commit_all("base")
    return git_repo


ROLES_YML = (
    "roles:\n  architect: [alice]\n"
    "rules:\n"
    "  README.md:\n    scope_changes: {approve: architect}\n"
    "  CLAUDE.md:\n    edit: architect\n"
)


@pytest.fixture
def configured_repo_with_roles(git_repo):
    git_repo.write("README.md", "v1\n")
    git_repo.write(".specguard/lock.json", LOCK)
    git_repo.write(".specguard/roles.yml", ROLES_YML)
    git_repo.commit_all("base")
    return git_repo


class TestCheckPermission:
    def test_scope_change_allowed_for_role_member(self, configured_repo_with_roles):
        result = mcp_server.check_permission(
            "alice", "README.md", "scope-change",
            repo_root=configured_repo_with_roles.root,
        )
        assert result["roles_configured"] is True
        assert result["allowed"] is True
        assert result["governing_role"] == "architect"
        assert result["advisory"] is True

    def test_scope_change_denied_for_outsider(self, configured_repo_with_roles):
        result = mcp_server.check_permission(
            "mallory", "README.md", "scope-change",
            repo_root=configured_repo_with_roles.root,
        )
        assert result["allowed"] is False
        assert result["governing_role"] == "architect"

    def test_edit_allowed_and_denied(self, configured_repo_with_roles):
        root = configured_repo_with_roles.root
        assert mcp_server.check_permission(
            "alice", "CLAUDE.md", "edit", repo_root=root
        )["allowed"] is True
        assert mcp_server.check_permission(
            "mallory", "CLAUDE.md", "edit", repo_root=root
        )["allowed"] is False

    def test_no_roles_is_permissive(self, configured_repo):
        result = mcp_server.check_permission(
            "anyone", "README.md", "scope-change", repo_root=configured_repo.root
        )
        assert result["roles_configured"] is False
        assert result["allowed"] is True

    def test_invalid_change_class_errors(self, configured_repo_with_roles):
        result = mcp_server.check_permission(
            "alice", "README.md", "delete",
            repo_root=configured_repo_with_roles.root,
        )
        assert "error" in result


class TestRedirect:
    def _scope_change(self):
        return FakeAdapter(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.94, "HIGH", ["SaaS pricing"], "Added pricing"
                )
            }
        )

    def test_would_block_scope_change_includes_redirect(
        self, configured_repo_with_roles
    ):
        result = mcp_server.check_proposed_change(
            "README.md", "v1\n\n## Pricing\n$9/mo\n",
            repo_root=configured_repo_with_roles.root, adapter=self._scope_change(),
        )
        assert result["verdict"]["outcome"] == "BLOCK"
        redirect = result["redirect"]
        assert redirect["would_block"] is True
        assert redirect["required_roles"] == ["architect"]
        assert "proposal" in redirect["suggestion"]

    def test_additive_change_has_no_redirect(self, configured_repo_with_roles):
        result = mcp_server.check_proposed_change(
            "README.md", "v1 with a typo fixed\n",
            repo_root=configured_repo_with_roles.root, adapter=FakeAdapter(),
        )
        assert "redirect" not in result


class TestCheckProposedChange:
    def test_scope_change_verdict_with_advisory_flag(self, configured_repo):
        adapter = FakeAdapter(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.94, "HIGH", ["SaaS pricing"], "Added pricing"
                )
            }
        )
        result = mcp_server.check_proposed_change(
            "README.md", "v1\n\n## Pricing\n$9/mo\n",
            repo_root=configured_repo.root, adapter=adapter,
        )
        assert result["advisory"] is True
        assert result["notice"] == ADVISORY_NOTICE  # SC-006
        assert result["classified"] is True
        verdict = result["verdict"]
        assert verdict["classification"]["classification"] == "SCOPE_CHANGE"
        assert verdict["classification"]["out_of_scope_topics"] == ["SaaS pricing"]

    def test_additive_verdict(self, configured_repo):
        result = mcp_server.check_proposed_change(
            "README.md", "v1 with a typo fixed\n",
            repo_root=configured_repo.root, adapter=FakeAdapter(),
        )
        assert result["verdict"]["outcome"] == "PASS"
        assert result["verdict"]["reason"] == "additive"

    def test_new_file_classified_against_empty_baseline(self, configured_repo):
        adapter = FakeAdapter()
        result = mcp_server.check_proposed_change(
            "AGENTS.md", "# Agent rules\n",
            repo_root=configured_repo.root, adapter=adapter,
        )
        assert result["classified"] is True
        assert adapter.call_count == 1

    def test_non_watched_path_short_circuits(self, configured_repo):
        adapter = FakeAdapter()
        result = mcp_server.check_proposed_change(
            "src/main.py", "print('hello')\n",
            repo_root=configured_repo.root, adapter=adapter,
        )
        assert result["watched"] is False
        assert adapter.call_count == 0  # no classification, no API call
        assert result["advisory"] is True

    def test_unconfigured_repo_returns_hint(self, git_repo):
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        result = mcp_server.check_proposed_change(
            "README.md", "v2\n", repo_root=git_repo.root, adapter=FakeAdapter()
        )
        assert result["configured"] is False
        assert "specguard init" in result["hint"]

    def test_missing_key_returns_warn_shape(self, configured_repo, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = mcp_server.check_proposed_change(
            "README.md", "v2\n", repo_root=configured_repo.root  # no adapter
        )
        assert result["classified"] is False
        assert "could not classify" in result["detail"]

    def test_classifier_error_returns_warn_shape(self, configured_repo):
        from specguard.classifier import ClassifierError

        adapter = FakeAdapter(responses={"README.md": ClassifierError("down")})
        result = mcp_server.check_proposed_change(
            "README.md", "v2\n", repo_root=configured_repo.root, adapter=adapter
        )
        assert result["classified"] is False

    def test_not_a_repo_is_a_tool_error(self, tmp_path):
        with pytest.raises(GitError):
            mcp_server.check_proposed_change(
                "README.md", "x\n", repo_root=tmp_path, adapter=FakeAdapter()
            )

    def test_blocked_model_is_a_hard_error(self, configured_repo, git_repo):
        # Guardrail (001 R2a): advisory mode never soft-fails a blocked model.
        configured_repo.write(".specguard/config.yml", "model: claude-opus-4-8\n")
        configured_repo.commit_all("blocked model at baseline")
        from specguard.config import ConfigError

        with pytest.raises(ConfigError, match="blocked by project guardrail"):
            mcp_server.check_proposed_change(
                "README.md", "v2\n",
                repo_root=configured_repo.root, adapter=FakeAdapter(),
            )


class TestFrameTools:
    def test_get_scope_lock(self, configured_repo):
        result = mcp_server.get_scope_lock(repo_root=configured_repo.root)
        assert result["configured"] is True
        assert result["scope_lock"]["goal"] == "A CLI tool"
        assert result["advisory"] is True

    def test_list_watched_paths_solo(self, configured_repo):
        result = mcp_server.list_watched_paths(repo_root=configured_repo.root)
        assert "README.md" in result["watch"]
        assert result["enforce_mode"] is False

    def test_list_watched_paths_enforce(self, configured_repo):
        configured_repo.write(
            ".specguard/roles.yml", "roles:\n  architect: [alice]\n"
        )
        configured_repo.commit_all("roles")
        result = mcp_server.list_watched_paths(repo_root=configured_repo.root)
        assert result["enforce_mode"] is True

    def test_unconfigured_hints(self, git_repo):
        git_repo.write("x.txt", "x\n")
        git_repo.commit_all("base")
        assert mcp_server.get_scope_lock(repo_root=git_repo.root)["configured"] is False
        assert (
            mcp_server.list_watched_paths(repo_root=git_repo.root)["configured"] is False
        )
