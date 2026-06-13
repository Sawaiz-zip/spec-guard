"""Stdio MCP server: write-time advisory verdicts for coding agents.

Contract: specs/002-local-tools/contracts/mcp-interface.md. The tool logic
lives in plain functions (testable without the `mcp` extra); only run()
imports the SDK. Every result is advisory — the merge gate enforces.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from specguard.classifier import AnthropicAdapter, ClassifierAdapter
from specguard.config import path_matches
from specguard.gitdiff import diff_from_contents, show_file
from specguard.localcheck import load_baseline_governance, require_repo_with_head
from specguard.localreport import ADVISORY_NOTICE, COULD_NOT_CLASSIFY
from specguard.models import Approval, PRContext, Verdict

SETUP_HINT = (
    "this repository has no .specguard/lock.json at the baseline — run "
    "`specguard init` to lock the project's goal and scope"
)

INSTALL_HINT = 'the MCP server needs the optional extra — pip install "specguard-ci[mcp]"'


def _base(repo_root: Path) -> tuple[str, Any]:
    short_sha = require_repo_with_head(repo_root)
    governance = load_baseline_governance(repo_root, "HEAD")
    return f"HEAD ({short_sha})", governance


def _advisory(payload: dict[str, Any]) -> dict[str, Any]:
    payload["advisory"] = True
    payload["notice"] = ADVISORY_NOTICE
    return payload


def check_proposed_change(
    path: str,
    proposed_content: str,
    repo_root: Path | None = None,
    adapter: ClassifierAdapter | None = None,
) -> dict[str, Any]:
    """Classify a change the agent is ABOUT to write — before any commit exists."""
    root = repo_root or Path.cwd()
    baseline, governance = _base(root)

    if governance.lock is None:
        return _advisory({"configured": False, "hint": SETUP_HINT})

    if not any(path_matches(path, pattern) for pattern in governance.config.watch):
        return _advisory(
            {
                "configured": True,
                "watched": False,
                "baseline": baseline,
                "detail": f"{path} is not a watched spec file — no classification performed",
            }
        )

    old_content = show_file(root, "HEAD", path) or ""
    changed = diff_from_contents(path, old_content, proposed_content)

    if adapter is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return _advisory(
                {
                    "configured": True,
                    "watched": True,
                    "classified": False,
                    "baseline": baseline,
                    "detail": f"ANTHROPIC_API_KEY is not set — {COULD_NOT_CLASSIFY}",
                }
            )
        adapter = AnthropicAdapter()

    from specguard.engine import evaluate_pr

    pr = PRContext(
        pr_number=0,
        base_sha=baseline,
        head_sha="proposed",
        author_login="(agent)",
        is_fork=False,
        repo="(local)",
    )

    def no_approvals() -> list[Approval]:
        return []

    verdict = evaluate_pr(
        [changed], governance.lock, governance.config, governance.roles,
        pr, adapter, no_approvals,
    )[0]

    if verdict.reason == "classifier_error":
        return _advisory(
            {
                "configured": True,
                "watched": True,
                "classified": False,
                "baseline": baseline,
                "detail": COULD_NOT_CLASSIFY,
            }
        )

    return _advisory(
        {
            "configured": True,
            "watched": True,
            "classified": True,
            "baseline": baseline,
            "verdict": _verdict_payload(verdict),
        }
    )


def _verdict_payload(verdict: Verdict) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "file": verdict.file,
        "outcome": verdict.outcome,
        "reason": verdict.reason,
        "would_block_until": verdict.required_approver_roles,
    }
    if verdict.classification is not None:
        payload["classification"] = verdict.classification.model_dump()
    return payload


def get_scope_lock(repo_root: Path | None = None) -> dict[str, Any]:
    """The locked frame — consult it BEFORE drafting (no classifier call)."""
    root = repo_root or Path.cwd()
    baseline, governance = _base(root)
    if governance.lock is None:
        return _advisory({"configured": False, "hint": SETUP_HINT})
    return _advisory(
        {
            "configured": True,
            "baseline": baseline,
            "scope_lock": governance.lock.model_dump(),
        }
    )


def list_watched_paths(repo_root: Path | None = None) -> dict[str, Any]:
    """Which files are governed, and whether roles enforcement is configured."""
    root = repo_root or Path.cwd()
    baseline, governance = _base(root)
    if governance.lock is None:
        return _advisory({"configured": False, "hint": SETUP_HINT})
    return _advisory(
        {
            "configured": True,
            "baseline": baseline,
            "watch": governance.config.watch,
            "enforce_mode": governance.roles is not None,
        }
    )


def run() -> None:
    """Start the stdio server. Requires the `specguard-ci[mcp]` extra."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(INSTALL_HINT) from exc

    server: Any = FastMCP("specguard")

    @server.tool()
    def specguard_check_proposed_change(path: str, proposed_content: str) -> dict[str, Any]:
        """Classify a proposed spec-file change against the locked scope
        BEFORE writing it. Advisory: the merge-time check enforces."""
        return check_proposed_change(path, proposed_content)

    @server.tool()
    def specguard_get_scope_lock() -> dict[str, Any]:
        """Read the repository's locked goal and scope (no classifier call)."""
        return get_scope_lock()

    @server.tool()
    def specguard_list_watched_paths() -> dict[str, Any]:
        """List governed file patterns and whether roles enforcement is on."""
        return list_watched_paths()

    server.run()  # stdio transport


if __name__ == "__main__":
    try:
        run()
    except ImportError as exc:
        print(f"specguard: error: {exc}", file=sys.stderr)
        sys.exit(2)
