"""Governance overlay: Spec Kit derivation + base-ref isolation (spec 004 US1).

These cover the MVP slice (T010, T011): the Spec Kit adapter derives a goal and
scope from the constitution and the touched feature specs, the multi-feature union,
constitution-only derivation, the no-truncation guarantee (FR-009), and the
base-ref isolation that stops a PR rewriting the scope it is judged by (FR-008).
Explicit-lock precedence and the parity test live with US3 (T014–T016).
"""

from __future__ import annotations

import json

import pytest

from conftest import FakeAdapter, GitRepo, make_classification
from specguard.config import ConfigError
from specguard.engine import evaluate_pr
from specguard.gitdiff import diff_from_contents
from specguard.governance import resolve_lock
from specguard.localcheck import load_baseline_governance
from specguard.models import Approval, Config, PRContext, ScopeLock

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


# ---------------------------------------------------------------------------
# User Story 3 — explicit lock & plain mode still win (T014–T016)
# ---------------------------------------------------------------------------

EXPLICIT_LOCK = {
    "goal": "A hand-authored goal that overrides the framework",
    "scope_in": ["explicitly allowed topic"],
    "scope_out": ["explicitly forbidden topic"],
}


def test_explicit_lock_short_circuits_spec_kit(git_repo: GitRepo) -> None:
    """FR-002: an explicit lock wins and the framework files are not consulted."""
    git_repo.write(".specify/memory/constitution.md", CONSTITUTION)
    git_repo.write(".specguard/lock.json", json.dumps(EXPLICIT_LOCK))
    base = git_repo.commit_all("spec kit + explicit lock")

    lock, source = resolve_lock(git_repo.root, base, [])

    assert source == "explicit-lock"
    assert lock is not None
    assert lock.goal == EXPLICIT_LOCK["goal"]
    assert lock.scope_out == ["explicitly forbidden topic"]
    # Nothing derived from the constitution leaked in.
    assert "web dashboard" not in lock.scope_out
    assert "Merge-Time Enforcement" not in lock.goal


def test_plain_repo_governance_is_unconfigured(git_repo: GitRepo) -> None:
    """FR-011: the unconfigured signal the SETUP_HINT path keys on is preserved —
    a plain repo yields lock=None / source='plain' through load_baseline_governance."""
    git_repo.write("README.md", "hello")
    base = git_repo.commit_all("plain repo")

    governance = load_baseline_governance(git_repo.root, base, ["README.md"])

    assert governance.lock is None
    assert governance.source == "plain"


def _no_approvals() -> list[Approval]:
    return []


def test_parity_derived_equals_hand_authored_and_ci_equals_local(
    git_repo: GitRepo,
) -> None:
    """SC-002 / analyze F1: a derived lock equals an equivalent hand-authored lock
    AND the CI route equals the local route — same lock, same verdict."""
    base = _speckit_repo(git_repo)
    changed_paths = ["specs/001-auth/spec.md"]

    # CI route: ci.py calls resolve_lock directly.
    ci_lock, ci_source = resolve_lock(git_repo.root, base, changed_paths)
    # Local route: cli/mcp go through load_baseline_governance.
    local = load_baseline_governance(git_repo.root, base, changed_paths)

    assert ci_source == local.source == "spec-kit"
    assert ci_lock is not None and local.lock is not None
    # F1 guard: identical base_ref + changed_paths ⇒ identical derived lock.
    assert ci_lock == local.lock

    # Equivalent hand-authored lock with the same values.
    hand = ScopeLock(
        goal=ci_lock.goal,
        scope_in=list(ci_lock.scope_in),
        scope_out=list(ci_lock.scope_out),
    )

    config = Config()
    pr = PRContext(
        pr_number=7, base_sha="base", head_sha="head",
        author_login="dev", is_fork=False, repo="acme/widgets",
    )
    changed = diff_from_contents("README.md", "old goal text", "new out-of-scope text")
    scope_change = make_classification(
        "SCOPE_CHANGE", 0.93, "HIGH", ["something out of scope"]
    )

    def verdict_for(lock: ScopeLock):
        return evaluate_pr(
            [changed], lock, config, None, pr,
            FakeAdapter(default=scope_change), _no_approvals,
        )[0]

    derived_verdict = verdict_for(ci_lock)
    hand_verdict = verdict_for(hand)

    assert derived_verdict.classification == hand_verdict.classification
    assert derived_verdict.outcome == hand_verdict.outcome
    assert derived_verdict.reason == hand_verdict.reason


# ---------------------------------------------------------------------------
# User Story 2 — OpenSpec derivation (T018)
# ---------------------------------------------------------------------------

OPENSPEC_PROJECT = """\
# Widgets Platform

A platform for managing widgets across many teams.
"""

PROPOSAL_AUTH = """\
# Add Authentication

## Why

Users need to sign in.

## What Changes

- add JWT login
- add session management

## Out of Scope

- biometric auth
- hardware security keys
"""

PROPOSAL_BILLING = """\
# Add Billing

## What Changes

- add invoices

## Non-Goals

- cryptocurrency payments
"""


def _openspec_repo(git_repo: GitRepo) -> str:
    git_repo.write("openspec/project.md", OPENSPEC_PROJECT)
    git_repo.write("openspec/changes/add-auth/proposal.md", PROPOSAL_AUTH)
    git_repo.write("openspec/changes/add-billing/proposal.md", PROPOSAL_BILLING)
    git_repo.write("README.md", "hello")
    return git_repo.commit_all("openspec layout")


def test_openspec_derives_from_touched_proposal(git_repo: GitRepo) -> None:
    base = _openspec_repo(git_repo)

    lock, source = resolve_lock(
        git_repo.root, base, ["openspec/changes/add-auth/proposal.md"]
    )

    assert source == "openspec"
    assert lock is not None
    assert lock.goal.startswith("Widgets Platform")
    assert "add JWT login" in lock.scope_in
    assert "add session management" in lock.scope_in
    assert "biometric auth" in lock.scope_out
    assert "hardware security keys" in lock.scope_out
    # The billing proposal was not touched, so its items are absent.
    assert "add invoices" not in lock.scope_in
    assert lock.locked_by == "openspec:openspec/project.md"


def test_openspec_unions_touched_proposals(git_repo: GitRepo) -> None:
    base = _openspec_repo(git_repo)

    lock, _ = resolve_lock(
        git_repo.root,
        base,
        [
            "openspec/changes/add-auth/proposal.md",
            "openspec/changes/add-billing/proposal.md",
        ],
    )

    assert lock is not None
    assert {"add JWT login", "add session management", "add invoices"}.issubset(
        set(lock.scope_in)
    )
    assert {"biometric auth", "hardware security keys", "cryptocurrency payments"}.issubset(
        set(lock.scope_out)
    )


def test_openspec_falls_back_to_first_change_dir(git_repo: GitRepo) -> None:
    """No change dir touched ⇒ the lexicographically-first proposal governs (R3)."""
    base = _openspec_repo(git_repo)

    # README.md touches no openspec/changes/<id>/ directory.
    lock, source = resolve_lock(git_repo.root, base, ["README.md"])

    assert source == "openspec"
    assert lock is not None
    # 'add-auth' sorts before 'add-billing', so its scope governs deterministically.
    assert "add JWT login" in lock.scope_in
    assert "add invoices" not in lock.scope_in


# ---------------------------------------------------------------------------
# Polish — degrade & error handling (T020)
# ---------------------------------------------------------------------------


def test_malformed_framework_file_raises_configerror(git_repo: GitRepo) -> None:
    """FR-007: a framework file that is not valid UTF-8 fails loudly (ConfigError),
    like a malformed lock.json — never a raw traceback / silent pass."""
    path = git_repo.root / ".specify/memory/constitution.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# Title\n\xff\xfe not valid utf-8 \x80\n")
    base = git_repo.commit_all("garbled constitution")

    with pytest.raises(ConfigError):
        resolve_lock(git_repo.root, base, [])


def test_framework_without_derivable_goal_degrades_to_plain(git_repo: GitRepo) -> None:
    """FR-007: Spec Kit detected but no goal derivable (no H1) ⇒ fall through to
    plain rather than crash or lock against nothing."""
    git_repo.write(
        ".specify/memory/constitution.md", "no headings here, just prose.\n"
    )
    base = git_repo.commit_all("goalless constitution")

    lock, source = resolve_lock(git_repo.root, base, [])

    assert lock is None
    assert source == "plain"


def test_spec_kit_wins_over_openspec(git_repo: GitRepo) -> None:
    """Precedence: when both frameworks are present, Spec Kit governs (R4)."""
    git_repo.write(".specify/memory/constitution.md", CONSTITUTION)
    git_repo.write("openspec/project.md", OPENSPEC_PROJECT)
    git_repo.write("openspec/changes/add-auth/proposal.md", PROPOSAL_AUTH)
    base = git_repo.commit_all("both frameworks")

    lock, source = resolve_lock(git_repo.root, base, [])

    assert source == "spec-kit"
    assert lock is not None
    assert "Merge-Time Enforcement Is the Security Layer" in lock.goal
