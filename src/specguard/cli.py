"""The `specguard` CLI: init, check, mcp.

Local surfaces are ADVISORY (constitution I): `check` previews what the merge
gate would say, the hook never blocks a commit, and every output discloses
that only the merge-time check enforces. Exit codes mirror ci.py (FR-004):
0 nothing would block, 1 would block, 2 configuration/environment error —
except `--hook` mode, which is unconditionally 0 (FR-006).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

from specguard import localreport
from specguard.classifier import ClassifierAdapter
from specguard.config import (
    CONFIG_PATH,
    LOCK_PATH,
    ROLES_PATH,
    ConfigError,
    parse_config,
    parse_lock,
    parse_roles,
)
from specguard.engine import evaluate_pr
from specguard.gitdiff import GitError
from specguard.localcheck import (
    CheckSnapshot,
    load_baseline_governance,
    require_repo_with_head,
    resolve_snapshot,
)
from specguard.models import Approval, PRContext, Verdict
from specguard.providers import make_adapter, required_env_var

SETUP_HINT = (
    "this repository has no .specguard/lock.json at the baseline — run "
    "`specguard init` to lock your project's goal and scope"
)

DEFAULT_HOOK_TIMEOUT = 30.0

WORKFLOW_SNIPPET = """\
name: specguard
on:
  pull_request:
  pull_request_review:
    types: [submitted]
permissions:
  contents: read
  pull-requests: read
jobs:
  specguard:                               # the required branch-protection check
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}             # required: base...head history
      - uses: Sawaiz-zip/spec-guard@v0
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
  reevaluate:                              # an approval re-runs the check in place
    if: github.event_name == 'pull_request_review' && github.event.review.state == 'approved'
    runs-on: ubuntu-latest
    permissions: {actions: write}
    steps:
      - env:
          GH_TOKEN: ${{ github.token }}
        run: |
          run_id=$(gh api "repos/${{ github.repository }}/actions/workflows/specguard.yml/runs?event=pull_request&head_sha=${{ github.event.pull_request.head.sha }}" --jq '.workflow_runs[0].id // empty')
          [ -n "$run_id" ] && gh api -X POST "repos/${{ github.repository }}/actions/runs/$run_id/rerun"
"""

CONFIG_TEMPLATE = """\
# SpecGuard settings — every key is optional; these are the defaults.
# watch:
#   - "README.md"
#   - "CLAUDE.md"
#   - "AGENTS.md"
#   - "ARCHITECTURE.md"
#   - "*.kilo"
#   - ".specguard/**"
# block_threshold: 0.75
# on_error: warn          # vendor outage: pass with a loud warning ("fail" to block)
# model: claude-sonnet-4-6
# max_diff_chars: 30000
"""

HOOK_SCRIPT = """\
#!/bin/sh
# SpecGuard advisory pre-commit hook — warns about scope changes in staged
# spec files but NEVER prevents a commit (merge-time enforcement only).
specguard check --staged --hook
exit 0
"""


def main(argv: list[str] | None = None, adapter: ClassifierAdapter | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="specguard",
        description="Semantic governance for spec files — local advisory tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="scaffold .specguard/ configuration interactively"
    )
    init_parser.add_argument(
        "--force", action="store_true", help="overwrite an existing lock.json"
    )
    init_parser.add_argument(
        "--yes", action="store_true",
        help="non-interactive: placeholder goal, skip all optional files",
    )

    check_parser = subparsers.add_parser(
        "check", help="preview the merge gate's verdicts for local changes"
    )
    check_parser.add_argument(
        "--staged", action="store_true", help="evaluate the index instead of the working tree"
    )
    check_parser.add_argument("--base", help="baseline ref for a committed range")
    check_parser.add_argument("--head", help="head ref for a committed range (default HEAD)")
    check_parser.add_argument(
        "--json", action="store_true", help="machine-readable verdict output"
    )
    check_parser.add_argument(
        "--hook", action="store_true",
        help="pre-commit hook mode: always exit 0, silent when nothing watched changed",
    )

    subparsers.add_parser("mcp", help="run the stdio MCP server (needs the [mcp] extra)")

    args = parser.parse_args(argv)
    if args.command == "init":
        return _cmd_init(args)
    if args.command == "check":
        return _cmd_check(args, adapter)
    return _cmd_mcp()


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace, adapter: ClassifierAdapter | None) -> int:
    repo_root = Path.cwd()
    try:
        return _run_check(repo_root, args, adapter)
    except (ConfigError, GitError) as exc:
        if args.hook:
            print(f"specguard: {exc} — {localreport.COULD_NOT_CLASSIFY}")
            return 0
        print(f"specguard: error: {exc}", file=sys.stderr)
        return 2


def _local_login(repo_root: Path) -> str:
    import subprocess

    for key in ("specguard.login", "github.user", "user.name"):
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return "(local)"


def _run_check(
    repo_root: Path, args: argparse.Namespace, adapter: ClassifierAdapter | None
) -> int:
    require_repo_with_head(repo_root)
    base_ref = args.base or "HEAD"
    governance = load_baseline_governance(repo_root, base_ref)
    if governance.lock is None:
        if not args.hook:
            print(f"specguard: {SETUP_HINT}")
        return 0

    snapshot = resolve_snapshot(
        repo_root,
        staged=args.staged or args.hook,
        base=args.base,
        head=args.head,
        watch=governance.config.watch,
    )

    if not snapshot.changes:
        if args.hook:
            return 0  # silent: zero friction on non-spec commits
        _emit(args, [], snapshot)
        return 0

    if adapter is None:
        env_var = required_env_var(governance.config.provider)
        if not os.environ.get(env_var):
            hint = (
                f"{env_var} is not set — export it to classify with the "
                f"'{governance.config.provider}' provider"
            )
            if args.hook:
                print(f"specguard: {hint} — {localreport.COULD_NOT_CLASSIFY}")
                return 0
            print(f"specguard: error: {hint}", file=sys.stderr)
            return 2
        adapter = make_adapter(governance.config)

    pr = PRContext(
        pr_number=0,
        base_sha=snapshot.base_sha,
        head_sha="local",
        author_login=_local_login(repo_root),
        is_fork=False,
        repo="(local)",
    )

    def no_approvals() -> list[Approval]:
        return []

    def evaluate() -> list[Verdict]:
        assert governance.lock is not None
        return evaluate_pr(
            snapshot.changes,
            governance.lock,
            governance.config,
            governance.roles,
            pr,
            adapter,
            no_approvals,
        )

    if args.hook:
        timeout = float(os.environ.get("SPECGUARD_HOOK_TIMEOUT", DEFAULT_HOOK_TIMEOUT))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(evaluate)
            try:
                verdicts = future.result(timeout=timeout)
            except FutureTimeoutError:
                print(
                    f"specguard: classifier timed out after {timeout:.0f}s — "
                    f"{localreport.COULD_NOT_CLASSIFY}"
                )
                future.cancel()
                return 0
        _emit(args, verdicts, snapshot)
        return 0  # the hook NEVER blocks (FR-006)

    verdicts = evaluate()
    _emit(args, verdicts, snapshot)
    return 1 if localreport.would_block(verdicts) else 0


def _emit(args: argparse.Namespace, verdicts: list[Verdict], snapshot: CheckSnapshot) -> None:
    if getattr(args, "json", False):
        print(localreport.render_json(verdicts, snapshot))
    else:
        print(localreport.render(verdicts, snapshot))


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _ask_list(prompt: str) -> list[str]:
    raw = _ask(prompt)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _ask_yes(prompt: str) -> bool:
    return _ask(f"{prompt} [y/N] ").lower() in ("y", "yes")


def _cmd_init(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    if not (repo_root / ".git").exists():
        print("specguard: error: not a git repository", file=sys.stderr)
        return 2

    lock_file = repo_root / LOCK_PATH
    if lock_file.exists() and not args.force:
        print(
            f"specguard: error: {LOCK_PATH} already exists — re-run with --force "
            "to overwrite the scope lock",
            file=sys.stderr,
        )
        return 2

    created: list[str] = []
    skipped: list[str] = []

    if args.yes:
        goal = "TODO: replace with your locked project goal"
        scope_in: list[str] = []
        scope_out: list[str] = []
    else:
        print("SpecGuard locks your project's goal and scope in version control.")
        goal = ""
        while not goal:
            goal = _ask("Project goal (one sentence): ")
        scope_in = _ask_list("In-scope topics (comma-separated, may be empty): ")
        scope_out = _ask_list("Out-of-scope topics (comma-separated, may be empty): ")

    lock_text = json.dumps(
        {"goal": goal, "scope_in": scope_in, "scope_out": scope_out,
         "locked_at": None, "locked_by": None},
        indent=2,
    ) + "\n"
    parse_lock(lock_text)  # round-trip before writing (contract guarantee)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(lock_text)
    created.append(LOCK_PATH)

    _offer_optional_files(repo_root, args, created, skipped)

    print("\ncreated:")
    for path in created:
        print(f"  {path}")
    if skipped:
        print("skipped (add later when you need them):")
        for note in skipped:
            print(f"  {note}")
    print("\nnext: run `specguard check` after your next spec edit")
    return 0


def _offer_optional_files(
    repo_root: Path, args: argparse.Namespace, created: list[str], skipped: list[str]
) -> None:
    config_file = repo_root / CONFIG_PATH
    if args.yes or config_file.exists():
        skipped.append(f"{CONFIG_PATH} — settings template (defaults work without it)")
    elif _ask_yes(f"Write a commented settings template to {CONFIG_PATH}?"):
        parse_config(CONFIG_TEMPLATE)
        config_file.write_text(CONFIG_TEMPLATE)
        created.append(CONFIG_PATH)
    else:
        skipped.append(f"{CONFIG_PATH} — settings template (defaults work without it)")

    roles_file = repo_root / ROLES_PATH
    if args.yes or roles_file.exists():
        skipped.append(f"{ROLES_PATH} — roles switch warn mode to enforce mode")
    elif _ask_yes(f"Configure roles now (switches warnings to blocking)? Writes {ROLES_PATH}"):
        role = _ask("Approver role name [architect]: ") or "architect"
        members = _ask_list("GitHub usernames for this role (comma-separated): ")
        roles_text = (
            f"roles:\n  {role}: [{', '.join(members)}]\n"
            f"rules:\n"
            f'  ".specguard/**":\n    edit: {role}\n'
            f'  "README.md":\n    scope_changes: {{approve: {role}}}\n'
        )
        parse_roles(roles_text)
        roles_file.write_text(roles_text)
        created.append(ROLES_PATH)
    else:
        skipped.append(f"{ROLES_PATH} — roles switch warn mode to enforce mode")

    workflow_file = repo_root / ".github" / "workflows" / "specguard.yml"
    if args.yes or workflow_file.exists():
        skipped.append(".github/workflows/specguard.yml — the merge gate itself")
    elif _ask_yes("Write the GitHub Actions merge-gate workflow?"):
        workflow_file.parent.mkdir(parents=True, exist_ok=True)
        workflow_file.write_text(WORKFLOW_SNIPPET)
        created.append(".github/workflows/specguard.yml")
    else:
        skipped.append(".github/workflows/specguard.yml — the merge gate itself")

    hook_file = repo_root / ".git" / "hooks" / "pre-commit"
    if args.yes:
        skipped.append(".git/hooks/pre-commit — advisory commit-time warnings")
    elif hook_file.exists():
        skipped.append(
            ".git/hooks/pre-commit exists — add `specguard check --staged --hook` "
            "to it manually, or use the pre-commit framework"
        )
    elif _ask_yes("Install the advisory pre-commit hook (never blocks commits)?"):
        hook_file.parent.mkdir(parents=True, exist_ok=True)
        hook_file.write_text(HOOK_SCRIPT)
        hook_file.chmod(0o755)
        created.append(".git/hooks/pre-commit")
    else:
        skipped.append(".git/hooks/pre-commit — advisory commit-time warnings")


# ---------------------------------------------------------------------------
# mcp
# ---------------------------------------------------------------------------


def _cmd_mcp() -> int:
    from specguard import mcp_server

    try:
        mcp_server.run()
    except ImportError as exc:
        print(f"specguard: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
