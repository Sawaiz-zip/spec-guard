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

from specguard.approvals import ApprovalsError, has_qualified_approval
from specguard.classifier import ClassifierAdapter, ClassifierError
from specguard.gitdiff import ChangedFile
from specguard.models import (
    Approval,
    Classification,
    Config,
    PRContext,
    RegionsConfig,
    RolesConfig,
    ScopeLock,
    Verdict,
)
from specguard.regions import split_into_regions
from specguard.roles import is_edit_authorized, required_approver_roles


def evaluate_pr(
    changed: list[ChangedFile],
    lock: ScopeLock,
    config: Config,
    roles_config: RolesConfig | None,
    pr: PRContext,
    adapter: ClassifierAdapter,
    get_approvals: Callable[[], list[Approval]],
    regions_config: RegionsConfig | None = None,
    scope: str = "",
) -> list[Verdict]:
    """Produce one or more Verdicts per watched changed file (007 US1: a
    region-restricted file may yield several — one per touched region, plus a
    quiet pass for any change outside every declared region). Stateless and
    idempotent."""
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
        verdicts.extend(
            _evaluate_changed_file(
                changed_file,
                lock,
                config,
                roles_config,
                pr,
                adapter,
                approvals_once,
                regions_config,
                scope,
            )
        )
    return verdicts


def _display_path(path: str, scope: str) -> str:
    return f"{scope}/{path}" if scope else path


def _evaluate_changed_file(
    changed_file: ChangedFile,
    lock: ScopeLock,
    config: Config,
    roles_config: RolesConfig | None,
    pr: PRContext,
    adapter: ClassifierAdapter,
    approvals_once: Callable[[], list[Approval]],
    regions_config: RegionsConfig | None,
    scope: str,
) -> list[Verdict]:
    # Deterministic hard block (constitution V): path rule + platform identity,
    # decided before any API call, on the WHOLE file — orthogonal to region
    # locking (a protected path stays protected regardless of regions).
    if roles_config is not None and not is_edit_authorized(
        pr.author_login, changed_file.path, roles_config
    ):
        return [
            Verdict(
                file=_display_path(changed_file.path, scope),
                outcome="BLOCK",
                reason="protected_violation",
                classification=None,
                scope=scope,
            )
        ]

    anchors = regions_config.files.get(changed_file.path) if regions_config else None
    if anchors and changed_file.change == "modified":
        region_changes, has_outside_change = split_into_regions(changed_file, anchors)
        # Role-rule lookups (required_approver_roles) use the ORIGINAL file path —
        # roles.yml is written against "ARCHITECTURE.md", not the synthetic
        # "ARCHITECTURE.md#Out of Scope" region path.
        verdicts = [
            _classify_and_verdict(
                region,
                lock,
                config,
                roles_config,
                adapter,
                approvals_once,
                scope,
                role_path=changed_file.path,
            )
            for region in region_changes
        ]
        if has_outside_change:
            verdicts.append(
                Verdict(
                    file=_display_path(changed_file.path, scope),
                    outcome="PASS",
                    reason="region_ungoverned",
                    classification=None,
                    scope=scope,
                )
            )
        return verdicts

    return [
        _classify_and_verdict(
            changed_file,
            lock,
            config,
            roles_config,
            adapter,
            approvals_once,
            scope,
            role_path=changed_file.path,
        )
    ]


def _classify_and_verdict(
    changed_file: ChangedFile,
    lock: ScopeLock,
    config: Config,
    roles_config: RolesConfig | None,
    adapter: ClassifierAdapter,
    approvals_once: Callable[[], list[Approval]],
    scope: str,
    role_path: str,
) -> Verdict:
    try:
        classification = adapter.classify(lock, changed_file, config)
    except ClassifierError:
        outcome = "PASS" if config.on_error == "warn" else "BLOCK"
        return Verdict(
            file=_display_path(changed_file.path, scope),
            outcome=outcome,  # type: ignore[arg-type]
            reason="classifier_error",
            classification=None,
            scope=scope,
        )

    if classification.classification == "ADDITIVE":
        return Verdict(
            file=_display_path(changed_file.path, scope),
            outcome="PASS",
            reason="additive",
            classification=classification,
            scope=scope,
        )

    return _scope_change_verdict(
        changed_file, classification, config, roles_config, approvals_once, scope, role_path
    )


def _scope_change_verdict(
    changed_file: ChangedFile,
    classification: Classification,
    config: Config,
    roles_config: RolesConfig | None,
    approvals_once: Callable[[], list[Approval]],
    scope: str,
    role_path: str,
) -> Verdict:
    file = _display_path(changed_file.path, scope)
    if classification.confidence < config.block_threshold:
        return Verdict(
            file=file,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
            scope=scope,
        )

    # Solo mode: no roles.yml means there is nobody who could approve, so a
    # block would deadlock a team of one — warn with the full classification.
    if roles_config is None:
        return Verdict(
            file=file,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
            scope=scope,
        )

    required = required_approver_roles(role_path, roles_config)
    if not required:
        # Enforce mode but no scope_changes rule covers this path: blocking
        # would leave no approval escape hatch, so stay permissive (warn).
        return Verdict(
            file=file,
            outcome="WARN",
            reason="scope_change_low_confidence",
            classification=classification,
            scope=scope,
        )

    if has_qualified_approval(approvals_once(), required, roles_config):
        return Verdict(
            file=file,
            outcome="PASS",
            reason="scope_change_approved",
            classification=classification,
            required_approver_roles=required,
            scope=scope,
        )

    return Verdict(
        file=file,
        outcome="BLOCK",
        reason="scope_change_unapproved",
        classification=classification,
        required_approver_roles=required,
        scope=scope,
    )
