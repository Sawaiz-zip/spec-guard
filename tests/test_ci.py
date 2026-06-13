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


class TestSoloModePath:
    def test_scope_change_without_roles_warns_and_passes(self, ci_env, capsys):
        # lock.json present, no roles.yml — US4 independent test.
        base, head = setup_configured_repo(ci_env, roles=False)
        ci_env.write_event(load_event("pr_scope_change.json", base, head))
        client = FakeAnthropicClient(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.91, "HIGH", ["cloud sync"], "Added cloud sync"
                )
            }
        )
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "::error" not in captured.out
        assert "::warning file=README.md::" in captured.out
        assert "91%" in captured.out  # full classification in the annotation


class TestGovernanceConfigFromBase:
    def test_pr_cannot_rewrite_the_rules_it_is_judged_by(self, ci_env, capsys):
        """Regression (found live in sandbox E2E): a PR adding its author to
        the architect role must be judged by the BASE roles.yml, not its own."""
        repo = ci_env.repo
        repo.write(".specguard/lock.json", LOCK_JSON)
        repo.write(
            ".specguard/roles.yml",
            "roles:\n  architect: [alice]\n"
            "rules:\n  .specguard/**:\n    edit: architect\n",
        )
        base = repo.commit_all("base")
        # PR author "dev" promotes themself to architect in the PR itself.
        repo.write(
            ".specguard/roles.yml",
            "roles:\n  architect: [alice, dev]\n"
            "rules:\n  .specguard/**:\n    edit: architect\n",
        )
        head = repo.commit_all("self-promotion")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        client = FakeAnthropicClient()
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "::error file=.specguard/roles.yml::" in captured.out
        assert client.call_count == 0  # deterministic block, no API call

    def test_pr_cannot_loosen_its_own_scope_lock(self, ci_env, capsys):
        repo = ci_env.repo
        repo.write(".specguard/lock.json", LOCK_JSON)
        repo.write("README.md", "v1\n")
        base = repo.commit_all("base")
        # PR rewrites the lock to allow what it adds; base lock must win.
        repo.write(
            ".specguard/lock.json",
            LOCK_JSON.replace('"SaaS pricing", ', ""),
        )
        repo.write("README.md", "v1\nPricing: $99/mo\n")
        head = repo.commit_all("loosen lock + add pricing")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        client = FakeAnthropicClient()
        ci.main(client=client)
        # The classifier prompt must carry the BASE lock (with SaaS pricing
        # still out of scope), not the PR's edited one.
        scope_calls = [
            c for c in client.calls if c.file_path == "README.md"
        ]
        assert scope_calls, "README.md should have been classified"
        user_msg = scope_calls[0].kwargs["messages"][0]["content"]
        assert "SaaS pricing" in user_msg


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
