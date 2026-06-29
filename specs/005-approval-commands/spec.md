# Feature Specification: Approval Commands & Agent Containment

**Feature Branch**: `005-approval-commands`

**Created**: 2026-06-29

**Status**: Draft

**Input**: User description: "Complete the approval paths and write-time redirect the shipped gate
only half-implements — add a `/specguard approve` PR comment command and a `specguard approve <pr>`
CLI alongside the existing native-review path, and give the MCP server a `check_permission` tool plus a
write-time redirect that steers an agent away from out-of-scope edits. Merge-time stays the only
enforcement; the full GitHub App and GitLab are out of scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Approve a blocked PR with a comment command (Priority: P1)

A maintainer gets pinged that a PR is blocked on a scope change they own. They are on their phone, away
from a desk. Instead of opening the full review UI, they type `/specguard approve` as a PR comment; the
gate re-evaluates, recognizes their comment as a qualifying approval because their GitHub login is in an
authorizing role for that file, and the check flips green.

**Why this priority**: This is the approval path the product spec calls out as mobile-friendly and the
most visible half-built seam — today a block can ONLY be cleared by a full native review. It is the
highest-leverage completion of the team workflow.

**Independent Test**: On a PR blocked by a SCOPE_CHANGE, have an authorized role member comment
`/specguard approve`; confirm the gate re-runs and the verdict flips to approved. Have a non-authorized
user comment the same and confirm it does NOT clear the block.

**Acceptance Scenarios**:

1. **Given** a PR blocked by a SCOPE_CHANGE on a watched file, **When** a user whose GitHub login is in
   an authorizing role for that file comments `/specguard approve`, **Then** the gate re-evaluates and
   the check passes, recorded identically to a native-review approval.
2. **Given** the same blocked PR, **When** a user NOT in an authorizing role comments `/specguard
   approve`, **Then** the block stands and the gate's existing block output continues to name the role
   whose approval is required (so it is visible that the comment did not satisfy it) — no new per-comment
   reply surface is added (constitution VI).
3. **Given** a comment that is ordinary discussion (not the command), **When** it is posted, **Then**
   nothing is re-evaluated and no approval is recorded.

---

### User Story 2 - Approve from the terminal (Priority: P2)

A developer reviewing on their laptop wants to approve without leaving the terminal. They run
`specguard approve <pr-number>`; it records an approval for that PR through the platform, which the gate
then recognizes exactly as it would a native review.

**Why this priority**: Completes the third F4 path and serves the CLI-first audience, but it is a
convenience wrapper over the platform's own review mechanism, so it is lower-leverage than the comment
command that unlocks mobile/non-CLI approvers.

**Independent Test**: Run `specguard approve <pr>` as an authorized user against a blocked PR and confirm
the gate subsequently passes; run it as an unauthorized user and confirm the gate still blocks.

**Acceptance Scenarios**:

1. **Given** a blocked PR and an authorized caller, **When** they run `specguard approve <pr-number>`,
   **Then** an approval is recorded on the PR and the next gate evaluation passes.
2. **Given** a caller without credentials/permission, **When** they run the command, **Then** it fails
   loudly with an actionable message and records nothing.

---

### User Story 3 - Agent gets steered before writing out-of-scope content (Priority: P3)

A coding agent (e.g. Claude Code via the MCP server) is about to edit a watched spec file. Before
writing, it checks the change; when the edit would be a blocking scope change, the response not only
classifies it but tells the agent which role must approve and suggests drafting it as a separate change
proposal instead of writing it directly. The agent can also ask whether a given identity is even allowed
to make this class of change to a file.

**Why this priority**: Turns the MCP server from a passive classifier into actual containment (F7), but
it is advisory polish on an already-working surface, so it ranks below the two enforcement-completing
approval paths.

**Independent Test**: Call the permission tool for an identity/file/change-class and confirm the answer
matches the roles rules; call the proposed-change check on a would-block scope change and confirm the
response names the required role and suggests the proposal alternative.

**Acceptance Scenarios**:

1. **Given** roles that grant scope-change approval on a file to one role, **When** the permission tool
   is asked whether an identity in that role may make a scope change to that file, **Then** it answers
   yes; for an identity outside the role it answers no.
2. **Given** a proposed edit that would block as a SCOPE_CHANGE, **When** the agent checks it before
   writing, **Then** the advisory response names the required approver role and suggests proposing it as
   a separate change rather than editing directly.
3. **Given** a proposed edit that is additive/in-scope, **When** the agent checks it, **Then** the
   response is unchanged from today (no added friction).

---

### Edge Cases

- **Comment command with extra text** (`/specguard approve please`) → the command is still recognized;
  trailing text is ignored.
- **Approval then a new out-of-scope commit** → a comment/CLI approval applies to the state it approved;
  a later substantive change must not silently inherit the old approval (same staleness rule the native
  review path already follows).
- **Comment author identity** → authorization uses the comment author's server-side platform login, never
  any locally-asserted identity (constitution V).
- **Comment command on a PR with nothing blocked** → re-evaluation runs and simply reports the current
  (passing) state; the command is harmless.
- **CLI approve without network/permission** → fails loudly (constitution: config/credential errors are
  loud), records nothing.
- **Multiple approval paths on one PR** → native review, comment command, and CLI are evaluated by the
  same rule and never conflict; any one qualifying approval clears the block.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A PR comment of `/specguard approve` from a user whose platform login is in an authorizing
  role for the affected file(s) MUST count as a qualifying approval for that PR, evaluated by the same
  authorization rule as a native approving review.
- **FR-002**: A `/specguard approve` comment MUST trigger re-evaluation of the gate for that PR without
  requiring a new commit.
- **FR-003**: A comment command from a user NOT in an authorizing role MUST NOT clear the block. Missing
  authorization is made visible through the gate's existing block output, which names the required
  approver role(s); no new per-comment reply/notification surface is added (constitution VI).
- **FR-004**: `specguard approve <pr-number>` MUST record an approval for the PR through the platform such
  that the gate recognizes it, using the caller's own credentials/identity.
- **FR-005**: All three approval paths (native review, comment command, CLI) MUST be evaluated and
  recorded identically — one shared authorization rule, one shared verdict shape (constitution III).
- **FR-006**: Authorization for every path MUST use the server-side platform login, never locally-asserted
  git author data (constitution V).
- **FR-007**: The MCP server MUST expose a permission query that, given an identity, a watched file, and a
  class of change, answers whether the roles rules permit it.
- **FR-008**: When a proposed change would block as a SCOPE_CHANGE, the MCP write-time check MUST name the
  required approver role(s) and suggest drafting the change as a separate proposal instead of writing it
  directly; for additive/in-scope changes the response MUST be unchanged (no added friction,
  constitution IV).
- **FR-009**: All new approval surfaces remain advisory-or-recorded inputs to the merge-time check, which
  stays the only enforcement layer; nothing local/MCP enforces (constitution I).
- **FR-010**: An approval (any path) MUST apply to the state it approved; a later substantive change MUST
  NOT inherit a prior approval. Native reviews defer to the platform's stale-review dismissal (branch
  protection); comment-command approvals — which the platform does NOT auto-dismiss — MUST be filtered in
  code so a comment posted before the current head commit does not qualify. This makes the comment path at
  least as strict as the review path (intentional asymmetry, not identical mechanics).
- **FR-011**: Ordinary PR comments that are not the command MUST cause no re-evaluation and record no
  approval.

### Key Entities *(include if feature involves data)*

- **Approval**: a recorded act that can clear a scope-change block — now sourced from a native review, a
  `/specguard approve` comment, or the CLI; each carries the approver's platform login and the state it
  applies to.
- **Approval source**: which path produced an approval (native-review | comment-command | cli); surfaced
  for the audit trail, but does not change how the approval is evaluated.
- **Permission query**: an identity + watched file + change class, answered against the roles rules.

## Success Criteria *(mandatory)*

- **SC-001**: A blocked PR can be cleared by an authorized maintainer using only a PR comment, with no
  desktop review UI and no new commit.
- **SC-002**: A blocked PR can be cleared from the terminal with a single `specguard approve <pr>` command
  by an authorized caller.
- **SC-003**: For the same PR state and roles, all three approval paths produce the same verdict — a
  qualifying approver clears the block and a non-qualifying one does not — verified across the paths.
- **SC-004**: An unauthorized actor cannot clear a block through any path (comment, CLI, or review).
- **SC-005**: An agent checking a would-block change before writing receives, in one response, the
  required approver role and the proposal alternative; additive changes see no change in behavior.

## Assumptions

- **Platform**: GitHub, consistent with the shipped gate. GitLab is explicitly out of scope this phase.
- **Comment command transport**: the command is handled by a repository automation triggered on PR
  comment events (no standalone hosted service/App this phase — that remains future work). The exact
  trigger wiring is settled during planning.
- **CLI approval mechanism**: the CLI records approval via the platform's own review mechanism using the
  caller's token, so it is recognized by the existing approval detection without a second code path.
- **Command syntax**: `/specguard approve` is the approval verb for this phase; other verbs (e.g.
  `request-changes`, `deny`) are out of scope.
- **Identity source**: the platform-verified login of the comment author / CLI caller; this is the same
  identity basis the native-review path already uses.
- **Staleness**: this phase reuses the gate's existing notion of which PR state an approval applies to; it
  does not introduce a new approval-invalidation model beyond matching that behavior.
- **No persistence service**: approvals continue to ride platform-native state (reviews / comments)
  re-read each evaluation; SpecGuard stores no separate approval database (matches the current design).
