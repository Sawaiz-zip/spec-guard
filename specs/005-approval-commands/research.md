# Research: Approval Commands & Agent Containment

Resolves the deferred items: the comment-command transport, the staleness rule, and the CLI's approval
mechanism.

## R1. No new dependency, no new module

**Decision**: Extend existing files. `approvals.py` already uses `httpx` against the GitHub REST API;
the comments read and the review POST go through the same client + mock-transport test pattern.

**Rationale**: The feature is "more producers of the existing `Approval` entity," not a new subsystem.
Keeping the engine and `has_qualified_approval` untouched is what guarantees the three paths agree
(constitution III). Alternatives (a dedicated approvals service / DB) are rejected — they'd break the
"approvals ride platform-native state" property and add a persistence surface the constitution avoids.

## R2. Comment-command transport — `issue_comment` rerun, not a hosted listener

**Decision**: A repository workflow job triggered on `issue_comment` (type `created`) detects a body
matching `/specguard approve` on a PR, resolves the PR head SHA via the API, and **reruns the existing
`pull_request` workflow run** for that SHA — exactly the mechanism the shipped `reevaluate` job already
uses for `pull_request_review`. `ci.py` never learns about `issue_comment` events; it just re-reads
approvals (now reviews **+** comments) on the rerun.

**Why this shape**:
- No hosted App/webhook listener needed this phase (that's the deferred GitHub App work).
- Authorization is **not** done in the workflow. The workflow grants nothing; it only retriggers the
  required check. `ci.py` recomputes authorization against `roles.yml` read from the **trusted base**, so
  a comment from a non-role login produces a non-qualifying `Approval` and the block stands (FR-003,
  constitution I/V). This is the critical security property: "anyone can trigger a rerun; nobody can
  self-approve by commenting."

**Alternatives considered**: (a) a `repository_dispatch`/App webhook — deferred (needs the App). (b)
having the comment workflow itself post a status — rejected: it would become a second enforcement surface
(violates constitution I) and could be triggered by a non-authorized commenter.

**Command parsing**: match the first line, trimmed; `/specguard approve` with optional trailing text is
accepted (edge case); anything else is ignored (FR-011).

## R3. Staleness — comment approvals filter on the head-commit time

**Decision**: A `/specguard approve` comment qualifies only if its `created_at` is ≥ the PR head commit's
commit timestamp. `ci.py` fetches the head commit's date once (commits API) and passes it to
`fetch_comment_approvals`, which drops older comments.

**Rationale**: Branch protection auto-dismisses native reviews on push; comments have no such mechanism,
so an old `/specguard approve` from before new commits must not silently re-qualify (FR-010). Comparing to
the head-commit time reproduces the native "approval applies to the approved state" behavior without
inventing a new invalidation model. The CLI path (D4) needs no special handling — it submits a real
review, which the platform dismisses on push like any review.

**Alternatives considered**: tie the comment to a specific SHA mentioned in the body — rejected as poor
UX (humans won't paste SHAs); timestamp is good enough and deterministic.

## R4. CLI approval — submit a native review

**Decision**: `specguard approve <pr>` POSTs `{event: "APPROVE"}` to the PR reviews endpoint using the
caller's token (`GH_TOKEN`/`GITHUB_TOKEN`), with the repo inferred from the `origin` remote. It is then
recognized by the existing `fetch_approvals`.

**Rationale**: Reusing the native review mechanism means zero new evaluation logic and free staleness
handling (FR-004, FR-005). The CLI is a convenience wrapper, not a parallel approval store. Missing
token, wrong repo, or insufficient permission → loud failure, nothing recorded (config/credential errors
are loud per the constitution).

**Alternatives considered**: post a `/specguard approve` comment from the CLI instead — rejected: it would
route through the comment-staleness path unnecessarily when a native review is cleaner and
self-dismissing.

## R5. MCP permission query + redirect

**Decision**: `roles.change_permission(login, path, change_class)` returns a small result (allowed +
the governing role, if any) computed from the existing `matching_rule` / `is_edit_authorized` /
`required_approver_roles` helpers. The MCP tool `specguard_check_permission` wraps it. The write-time
redirect adds a `redirect` field to the advisory payload of `check_proposed_change` **only** when the
verdict would block, naming the required role(s) and suggesting the proposal alternative.

**Rationale**: Reuses the deterministic role resolution (constitution V); adds advice, not enforcement
(constitution I). Additive/in-scope responses are unchanged so the agent feels zero friction on the
common path (FR-008, constitution IV).

## R6. Audit provenance without changing evaluation

**Decision**: add `ApprovalSource = Literal["native-review", "comment-command", "cli"]` and an optional
`Approval.source` (default `"native-review"`). Surfaced in the audit/log + payloads; **never** read by
`has_qualified_approval`.

**Rationale**: the Key Entity "approval source" is for traceability (who approved how), but evaluation
must stay source-blind so the paths can't diverge (FR-005). The CLI path produces native reviews, so it
reports as `native-review` from the gate's perspective — provenance of "a human ran the CLI" is on the
CLI side; the gate sees a review.
