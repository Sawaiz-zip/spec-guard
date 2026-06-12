"""Pydantic models: on-disk config shapes and in-memory verdict pipeline shapes.

Field shapes mirror specs/001-pr-spec-gate/data-model.md exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_WATCH = [
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "*.kilo",
    ".specguard/**",
]


class ScopeLock(BaseModel):
    """`.specguard/lock.json` — the locked project goal and scope."""

    goal: str = Field(min_length=1)
    scope_in: list[str]
    scope_out: list[str]
    locked_at: str | None = None
    locked_by: str | None = None


class Config(BaseModel):
    """`.specguard/config.yml` — all fields optional with defaults."""

    watch: list[str] = Field(default_factory=lambda: list(DEFAULT_WATCH))
    block_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    on_error: Literal["warn", "fail"] = "warn"
    model: str = "claude-opus-4-8"
    max_diff_chars: int = Field(default=30000, gt=0)


class ScopeChangeRule(BaseModel):
    """Semantic rule: which role's APPROVED review unblocks a SCOPE_CHANGE."""

    approve: str | None = None


class Rule(BaseModel):
    """Per-path-glob rule in roles.yml; most-specific match wins."""

    edit: str | None = None
    scope_changes: ScopeChangeRule | None = None


class RolesConfig(BaseModel):
    """`.specguard/roles.yml` — presence of this file is the enforce-mode switch."""

    roles: dict[str, list[str]]
    rules: dict[str, Rule] = Field(default_factory=dict)


class Classification(BaseModel):
    """The LLM output contract — see contracts/classifier.md."""

    classification: Literal["ADDITIVE", "SCOPE_CHANGE"]
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["LOW", "MEDIUM", "HIGH"]
    out_of_scope_topics: list[str]
    summary: str
    explanation: str


VerdictReason = Literal[
    "additive",
    "scope_change_approved",
    "scope_change_unapproved",
    "scope_change_low_confidence",
    "protected_violation",
    "classifier_error",
    "not_configured",
]


class Verdict(BaseModel):
    """Engine output — the shared contract every surface formats."""

    file: str
    outcome: Literal["PASS", "WARN", "BLOCK"]
    reason: VerdictReason
    classification: Classification | None = None
    required_approver_roles: list[str] = Field(default_factory=list)


class PRContext(BaseModel):
    """Assembled by ci.py from the GitHub event payload."""

    pr_number: int
    base_sha: str
    head_sha: str
    author_login: str
    is_fork: bool
    repo: str


class Approval(BaseModel):
    """Latest review per reviewer; qualifies iff state == APPROVED."""

    reviewer_login: str
    state: str
