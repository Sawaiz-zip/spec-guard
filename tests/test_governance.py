"""Governance overlay: Spec Kit derivation + base-ref isolation (spec 004 US1).

These cover the MVP slice (T010, T011): the Spec Kit adapter derives a goal and
scope from the constitution and the touched feature specs, the multi-feature union,
constitution-only derivation, the no-truncation guarantee (FR-009), and the
base-ref isolation that stops a PR rewriting the scope it is judged by (FR-008).
Explicit-lock precedence and the parity test live with US3 (T014–T016).
"""

from __future__ import annotations

from tests.conftest import GitRepo

from specguard.governance import resolve_lock

# A hard-wrapped constitution (mirrors the real one) — the wrapping is deliberate:
# the parser must re-join continuation lines or it truncates the scope list.
CONSTITUTION = """\
# Sample Project Constitution

## Core Principles

### I. Merge-Time Enforcement Is the Security Layer

The server-side merge check is the ONLY enforcement layer that MUST be treated as
a security boundary. Local layers are advisory.

### II. Governance Overlay

SpecGuard reads existing file conventions.

## Additional Constraints & Scope Boundaries

- Explicitly out of scope for the product (decided, not deferred): web dashboard;
  own spec format or proposal workflow; forking or embedding other frameworks;
  code-vs-spec drift detection; SaaS subscription as the primary business model.
- `.specguard/**` configuration is itself protected by the role rules it defines.
"""

FEATURE_AUTH = """\
# Feature Specification: Authentication

## Requirements

- Out of scope: biometric login; hardware tokens.
"""

FEATURE_BILLING = """\
# Feature Specification: Billing

## Requirements

- Out of scope: cryptocurrency payments.
"""


def _speckit_repo(git_repo: GitRepo) -> str:
    """Commit a Spec Kit layout and return the base sha."""
    git_repo.write(".specify/memory/constitution.md", CONSTITUTION)
    git_repo.write("specs/001-auth/spec.md", FEATURE_AUTH)
    git_repo.write("specs/002-billing/spec.md", FEATURE_BILLING)
    git_repo.write("README.md", "hello")
    return git_repo.commit_all("spec kit layout")


def test_speckit_derives_goal_and_scope_out(git_repo: GitRepo) -> None:
    base = _speckit_repo(git_repo)

    lock, source = resolve_lock(git_repo.root, base, [])

    assert source == "spec-kit"
    assert lock is not None
    # Goal = project identity + first principle's opening sentence.
    assert "Merge-Time Enforcement Is the Security Layer" in lock.goal
    assert lock.goal.startswith("Sample Project")
    # The full hard-wrapped out-of-scope list is parsed (no truncation).
    assert "web dashboard" in lock.scope_out
    assert "own spec format or proposal workflow" in lock.scope_out
    assert "SaaS subscription as the primary business model" in lock.scope_out
    # The unrelated sibling bullet must NOT be swept into scope_out.
    assert not any(".specguard" in item for item in lock.scope_out)
    assert lock.locked_by == "spec-kit:.specify/memory/constitution.md"


def test_speckit_unions_scope_across_two_touched_features(git_repo: GitRepo) -> None:
    base = _speckit_repo(git_repo)

    lock, _ = resolve_lock(
        git_repo.root,
        base,
        ["specs/001-auth/spec.md", "specs/002-billing/spec.md"],
    )

    assert lock is not None
    # Constitution scope_out plus BOTH touched features' scope_out, unioned.
    assert "web dashboard" in lock.scope_out
    assert "biometric login" in lock.scope_out
    assert "hardware tokens" in lock.scope_out
    assert "cryptocurrency payments" in lock.scope_out


def test_speckit_constitution_only_when_no_feature_touched(git_repo: GitRepo) -> None:
    base = _speckit_repo(git_repo)

    lock, _ = resolve_lock(git_repo.root, base, ["README.md"])

    assert lock is not None
    # No feature dir touched ⇒ constitution alone; feature-specific items absent.
    assert "web dashboard" in lock.scope_out
    assert "biometric login" not in lock.scope_out
    assert "cryptocurrency payments" not in lock.scope_out


def test_speckit_scope_out_not_truncated(git_repo: GitRepo) -> None:
    """FR-009: a long derived scope list is preserved in full (G1 guard)."""
    base = _speckit_repo(git_repo)

    lock, _ = resolve_lock(
        git_repo.root,
        base,
        ["specs/001-auth/spec.md", "specs/002-billing/spec.md"],
    )

    assert lock is not None
    # 5 constitution items + 2 (auth) + 1 (billing) = 8 distinct items, none dropped.
    expected = {
        "web dashboard",
        "own spec format or proposal workflow",
        "forking or embedding other frameworks",
        "code-vs-spec drift detection",
        "SaaS subscription as the primary business model",
        "biometric login",
        "hardware tokens",
        "cryptocurrency payments",
    }
    assert expected.issubset(set(lock.scope_out))


def test_speckit_empty_scope_is_valid_not_a_crash(git_repo: GitRepo) -> None:
    """Constitution with a goal but no scope markers ⇒ goal + empty lists (FR-007)."""
    git_repo.write(
        ".specify/memory/constitution.md",
        "# Bare Project\n\n## Core Principles\n\n### I. Do One Thing\n\nKeep it simple.\n",
    )
    base = git_repo.commit_all("bare spec kit")

    lock, source = resolve_lock(git_repo.root, base, [])

    assert source == "spec-kit"
    assert lock is not None
    assert lock.goal.startswith("Bare Project")
    assert lock.scope_out == []
    assert lock.scope_in == []


def test_base_ref_isolation(git_repo: GitRepo) -> None:
    """FR-008: framework edits in the HEAD commit do not change the derived lock —
    derivation reads only the base ref."""
    base = _speckit_repo(git_repo)

    # A later commit rewrites the constitution's scope (an attacker-style edit).
    git_repo.write(
        ".specify/memory/constitution.md",
        CONSTITUTION.replace("web dashboard", "ANYTHING GOES NOW"),
    )
    git_repo.commit_all("tamper with scope at head")

    lock_at_base, _ = resolve_lock(git_repo.root, base, [])

    assert lock_at_base is not None
    # The base-ref derivation is unaffected by the head-commit tampering.
    assert "web dashboard" in lock_at_base.scope_out
    assert "ANYTHING GOES NOW" not in lock_at_base.scope_out


def test_plain_when_no_framework_and_no_lock(git_repo: GitRepo) -> None:
    """FR-011: a repo with neither framework nor lock is unchanged (None/plain)."""
    git_repo.write("README.md", "hello")
    base = git_repo.commit_all("plain repo")

    lock, source = resolve_lock(git_repo.root, base, ["README.md"])

    assert lock is None
    assert source == "plain"
