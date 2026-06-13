"""The single validator core (constitution III): per-file verdict pipeline.

Pipeline per watched changed file (plan.md D2):

    roles edit-rule check ──unauthorized──► BLOCK protected_violation  [no API call]
            │ authorized / no rule
            ▼
    classifier (Claude) ──ADDITIVE──► PASS (quiet log)
            │ SCOPE_CHANGE
            ├─ confidence < block_threshold ──► WARN
            └─ confidence ≥ block_threshold
                    ├─ no roles.yml (solo mode) ──► WARN
                    ├─ qualifying approval found ──► PASS
                    └─ none ──► BLOCK (lists required role(s))

Every surface (ci, future CLI/hook/MCP) consumes the Verdict list this module
produces and differs only in formatting.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from specguard.approvals import ApprovalsError, has_qualified_approval
from specguard.classifier import ClassifierError, classify
from specguard.gitdiff import ChangedFile
from specguard.models import (
    Approval,
    Classification,
    Config,
    PRContext,
    RolesConfig,
    ScopeLock,
    Verdict,
)
from specguard.roles import is_edit_authorized, required_approver_roles


def evaluate_pr(
    changed: list[ChangedFile],
    lock: ScopeLock,
    config: Config,
    roles_config: RolesConfig | None,
    pr: PRContext,
    client: Any,
    get_approvals: Callable[[], list[Approval]],
) -> list[Verdict]:
    """Produce one Verdict per watched changed file. Stateless and idempotent."""
    approvals: list[Approval] | None = None  # fetched lazily, at most once

    def approvals_once() -> list[Approval]:
        nonlocal approvals
        if approvals is None:
            try:
                approvals = get_approvals()
            except ApprovalsError:
                # Unable to read reviews — a blocked verdict stays blocked.
                approvals = []
        return approvals

    verdicts: list[Verdict] = []
    for changed_file in changed:
        verdicts.append(
            _evaluate_file(
                changed_file, lock, config, roles_config, pr, client, approvals_once
            )
        )
    return verdicts


def _evaluate_file(
    changed_file: ChangedFile,
    lock: ScopeLock,
    config: Config,
    roles_config: RolesConfig | None,
    pr: PRContext,
    client: Any,
    approvals_once: Callable[[], list[Approval]],
) -> Verdict:
    # Deterministic hard block (constitution V): path rule + platform identity,
    # decided before any API call.
    if roles_config is not None and not is_edit_authorized(
        pr.author_login, changed_file.path, roles_config
    ):
        return Verdict(
            file=changed_file.path,
            outcome="BLOCK",
            reason="protected_violation",
            classification=None,
        )

    try:
        classification = classify(client, lock, changed_file, config)
    except ClassifierError:
        outcome = "PASS" if config.on_error == "warn" else "BLOCK"
        return Verdict(
            file=changed_file.path,
            outcome=outcome,  # type: ignore[arg-type]
            reason="classifier_error",
            classification=None,
        )

    if classification.classification == "ADDITIVE":
        return Verdict(
            file=changed_file.path,
            outcome="PASS",
            reason="additive",
            classification=classification,
        )

    return _scope_change_verdict(
        changed_file, classification, config, roles_config, approvals_once
    )


def _scope_change_verdict(
    changed_file: ChangedFile,
    classification: Classification,
    config: Config,
    roles_config: RolesConfig | None,
    approvals_once: Callable[[], list[Approval]],
) -> Verdict:
    if classification.confidence < config.block_threshold:
        return Verdict(
            file=changed_file.path,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
        )

    # Solo mode: no roles.yml means there is nobody who could approve, so a
    # block would deadlock a team of one — warn with the full classification.
    if roles_config is None:
        return Verdict(
            file=changed_file.path,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
        )

    required = required_approver_roles(changed_file.path, roles_config)
    if not required:
        # Enforce mode but no scope_changes rule covers this path: blocking
        # would leave no approval escape hatch, so stay permissive (warn).
        return Verdict(
            file=changed_file.path,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
        )

    if has_qualified_approval(approvals_once(), required, roles_config):
        return Verdict(
            file=changed_file.path,
            outcome="PASS",
            reason="scope_change_approved",
            classification=classification,
            required_approver_roles=required,
        )

    return Verdict(
        file=changed_file.path,
        outcome="BLOCK",
        reason="scope_change_unapproved",
        classification=classification,
        required_approver_roles=required,
    )
