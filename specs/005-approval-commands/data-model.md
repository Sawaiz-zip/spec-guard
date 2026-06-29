# Data Model: Approval Commands & Agent Containment

In-memory entities. The engine's evaluation contract is unchanged — this feature adds *sources* and
*advice*, not new verdict logic.

## Approval (existing — `models.py`, one optional field added)

| Field | Type | Notes |
|---|---|---|
| `reviewer_login` | `str` | The approver's server-side platform login (constitution V). |
| `state` | `str` | `APPROVED` / `CHANGES_REQUESTED` / `DISMISSED` — unchanged. |
| `source` | `ApprovalSource` *(new, default `"native-review"`)* | Audit/provenance only; **not** read by `has_qualified_approval`. |

A comment-command approval is an `Approval(reviewer_login=<commenter>, state="APPROVED",
source="comment-command")`. The CLI submits a native review, so the gate reads it back as an ordinary
`source="native-review"` approval.

## ApprovalSource (new — `Literal` in `models.py`)

```
ApprovalSource = Literal["native-review", "comment-command", "cli"]
```

## ChangeClass (new — `Literal`, for the permission query)

```
ChangeClass = Literal["edit", "scope-change"]
```

`edit` → governed by an `edit:` rule (deterministic hard block, constitution V). `scope-change` →
governed by a `scope_changes.approve` rule.

## PermissionResult (new — small dataclass returned by `roles.change_permission`)

| Field | Type | Notes |
|---|---|---|
| `allowed` | `bool` | Whether the identity may make that class of change to that file. |
| `governing_role` | `str \| None` | The role that governs it (the `edit` role, or the `scope_changes.approve` role), if any. |
| `reason` | `str` | Human-readable one-liner for the MCP/CLI surface. |

Resolution: `edit` → `is_edit_authorized(login, path)` (True when no `edit:` rule covers the path);
`scope-change` → allowed iff `login` is in `required_approver_roles(path)` (or no rule covers it, in
which case it's permissive, matching the engine's "no rule ⇒ warn, not block").

## Comment command (parsed, not stored)

`APPROVE_COMMAND = "/specguard approve"`. A PR issue-comment qualifies when its first line, trimmed,
starts with the command (trailing text ignored) **and** `created_at >= head_commit_committed_at`
(staleness, FR-010). Non-matching comments are ignored (FR-011).

## MCP redirect (added to an existing payload)

On a would-block SCOPE_CHANGE, `check_proposed_change` adds:

```
"redirect": {
  "would_block": true,
  "required_roles": [...],          # from the verdict
  "suggestion": "draft this as a separate change/proposal instead of editing <file> directly"
}
```

Absent for additive/in-scope verdicts (no added friction, constitution IV).

## Error model (reuses existing classes)

- CLI `approve` without a token / repo / permission → loud CLI error (exit 2), nothing recorded.
- Comments API unavailable during CI → treated like the existing `ApprovalsError`: a blocked verdict
  stays blocked (never silently approved).
