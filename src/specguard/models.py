"""Pydantic models: on-disk config shapes and in-memory verdict pipeline shapes.

Field shapes mirror specs/001-pr-spec-gate/data-model.md exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_WATCH = [
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "ARCHITECTURE.md",
    "*.kilo",
    ".specguard/**",
]

Provider = Literal["anthropic", "openai", "gemini", "openrouter"]

# Default backend + model. Sonnet 4.6 is the calibrated default (passed the
# golden-corpus gate 27/27, research.md R7a). Other providers are opt-in and
# require an explicit model — there is no sensible cross-provider default.
DEFAULT_PROVIDER: Provider = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-6"

# Guardrail: Opus 4.8 must never be invoked — not by default, not via
# config.yml, not via SPECGUARD_MODEL, not by the eval harness. Calibration
# showed Sonnet 4.6 classifies the golden corpus identically at ~6x lower
# cost (research.md R7a), so there is no quality case for the spend.
BLOCKED_MODEL_MARKERS = ("opus-4-8",)


def assert_model_allowed(model: str) -> None:
    """Raises ValueError when the model is on the blocklist."""
    for marker in BLOCKED_MODEL_MARKERS:
        if marker in model:
            raise ValueError(
                f"model '{model}' is blocked by project guardrail — "
                f"use {DEFAULT_MODEL} or another non-Opus-4.8 model"
            )


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
    provider: Provider = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    max_diff_chars: int = Field(default=30000, gt=0)

    @field_validator("model")
    @classmethod
    def _model_not_blocked(cls, value: str) -> str:
        assert_model_allowed(value)
        return value

    @model_validator(mode="after")
    def _provider_needs_explicit_model(self) -> Config:
        # The default model is Anthropic-specific; a non-Anthropic provider
        # left on that default would send a Claude model id to the wrong API.
        if self.provider != "anthropic" and self.model == DEFAULT_MODEL:
            raise ValueError(
                f"provider '{self.provider}' requires an explicit `model:` in "
                f".specguard/config.yml (the default '{DEFAULT_MODEL}' is "
                "Anthropic-only)"
            )
        return self


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
