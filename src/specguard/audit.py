"""Audit export (007 US3): a machine-readable record of verdicts + approvals,
derived entirely from data the gate already computes — no new datastore, no
secrets. Opt-in via `SPECGUARD_AUDIT_PATH` on the CI gate this phase (research
.md R7 — embedding the same payload into the GitHub App's check-run output is
a documented, deferred follow-up).

The audit timestamp is the PR's head commit time (already fetched for comment-
approval staleness), not a per-approval timestamp — see research.md R6.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from specguard.models import Approval, PRContext, Verdict


class AuditApproval(BaseModel):
    login: str
    state: str
    source: str


class AuditEntry(BaseModel):
    """One verdict, as a compliance-record row. No secrets, no API keys."""

    repo: str
    pr_number: int
    head_sha: str
    file: str
    scope: str
    outcome: str
    reason: str
    classification: str | None
    confidence: float | None
    required_approver_roles: list[str]
    approvals: list[AuditApproval]
    as_of: str | None


def build_audit_entries(
    verdicts: list[Verdict],
    approvals: list[Approval],
    pr: PRContext,
    as_of: str | None = None,
) -> list[AuditEntry]:
    """One AuditEntry per verdict. `approvals` is the full PR-level list (every
    review/comment seen, not just ones that happened to qualify) so a reviewer
    can independently correlate against roles.yml; deliberately decoupled from
    RolesConfig to keep this module simple (research.md)."""
    audit_approvals = [
        AuditApproval(login=a.reviewer_login, state=a.state, source=a.source)
        for a in approvals
    ]
    entries = []
    for v in verdicts:
        entries.append(
            AuditEntry(
                repo=pr.repo,
                pr_number=pr.pr_number,
                head_sha=pr.head_sha,
                file=v.file,
                scope=v.scope,
                outcome=v.outcome,
                reason=v.reason,
                classification=v.classification.classification if v.classification else None,
                confidence=v.classification.confidence if v.classification else None,
                required_approver_roles=v.required_approver_roles,
                approvals=audit_approvals,
                as_of=as_of,
            )
        )
    return entries


def export_audit_json(entries: list[AuditEntry]) -> str:
    return json.dumps([e.model_dump() for e in entries], indent=2)
