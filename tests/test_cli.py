"""CLI: check exit codes and output, init scaffolding, hook never-blocks matrix."""

from __future__ import annotations

import json

import pytest

from conftest import FakeAdapter, make_classification
from specguard import cli
from specguard.classifier import ClassifierError
from specguard.localreport import ADVISORY_NOTICE

LOCK = json.dumps(
    {"goal": "A CLI tool", "scope_in": ["tasks"], "scope_out": ["SaaS pricing"]}
)


@pytest.fixture
def configured_repo(git_repo, monkeypatch):
    git_repo.write("README.md", "v1\n")
    git_repo.write(".specguard/lock.json", LOCK)
    git_repo.commit_all("base")
    monkeypatch.chdir(git_repo.root)
    return git_repo


def scope_change_adapter(confidence: float = 0.93) -> FakeAdapter:
    return FakeAdapter(
        responses={
            "README.md": make_classification(
                "SCOPE_CHANGE", confidence, "HIGH", ["SaaS pricing"], "Added pricing"
            )
        }
    )


# ---------------------------------------------------------------------------
# US1: specguard check (T011)
# ---------------------------------------------------------------------------


class TestCheck:
    def test_additive_exits_zero_with_quiet_line(self, configured_repo, capsys):
        configured_repo.write("README.md", "v1 fixed typo\n")
        code = cli.main(["check"], adapter=FakeAdapter())
        out = capsys.readouterr().out
        assert code == 0
        assert "ADDITIVE" in out
        assert ADVISORY_NOTICE in out  # SC-006
        assert "baseline HEAD" in out  # FR-010 disclosure

    def test_scope_change_exits_one_with_would_block(self, configured_repo, capsys):
        configured_repo.write(
            ".specguard/roles.yml",
            "roles:\n  architect: [alice]\n"
            "rules:\n  README.md:\n    scope_changes: {approve: architect}\n",
        )
        configured_repo.commit_all("add roles")
        configured_repo.write("README.md", "v1 plus pricing\n")
        code = cli.main(["check"], adapter=scope_change_adapter())
        out = capsys.readouterr().out
        assert code == 1
        assert "SCOPE CHANGE" in out
        assert "would block until architect approves" in out  # FR-011

    def test_solo_scope_change_warns_and_exits_zero(self, configured_repo, capsys):
        configured_repo.write("README.md", "v1 plus pricing\n")
        code = cli.main(["check"], adapter=scope_change_adapter())
        out = capsys.readouterr().out
        assert code == 0  # solo mode: WARN, nothing would block
        assert "SCOPE CHANGE" in out

    def test_json_output_carries_notice_and_verdicts(self, configured_repo, capsys):
        configured_repo.write("README.md", "v1 fixed typo\n")
        code = cli.main(["check", "--json"], adapter=FakeAdapter())
        payload = json.loads(capsys.readouterr().out)
        assert code == 0
        assert payload["advisory"] is True
        assert payload["notice"] == ADVISORY_NOTICE  # SC-006 in json too
        assert payload["would_block"] is False
        assert payload["verdicts"][0]["reason"] == "additive"

    def test_no_watched_changes_message(self, configured_repo, capsys):
        adapter = FakeAdapter()
        code = cli.main(["check"], adapter=adapter)
        out = capsys.readouterr().out
        assert code == 0
        assert "no watched spec files changed" in out
        assert adapter.call_count == 0

    def test_unconfigured_repo_setup_hint(self, git_repo, monkeypatch, capsys):
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        monkeypatch.chdir(git_repo.root)
        code = cli.main(["check"], adapter=FakeAdapter())
        assert code == 0
        assert "specguard init" in capsys.readouterr().out

    def test_missing_key_exits_two_with_hint(self, configured_repo, capsys, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        configured_repo.write("README.md", "v2\n")
        code = cli.main(["check"])  # no adapter injected
        assert code == 2
        assert "ANTHROPIC_API_KEY" in capsys.readouterr().err

    def test_not_a_repo_exits_two(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        code = cli.main(["check"], adapter=FakeAdapter())
        assert code == 2
        assert "not a git repository" in capsys.readouterr().err

    def test_range_mode_matches_committed_diff(self, configured_repo, capsys):
        base = configured_repo.git("rev-parse", "HEAD")
        configured_repo.write("README.md", "v2 committed\n")
        configured_repo.commit_all("edit")
        code = cli.main(["check", "--base", base], adapter=FakeAdapter())
        assert code == 0
        assert "ADDITIVE" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# US2: specguard init (T014)
# ---------------------------------------------------------------------------


class TestInit:
    def test_interactive_init_writes_valid_lock(self, git_repo, monkeypatch, capsys):
        monkeypatch.chdir(git_repo.root)
        answers = iter(
            [
                "A web app for recipes",       # goal
                "recipes, search",             # scope_in
                "SSO, billing",                # scope_out
                "n",                           # config.yml offer
                "n",                           # roles offer
                "n",                           # workflow offer
                "n",                           # hook offer
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        code = cli.main(["init"])
        assert code == 0
        lock = json.loads((git_repo.root / ".specguard/lock.json").read_text())
        assert lock["goal"] == "A web app for recipes"
        assert lock["scope_in"] == ["recipes", "search"]
        assert lock["scope_out"] == ["SSO", "billing"]
        out = capsys.readouterr().out
        assert ".specguard/lock.json" in out
        assert "specguard check" in out  # next step named

    def test_goal_reprompted_until_nonempty(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo.root)
        answers = iter(["", "", "Real goal", "", "", "n", "n", "n", "n"])
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        assert cli.main(["init"]) == 0
        lock = json.loads((git_repo.root / ".specguard/lock.json").read_text())
        assert lock["goal"] == "Real goal"

    def test_refuses_existing_lock_without_force(self, git_repo, monkeypatch, capsys):
        monkeypatch.chdir(git_repo.root)
        git_repo.write(".specguard/lock.json", LOCK)
        code = cli.main(["init", "--yes"])
        assert code == 2
        assert "--force" in capsys.readouterr().err

    def test_force_overwrites(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo.root)
        git_repo.write(".specguard/lock.json", LOCK)
        assert cli.main(["init", "--yes", "--force"]) == 0
        lock = json.loads((git_repo.root / ".specguard/lock.json").read_text())
        assert lock["goal"].startswith("TODO")

    def test_yes_mode_skips_optional_files(self, git_repo, monkeypatch, capsys):
        monkeypatch.chdir(git_repo.root)
        code = cli.main(["init", "--yes"])
        assert code == 0
        assert (git_repo.root / ".specguard/lock.json").exists()
        assert not (git_repo.root / ".specguard/config.yml").exists()
        assert not (git_repo.root / ".specguard/roles.yml").exists()
        assert "skipped" in capsys.readouterr().out

    def test_roles_offer_writes_valid_roles(self, git_repo, monkeypatch):
        monkeypatch.chdir(git_repo.root)
        answers = iter(
            [
                "Goal",      # goal
                "",          # scope_in
                "",          # scope_out
                "n",         # config offer
                "y",         # roles offer
                "",          # role name → default architect
                "alice, bob",  # members
                "n",         # workflow
                "n",         # hook
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _: next(answers))
        assert cli.main(["init"]) == 0
        from specguard.config import load_roles

        roles = load_roles(git_repo.root)
        assert roles is not None
        assert roles.roles["architect"] == ["alice", "bob"]

    def test_not_a_repo_exits_two(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert cli.main(["init", "--yes"]) == 2
        assert "not a git repository" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# US3: hook never blocks (T017)
# ---------------------------------------------------------------------------


class TestHookNeverBlocks:
    def test_block_verdict_still_exits_zero(self, configured_repo, capsys):
        configured_repo.write(
            ".specguard/roles.yml",
            "roles:\n  architect: [alice]\n"
            "rules:\n  README.md:\n    scope_changes: {approve: architect}\n",
        )
        configured_repo.commit_all("roles")
        configured_repo.write("README.md", "pricing!\n")
        configured_repo.git("add", "README.md")
        code = cli.main(["check", "--hook"], adapter=scope_change_adapter())
        out = capsys.readouterr().out
        assert code == 0  # SC-003: warned, never blocked
        assert "SCOPE CHANGE" in out

    def test_classifier_error_exits_zero(self, configured_repo, capsys):
        configured_repo.write("README.md", "v2\n")
        configured_repo.git("add", "README.md")
        adapter = FakeAdapter(responses={"README.md": ClassifierError("down")})
        code = cli.main(["check", "--hook"], adapter=adapter)
        assert code == 0

    def test_missing_key_exits_zero_with_skip_notice(
        self, configured_repo, capsys, monkeypatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        configured_repo.write("README.md", "v2\n")
        configured_repo.git("add", "README.md")
        code = cli.main(["check", "--hook"])  # no adapter
        out = capsys.readouterr().out
        assert code == 0
        assert "could not classify" in out

    def test_config_error_exits_zero(self, git_repo, monkeypatch, capsys):
        git_repo.write(".specguard/lock.json", "{nope")
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        git_repo.write("README.md", "v2\n")
        git_repo.git("add", "README.md")
        monkeypatch.chdir(git_repo.root)
        code = cli.main(["check", "--hook"], adapter=FakeAdapter())
        assert code == 0

    def test_timeout_exits_zero_with_skip_notice(
        self, configured_repo, capsys, monkeypatch
    ):
        import time

        class SlowAdapter(FakeAdapter):
            def classify(self, lock, changed, config):
                time.sleep(2)
                return super().classify(lock, changed, config)

        monkeypatch.setenv("SPECGUARD_HOOK_TIMEOUT", "0.2")
        configured_repo.write("README.md", "v2\n")
        configured_repo.git("add", "README.md")
        code = cli.main(["check", "--hook"], adapter=SlowAdapter())
        out = capsys.readouterr().out
        assert code == 0
        assert "timed out" in out

    def test_nothing_staged_is_silent(self, configured_repo, capsys):
        configured_repo.write("README.md", "unstaged only\n")  # NOT added
        code = cli.main(["check", "--hook"], adapter=FakeAdapter())
        assert code == 0
        assert capsys.readouterr().out == ""  # zero friction (constitution IV)

    def test_unconfigured_repo_hook_is_silent(self, git_repo, monkeypatch, capsys):
        git_repo.write("README.md", "v1\n")
        git_repo.commit_all("base")
        monkeypatch.chdir(git_repo.root)
        code = cli.main(["check", "--hook"], adapter=FakeAdapter())
        assert code == 0
        assert capsys.readouterr().out == ""
