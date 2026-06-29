# Tasks: Approval Commands & Agent Containment

**Input**: Design documents from `/specs/005-approval-commands/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Feature**: Completes the F4 approval paths (`/specguard approve` comment + `specguard approve` CLI) and
the F7 MCP containment, by treating **approval as a source** — both new paths produce the same `Approval`
the unchanged engine already evaluates (constitution III).

**Tests**: included — the contract defines a test contract and the constitution requires mocked CI tests
(no live token). New tests use the existing `httpx` mock-transport pattern + `FakeAdapter`.

**Conventions**: `[P]` = parallelizable (different files, no incomplete deps). `[US#]` = user story.

---

## Phase 1: Setup

- [X] T001 [P] Add an issue-comments mock-transport helper to `tests/conftest.py` (mirroring the existing
  Reviews-API transport used by `test_approvals.py`) returning a configurable comment list, plus a helper
  to assert a captured review-POST — reused by US1/US2 tests.

## Phase 2: Foundational (blocking — shared entity change)

**⚠️ Must complete before the user stories.**

- [X] T002 `src/specguard/models.py`: add `ApprovalSource = Literal["native-review", "comment-command",
  "cli"]` and an optional `Approval.source: ApprovalSource = "native-review"` (audit/provenance only —
  `has_qualified_approval` must NOT read it, keeping evaluation source-blind, FR-005).

## Phase 3: User Story 1 — `/specguard approve` comment command (Priority: P1) 🎯 MVP

**Goal**: An authorized maintainer clears a SCOPE_CHANGE block by commenting `/specguard approve` — no
desktop review UI, no new commit.

**Independent test**: On a blocked PR, an authorized login's command comment (posted at/after the head
commit) clears the block; a non-authorized commenter's identical comment does not.

- [X] T003 [US1] `src/specguard/approvals.py`: add `APPROVE_COMMAND = "/specguard approve"` and
  `fetch_comment_approvals(repo, pr_number, token, since, transport=None) -> list[Approval]` — read the PR
  issue comments (paginated), accept a comment whose first line (trimmed) starts with the command
  (trailing text ignored), filter `created_at >= since` (staleness, FR-010), emit
  `Approval(reviewer_login=<author>, state="APPROVED", source="comment-command")`; raise `ApprovalsError`
  on API failure (a block stays blocked).
- [X] T004 [US1] `src/specguard/ci.py`: make `get_approvals()` return `fetch_approvals(...) +
  fetch_comment_approvals(..., since=head_commit_time)`, fetching the PR head commit's committed time once
  (commits API) to pass as `since`. Engine + `has_qualified_approval` unchanged (FR-005).
- [X] T005 [US1] `src/specguard/cli.py`: extend `WORKFLOW_SNIPPET` (written by `specguard init`) with an
  `issue_comment`-triggered `comment-approve` job that, on a `/specguard approve` comment on a PR,
  resolves the PR head SHA via the API and reruns the `pull_request` workflow run for that SHA — same
  rerun mechanism as the existing `reevaluate` job. The job grants no authority (D2).
- [X] T006 [P] [US1] `tests/test_approvals.py`: command parsing (accept `/specguard approve`,
  `/specguard approve please`; reject `please /specguard approve`, `/specguard deny`, ordinary text) and
  staleness (a command comment older than the head commit does NOT qualify; at/after does).
- [X] T007 [P] [US1] `tests/test_ci.py`: with the combined source, an authorized login's command comment
  clears a SCOPE_CHANGE block; a non-authorized commenter's identical comment leaves it blocked; a stale
  comment does not qualify (FR-001/003, SC-001). Include a **cross-path parity** assertion (analyze G1):
  for the same PR + roles, an authorized approver clears the block via a comment-source `Approval` AND via
  an equivalent native-review `Approval`, while a non-authorized login clears it via neither — proving all
  paths evaluate identically (FR-005, SC-003, SC-004).

**Checkpoint**: the comment-command approval path works end to end — the MVP.

## Phase 4: User Story 2 — `specguard approve <pr>` CLI (Priority: P2)

**Goal**: Clear a block from the terminal with one command.

**Independent test**: `specguard approve <pr>` as an authorized caller submits a review the gate then
recognizes; without a token it exits 2 and posts nothing.

- [ ] T008 [US2] `src/specguard/approvals.py`: add `submit_approval_review(repo, pr_number, token,
  transport=None) -> None` — POST `{event: "APPROVE"}` to the PR reviews endpoint; raise a loud error on
  missing/invalid token or insufficient permission (records nothing).
- [ ] T009 [US2] `src/specguard/cli.py`: add the `approve <pr-number>` subcommand — resolve the repo from
  the `origin` remote and the token from `GH_TOKEN`/`GITHUB_TOKEN`, call `submit_approval_review`; exit 0
  with a confirmation line, exit 2 with an actionable message on missing token/repo/permission (FR-004).
- [ ] T010 [P] [US2] `tests/test_cli.py`: `approve` success asserts the review POST (mock transport);
  missing token → exit 2 and no POST.

**Checkpoint**: all three approval paths (review, comment, CLI) clear a block identically (SC-003).

## Phase 5: User Story 3 — MCP agent containment (Priority: P3)

**Goal**: The MCP server answers permission questions and steers an agent away from out-of-scope edits.

**Independent test**: `check_permission` matches the roles rules; a would-block proposed change returns a
`redirect` naming the role + proposal suggestion; an additive change does not.

- [ ] T011 [US3] `src/specguard/roles.py`: add `ChangeClass = Literal["edit", "scope-change"]` (in
  `models.py`), a `PermissionResult` dataclass (`allowed`, `governing_role`, `reason`), and
  `change_permission(login, path, change_class, roles_config) -> PermissionResult` reusing
  `matching_rule` / `is_edit_authorized` / `required_approver_roles` (pure, no I/O).
- [ ] T012 [US3] `src/specguard/mcp_server.py`: add the `specguard_check_permission(identity, path,
  change_class)` tool (plain function + `@server.tool()` wrapper, advisory payload); and add a `redirect`
  object to `check_proposed_change`'s payload ONLY when the verdict would block — required role(s) +
  "draft this as a separate change/proposal instead of editing <file> directly"; absent for additive
  (FR-008, constitution IV).
- [ ] T013 [P] [US3] `tests/test_mcp_server.py`: `check_permission` yes/no for both `edit` and
  `scope-change`; `redirect` present on a would-block SCOPE_CHANGE response, absent on an additive one.

**Checkpoint**: the MCP plugin contains the agent, not just classifies.

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T014 [P] `README.md`: document the three approval paths (native review · `/specguard approve`
  comment · `specguard approve <pr>` CLI) and that merge-time stays the only enforcement; add
  `check_permission` to the MCP tools list in Local Tools.
- [ ] T015 Final gate: `pytest && ruff check src tests && mypy src` all green; record final test count and
  status in this tasks file's notes.

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** must precede the user stories.
- **US1 (T003–T007)** depends on Foundational (the `comment-command` source value). **This is the MVP.**
- **US2 (T008–T010)** depends only on Foundational; independent of US1.
- **US3 (T011–T013)** depends only on Foundational; independent of US1/US2.
- **Polish (T014–T015)** last.

## Parallel Opportunities

- T006 ∥ T007 (different test files); within US2, T010 is independent; US3 T013 independent.
- US2 and US3 can proceed in parallel with US1 once Foundational lands (different files).
- T014 in Polish is independent.

## Implementation Strategy

- **MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: the `/specguard approve` comment command — the
  highest-leverage approval completion. Shippable alone.
- **Increment 2 = US2**: the CLI convenience path (native-review submission; minimal risk).
- **Increment 3 = US3**: MCP containment (advisory polish on the agent surface).
- Engine and `has_qualified_approval` stay untouched throughout — the guarantee that all paths agree.

## Notes

- No new module, no new dependency (research R1).
- The comment workflow grants no authority — authorization is recomputed in `ci.py` from the trusted base,
  so anyone can trigger a rerun but nobody can self-approve by commenting (constitution I/V, D2).
- Out of scope this phase: full GitHub App (webhooks/Checks API) and GitLab.
