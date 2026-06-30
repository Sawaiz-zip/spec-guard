"""Audit export: entry building from verdicts/approvals, JSON serialization, no secrets."""

from __future__ import annotations

import json

from conftest import make_classification
from specguard.audit import build_audit_entries, export_audit_json
from specguard.models import Approval, PRContext, Verdict


def pr_context() -> PRContext:
    return PRContext(
        pr_number=42, base_sha="abc1234", head_sha="def5678",
        author_login="dev", is_fork=False, repo="acme/widgets",
    )


class TestBuildAuditEntries:
    def test_one_entry_per_verdict(self):
        verdicts = [
            Verdict(file="README.md", outcome="PASS", reason="additive",
                    classification=make_classification("ADDITIVE", 0.95)),
            Verdict(file="ARCHITECTURE.md", outcome="BLOCK", reason="scope_change_unapproved",
                    classification=make_classification("SCOPE_CHANGE", 0.9, "HIGH", ["x"], "s"),
                    required_approver_roles=["architect"]),
        ]
        entries = build_audit_entries(verdicts, [], pr_context(), as_of="2026-06-30T00:00:00Z")
        assert len(entries) == 2
        assert entries[0].file == "README.md"
        assert entries[0].outcome == "PASS"
        assert entries[0].classification == "ADDITIVE"
        assert entries[1].required_approver_roles == ["architect"]
        assert entries[1].as_of == "2026-06-30T00:00:00Z"

    def test_classification_none_when_verdict_has_none(self):
        verdicts = [Verdict(file="x.md", outcome="BLOCK", reason="protected_violation")]
        entries = build_audit_entries(verdicts, [], pr_context())
        assert entries[0].classification is None
        assert entries[0].confidence is None

    def test_approvals_carried_on_every_entry(self):
        verdicts = [
            Verdict(file="a.md", outcome="PASS", reason="additive",
                    classification=make_classification("ADDITIVE", 0.9)),
        ]
        approvals = [
            Approval(reviewer_login="alice", state="APPROVED", source="native-review"),
            Approval(reviewer_login="bob", state="APPROVED", source="comment-command"),
        ]
        entries = build_audit_entries(verdicts, approvals, pr_context())
        assert len(entries[0].approvals) == 2
        assert {a.login for a in entries[0].approvals} == {"alice", "bob"}
        assert {a.source for a in entries[0].approvals} == {"native-review", "comment-command"}

    def test_scope_field_propagated(self):
        verdicts = [
            Verdict(file="packages/api/README.md", outcome="PASS", reason="additive",
                    classification=make_classification("ADDITIVE", 0.9), scope="packages/api"),
        ]
        entries = build_audit_entries(verdicts, [], pr_context())
        assert entries[0].scope == "packages/api"

    def test_repo_and_pr_metadata_present(self):
        verdicts = [Verdict(file="a.md", outcome="PASS", reason="additive",
                             classification=make_classification("ADDITIVE", 0.9))]
        entries = build_audit_entries(verdicts, [], pr_context())
        assert entries[0].repo == "acme/widgets"
        assert entries[0].pr_number == 42
        assert entries[0].head_sha == "def5678"


class TestExportAuditJson:
    def test_round_trips_as_valid_json(self):
        verdicts = [
            Verdict(file="a.md", outcome="BLOCK", reason="scope_change_unapproved",
                    classification=make_classification("SCOPE_CHANGE", 0.9, "HIGH", ["x"], "s"),
                    required_approver_roles=["architect"]),
        ]
        entries = build_audit_entries(
            verdicts,
            [Approval(reviewer_login="alice", state="APPROVED")],
            pr_context(),
            as_of="2026-06-30T00:00:00Z",
        )
        payload = json.loads(export_audit_json(entries))
        assert len(payload) == 1
        assert payload[0]["file"] == "a.md"
        assert payload[0]["approvals"][0]["login"] == "alice"

    def test_no_secrets_in_output(self):
        verdicts = [Verdict(file="a.md", outcome="PASS", reason="additive",
                             classification=make_classification("ADDITIVE", 0.9))]
        entries = build_audit_entries(verdicts, [], pr_context())
        text = export_audit_json(entries)
        for forbidden in ("api_key", "token", "secret", "ANTHROPIC", "sk-ant"):
            assert forbidden.lower() not in text.lower()

    def test_empty_verdicts_yields_empty_list(self):
        assert export_audit_json(build_audit_entries([], [], pr_context())) == "[]"
