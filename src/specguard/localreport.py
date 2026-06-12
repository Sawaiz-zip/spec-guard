"""Terminal rendering for local verdicts (formatting only — constitution III).

The advisory notice appears in EVERY output, human and JSON (SC-006): local
surfaces preview the merge gate, they never enforce.
"""

from __future__ import annotations

import json

from specguard.localcheck import CheckSnapshot
from specguard.models import Verdict

ADVISORY_NOTICE = (
    "advisory only — local results do not enforce anything; the merge-time "
    "check on your default branch is the only enforcing layer."
)

COULD_NOT_CLASSIFY = "could not classify — advisory check skipped"


def would_block(verdicts: list[Verdict]) -> bool:
    return any(v.outcome == "BLOCK" for v in verdicts)


def _verdict_lines(verdict: Verdict) -> list[str]:
    c = verdict.classification
    if verdict.reason == "additive":
        assert c is not None
        return [f"✅ {verdict.file} — ADDITIVE ({c.confidence:.0%}): {c.summary}"]
    if verdict.reason == "classifier_error":
        return [f"⚠️  {verdict.file} — {COULD_NOT_CLASSIFY}"]
    if verdict.reason == "protected_violation":
        return [
            f"❌ {verdict.file} — protected path",
            "   the merge gate hard-blocks edits to this path unless the PR "
            "author's GitHub login is in the authorized role",
        ]
    assert c is not None
    icon = "❌" if verdict.outcome == "BLOCK" else "⚠️ "
    lines = [
        f"{icon} {verdict.file} — SCOPE CHANGE ({c.confidence:.0%}): {c.summary}"
    ]
    if c.out_of_scope_topics:
        lines.append(f"   out-of-scope: [{', '.join(c.out_of_scope_topics)}]")
    if verdict.required_approver_roles:
        roles = ", ".join(verdict.required_approver_roles)
        lines.append(f"   would block until {roles} approves (merge-time check)")
    if verdict.reason == "scope_change_approved":
        lines.append("   a qualifying approval exists on the PR")
    return lines


def render(verdicts: list[Verdict], snapshot: CheckSnapshot) -> str:
    header = (
        f"specguard check — baseline {snapshot.base_ref} ({snapshot.base_sha}) "
        f"vs {snapshot.head_desc}"
    )
    lines = [header, ""]
    if not verdicts:
        lines.append("no watched spec files changed in this snapshot")
    for verdict in verdicts:
        lines.extend(_verdict_lines(verdict))
    lines.extend(["", f"⚠ {ADVISORY_NOTICE}"])
    return "\n".join(lines)


def render_json(verdicts: list[Verdict], snapshot: CheckSnapshot) -> str:
    return json.dumps(
        {
            "baseline": f"{snapshot.base_ref} ({snapshot.base_sha})",
            "compared_to": snapshot.head_desc,
            "advisory": True,
            "notice": ADVISORY_NOTICE,
            "would_block": would_block(verdicts),
            "verdicts": [v.model_dump() for v in verdicts],
        },
        indent=2,
    )
