# Contract: Approval Paths & Agent Containment

The interfaces this feature exposes and the guarantees tests must hold.

## `approvals.fetch_comment_approvals(repo, pr_number, token, since, transport=None) -> list[Approval]`

Reads the PR's issue comments and returns one `Approval(state="APPROVED", source="comment-command")` per
qualifying `/specguard approve` comment.

**Guarantees**:
1. A comment whose first line (trimmed) starts with `/specguard approve` qualifies; trailing text is
   ignored.
2. Only comments with `created_at >= since` (the head-commit time) qualify (staleness, FR-010).
3. The `reviewer_login` is the comment author's API-reported login (server-side identity, FR-006).
4. Non-command comments produce nothing (FR-011).
5. API failure raises `ApprovalsError` (same class as `fetch_approvals`) — a blocked verdict stays
   blocked, never silently approved.

## `ci.get_approvals()` (composed source)

Returns `fetch_approvals(...) + fetch_comment_approvals(..., since=head_commit_time)`. The engine's
`has_qualified_approval` is unchanged and source-blind — a qualifying review OR a qualifying comment
clears the block; a non-authorized login via either path does not (FR-001, FR-003, FR-005).

## `approvals.submit_approval_review(repo, pr_number, token, transport=None) -> None`

POSTs an approving review (`event: "APPROVE"`) to the PR. Used by the CLI.

**Guarantees**:
1. On success the review exists and is later recognized by `fetch_approvals` (FR-004).
2. Missing/invalid token or insufficient permission → raises a loud error; nothing is recorded.

## CLI: `specguard approve <pr-number>`

**Guarantees**:
1. Resolves repo from the `origin` remote and token from `GH_TOKEN`/`GITHUB_TOKEN`; submits the approval.
2. Exit 0 on success with a confirmation line; exit 2 on missing token / repo / permission with an
   actionable message (records nothing).

## `roles.change_permission(login, path, change_class) -> PermissionResult`

Answers whether `login` may make `change_class` ∈ {`edit`, `scope-change`} to `path` under the roles
rules. Pure function over `roles.yml` (no I/O), reusing `matching_rule` / `is_edit_authorized` /
`required_approver_roles`.

## MCP tools

- `specguard_check_permission(identity, path, change_class)` → the `PermissionResult` as an advisory
  payload (FR-007).
- `specguard_check_proposed_change(...)` → unchanged shape, **plus** a `redirect` object when the verdict
  would block (names required role(s) + proposal suggestion); absent for additive (FR-008,
  constitution IV).

## Workflow snippet (written by `specguard init`)

Adds an `issue_comment`-triggered job that, on a `/specguard approve` comment on a PR, reruns the
`pull_request` workflow run for the PR head SHA (same rerun mechanism as the existing `reevaluate` job).
The job grants no authority — authorization is recomputed in `ci.py` (D2).

## Test contract (what the new/updated tests must assert)

- **Comment parse**: `/specguard approve`, `/specguard approve please` qualify; `please /specguard
  approve`, `/specguard deny`, ordinary text do not.
- **Comment staleness**: a command comment older than the head commit does NOT qualify; one at/after
  does (FR-010).
- **Authorization parity**: an authorized login clears the block via review, via comment, and via CLI;
  a non-authorized login clears it via none (FR-003, FR-005, SC-003, SC-004).
- **CLI**: success submits the review (mock transport asserts the POST); no token → exit 2, no POST.
- **Permission query**: `change_permission` yes/no matches the roles rules for both classes.
- **MCP redirect**: a would-block SCOPE_CHANGE response includes `redirect` with the required role +
  suggestion; an additive response does NOT (FR-008).
- **Backward compatibility**: existing approval/engine/ci tests stay green; native-review behavior
  unchanged.
