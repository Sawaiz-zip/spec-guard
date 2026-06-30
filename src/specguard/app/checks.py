"""Checks-API client: create or update the `specguard` check run.

The check run is anchored to the PR head SHA. An authorized approval (or a
re-request) updates the SAME run in place — never a second check — which is
how the App retires the Actions-era re-run workaround (FR-002/FR-003).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from specguard.app.auth import _HEADERS, API_BASE

CHECK_NAME = "specguard"

Conclusion = Literal["success", "failure", "neutral"]


class ChecksError(Exception):
    """Checks API call failed."""


@dataclass
class CheckRunResult:
    """The verdict rendered for a check run."""

    conclusion: Conclusion
    title: str
    summary: str


def _output(result: CheckRunResult) -> dict[str, Any]:
    return {"title": result.title, "summary": result.summary}


def find_check_run_id(
    repo: str,
    head_sha: str,
    token: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> int | None:
    """The id of an existing `specguard` check run on this SHA, if any."""
    url = f"{API_BASE}/repos/{repo}/commits/{head_sha}/check-runs"
    headers = {"Authorization": f"Bearer {token}", **_HEADERS}
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            response = client.get(url, headers=headers, params={"check_name": CHECK_NAME})
            response.raise_for_status()
            runs = response.json().get("check_runs", [])
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise ChecksError(f"could not list check runs: {exc}") from exc
    return int(runs[0]["id"]) if runs else None


def upsert_check_run(
    repo: str,
    head_sha: str,
    token: str,
    result: CheckRunResult,
    *,
    transport: httpx.BaseTransport | None = None,
) -> int:
    """Create the head-SHA check run, or update it in place if it already exists.

    Idempotent (FR-009): re-evaluating the same commit converges to one run.
    Returns the check-run id.
    """
    headers = {"Authorization": f"Bearer {token}", **_HEADERS}
    body: dict[str, Any] = {
        "name": CHECK_NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": result.conclusion,
        "output": _output(result),
    }
    existing = find_check_run_id(repo, head_sha, token, transport=transport)
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            if existing is None:
                url = f"{API_BASE}/repos/{repo}/check-runs"
                response = client.post(url, headers=headers, json=body)
            else:
                url = f"{API_BASE}/repos/{repo}/check-runs/{existing}"
                response = client.patch(url, headers=headers, json=body)
            response.raise_for_status()
            return int(response.json()["id"])
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise ChecksError(f"could not upsert check run: {exc}") from exc
