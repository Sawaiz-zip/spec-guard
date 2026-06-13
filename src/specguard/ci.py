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
from specguard.approvals import fetch_approvals
from specguard.classifier import AnthropicAdapter
from specguard.config import (
    CONFIG_PATH,
    LOCK_PATH,
    ROLES_PATH,
    ConfigError,
    detect_framework,
    parse_config,
    parse_lock,
    parse_roles,
)
from specguard.engine import evaluate_pr
from specguard.gitdiff import GitError, show_file, watched_changes
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
    lock_text = show_file(repo_root, pr.base_sha, LOCK_PATH)
    if lock_text is None:
        report.notice(SETUP_HINT)
        return 0

    lock = parse_lock(lock_text, f"{pr.base_sha[:7]}:{LOCK_PATH}")
    config = parse_config(
        show_file(repo_root, pr.base_sha, CONFIG_PATH), f"{pr.base_sha[:7]}:{CONFIG_PATH}"
    )
    roles_config = parse_roles(
        show_file(repo_root, pr.base_sha, ROLES_PATH), f"{pr.base_sha[:7]}:{ROLES_PATH}"
    )

    framework = detect_framework(repo_root)
    if framework:
        report.notice(
            f"SpecGuard: {framework} detected — adapter coming; using plain mode"
        )

    changed = watched_changes(repo_root, pr.base_sha, pr.head_sha, config.watch)
    if not changed:
        report.notice("SpecGuard: no watched spec files changed in this PR")
        return 0

    # Test injection keeps the Anthropic SDK seam; real runs pick the backend
    # declared by config.provider (anthropic/openai/gemini/openrouter).
    adapter = AnthropicAdapter(client=client) if client is not None else make_adapter(config)

    token = os.environ.get("GITHUB_TOKEN", "")

    def get_approvals() -> list[Approval]:
        return fetch_approvals(pr.repo, pr.pr_number, token)

    verdicts = evaluate_pr(changed, lock, config, roles_config, pr, adapter, get_approvals)

    report.emit_annotations(verdicts, pr, roles_config)
    report.write_summary(verdicts, pr, roles_config)

    return 1 if any(v.outcome == "BLOCK" for v in verdicts) else 0


if __name__ == "__main__":
    sys.exit(main())
