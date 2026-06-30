"""Per-commit authorship — the basis for the propose-only `agents` role (FR-005).

The Actions gate keys authorship off the PR opener; the App can attribute the
change to who actually authored the head commit (human / `[bot]` / App), so
"agents propose, humans approve" holds even when a human opened the PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from specguard.app.auth import _HEADERS, API_BASE


class CommitsError(Exception):
    """Could not read PR commits."""


@dataclass
class CommitAuthor:
    login: str
    is_bot: bool


def _is_bot(user: dict[str, Any]) -> bool:
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def attribute_author(
    repo: str,
    pr_number: int,
    opener_login: str,
    token: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> CommitAuthor:
    """Attribute the PR to its HEAD commit's author, falling back to the opener.

    Head-commit attribution is the simple, defensible rule: it is the change
    actually being merged. Multi-author precedence is a documented refinement.
    """
    url = f"{API_BASE}/repos/{repo}/pulls/{pr_number}/commits"
    headers = {"Authorization": f"Bearer {token}", **_HEADERS}
    try:
        with httpx.Client(timeout=30.0, transport=transport) as client:
            response = client.get(url, headers=headers, params={"per_page": 100})
            response.raise_for_status()
            commits = response.json()
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise CommitsError(f"could not read PR commits: {exc}") from exc

    if not commits:
        return CommitAuthor(login=opener_login, is_bot=opener_login.endswith("[bot]"))
    author = (commits[-1].get("author") or {})  # GitHub-linked account of the head commit
    login = author.get("login") or opener_login
    return CommitAuthor(login=login, is_bot=_is_bot(author) if author else False)
