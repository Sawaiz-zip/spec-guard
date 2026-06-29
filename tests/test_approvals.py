"""Approvals: Reviews API parsing (httpx mocked) and role qualification."""

from __future__ import annotations

import json

import httpx
import pytest

from specguard.approvals import (
    ApprovalsError,
    fetch_approvals,
    fetch_comment_approvals,
    has_qualified_approval,
    submit_approval_review,
)
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


HEAD_TIME = "2026-06-29T12:00:00Z"


def comment(login: str, body: str, created_at: str, cid: int = 1) -> dict:
    return {"id": cid, "user": {"login": login}, "body": body, "created_at": created_at}


def comments_transport(comments: list[dict]) -> httpx.MockTransport:
    return httpx.MockTransport(
        lambda request: httpx.Response(200, content=json.dumps(comments))
    )


def fetch_comments(comments: list[dict], since: str = HEAD_TIME) -> list[Approval]:
    return fetch_comment_approvals(
        "acme/widgets", 7, "tok", since, transport=comments_transport(comments)
    )


class TestFetchCommentApprovals:
    def test_command_comment_after_head_qualifies(self):
        approvals = fetch_comments(
            [comment("alice", "/specguard approve", "2026-06-29T13:00:00Z")]
        )
        assert approvals == [
            Approval(
                reviewer_login="alice", state="APPROVED", source="comment-command"
            )
        ]

    def test_trailing_text_is_accepted(self):
        approvals = fetch_comments(
            [comment("alice", "/specguard approve please ship it", "2026-06-29T13:00:00Z")]
        )
        assert [a.reviewer_login for a in approvals] == ["alice"]

    def test_command_not_at_line_start_is_ignored(self):
        approvals = fetch_comments(
            [comment("alice", "please /specguard approve", "2026-06-29T13:00:00Z")]
        )
        assert approvals == []

    def test_other_commands_and_chatter_are_ignored(self):
        approvals = fetch_comments(
            [
                comment("alice", "/specguard deny", "2026-06-29T13:00:00Z", 1),
                comment("bob", "looks good to me", "2026-06-29T13:00:00Z", 2),
            ]
        )
        assert approvals == []

    def test_stale_comment_before_head_commit_does_not_qualify(self):
        # Posted an hour BEFORE the head commit — must not re-qualify (FR-010).
        approvals = fetch_comments(
            [comment("alice", "/specguard approve", "2026-06-29T11:00:00Z")]
        )
        assert approvals == []

    def test_api_failure_raises_approvals_error(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(500))
        with pytest.raises(ApprovalsError):
            fetch_comment_approvals("acme/widgets", 7, "tok", HEAD_TIME, transport=transport)

    def test_targets_issue_comments_endpoint(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content="[]")

        fetch_comment_approvals(
            "acme/widgets", 7, "tok", HEAD_TIME, transport=httpx.MockTransport(handler)
        )
        assert seen[0].url.path == "/repos/acme/widgets/issues/7/comments"
        assert seen[0].headers["Authorization"] == "Bearer tok"


class TestSubmitApprovalReview:
    def test_posts_approve_event_to_reviews_endpoint(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, content="{}")

        submit_approval_review(
            "acme/widgets", 7, "tok", transport=httpx.MockTransport(handler)
        )
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/repos/acme/widgets/pulls/7/reviews"
        assert json.loads(seen[0].content) == {"event": "APPROVE"}
        assert seen[0].headers["Authorization"] == "Bearer tok"

    def test_permission_failure_raises_approvals_error(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(403))
        with pytest.raises(ApprovalsError):
            submit_approval_review("acme/widgets", 7, "tok", transport=transport)


class TestCrossPathParity:
    """G1 / FR-005 / SC-003 / SC-004: comment and review approvals evaluate
    identically — has_qualified_approval is source-blind."""

    def test_authorized_login_qualifies_via_either_source(self):
        for source in ("native-review", "comment-command"):
            approvals = [
                Approval(reviewer_login="alice", state="APPROVED", source=source)
            ]
            assert has_qualified_approval(approvals, ["architect"], ROLES)

    def test_unauthorized_login_qualifies_via_neither_source(self):
        for source in ("native-review", "comment-command"):
            approvals = [
                Approval(reviewer_login="mallory", state="APPROVED", source=source)
            ]
            assert not has_qualified_approval(approvals, ["architect"], ROLES)
