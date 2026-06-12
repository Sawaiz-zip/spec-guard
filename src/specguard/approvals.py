"""Qualifying-approval detection via the GitHub Reviews API.

A review qualifies when (a) it is the reviewer's LATEST review on the PR,
(b) its state is APPROVED, and (c) the reviewer belongs to an authorizing
role. Re-evaluation rides on the `pull_request_review` workflow trigger —
no new commits needed to flip a BLOCK to PASS.
"""

from __future__ import annotations

from typing import Any

import httpx

from specguard.models import Approval, RolesConfig
from specguard.roles import is_member

API_BASE = "https://api.github.com"


class ApprovalsError(Exception):
    """Reviews API unavailable — callers treat blocked verdicts as unapproved."""


def fetch_approvals(repo: str, pr_number: int, token: str) -> list[Approval]:
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
        with httpx.Client(timeout=30.0) as client:
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
