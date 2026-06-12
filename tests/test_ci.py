"""ci.py end-to-end against fixture event payloads in a temporary git repo."""

from __future__ import annotations

import json
from pathlib import Path

from conftest import CIEnvironment, FakeAnthropicClient, make_classification
from specguard import ci

EVENTS = Path(__file__).parent / "fixtures" / "events"

LOCK_JSON = json.dumps(
    {
        "goal": "A local CLI tool for tracking personal todo lists",
        "scope_in": ["task creation", "local file storage"],
        "scope_out": ["SaaS pricing", "cloud sync"],
    }
)


def load_event(name: str, base_sha: str, head_sha: str) -> dict:
    text = (EVENTS / name).read_text()
    return json.loads(text.replace("BASE_SHA", base_sha).replace("HEAD_SHA", head_sha))


def setup_configured_repo(env: CIEnvironment, roles: bool = False) -> tuple[str, str]:
    """Two commits: base with config + README, head with a README edit."""
    repo = env.repo
    repo.write(".specguard/lock.json", LOCK_JSON)
    if roles:
        repo.write(
            ".specguard/roles.yml",
            "roles:\n  architect: [alice]\n"
            "rules:\n  README.md:\n    scope_changes: {approve: architect}\n",
        )
    repo.write("README.md", "hello wrld\n")
    base = repo.commit_all("base")
    repo.write("README.md", "hello world\n")
    head = repo.commit_all("edit readme")
    return base, head


class TestAdditivePath:
    def test_typo_fix_exits_zero_with_no_annotations(self, ci_env, capsys):
        base, head = setup_configured_repo(ci_env)
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        client = FakeAnthropicClient(
            responses={"README.md": make_classification("ADDITIVE", 0.97)}
        )
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "::error" not in captured.out
        assert "::warning" not in captured.out
        summary = ci_env.summary_path.read_text()
        assert "ADDITIVE" in summary
        assert summary.count("README.md") == 1

    def test_review_event_handled_identically(self, ci_env, capsys):
        base, head = setup_configured_repo(ci_env)
        ci_env.write_event(load_event("pr_typo_fix_review.json", base, head))
        exit_code = ci.main(client=FakeAnthropicClient())
        assert exit_code == 0
        assert "::error" not in capsys.readouterr().out


class TestScopeChangePath:
    def test_scope_change_blocks_with_error_annotation(self, ci_env, capsys, monkeypatch):
        base, head = setup_configured_repo(ci_env, roles=True)
        ci_env.write_event(load_event("pr_scope_change.json", base, head))
        monkeypatch.setattr(ci, "fetch_approvals", lambda *a, **k: [])
        client = FakeAnthropicClient(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.93, "HIGH", ["SaaS pricing"], "Added pricing tiers"
                )
            }
        )
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "::error file=README.md::" in captured.out
        assert "93%" in captured.out
        assert "SaaS pricing" in captured.out
        assert "architect" in captured.out
        summary = ci_env.summary_path.read_text()
        assert "Changes requested" in summary


class TestForkPath:
    def test_fork_pr_skips_with_warning(self, ci_env, capsys):
        ci_env.write_event(load_event("pr_fork.json", "x", "y"))
        exit_code = ci.main(client=FakeAnthropicClient())
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "::warning" in captured.out
        assert "fork" in captured.out.lower()


class TestUnconfiguredAndErrors:
    def test_no_specguard_dir_passes_with_setup_notice(self, ci_env, capsys):
        repo = ci_env.repo
        repo.write("README.md", "v1\n")
        base = repo.commit_all("base")
        repo.write("README.md", "v2\n")
        head = repo.commit_all("head")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        exit_code = ci.main(client=FakeAnthropicClient())
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "::notice" in captured.out
        assert "lock.json" in captured.out

    def test_malformed_lock_exits_two_with_error(self, ci_env, capsys):
        repo = ci_env.repo
        repo.write(".specguard/lock.json", "{not json")
        repo.write("README.md", "v1\n")
        base = repo.commit_all("base")
        repo.write("README.md", "v2\n")
        head = repo.commit_all("head")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        exit_code = ci.main(client=FakeAnthropicClient())
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "::error" in captured.out
        assert "lock.json" in captured.out

    def test_no_watched_files_changed_passes(self, ci_env, capsys):
        repo = ci_env.repo
        repo.write(".specguard/lock.json", LOCK_JSON)
        repo.write("src/main.py", "print('v1')\n")
        base = repo.commit_all("base")
        repo.write("src/main.py", "print('v2')\n")
        head = repo.commit_all("head")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        client = FakeAnthropicClient()
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert client.call_count == 0
        assert "no watched spec files" in captured.out
