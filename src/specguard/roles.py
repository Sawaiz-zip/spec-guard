"""Role and path-rule resolution from `.specguard/roles.yml`.

Rule matching is fnmatch-style; when several patterns match a path the most
specific wins (most literal characters, then longest pattern). Unknown role
references are rejected at load time (config.load_roles), so resolution here
can trust the config.
"""

from __future__ import annotations

from specguard.config import path_matches
from specguard.models import RolesConfig, Rule


def member_logins(roles_config: RolesConfig, role: str) -> list[str]:
    return roles_config.roles.get(role, [])


def is_member(login: str, role: str, roles_config: RolesConfig) -> bool:
    members = member_logins(roles_config, role)
    return "*" in members or login in members


def resolve_roles(login: str, roles_config: RolesConfig) -> set[str]:
    """All roles the login belongs to (wildcard `*` membership included)."""
    return {
        role for role in roles_config.roles if is_member(login, role, roles_config)
    }


def _specificity(pattern: str) -> tuple[int, int]:
    literal_chars = sum(1 for ch in pattern if ch not in "*?[]")
    return (literal_chars, len(pattern))


def matching_rule(path: str, roles_config: RolesConfig) -> Rule | None:
    """The most-specific rule whose glob matches the path, or None."""
    candidates = [
        (pattern, rule)
        for pattern, rule in roles_config.rules.items()
        if path_matches(path, pattern)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: _specificity(item[0]), reverse=True)
    return candidates[0][1]


def is_edit_authorized(login: str, path: str, roles_config: RolesConfig) -> bool:
    """False only when an `edit:` rule covers the path and login is outside the role.

    This is the deterministic hard-block input (constitution V): path rules
    plus platform-verified identity, never the classifier.
    """
    rule = matching_rule(path, roles_config)
    if rule is None or rule.edit is None:
        return True
    return is_member(login, rule.edit, roles_config)


def required_approver_roles(path: str, roles_config: RolesConfig) -> list[str]:
    """Roles whose APPROVED review unblocks a SCOPE_CHANGE on this path."""
    rule = matching_rule(path, roles_config)
    if rule is None or rule.scope_changes is None or rule.scope_changes.approve is None:
        return []
    return [rule.scope_changes.approve]
