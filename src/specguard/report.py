"""Verdict formatting: GitHub workflow-command annotations + step summary.

This module only formats — it never decides (constitution III). Additive
verdicts produce zero annotations and exactly one quiet summary line
(constitution IV).
"""

from __future__ import annotations

import os
from pathlib import Path

from specguard.models import PRContext, RolesConfig, Verdict
from specguard.roles import member_logins


def _annotation_text(verdict: Verdict, pr: PRContext, roles_config: RolesConfig | None) -> str:
    c = verdict.classification
    if verdict.reason == "protected_violation":
        return (
            f"Protected path: {pr.author_login} is not authorized to edit "
            f"{verdict.file} (deterministic rule, no classification performed)"
        )
    if verdict.reason == "classifier_error":
        return (
            f"SpecGuard could not classify {verdict.file} — review this change "
            "manually (classifier unavailable)"
        )
    assert c is not None
    parts = [
        f"SCOPE CHANGE ({c.confidence:.0%} confidence): {c.summary}",
    ]
    if c.out_of_scope_topics:
        parts.append(f"out-of-scope: [{', '.join(c.out_of_scope_topics)}]")
    if verdict.required_approver_roles:
        roles_text = ", ".join(
            _role_with_members(role, roles_config)
            for role in verdict.required_approver_roles
        )
        parts.append(f"requires approval from: {roles_text}")
    return " — ".join(parts)


def _role_with_members(role: str, roles_config: RolesConfig | None) -> str:
    if roles_config is None:
        return role
    members = ", ".join(f"@{login}" for login in member_logins(roles_config, role))
    return f"{members} ({role})" if members else role


def emit_annotations(
    verdicts: list[Verdict], pr: PRContext, roles_config: RolesConfig | None
) -> None:
    """Print ::error/::warning workflow commands. PASS verdicts are silent,
    except classifier_error under on_error=warn which must warn loudly (R4)."""
    for verdict in verdicts:
        text = None
        level = None
        if verdict.outcome == "BLOCK":
            level = "error"
            text = _annotation_text(verdict, pr, roles_config)
        elif verdict.outcome == "WARN" or verdict.reason == "classifier_error":
            level = "warning"
            text = _annotation_text(verdict, pr, roles_config)
        if level and text:
            print(f"::{level} file={verdict.file}::{_escape(text)}")


def notice(message: str) -> None:
    print(f"::notice::{_escape(message)}")


def warning(message: str) -> None:
    print(f"::warning::{_escape(message)}")


def _escape(text: str) -> str:
    # Workflow-command data: newlines and percent signs must be URL-escaped.
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def write_summary(
    verdicts: list[Verdict], pr: PRContext, roles_config: RolesConfig | None
) -> None:
    """Markdown verdict table to $GITHUB_STEP_SUMMARY (§F4 block format)."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    lines: list[str] = [_headline(verdicts), ""]
    for verdict in verdicts:
        lines.extend(_summary_block(verdict, pr, roles_config))
    Path(summary_path).open("a").write("\n".join(lines) + "\n")


def _headline(verdicts: list[Verdict]) -> str:
    if any(v.outcome == "BLOCK" for v in verdicts):
        return "❌ specguard — Changes requested"
    if any(v.outcome == "WARN" for v in verdicts):
        return "⚠️ specguard — Passed with warnings"
    return "✅ specguard — All changes within locked scope"


def _summary_block(
    verdict: Verdict, pr: PRContext, roles_config: RolesConfig | None
) -> list[str]:
    c = verdict.classification
    if verdict.reason == "additive":
        assert c is not None
        line = f"✅ `{verdict.file}` — ADDITIVE ({c.confidence:.0%}): {c.summary}"
        if c.confidence < 0.60:
            line += " (low confidence — a quick look is suggested)"
        return [line, ""]
    if verdict.reason == "scope_change_approved":
        assert c is not None
        return [
            f"✅ `{verdict.file}` — SCOPE CHANGE ({c.confidence:.0%}) approved by a "
            "qualifying review",
            "",
        ]
    if verdict.reason == "classifier_error":
        icon = "❌" if verdict.outcome == "BLOCK" else "⚠️"
        return [
            f"{icon} `{verdict.file}` — could not classify (classifier unavailable); "
            "review manually",
            "",
        ]
    if verdict.reason == "protected_violation":
        return [
            "❌ specguard — Changes requested",
            f"   📄 {verdict.file}",
            "   Protected path: only the authorized role may edit this file.",
            f"   {pr.author_login} does not have edit rights on this file.",
            "",
        ]
    assert c is not None
    icon = "❌" if verdict.outcome == "BLOCK" else "⚠️"
    header = "Changes requested" if verdict.outcome == "BLOCK" else "Warning"
    lines = [
        f"{icon} specguard — {header}",
        f"   📄 {verdict.file}",
        f"   Classification: SCOPE CHANGE (confidence {c.confidence:.0%})",
        f'   Added: "{c.summary}"',
        f"   Locked scope says: out-of-scope [{', '.join(c.out_of_scope_topics)}]",
    ]
    if verdict.required_approver_roles:
        roles_text = ", ".join(
            _role_with_members(role, roles_config)
            for role in verdict.required_approver_roles
        )
        lines.append(f"   Requires approval from: {roles_text}")
        lines.append(
            f"   {pr.author_login} does not have scope-change rights on this file."
        )
    lines.append("")
    return lines
