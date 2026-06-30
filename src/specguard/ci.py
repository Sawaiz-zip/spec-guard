"""GitHub Actions entrypoint: `python -m specguard.ci`.

Exit codes: 0 = no BLOCK verdicts, 1 = at least one BLOCK (fails the required
check), 2 = configuration error (always loud — constitution: config errors
fail the check).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from specguard import report
from specguard.approvals import (
    fetch_approvals,
    fetch_comment_approvals,
    fetch_commit_time,
)
from specguard.audit import build_audit_entries, export_audit_json
from specguard.classifier import AnthropicAdapter
from specguard.config import CONFIG_PATH, ConfigError, parse_config
from specguard.engine import evaluate_pr
from specguard.gitdiff import GitError, show_file, watched_changes
from specguard.models import Approval, PRContext, RolesConfig, Verdict
from specguard.providers import make_adapter
from specguard.scopes import rescope_changed_file, resolve_scopes

SETUP_HINT = (
    "SpecGuard is installed but this repository has no .specguard/lock.json — "
    "create one to lock your project's goal and scope. "
    "See https://github.com/Sawaiz-zip/spec-guard#quickstart"
)


def _pr_context(event: dict[str, Any]) -> PRContext | None:
    pr = event.get("pull_request")
    if not pr:
        return None
    base_repo = (pr.get("base") or {}).get("repo") or {}
    head_repo = (pr.get("head") or {}).get("repo") or {}
    repo = os.environ.get("GITHUB_REPOSITORY") or base_repo.get("full_name", "")
    return PRContext(
        pr_number=pr["number"],
        base_sha=pr["base"]["sha"],
        head_sha=pr["head"]["sha"],
        author_login=pr["user"]["login"],
        is_fork=head_repo.get("full_name") != base_repo.get("full_name"),
        repo=repo,
    )


def main(client: Any | None = None, repo_root: Path | None = None) -> int:
    try:
        return _run(client, repo_root or Path.cwd())
    except ConfigError as exc:
        print(f"::error::SpecGuard configuration error: {exc}")
        return 2
    except GitError as exc:
        print(
            f"::error::SpecGuard git error: {exc} "
            "(is the checkout fetch-depth: 0?)"
        )
        return 2


def _run(client: Any | None, repo_root: Path) -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("::error::GITHUB_EVENT_PATH is not set — SpecGuard must run in Actions")
        return 2
    event = json.loads(Path(event_path).read_text())

    pr = _pr_context(event)
    if pr is None:
        report.notice("SpecGuard: not a pull_request event — nothing to do")
        return 0

    if pr.is_fork:
        report.warning(
            "SpecGuard skipped: secrets are unavailable on fork PRs, so this "
            "change was not classified — review spec-file changes manually"
        )
        return 0

    # Governance config is read at the PR BASE, never from the checkout: the
    # checkout is the PR's own merge result, so trusting it would let any PR
    # rewrite the rules it is judged by (verified live in sandbox E2E). Only
    # `watch` is resolved from the repo-root config — a deliberate phase-1
    # simplification for multi-scope repos (007 research.md R4 family);
    # everything else (lock, threshold, roles, regions) is per-scope below.
    config = parse_config(
        show_file(repo_root, pr.base_sha, CONFIG_PATH), f"{pr.base_sha[:7]}:{CONFIG_PATH}"
    )

    changed = watched_changes(repo_root, pr.base_sha, pr.head_sha, config.watch)
    if not changed:
        report.notice("SpecGuard: no watched spec files changed in this PR")
        return 0

    # Group changed files by nearest-ancestor explicit-lock scope (007 US2);
    # a repo with no subdirectory scopes yields exactly one repo-root scope
    # using the existing governance overlay (explicit lock > Spec Kit >
    # OpenSpec > plain) — fully backward compatible (FR-003).
    scopes = resolve_scopes(repo_root, pr.base_sha, changed)
    if not scopes:
        report.notice(SETUP_HINT)
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    approvals_cache: list[Approval] | None = None

    def get_approvals() -> list[Approval]:
        # Approvals come from two platform-native sources, evaluated identically
        # by the engine: native reviews AND `/specguard approve` comments posted
        # at/after the head commit (FR-005, FR-010). A failure in either read
        # raises ApprovalsError, which the engine treats as "no approvals" so a
        # blocked verdict stays blocked (fail-closed). Memoized: one PR has one
        # set of reviews/comments shared across every scope.
        nonlocal approvals_cache
        if approvals_cache is None:
            reviews = fetch_approvals(pr.repo, pr.pr_number, token)
            since = fetch_commit_time(pr.repo, pr.head_sha, token)
            comments = fetch_comment_approvals(pr.repo, pr.pr_number, token, since)
            approvals_cache = reviews + comments
        return approvals_cache

    all_verdicts: list[Verdict] = []
    scope_roles: dict[str, RolesConfig | None] = {}
    for scope in scopes:
        report.notice(
            f"SpecGuard: governance source for "
            f"{scope.scope_dir or '(repo root)'} — {scope.source}"
        )
        scope_roles[scope.scope_dir] = scope.roles
        rescoped = [rescope_changed_file(c, scope.scope_dir) for c in scope.changed]
        # Test injection keeps the Anthropic SDK seam; real runs pick the
        # backend declared by config.provider (anthropic/openai/gemini/openrouter).
        scope_adapter = (
            AnthropicAdapter(client=client) if client is not None else make_adapter(scope.config)
        )
        verdicts = evaluate_pr(
            rescoped,
            scope.lock,
            scope.config,
            scope.roles,
            pr,
            scope_adapter,
            get_approvals,
            regions_config=scope.regions,
            scope=scope.scope_dir,
        )
        all_verdicts.extend(verdicts)

    report.emit_annotations(all_verdicts, pr, roles_config=None, scope_roles=scope_roles)
    report.write_summary(all_verdicts, pr, roles_config=None, scope_roles=scope_roles)

    audit_path = os.environ.get("SPECGUARD_AUDIT_PATH")
    if audit_path:
        as_of = fetch_commit_time(pr.repo, pr.head_sha, token)
        entries = build_audit_entries(all_verdicts, get_approvals(), pr, as_of=as_of)
        Path(audit_path).write_text(export_audit_json(entries))

    return 1 if any(v.outcome == "BLOCK" for v in all_verdicts) else 0


if __name__ == "__main__":
    sys.exit(main())
