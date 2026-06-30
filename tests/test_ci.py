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


def _no_network_approvals(monkeypatch, reviews=None, comments=None) -> None:
    """Neutralize the live GitHub reads in ci.get_approvals; inject canned data."""
    monkeypatch.setattr(ci, "fetch_approvals", lambda *a, **k: list(reviews or []))
    monkeypatch.setattr(ci, "fetch_commit_time", lambda *a, **k: "2020-01-01T00:00:00Z")
    monkeypatch.setattr(
        ci, "fetch_comment_approvals", lambda *a, **k: list(comments or [])
    )


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
        _no_network_approvals(monkeypatch)
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

    def _scope_change_with(self, ci_env, monkeypatch, comments):
        from specguard.models import Approval

        base, head = setup_configured_repo(ci_env, roles=True)
        ci_env.write_event(load_event("pr_scope_change.json", base, head))
        _no_network_approvals(
            monkeypatch,
            comments=[
                Approval(reviewer_login=login, state="APPROVED", source="comment-command")
                for login in comments
            ],
        )
        client = FakeAnthropicClient(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.93, "HIGH", ["SaaS pricing"], "Added pricing tiers"
                )
            }
        )
        return ci.main(client=client)

    def test_comment_approval_from_authorized_login_clears_block(
        self, ci_env, capsys, monkeypatch
    ):
        # alice is the architect; her `/specguard approve` comment clears the block.
        exit_code = self._scope_change_with(ci_env, monkeypatch, ["alice"])
        assert exit_code == 0
        assert "::error" not in capsys.readouterr().out

    def test_comment_approval_from_unauthorized_login_does_not_clear(
        self, ci_env, capsys, monkeypatch
    ):
        # mallory is not in the architect role — the block stands (FR-003).
        exit_code = self._scope_change_with(ci_env, monkeypatch, ["mallory"])
        assert exit_code == 1
        assert "::error file=README.md::" in capsys.readouterr().out


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


class TestMultiScope:
    """007 US2: end-to-end through ci.py with two package scopes."""

    def setup_monorepo(self, repo):
        repo.write(
            ".specguard/config.yml",
            'watch: ["**/README.md", ".specguard/**", "**/.specguard/**"]\n',
        )
        repo.write(
            "packages/api/.specguard/lock.json",
            json.dumps({"goal": "API service", "scope_in": [], "scope_out": ["billing"]}),
        )
        repo.write(
            "packages/web/.specguard/lock.json",
            json.dumps({"goal": "Web app", "scope_in": [], "scope_out": ["payments"]}),
        )
        repo.write("packages/api/README.md", "# API\n")
        repo.write("packages/web/README.md", "# Web\n")
        base = repo.commit_all("base")
        repo.write("packages/api/README.md", "# API\nBilling integration coming.\n")
        repo.write("packages/web/README.md", "# Web\nJust a typo fxi.\n")
        head = repo.commit_all("two-package change")
        return base, head

    def test_independent_verdicts_per_scope(self, ci_env, capsys):
        base, head = self.setup_monorepo(ci_env.repo)
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        client = FakeAnthropicClient(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.95, "HIGH", ["billing"], "billing mention"
                ),
            },
            default=make_classification("ADDITIVE", 0.95),
        )
        exit_code = ci.main(client=client)
        captured = capsys.readouterr()
        # Solo mode (no roles.yml in either scope) -> the api scope-change warns,
        # never blocks; the web typo fix passes quietly. Exit 0 either way.
        assert exit_code == 0
        assert "::warning file=packages/api/README.md::" in captured.out
        assert "billing" in captured.out
        summary = ci_env.summary_path.read_text()
        assert "packages/api/README.md" in summary
        assert "packages/web/README.md" in summary

    def test_scope_protected_path_uses_that_scopes_own_roles(self, ci_env, capsys):
        repo = ci_env.repo
        repo.write(
            ".specguard/config.yml",
            'watch: ["**/README.md", ".specguard/**", "**/.specguard/**"]\n',
        )
        repo.write(
            "packages/api/.specguard/lock.json",
            json.dumps({"goal": "API", "scope_in": [], "scope_out": []}),
        )
        repo.write(
            "packages/api/.specguard/roles.yml",
            "roles:\n  api-team: [alice]\nrules:\n  .specguard/**:\n    edit: api-team\n",
        )
        repo.write("packages/api/README.md", "v1\n")
        base = repo.commit_all("base")
        # "dev" (not api-team) edits the scope's OWN protected roles.yml.
        repo.write(
            "packages/api/.specguard/roles.yml",
            "roles:\n  api-team: [alice, dev]\nrules:\n  .specguard/**:\n    edit: api-team\n",
        )
        head = repo.commit_all("self-promotion")
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        exit_code = ci.main(client=FakeAnthropicClient())
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "::error file=packages/api/.specguard/roles.yml::" in captured.out


class TestAuditExport:
    def test_writes_one_entry_per_verdict(self, ci_env, capsys, tmp_path, monkeypatch):
        base, head = setup_configured_repo(ci_env)
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        audit_path = tmp_path / "audit.json"
        monkeypatch.setenv("SPECGUARD_AUDIT_PATH", str(audit_path))
        _no_network_approvals(monkeypatch)
        client = FakeAnthropicClient(
            responses={"README.md": make_classification("ADDITIVE", 0.97)}
        )
        exit_code = ci.main(client=client)
        assert exit_code == 0
        entries = json.loads(audit_path.read_text())
        assert len(entries) == 1
        assert entries[0]["file"] == "README.md"
        assert entries[0]["outcome"] == "PASS"
        assert entries[0]["repo"] == "acme/widgets"

    def test_no_env_var_means_no_file_written(self, ci_env, capsys, tmp_path, monkeypatch):
        monkeypatch.delenv("SPECGUARD_AUDIT_PATH", raising=False)
        base, head = setup_configured_repo(ci_env)
        ci_env.write_event(load_event("pr_typo_fix.json", base, head))
        ci.main(client=FakeAnthropicClient())
        assert not (tmp_path / "audit.json").exists()
