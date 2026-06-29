# Implementation Plan: Approval Commands & Agent Containment

**Branch**: `005-approval-commands` | **Date**: 2026-06-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-approval-commands/spec.md`

## Summary

Complete the F4 approval paths and the F7 write-time redirect on top of the shipped gate, without a
GitHub App. The lever is the **approval source**: today `engine.evaluate_pr` clears a SCOPE_CHANGE block
when `has_qualified_approval` finds an `APPROVED` native review from an authorizing role. This feature
adds two more producers of the same `Approval` value — a `/specguard approve` PR comment and a
`specguard approve <pr>` CLI — so the engine's authorization rule and verdict shape stay byte-identical
across all three paths (constitution III). The comment command is recognized by a new
`fetch_comment_approvals` source merged into `ci.get_approvals`; a small `issue_comment` workflow job
reuses the existing "rerun the pull_request run" mechanism to re-evaluate without a new commit. The CLI
submits a native approving review through the platform, so the existing review detection already sees it
— no second evaluation path. The MCP server gains a `check_permission` tool and a would-block redirect
that names the required role and suggests proposing the change instead of writing it. Merge-time stays
the only enforcement (constitution I); authorization is the server-side login everywhere (constitution
V).

## Technical Context

**Language/Version**: Python ≥ 3.10 (unchanged).

**Primary Dependencies**: unchanged core (httpx for the GitHub REST calls — already used by
`approvals.py`). No new dependencies.

**Storage**: none — approvals continue to ride platform-native state (reviews + comments), re-read each
evaluation. No approval database (matches current design).

**Testing**: pytest with `httpx` mock transports (the pattern `fetch_approvals` already uses) for the
comments API and the review-POST; `FakeAdapter` for engine paths; no live token needed. New cases in
`tests/test_approvals.py`, `tests/test_cli.py`, `tests/test_mcp_server.py`, `tests/test_ci.py`.

**Target Platform**: GitHub (consistent with the shipped gate). GitLab out of scope this phase.

**Project Type**: same single package; no new module — extends `approvals.py`, `roles.py`, `cli.py`,
`mcp_server.py`, the workflow snippet, and adds an optional `Approval.source`.

**Performance Goals / Constraints**: one extra REST read (issue comments) per CI evaluation, paginated
like reviews; negligible vs. the LLM call. The comment workflow only triggers a rerun — it never
classifies and grants no authority.

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — all pass.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time is the security layer | ✅ | Comment/CLI are additional *inputs* to the same required check; the comment workflow only re-runs that check and enforces nothing itself. A commenter can trigger a rerun but cannot self-approve unless their login is genuinely in the role (authz happens inside `ci.py`, not the workflow). |
| II. Governance overlay | ✅ | No new spec formats; reuses `roles.yml` rules. |
| III. One shared validator core | ✅ | All three paths produce an `Approval` evaluated by the unchanged `has_qualified_approval`; one rule, one verdict shape. |
| IV. Zero friction for additive | ✅ | The MCP redirect fires ONLY on a would-block SCOPE_CHANGE; additive responses are unchanged. |
| V. Deterministic blocks, platform identity | ✅ | Comment/CLI authorization uses the server-side comment-author / caller login from the API, never local git author. Hard blocks unchanged. |
| VI. No dashboard | ✅ | PR comments, CLI, terminal only — no new UI. |

*No constitution amendment required.*

## Project Structure

```text
specs/005-approval-commands/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/approval-paths.md
└── tasks.md   (created by /speckit-tasks)

src/specguard/
├── approvals.py   # + fetch_comment_approvals(); + submit_approval_review() (CLI); APPROVE_COMMAND const
├── roles.py       # + change_permission(login, path, change_class) — the MCP permission query
├── ci.py          # get_approvals() = reviews + comment approvals; fetch head-commit time for staleness
├── cli.py         # + `approve <pr>` subcommand; WORKFLOW_SNIPPET gains the issue_comment job
├── mcp_server.py  # + specguard_check_permission tool; would-block redirect in check_proposed_change
└── models.py      # + ApprovalSource literal; optional Approval.source (audit only, engine ignores it)

.github/workflows/specguard.yml   # documented snippet: add the comment-approve trigger (via cli init)

tests/
├── test_approvals.py   # comment-command parse + staleness; submit review POST
├── test_cli.py         # `specguard approve` success / unauthorized-or-no-token failure
├── test_mcp_server.py  # check_permission yes/no; redirect on block, unchanged on additive
└── test_ci.py          # combined review+comment approvals clear / don't clear a block
```

**Structure Decision**: No new module — this feature is "more producers of an existing entity." Keeping
`Approval` as the single currency (extending its *sources*, not the engine) is what preserves the
shared-core guarantee. The comment trigger lives in the workflow YAML the `init` command writes, not in
new Python, so ci.py needs no awareness of `issue_comment` events.

## Core Design Decisions

### D1. Approval source, not a new evaluation path

`ci.get_approvals()` becomes `fetch_approvals(reviews) + fetch_comment_approvals(comments)`, both
returning `list[Approval]`. `has_qualified_approval` is unchanged: a comment from a login outside the
authorizing role simply isn't a qualifying approval (FR-003). This is the whole reason all three paths
evaluate identically (FR-005).

### D2. The comment command triggers a rerun; it grants no authority

A new `issue_comment`-triggered job detects `/specguard approve` (body, trimmed, trailing text ignored),
resolves the PR head SHA via the API, and reruns the existing `pull_request` workflow run for that SHA —
the same mechanism the shipped `reevaluate` job uses for `pull_request_review`. The rerun re-reads
reviews **and** comments and now finds the qualifying comment approval. Security: the workflow trusts the
comment author for *nothing* — authorization is recomputed in `ci.py` against `roles.yml` from the
trusted base, so triggering a rerun can never self-approve (constitution I/V). Recorded in research.md
R2.

### D3. Staleness via head-commit timestamp (FR-010)

Native reviews are auto-dismissed on push by branch protection (an optional repo setting); comments are
never auto-dismissed. To avoid a stale `/specguard approve` silently re-qualifying across new commits, a
comment approval counts only when posted at/after the PR head commit's commit time — `ci.py` fetches that
time once and `fetch_comment_approvals` filters on it. This is a **deliberate asymmetry**: the comment
path enforces staleness in code (always strict), while the review path continues to defer to branch
protection. The comment path is therefore at least as strict as the review path, never looser — no new
invalidation model is introduced (research.md R3).

### D4. CLI approve = submit a native review

`specguard approve <pr>` POSTs an approving review (`event: APPROVE`) via the platform using the caller's
token (resolved from `GH_TOKEN`/`GITHUB_TOKEN`, repo from the `origin` remote). Because it's a real
review, the existing `fetch_approvals` recognizes it — no second code path, and staleness is handled by
the platform's own review dismissal. Missing token/permission fails loudly, records nothing
(FR-004, edge case).

### D5. MCP containment is read-only advice

`specguard_check_permission(identity, path, change_class)` answers from `roles.py`
(`is_edit_authorized` / `required_approver_roles` + `is_member`). The would-block redirect adds a
`redirect` field to the existing advisory payload naming the required role(s) and suggesting "draft this
as a separate change/proposal instead of editing directly" — only when the verdict would block; additive
responses are untouched (FR-008, constitution IV).

### D6. `Approval.source` is audit-only

An optional `source: ApprovalSource = "native-review"` records provenance for the log/payload (Key
Entity) but is never read by `has_qualified_approval` — evaluation stays source-blind (FR-005).

## Complexity Tracking

> No constitution violations — table intentionally empty.
