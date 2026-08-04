"""Terminal rendering for local verdicts (formatting only — constitution III).

The advisory notice appears in EVERY output, human and JSON (SC-006): local
surfaces preview the merge gate, they never enforce.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from specguard.governance import GovernanceSource
from specguard.models import Verdict

if TYPE_CHECKING:
    from specguard.localcheck import CheckSnapshot

# Human-readable label for each governance source (SC-005).
SOURCE_LABEL: dict[GovernanceSource, str] = {
    "explicit-lock": "explicit lock (.specguard/lock.json)",
    "spec-kit": "Spec Kit (.specify/)",
    "openspec": "OpenSpec (openspec/)",
    "plain": "plain",
}

ADVISORY_NOTICE = (
    "advisory only — local results do not enforce anything; the merge-time "
    "check on your default branch is the only enforcing layer."
)

COULD_NOT_CLASSIFY = "could not classify — advisory check skipped"


def would_block(verdicts: list[Verdict]) -> bool:
    return any(v.outcome == "BLOCK" for v in verdicts)


def _display_path(verdict: Verdict) -> str:
    """The changed file's repo-relative path. In a monorepo the engine sees a
    scope-relative path (the scope prefix is stripped before classification), so
    re-attach the scope directory for an unambiguous, clickable path."""
    return f"{verdict.scope}/{verdict.file}" if verdict.scope else verdict.file


def _verdict_lines(verdict: Verdict) -> list[str]:
    c = verdict.classification
    path = _display_path(verdict)
    if verdict.reason == "additive":
        assert c is not None
        return [f"✅ {path} — ADDITIVE ({c.confidence:.0%}): {c.summary}"]
    if verdict.reason == "classifier_error":
        return [f"⚠️  {path} — {COULD_NOT_CLASSIFY}"]
    if verdict.reason == "protected_violation":
        return [
            f"❌ {path} — protected path",
            "   the merge gate hard-blocks edits to this path unless the PR "
            "author's GitHub login is in the authorized role",
        ]
    if verdict.reason == "region_ungoverned":
        return [f"✅ {path} — outside the locked region(s); not classified"]
    assert c is not None
    icon = "❌" if verdict.outcome == "BLOCK" else "⚠️ "
    lines = [
        f"{icon} {path} — SCOPE CHANGE ({c.confidence:.0%}): {c.summary}"
    ]
    if c.out_of_scope_topics:
        lines.append(f"   out-of-scope: [{', '.join(c.out_of_scope_topics)}]")
    if verdict.required_approver_roles:
        roles = ", ".join(verdict.required_approver_roles)
        lines.append(f"   would block until {roles} approves (merge-time check)")
    if verdict.reason == "scope_change_approved":
        lines.append("   a qualifying approval exists on the PR")
    return lines


def _source_lines(sources: dict[str, GovernanceSource]) -> list[str]:
    """One 'Governance source:' line for a single scope, or a labeled list when a
    monorepo PR spans several scopes (007 US2)."""
    if len(sources) <= 1:
        default: GovernanceSource = "plain"
        source = next(iter(sources.values()), default)
        return [f"Governance source: {SOURCE_LABEL[source]}"]
    lines = ["Governance sources:"]
    for scope_dir, source in sorted(sources.items()):
        lines.append(f"  {scope_dir or '(repo root)'}: {SOURCE_LABEL[source]}")
    return lines


def render(
    verdicts: list[Verdict],
    snapshot: CheckSnapshot,
    sources: dict[str, GovernanceSource] | None = None,
) -> str:
    header = (
        f"specguard check — baseline {snapshot.base_ref} ({snapshot.base_sha}) "
        f"vs {snapshot.head_desc}"
    )
    lines = [header, *_source_lines(sources or {}), ""]
    if not verdicts:
        lines.append("no watched spec files changed in this snapshot")
    for verdict in verdicts:
        lines.extend(_verdict_lines(verdict))
    lines.extend(["", f"⚠ {ADVISORY_NOTICE}"])
    return "\n".join(lines)


def render_json(
    verdicts: list[Verdict],
    snapshot: CheckSnapshot,
    sources: dict[str, GovernanceSource] | None = None,
) -> str:
    sources = sources or {}
    return json.dumps(
        {
            "baseline": f"{snapshot.base_ref} ({snapshot.base_sha})",
            "compared_to": snapshot.head_desc,
            # Back-compat: the single (or repo-root) source stays under the
            # original key; the full per-scope map is added alongside it.
            "governance_source": sources.get("", next(iter(sources.values()), "plain")),
            "governance_sources": sources,
            "advisory": True,
            "notice": ADVISORY_NOTICE,
            "would_block": would_block(verdicts),
            "verdicts": [v.model_dump() for v in verdicts],
        },
        indent=2,
    )
