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
from specguard.classifier import AnthropicAdapter
from specguard.config import (
    CONFIG_PATH,
    ROLES_PATH,
    ConfigError,
    parse_config,
    parse_roles,
)
from specguard.engine import evaluate_pr
from specguard.gitdiff import GitError, show_file, watched_changes
from specguard.governance import resolve_lock
from specguard.models import Approval, PRContext
from specguard.providers import make_adapter

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
    # rewrite the rules it is judged by (verified live in sandbox E2E).
    config = parse_config(
        show_file(repo_root, pr.base_sha, CONFIG_PATH), f"{pr.base_sha[:7]}:{CONFIG_PATH}"
    )
    roles_config = parse_roles(
        show_file(repo_root, pr.base_sha, ROLES_PATH), f"{pr.base_sha[:7]}:{ROLES_PATH}"
    )

    changed = watched_changes(repo_root, pr.base_sha, pr.head_sha, config.watch)
    if not changed:
        report.notice("SpecGuard: no watched spec files changed in this PR")
        return 0

    # The lock comes from the governance overlay (explicit lock > Spec Kit >
    # OpenSpec > plain), derived from the same base ref and changed paths so the
    # verdict matches what the local tools produce (constitution III, FR-005).
    lock, source = resolve_lock(
        repo_root, pr.base_sha, [c.path for c in changed]
    )
    if lock is None:
        report.notice(SETUP_HINT)
        return 0
    report.notice(f"SpecGuard: governance source — {source}")

    # Test injection keeps the Anthropic SDK seam; real runs pick the backend
    # declared by config.provider (anthropic/openai/gemini/openrouter).
    adapter = AnthropicAdapter(client=client) if client is not None else make_adapter(config)

    token = os.environ.get("GITHUB_TOKEN", "")

    def get_approvals() -> list[Approval]:
        # Approvals come from two platform-native sources, evaluated identically
        # by the engine: native reviews AND `/specguard approve` comments posted
        # at/after the head commit (FR-005, FR-010). A failure in either read
        # raises ApprovalsError, which the engine treats as "no approvals" so a
        # blocked verdict stays blocked (fail-closed).
        reviews = fetch_approvals(pr.repo, pr.pr_number, token)
        since = fetch_commit_time(pr.repo, pr.head_sha, token)
        comments = fetch_comment_approvals(pr.repo, pr.pr_number, token, since)
        return reviews + comments

    verdicts = evaluate_pr(changed, lock, config, roles_config, pr, adapter, get_approvals)

    report.emit_annotations(verdicts, pr, roles_config)
    report.write_summary(verdicts, pr, roles_config)

    return 1 if any(v.outcome == "BLOCK" for v in verdicts) else 0


if __name__ == "__main__":
    sys.exit(main())
