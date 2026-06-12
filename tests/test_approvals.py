"""Approvals: Reviews API parsing (httpx mocked) and role qualification."""

from __future__ import annotations

import json

import httpx
import pytest

from specguard.approvals import ApprovalsError, fetch_approvals, has_qualified_approval
from specguard.models import Approval, RolesConfig

ROLES = RolesConfig.model_validate(
    {"roles": {"architect": ["alice"], "maintainers": ["bob"]}}
)


def review(login: str, state: str, review_id: int) -> dict:
    return {"id": review_id, "user": {"login": login}, "state": state}


def transport_returning(reviews: list[dict]) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(reviews))
    )


class TestFetchApprovals:
    def test_latest_review_per_reviewer_wins(self):
        reviews = [
            review("alice", "CHANGES_REQUESTED", 1),
            review("bob", "APPROVED", 2),
            review("alice", "APPROVED", 3),  # alice's latest supersedes
        ]
        approvals = fetch_approvals(
            "acme/widgets", 7, "tok", transport=transport_returning(reviews)
        )
        states = {a.reviewer_login: a.state for a in approvals}
        assert states == {"alice": "APPROVED", "bob": "APPROVED"}

    def test_changes_requested_supersedes_earlier_approval(self):
        reviews = [review("alice", "APPROVED", 1), review("alice", "CHANGES_REQUESTED", 2)]
        approvals = fetch_approvals(
            "acme/widgets", 7, "tok", transport=transport_returning(reviews)
        )
        assert approvals == [Approval(reviewer_login="alice", state="CHANGES_REQUESTED")]

    def test_commented_reviews_do_not_change_state(self):
        reviews = [review("alice", "APPROVED", 1), review("alice", "COMMENTED", 2)]
        approvals = fetch_approvals(
            "acme/widgets", 7, "tok", transport=transport_returning(reviews)
        )
        assert approvals == [Approval(reviewer_login="alice", state="APPROVED")]

    def test_api_failure_raises_approvals_error(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(500))
        with pytest.raises(ApprovalsError):
            fetch_approvals("acme/widgets", 7, "tok", transport=transport)

    def test_request_targets_reviews_endpoint_with_auth(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content="[]")

        fetch_approvals(
            "acme/widgets", 7, "tok", transport=httpx.MockTransport(handler)
        )
        assert seen[0].url.path == "/repos/acme/widgets/pulls/7/reviews"
        assert seen[0].headers["Authorization"] == "Bearer tok"


class TestQualification:
    def test_approved_role_member_qualifies(self):
        approvals = [Approval(reviewer_login="alice", state="APPROVED")]
        assert has_qualified_approval(approvals, ["architect"], ROLES)

    def test_approved_non_member_does_not_qualify(self):
        approvals = [Approval(reviewer_login="mallory", state="APPROVED")]
        assert not has_qualified_approval(approvals, ["architect"], ROLES)

    def test_member_of_wrong_role_does_not_qualify(self):
        approvals = [Approval(reviewer_login="bob", state="APPROVED")]  # maintainer
        assert not has_qualified_approval(approvals, ["architect"], ROLES)

    def test_changes_requested_does_not_qualify(self):
        approvals = [Approval(reviewer_login="alice", state="CHANGES_REQUESTED")]
        assert not has_qualified_approval(approvals, ["architect"], ROLES)

    def test_any_of_multiple_required_roles_qualifies(self):
        approvals = [Approval(reviewer_login="bob", state="APPROVED")]
        assert has_qualified_approval(approvals, ["architect", "maintainers"], ROLES)

    def test_no_approvals_no_qualification(self):
        assert not has_qualified_approval([], ["architect"], ROLES)
