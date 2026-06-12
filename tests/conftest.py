"""Shared fixtures: FakeAnthropicClient, sample configs, git repo + event factories.

The fake mirrors the exact slice of the Anthropic SDK the classifier uses:
`client.messages.parse(...)` returning an object with `.parsed_output`.
No test in this suite touches the network or needs an API key.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from specguard.models import (
    Classification,
    Config,
    PRContext,
    RolesConfig,
    ScopeLock,
)

# ---------------------------------------------------------------------------
# FakeAnthropicClient
# ---------------------------------------------------------------------------


@dataclass
class FakeParsedResponse:
    """Shape-compatible stand-in for anthropic.types.ParsedMessage."""

    parsed_output: Classification | None
    text: str = ""


@dataclass
class _RecordedCall:
    kwargs: dict[str, Any]
    file_path: str | None


class _FakeMessages:
    def __init__(self, client: FakeAnthropicClient) -> None:
        self._client = client

    def parse(self, **kwargs: Any) -> FakeParsedResponse:
        return self._client._handle_parse(kwargs)


class FakeAnthropicClient:
    """Canned classifier responses keyed by file path.

    `responses` values may be:
      - Classification: returned as a parsed response
      - Exception: raised (simulates API errors)
      - str: returned as an unparseable text response (parsed_output=None),
        which triggers the classifier's re-ask path
      - list of the above: consumed one entry per call to that path
    `default` is used when a path has no entry.
    """

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        default: Any | None = None,
    ) -> None:
        self.responses = dict(responses or {})
        self.default = default if default is not None else _additive()
        self.calls: list[_RecordedCall] = []
        self.messages = _FakeMessages(self)

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def _handle_parse(self, kwargs: dict[str, Any]) -> FakeParsedResponse:
        file_path = _extract_file_path(kwargs)
        self.calls.append(_RecordedCall(kwargs=kwargs, file_path=file_path))

        scripted = (
            self.responses.get(file_path, self.default)
            if file_path is not None
            else self.default
        )
        if isinstance(scripted, list):
            scripted = scripted.pop(0) if scripted else self.default
        if isinstance(scripted, Exception):
            raise scripted
        if isinstance(scripted, str):
            return FakeParsedResponse(parsed_output=None, text=scripted)
        return FakeParsedResponse(parsed_output=scripted)


def _extract_file_path(kwargs: dict[str, Any]) -> str | None:
    for message in kwargs.get("messages", []):
        content = message.get("content", "")
        if isinstance(content, str):
            match = re.search(r'<file path="([^"]+)"', content)
            if match:
                return match.group(1)
    return None


def _additive() -> Classification:
    return Classification(
        classification="ADDITIVE",
        confidence=0.95,
        risk_level="LOW",
        out_of_scope_topics=[],
        summary="Wording clarification within scope",
        explanation="The change only rewords existing in-scope material.",
    )


def make_classification(
    classification: str = "ADDITIVE",
    confidence: float = 0.95,
    risk_level: str = "LOW",
    out_of_scope_topics: list[str] | None = None,
    summary: str = "summary",
    explanation: str = "explanation",
) -> Classification:
    return Classification(
        classification=classification,  # type: ignore[arg-type]
        confidence=confidence,
        risk_level=risk_level,  # type: ignore[arg-type]
        out_of_scope_topics=out_of_scope_topics or [],
        summary=summary,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Sample config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_lock() -> ScopeLock:
    return ScopeLock(
        goal="A local CLI tool for tracking personal todo lists",
        scope_in=["task creation", "task completion", "local file storage"],
        scope_out=["SaaS pricing", "cloud sync", "SSO"],
    )


@pytest.fixture
def sample_config() -> Config:
    return Config()


@pytest.fixture
def sample_roles() -> RolesConfig:
    return RolesConfig.model_validate(
        {
            "roles": {
                "architect": ["alice"],
                "maintainers": ["bob", "charlie"],
            },
            "rules": {
                ".specguard/**": {"edit": "architect"},
                "README.md": {"scope_changes": {"approve": "architect"}},
            },
        }
    )


@pytest.fixture
def pr_context() -> PRContext:
    return PRContext(
        pr_number=7,
        base_sha="base000",
        head_sha="head000",
        author_login="dev",
        is_fork=False,
        repo="acme/widgets",
    )


@pytest.fixture
def fake_client() -> FakeAnthropicClient:
    return FakeAnthropicClient()


# ---------------------------------------------------------------------------
# Git repo factory (for gitdiff + ci tests)
# ---------------------------------------------------------------------------


@dataclass
class GitRepo:
    root: Path
    base_sha: str = ""
    head_sha: str = ""

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def write(self, rel_path: str, content: str) -> None:
        path = self.root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def delete(self, rel_path: str) -> None:
        (self.root / rel_path).unlink()

    def commit_all(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-m", message, "--allow-empty")
        return self.git("rev-parse", "HEAD")


@pytest.fixture
def git_repo(tmp_path: Path) -> GitRepo:
    """Empty initialized repo with identity configured; tests add commits."""
    repo = GitRepo(root=tmp_path / "repo")
    repo.root.mkdir()
    repo.git("init", "-q", "-b", "main")
    repo.git("config", "user.name", "Test User")
    repo.git("config", "user.email", "test@example.com")
    return repo


# ---------------------------------------------------------------------------
# Event payload factory (pull_request / pull_request_review)
# ---------------------------------------------------------------------------


def make_pr_event(
    base_sha: str,
    head_sha: str,
    author: str = "dev",
    repo: str = "acme/widgets",
    head_repo: str | None = None,
    pr_number: int = 7,
) -> dict[str, Any]:
    return {
        "pull_request": {
            "number": pr_number,
            "user": {"login": author},
            "base": {"sha": base_sha, "repo": {"full_name": repo}},
            "head": {
                "sha": head_sha,
                "repo": {"full_name": head_repo or repo, "fork": head_repo is not None},
            },
        }
    }


@dataclass
class CIEnvironment:
    """Everything a ci.main() invocation needs, pre-wired to a tmp git repo."""

    repo: GitRepo
    event_path: Path
    summary_path: Path
    env: dict[str, str] = field(default_factory=dict)

    def write_event(self, event: dict[str, Any]) -> None:
        self.event_path.write_text(json.dumps(event))


@pytest.fixture
def ci_env(
    git_repo: GitRepo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CIEnvironment:
    event_path = tmp_path / "event.json"
    summary_path = tmp_path / "summary.md"
    summary_path.write_text("")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/widgets")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")
    monkeypatch.chdir(git_repo.root)
    return CIEnvironment(repo=git_repo, event_path=event_path, summary_path=summary_path)
