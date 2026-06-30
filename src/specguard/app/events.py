"""Webhook event → verdict, reusing the validator core against a temp checkout.

`evaluate` mirrors `ci.py._run` exactly — same config-at-base reads, same
governance overlay, same `evaluate_pr` — but classifies fork PRs (FR-001) and
returns a `CheckRunResult` instead of annotations. Every collaborator (clone,
token, approvals, authorship, adapter) is injectable so the whole pipeline is
unit-testable against a temp git repo with no live credentials.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specguard.app.checks import CheckRunResult
from specguard.app.commits import CommitAuthor, attribute_author
from specguard.app.repo import checkout as real_checkout
from specguard.classifier import ClassifierAdapter
from specguard.config import CONFIG_PATH, ROLES_PATH, parse_config, parse_roles
from specguard.engine import evaluate_pr
from specguard.gitdiff import show_file, watched_changes
from specguard.governance import resolve_lock
from specguard.models import Approval, PRContext, Verdict
from specguard.providers import make_adapter

# Webhook event names we act on; everything else is ignored (204).
HANDLED_EVENTS = {"pull_request", "pull_request_review", "check_run"}

SETUP_HINT = (
    "no .specguard/lock.json and no derivable Spec Kit/OpenSpec spec at the base — "
    "see https://github.com/Sawaiz-zip/spec-guard#quickstart"
)

CheckoutCM = Callable[[str, str, str, str], AbstractContextManager[Path]]
ApprovalsProvider = Callable[[PRContext, str], list[Approval]]
AttributeProvider = Callable[[str, int, str, str], CommitAuthor]


@dataclass
class PRWebhook:
    repo: str
    pr_number: int
    base_sha: str
    head_sha: str
    installation_id: int
    is_fork: bool
    opener_login: str


def parse_pr_webhook(event_name: str, payload: dict[str, Any]) -> PRWebhook | None:
    """Extract the PR coordinates from a handled event, or None to ignore it."""
    if event_name not in HANDLED_EVENTS:
        return None
    pr = payload.get("pull_request")
    if pr is None:  # check_run re-request carries the PR under check_run
        check_run = payload.get("check_run") or {}
        prs = check_run.get("pull_requests") or []
        pr = prs[0] if prs else None
    if not pr:
        return None
    base_repo = (pr.get("base") or {}).get("repo") or {}
    head_repo = (pr.get("head") or {}).get("repo") or {}
    repo = base_repo.get("full_name") or (payload.get("repository") or {}).get("full_name")
    installation = (payload.get("installation") or {}).get("id")
    if not repo or installation is None:
        return None
    return PRWebhook(
        repo=repo,
        pr_number=pr["number"],
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        installation_id=int(installation),
        is_fork=bool(head_repo.get("full_name") and head_repo["full_name"] != repo),
        opener_login=(pr.get("user") or {}).get("login", "(unknown)"),
    )


def _neutral(title: str, summary: str) -> CheckRunResult:
    return CheckRunResult(conclusion="neutral", title=title, summary=summary)


def _summary(verdicts: list[Verdict], source: str) -> str:
    lines = [f"Governance source: `{source}`.", ""]
    for v in verdicts:
        icon = {"BLOCK": "❌", "WARN": "⚠️", "PASS": "✅"}.get(v.outcome, "•")
        detail = v.classification.summary if v.classification else v.reason
        line = f"{icon} `{v.file}` — {v.reason}: {detail}"
        if v.required_approver_roles:
            line += f" (needs approval from {', '.join(v.required_approver_roles)})"
        lines.append(line)
    return "\n".join(lines)


def evaluate(
    pr: PRWebhook,
    token: str,
    *,
    checkout: CheckoutCM = real_checkout,
    adapter: ClassifierAdapter | None = None,
    approvals_provider: ApprovalsProvider | None = None,
    attribute: AttributeProvider = attribute_author,
) -> CheckRunResult:
    """Run the shared pipeline for one PR and render a check-run verdict.

    Fork PRs are classified (not skipped) — the token is the App's, held
    server-side (FR-001). Config/lock are read at the base ref (trusted-base
    rule). Errors degrade to a neutral conclusion, never an exception escaping
    to the webhook handler (FR-010).
    """
    with checkout(pr.repo, pr.base_sha, pr.head_sha, token) as repo_root:
        config = parse_config(
            show_file(repo_root, pr.base_sha, CONFIG_PATH),
            f"{pr.base_sha[:7]}:{CONFIG_PATH}",
        )
        roles_config = parse_roles(
            show_file(repo_root, pr.base_sha, ROLES_PATH),
            f"{pr.base_sha[:7]}:{ROLES_PATH}",
        )
        changed = watched_changes(repo_root, pr.base_sha, pr.head_sha, config.watch)
        if not changed:
            return CheckRunResult(
                conclusion="success",
                title="No watched spec files changed",
                summary="Nothing to govern in this pull request.",
            )

        lock, source = resolve_lock(repo_root, pr.base_sha, [c.path for c in changed])
        if lock is None:
            return _neutral("SpecGuard not configured", SETUP_HINT)

        # Attribute to the head-commit author so the propose-only agents rule
        # applies per actual author, not the PR opener (FR-005).
        author = attribute(pr.repo, pr.pr_number, pr.opener_login, token)
        pr_context = PRContext(
            pr_number=pr.pr_number,
            base_sha=pr.base_sha,
            head_sha=pr.head_sha,
            author_login=author.login,
            is_fork=pr.is_fork,
            repo=pr.repo,
        )

        run_adapter = adapter if adapter is not None else make_adapter(config)

        def get_approvals() -> list[Approval]:
            if approvals_provider is None:
                return []
            return approvals_provider(pr_context, token)

        verdicts = evaluate_pr(
            changed, lock, config, roles_config, pr_context, run_adapter, get_approvals
        )

    if any(v.outcome == "BLOCK" for v in verdicts):
        conclusion: Any = "failure"
        title = "Changes requested — unapproved scope change"
    elif any(v.reason == "classifier_error" for v in verdicts):
        conclusion = "neutral"
        title = "Could not classify — review manually"
    else:
        conclusion = "success"
        title = "All changes within locked scope"
    return CheckRunResult(conclusion=conclusion, title=title, summary=_summary(verdicts, source))
