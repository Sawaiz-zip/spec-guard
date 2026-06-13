"""Engine verdict-pipeline scenarios via FakeAdapter (no network)."""

from __future__ import annotations

from conftest import FakeAdapter, make_classification
from specguard.classifier import ClassifierError
from specguard.engine import evaluate_pr
from specguard.gitdiff import diff_from_contents
from specguard.models import Approval, Config

CHANGED_README = [diff_from_contents("README.md", "hello wrld\n", "hello world\n")]


def no_approvals() -> list[Approval]:
    return []


# ---------------------------------------------------------------------------
# US2: additive changes pass silently (T019)
# ---------------------------------------------------------------------------


class TestAdditive:
    def test_additive_high_confidence_passes(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("ADDITIVE", 0.95)}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert len(verdicts) == 1
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "additive"
        assert verdicts[0].classification is not None
        assert verdicts[0].required_approver_roles == []

    def test_additive_low_confidence_still_passes(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("ADDITIVE", 0.55)}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "additive"
        assert verdicts[0].classification.confidence == 0.55

    def test_additive_in_solo_mode_passes(
        self, sample_lock, sample_config, pr_context
    ):
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, None, pr_context,
            FakeAdapter(), no_approvals,
        )
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "additive"

    def test_one_verdict_per_changed_file(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        changed = [
            diff_from_contents("README.md", "a\n", "b\n"),
            diff_from_contents("ARCHITECTURE.md", "c\n", "d\n"),
        ]
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr_context,
            FakeAdapter(), no_approvals,
        )
        assert [v.file for v in verdicts] == ["README.md", "ARCHITECTURE.md"]
        assert all(v.outcome == "PASS" for v in verdicts)


# ---------------------------------------------------------------------------
# US1: scope change blocked until authorized approval
# ---------------------------------------------------------------------------


class TestScopeChange:
    def test_high_confidence_unapproved_blocks(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={
                "README.md": make_classification(
                    "SCOPE_CHANGE", 0.94, "HIGH", ["SaaS pricing"], "Added pricing"
                )
            }
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "BLOCK"
        assert verdicts[0].reason == "scope_change_unapproved"
        assert verdicts[0].required_approver_roles == ["architect"]

    def test_qualified_approval_flips_to_pass(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.94, "HIGH")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client,
            lambda: [Approval(reviewer_login="alice", state="APPROVED")],
        )
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "scope_change_approved"

    def test_unqualified_approval_still_blocks(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.94, "HIGH")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client,
            lambda: [Approval(reviewer_login="bob", state="APPROVED")],  # not architect
        )
        assert verdicts[0].outcome == "BLOCK"

    def test_below_threshold_warns_never_blocks(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.60, "MEDIUM")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "WARN"
        assert verdicts[0].reason == "scope_change_low_confidence"

    def test_custom_threshold_respected(
        self, sample_lock, sample_roles, pr_context
    ):
        config = Config(block_threshold=0.9)
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.85, "HIGH")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "WARN"

    def test_no_approver_rule_for_path_warns(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        # ARCHITECTURE.md has no scope_changes rule in sample_roles: blocking
        # would leave no approval escape hatch, so the engine warns.
        changed = [diff_from_contents("ARCHITECTURE.md", "a\n", "b\n")]
        client = FakeAdapter(
            responses={"ARCHITECTURE.md": make_classification("SCOPE_CHANGE", 0.95, "HIGH")}
        )
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "WARN"


# ---------------------------------------------------------------------------
# US3: protected file edited by unauthorized identity (T023)
# ---------------------------------------------------------------------------


class TestProtectedViolation:
    def test_unauthorized_author_hard_blocked_without_api_call(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        # pr_context.author_login == "dev", not in the architect role.
        changed = [diff_from_contents(".specguard/roles.yml", "a\n", "b\n")]
        client = FakeAdapter()
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "BLOCK"
        assert verdicts[0].reason == "protected_violation"
        assert verdicts[0].classification is None  # deterministic — no LLM verdict
        assert client.call_count == 0

    def test_authorized_author_proceeds_to_classification(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        pr = pr_context.model_copy(update={"author_login": "alice"})  # architect
        changed = [diff_from_contents(".specguard/roles.yml", "a\n", "b\n")]
        client = FakeAdapter(
            responses={".specguard/roles.yml": make_classification("ADDITIVE", 0.9)}
        )
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "additive"
        assert client.call_count == 1

    def test_protected_block_has_no_approval_escape(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        # Even an architect approval does not unblock a protected violation.
        changed = [diff_from_contents(".specguard/config.yml", "a\n", "b\n")]
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr_context,
            FakeAdapter(),
            lambda: [Approval(reviewer_login="alice", state="APPROVED")],
        )
        assert verdicts[0].outcome == "BLOCK"
        assert verdicts[0].reason == "protected_violation"


# ---------------------------------------------------------------------------
# US4: solo developer warn mode (T027)
# ---------------------------------------------------------------------------


class TestSoloMode:
    def test_high_confidence_scope_change_warns_not_blocks(
        self, sample_lock, sample_config, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.90, "HIGH")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, None, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "WARN"
        # The full classification still rides along for the annotation.
        assert verdicts[0].classification is not None
        assert verdicts[0].classification.confidence == 0.90

    def test_low_confidence_scope_change_stays_warn(
        self, sample_lock, sample_config, pr_context
    ):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 0.50, "MEDIUM")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, None, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "WARN"

    def test_solo_mode_never_blocks(self, sample_lock, sample_config, pr_context):
        client = FakeAdapter(
            responses={"README.md": make_classification("SCOPE_CHANGE", 1.0, "HIGH")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, sample_config, None, pr_context,
            client, no_approvals,
        )
        assert all(v.outcome != "BLOCK" for v in verdicts)


# ---------------------------------------------------------------------------
# Error policy: classifier failures (T028)
# ---------------------------------------------------------------------------


class TestOnErrorPolicy:
    def test_on_error_warn_passes_with_classifier_error_reason(
        self, sample_lock, sample_roles, pr_context
    ):
        config = Config(on_error="warn")
        client = FakeAdapter(
            responses={"README.md": ClassifierError("schema exhausted")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "PASS"
        assert verdicts[0].reason == "classifier_error"
        assert verdicts[0].classification is None

    def test_on_error_fail_blocks(self, sample_lock, sample_roles, pr_context):
        config = Config(on_error="fail")
        client = FakeAdapter(
            responses={"README.md": ClassifierError("vendor outage")}
        )
        verdicts = evaluate_pr(
            CHANGED_README, sample_lock, config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].outcome == "BLOCK"
        assert verdicts[0].reason == "classifier_error"

    def test_error_on_one_file_does_not_poison_others(
        self, sample_lock, sample_config, sample_roles, pr_context
    ):
        changed = [
            diff_from_contents("README.md", "a\n", "b\n"),
            diff_from_contents("ARCHITECTURE.md", "c\n", "d\n"),
        ]
        client = FakeAdapter(
            responses={
                "README.md": ClassifierError("boom"),
                "ARCHITECTURE.md": make_classification("ADDITIVE", 0.9),
            }
        )
        verdicts = evaluate_pr(
            changed, sample_lock, sample_config, sample_roles, pr_context,
            client, no_approvals,
        )
        assert verdicts[0].reason == "classifier_error"
        assert verdicts[1].outcome == "PASS"
        assert verdicts[1].reason == "additive"
