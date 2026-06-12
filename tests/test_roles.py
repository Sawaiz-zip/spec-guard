"""Role resolution, glob rule matching, and roles.yml validation."""

from __future__ import annotations

import pytest

from specguard.config import ConfigError, load_roles
from specguard.models import RolesConfig
from specguard.roles import (
    is_edit_authorized,
    matching_rule,
    required_approver_roles,
    resolve_roles,
)


def roles(raw: dict) -> RolesConfig:
    return RolesConfig.model_validate(raw)


class TestGlobMatching:
    CONFIG = roles(
        {
            "roles": {"architect": ["alice"], "maintainers": ["bob"]},
            "rules": {
                "*.md": {"scope_changes": {"approve": "maintainers"}},
                "ARCHITECTURE.md": {"scope_changes": {"approve": "architect"}},
                ".specguard/**": {"edit": "architect"},
            },
        }
    )

    def test_exact_match(self):
        rule = matching_rule("ARCHITECTURE.md", self.CONFIG)
        assert rule is not None and rule.scope_changes.approve == "architect"

    def test_wildcard_match(self):
        rule = matching_rule("README.md", self.CONFIG)
        assert rule is not None and rule.scope_changes.approve == "maintainers"

    def test_most_specific_rule_wins(self):
        # ARCHITECTURE.md matches both "*.md" and the exact rule.
        rule = matching_rule("ARCHITECTURE.md", self.CONFIG)
        assert rule.scope_changes.approve == "architect"

    def test_directory_glob(self):
        rule = matching_rule(".specguard/roles.yml", self.CONFIG)
        assert rule is not None and rule.edit == "architect"

    def test_no_match(self):
        assert matching_rule("src/main.py", self.CONFIG) is None


class TestMembership:
    def test_resolve_roles(self):
        config = roles(
            {"roles": {"architect": ["alice"], "maintainers": ["alice", "bob"]}}
        )
        assert resolve_roles("alice", config) == {"architect", "maintainers"}
        assert resolve_roles("bob", config) == {"maintainers"}
        assert resolve_roles("mallory", config) == set()

    def test_wildcard_membership(self):
        config = roles(
            {
                "roles": {"everyone": ["*"], "architect": ["alice"]},
                "rules": {"README.md": {"edit": "everyone"}},
            }
        )
        assert resolve_roles("anyone-at-all", config) == {"everyone"}
        assert is_edit_authorized("anyone-at-all", "README.md", config)


class TestEditAuthorization:
    CONFIG = roles(
        {
            "roles": {"architect": ["alice"]},
            "rules": {".specguard/**": {"edit": "architect"}},
        }
    )

    def test_member_authorized(self):
        assert is_edit_authorized("alice", ".specguard/lock.json", self.CONFIG)

    def test_non_member_blocked(self):
        assert not is_edit_authorized("dev", ".specguard/lock.json", self.CONFIG)

    def test_unruled_path_always_authorized(self):
        assert is_edit_authorized("dev", "README.md", self.CONFIG)


class TestApproverRoles:
    def test_approver_role_for_ruled_path(self):
        config = roles(
            {
                "roles": {"architect": ["alice"]},
                "rules": {"README.md": {"scope_changes": {"approve": "architect"}}},
            }
        )
        assert required_approver_roles("README.md", config) == ["architect"]
        assert required_approver_roles("OTHER.md", config) == []


class TestRolesFileValidation:
    def test_unknown_role_in_edit_rule_raises(self, tmp_path):
        (tmp_path / ".specguard").mkdir()
        (tmp_path / ".specguard" / "roles.yml").write_text(
            "roles:\n  architect: [alice]\n"
            "rules:\n  README.md:\n    edit: ghosts\n"
        )
        with pytest.raises(ConfigError, match="unknown role 'ghosts'"):
            load_roles(tmp_path)

    def test_unknown_role_in_approve_rule_raises(self, tmp_path):
        (tmp_path / ".specguard").mkdir()
        (tmp_path / ".specguard" / "roles.yml").write_text(
            "roles:\n  architect: [alice]\n"
            "rules:\n  README.md:\n    scope_changes: {approve: phantoms}\n"
        )
        with pytest.raises(ConfigError, match="unknown role 'phantoms'"):
            load_roles(tmp_path)

    def test_missing_roles_file_is_solo_mode(self, tmp_path):
        (tmp_path / ".specguard").mkdir()
        assert load_roles(tmp_path) is None

    def test_valid_roles_file_loads(self, tmp_path):
        (tmp_path / ".specguard").mkdir()
        (tmp_path / ".specguard" / "roles.yml").write_text(
            "roles:\n  architect: [alice]\n"
            "rules:\n  .specguard/**:\n    edit: architect\n"
        )
        config = load_roles(tmp_path)
        assert config is not None
        assert config.roles["architect"] == ["alice"]
