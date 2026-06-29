"""Qualifying-approval detection via the GitHub Reviews API.

A review qualifies when (a) it is the reviewer's LATEST review on the PR,
(b) its state is APPROVED, and (c) the reviewer belongs to an authorizing
role. Re-evaluation rides on the `pull_request_review` workflow trigger —
no new commits needed to flip a BLOCK to PASS.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from specguard.models import Approval, RolesConfig
from specguard.roles import is_member

API_BASE = "https://api.github.com"

APPROVE_COMMAND = "/specguard approve"

_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class ApprovalsError(Exception):
    """Reviews API unavailable — callers treat blocked verdicts as unapproved."""


def fetch_approvals(
    repo: str,
    pr_number: int,
    token: str,
    transport: httpx.BaseTransport | None = None,
) -> list[Approval]:
    """Latest review per reviewer for the PR (paginated, newest state wins)."""
    reviews: list[dict[str, Any]] = []
    url = f"{API_BASE}/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    page = 1
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            while True:
                response = client.get(
                    url, headers=headers, params={"per_page": 100, "page": page}
                )
                response.raise_for_status()
                batch = response.json()
                reviews.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
    except httpx.HTTPError as exc:
        raise ApprovalsError(f"could not fetch PR reviews: {exc}") from exc

    # Reviews arrive oldest-first; keep each reviewer's latest substantive state.
    # COMMENTED reviews don't change approval state, so they are ignored.
    latest: dict[str, str] = {}
    for review in reviews:
        login = (review.get("user") or {}).get("login")
        state = review.get("state", "")
        if login and state in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[login] = state
    return [Approval(reviewer_login=login, state=state) for login, state in latest.items()]


def _parse_dt(value: str) -> datetime:
    """Parse a GitHub ISO-8601 timestamp (Zulu) — 3.10-safe (no bare 'Z')."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_approve_command(body: str) -> bool:
    """True when the comment's first non-empty line is the approve command.

    Trailing text (`/specguard approve please`) is accepted; the command must be
    at the START of the first line — `please /specguard approve` does not count.
    """
    stripped = body.strip()
    if not stripped:
        return False
    first_line = stripped.splitlines()[0].strip().lower()
    return first_line.startswith(APPROVE_COMMAND)


def fetch_commit_time(
    repo: str, sha: str, token: str, transport: httpx.BaseTransport | None = None
) -> str:
    """The committer date of `sha` (ISO-8601) — the staleness boundary for comments."""
    url = f"{API_BASE}/repos/{repo}/commits/{sha}"
    headers = {"Authorization": f"Bearer {token}", **_HEADERS}
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return str(response.json()["commit"]["committer"]["date"])
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise ApprovalsError(f"could not read head commit time: {exc}") from exc


def fetch_comment_approvals(
    repo: str,
    pr_number: int,
    token: str,
    since: str,
    transport: httpx.BaseTransport | None = None,
) -> list[Approval]:
    """Qualifying `/specguard approve` PR comments as APPROVED approvals.

    Only comments posted at/after `since` (the head-commit time) count, so a stale
    approval from before the latest commit does not re-qualify (FR-010). The
    commenter's API-reported login is the server-side identity (FR-006).
    """
    comments: list[dict[str, Any]] = []
    url = f"{API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"Bearer {token}", **_HEADERS}
    page = 1
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            while True:
                response = client.get(
                    url, headers=headers, params={"per_page": 100, "page": page}
                )
                response.raise_for_status()
                batch = response.json()
                comments.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
    except httpx.HTTPError as exc:
        raise ApprovalsError(f"could not fetch PR comments: {exc}") from exc

    since_dt = _parse_dt(since)
    approvals: list[Approval] = []
    for comment in comments:
        login = (comment.get("user") or {}).get("login")
        created = comment.get("created_at")
        if not login or not created:
            continue
        if not _is_approve_command(comment.get("body") or ""):
            continue
        if _parse_dt(created) < since_dt:
            continue  # stale: posted before the current head commit
        approvals.append(
            Approval(
                reviewer_login=login, state="APPROVED", source="comment-command"
            )
        )
    return approvals


def has_qualified_approval(
    approvals: list[Approval],
    required_roles: list[str],
    roles_config: RolesConfig,
) -> bool:
    """True iff an APPROVED reviewer belongs to any of the required roles."""
    for approval in approvals:
        if approval.state != "APPROVED":
            continue
        if any(
            is_member(approval.reviewer_login, role, roles_config)
            for role in required_roles
        ):
            return True
    return False
