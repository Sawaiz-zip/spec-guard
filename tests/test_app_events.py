"""The App's evaluate() pipeline against a temp git repo — the parity-critical path."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from conftest import FakeAdapter, make_classification
from specguard.app.commits import CommitAuthor
from specguard.app.events import PRWebhook, evaluate, parse_pr_webhook
from specguard.models import Approval

LOCK = json.dumps(
    {"goal": "A local CLI tool", "scope_in": ["tasks"], "scope_out": ["SaaS pricing"]}
)
ROLES = (
    "roles:\n  architect: [alice]\n"
    "rules:\n  README.md:\n    scope_changes: {approve: architect}\n"
)


def build_repo(git_repo, *, roles: bool, new_readme: str) -> tuple[str, str]:
    git_repo.write(".specguard/lock.json", LOCK)
    if roles:
        git_repo.write(".specguard/roles.yml", ROLES)
    git_repo.write("README.md", "v1\n")
    base = git_repo.commit_all("base")
    git_repo.write("README.md", new_readme)
    head = git_repo.commit_all("edit")
    return base, head


def webhook(repo_root: Path, base: str, head: str, opener: str = "dev") -> PRWebhook:
    return PRWebhook(
        repo="acme/widgets", pr_number=7, base_sha=base, head_sha=head,
        installation_id=1, is_fork=False, opener_login=opener,
    )


def fake_checkout_for(repo_root: Path):
    @contextmanager
    def _checkout(repo, base_sha, head_sha, token):
        yield repo_root  # the prepared temp git repo stands in for the clone
    return _checkout


def human(repo, pr_number, opener, token):
    return CommitAuthor(login=opener, is_bot=False)


class TestEvaluate:
    def test_additive_change_success(self, git_repo):
        base, head = build_repo(git_repo, roles=True, new_readme="v1 fixed typo\n")
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root),
            adapter=FakeAdapter(responses={"README.md": make_classification("ADDITIVE", 0.97)}),
            attribute=human,
        )
        assert result.conclusion == "success"

    def test_scope_change_unapproved_fails(self, git_repo):
        base, head = build_repo(git_repo, roles=True, new_readme="v1\nSaaS pricing tiers\n")
        sc = make_classification("SCOPE_CHANGE", 0.94, "HIGH", ["SaaS pricing"], "Added pricing")
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root),
            adapter=FakeAdapter(responses={"README.md": sc}),
            attribute=human,
        )
        assert result.conclusion == "failure"
        assert "architect" in result.summary

    def test_scope_change_approved_succeeds(self, git_repo):
        base, head = build_repo(git_repo, roles=True, new_readme="v1\nSaaS pricing tiers\n")
        sc = make_classification("SCOPE_CHANGE", 0.94, "HIGH", ["SaaS pricing"], "Added pricing")
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root),
            adapter=FakeAdapter(responses={"README.md": sc}),
            approvals_provider=lambda pr, tok: [
                Approval(reviewer_login="alice", state="APPROVED", source="native-review")
            ],
            attribute=human,
        )
        assert result.conclusion == "success"

    def test_no_watched_changes_success(self, git_repo):
        git_repo.write(".specguard/lock.json", LOCK)
        git_repo.write("src/main.py", "print(1)\n")
        base = git_repo.commit_all("base")
        git_repo.write("src/main.py", "print(2)\n")
        head = git_repo.commit_all("code only")
        adapter = FakeAdapter()
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root), adapter=adapter, attribute=human,
        )
        assert result.conclusion == "success"
        assert adapter.call_count == 0

    def test_unconfigured_repo_neutral(self, git_repo):
        git_repo.write("README.md", "v1\n")
        base = git_repo.commit_all("base")
        git_repo.write("README.md", "v2\n")
        head = git_repo.commit_all("edit")
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root), adapter=FakeAdapter(), attribute=human,
        )
        assert result.conclusion == "neutral"
        assert "not configured" in result.title.lower()

    def test_classifier_error_neutral_fail_open(self, git_repo):
        from specguard.classifier import ClassifierError

        base, head = build_repo(git_repo, roles=True, new_readme="v1 changed\n")
        result = evaluate(
            webhook(git_repo.root, base, head), "tok",
            checkout=fake_checkout_for(git_repo.root),
            adapter=FakeAdapter(responses={"README.md": ClassifierError("down")}),
            attribute=human,
        )
        assert result.conclusion == "neutral"  # on_error=warn → fail-open, visible

    def test_fork_pr_is_classified_not_skipped(self, git_repo):
        # FR-001: a fork PR runs the full pipeline (the token is the App's).
        base, head = build_repo(git_repo, roles=True, new_readme="v1\nSaaS pricing\n")
        pr = PRWebhook(
            repo="acme/widgets", pr_number=9, base_sha=base, head_sha=head,
            installation_id=1, is_fork=True, opener_login="outsider",
        )
        sc = make_classification("SCOPE_CHANGE", 0.95, "HIGH", ["SaaS pricing"], "pricing")
        adapter = FakeAdapter(responses={"README.md": sc})
        result = evaluate(
            pr, "tok", checkout=fake_checkout_for(git_repo.root),
            adapter=adapter, attribute=human,
        )
        assert adapter.call_count == 1  # classified despite being a fork
        assert result.conclusion == "failure"

    def test_bot_authored_scope_change_blocks(self, git_repo):
        # FR-005: bot-authored scope change blocks even though a human opened it.
        base, head = build_repo(git_repo, roles=True, new_readme="v1\nSaaS pricing\n")
        sc = make_classification("SCOPE_CHANGE", 0.95, "HIGH", ["SaaS pricing"], "pricing")
        bot = lambda repo, n, opener, tok: CommitAuthor(login="agent[bot]", is_bot=True)  # noqa: E731
        result = evaluate(
            webhook(git_repo.root, base, head, opener="alice"), "tok",  # architect opened
            checkout=fake_checkout_for(git_repo.root),
            adapter=FakeAdapter(responses={"README.md": sc}),
            attribute=bot,  # but a bot authored the commit
        )
        # agent[bot] is not the architect → still needs approval.
        assert result.conclusion == "failure"


class TestParsePrWebhook:
    def _pr_payload(self, fork: bool = False) -> dict:
        head_repo = "outsider/widgets" if fork else "acme/widgets"
        return {
            "installation": {"id": 5},
            "pull_request": {
                "number": 7,
                "user": {"login": "dev"},
                "base": {"sha": "base", "repo": {"full_name": "acme/widgets"}},
                "head": {"sha": "head", "repo": {"full_name": head_repo}},
            },
        }

    def test_pull_request_event_parsed(self):
        pr = parse_pr_webhook("pull_request", self._pr_payload())
        assert pr is not None
        assert pr.repo == "acme/widgets" and pr.pr_number == 7 and pr.installation_id == 5
        assert pr.is_fork is False

    def test_fork_detected(self):
        pr = parse_pr_webhook("pull_request", self._pr_payload(fork=True))
        assert pr is not None and pr.is_fork is True

    def test_unhandled_event_ignored(self):
        assert parse_pr_webhook("push", self._pr_payload()) is None

    def test_payload_without_pr_ignored(self):
        assert parse_pr_webhook("pull_request", {"installation": {"id": 5}}) is None

    def test_parity_with_ci_pr_context(self):
        """SC-003: the App derives the same PR coordinates ci.py does."""
        pr = parse_pr_webhook("pull_request", self._pr_payload())
        assert (pr.repo, pr.base_sha, pr.head_sha) == ("acme/widgets", "base", "head")
