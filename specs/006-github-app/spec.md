# Feature Specification: GitHub App (Native Checks, Fork PRs, Agent Identity)

**Feature Branch**: `006-github-app`

**Created**: 2026-06-13

**Status**: Draft

**Input**: The Phase 2 remainder from the roadmap — deliver SpecGuard as a GitHub App so it
can govern fork PRs, post a first-class check run via the Checks API, distinguish bot from
human authors, and re-evaluate approvals in place (retiring the Actions-era workarounds).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Govern pull requests from forks (Priority: P1)

An outside contributor opens a PR from their fork that edits a watched spec file. Today the
Actions gate **skips fork PRs** (forks can't read the repo's `ANTHROPIC_API_KEY` secret), so
drift from external contributors goes unchecked. With the App, the App's own server holds the
classifier credential and runs the check regardless of where the PR originates — the same
verdict an internal PR would get.

**Why this priority**: This is the single largest hole in the current product. Open-source
and any fork-based workflow get *zero* governance today; the App closes that.

**Independent Test**: From a fork, open a PR adding an out-of-scope topic to a watched file;
confirm the App posts a SCOPE_CHANGE check run that blocks merge — with no secret ever
exposed to the fork.

**Acceptance Scenarios**:

1. **Given** the App is installed, **When** a fork PR adds an out-of-scope topic, **Then**
   the App classifies it and posts a failing check run that blocks merge.
2. **Given** a fork PR with only an additive change, **When** the App runs, **Then** the
   check passes with no annotations (constitution IV preserved across origins).
3. **Given** the App processes a fork PR, **Then** no repository secret is exposed to
   fork-controlled code at any point.

---

### User Story 2 - One check that re-evaluates in place on approval (Priority: P2)

A maintainer approves a blocked scope change. Today the approval can't update the original
Actions check (branch protection counts every run named `specguard`), so SpecGuard works
around it by re-running the prior workflow. With the App owning its check run via the Checks
API, an authorized approval updates **the same check run** from failed → passed directly, and
the check exposes a native "Re-run" affordance.

**Why this priority**: Removes the two brittle Actions-era workarounds (the `reevaluate`
re-run job and the forgeable-timestamp comment staleness) by using the platform's native
commit-anchored check model. Cleaner UX and closes the staleness gap.

**Independent Test**: Block a PR on a scope change, approve via native review; confirm the
*existing* check run flips to passed (no new run created) and merge unblocks.

**Acceptance Scenarios**:

1. **Given** a blocked check run, **When** an authorized role approves, **Then** that same
   check run transitions to passed without creating a second check.
2. **Given** new commits land after an approval, **When** the App re-evaluates, **Then** the
   stale approval does not carry over (staleness anchored to the commit natively, not a
   wall-clock timestamp).
3. **Given** the classifier is unavailable, **When** the App runs, **Then** the check
   reports a neutral/visible "could not classify" conclusion per the `on_error` policy
   (fail-open default), never a hard error.

---

### User Story 3 - Distinguish agent commits from human commits (Priority: P3)

A repo wants agents to be able to *propose* spec changes but require a human in an authorized
role to approve direction changes — even when a human and an agent commit to the same PR.
The App reads platform-verified identity (App-authored vs. user-authored, and `[bot]`
accounts) to attribute authorship more precisely than the PR-opener login the Actions gate
relies on.

**Why this priority**: Enables the "agents propose, humans approve" governance story that is
central to SpecGuard's reason for existing, but which the Actions gate can only approximate
via the PR-author login.

**Independent Test**: A PR whose scope-changing commits are authored by a bot identity is
blocked pending human approval even if the PR opener is human; a human-authored equivalent
follows the normal role rules.

**Acceptance Scenarios**:

1. **Given** a roles config marks an `agents` role as propose-only, **When** a scope change
   is attributed to a bot identity, **Then** it requires human approval regardless of who
   opened the PR.
2. **Given** mixed human+bot commits on one PR, **When** the App attributes authorship,
   **Then** it uses platform-verified per-commit identity, not just the PR opener.

---

### User Story 4 - Installation without a new dashboard or login (Priority: P4)

A maintainer installs the App from the GitHub Marketplace/installation screen and configures
everything through the same in-repo `.specguard/` files they already use — no SpecGuard
website, no separate login (constitution VI). Per-repo enablement and which spec files are
watched stay in the repo.

**Why this priority**: The App introduces server-side infrastructure for the first time;
this story is the guardrail that it does not drag a hosted UI/login along with it.

**Independent Test**: Install the App on a repo with an existing `.specguard/lock.json`;
confirm it governs immediately with configuration read only from the repo and GitHub's native
install screen — no SpecGuard-hosted dashboard involved.

**Acceptance Scenarios**:

1. **Given** a repo with `.specguard/` config, **When** the App is installed, **Then** it
   governs using only that in-repo config plus GitHub's native install/permissions screen.
2. **Given** no `.specguard/lock.json` and no derivable framework spec, **When** the App
   runs, **Then** it posts a neutral setup-hint check, identical to the Actions behavior.

---

### Edge Cases

- App webhook delivery fails or retries — check runs must be idempotent (re-deriving all
  state from the commit), so a duplicate delivery does not produce conflicting verdicts.
- App lacks permission on a repo (revoked mid-flight) — fail loudly in logs, never silently
  pass a scope change.
- A repo runs BOTH the Actions gate and the App — they must not post duplicate conflicting
  required checks; the App run is authoritative and the Actions workflow is documented as
  mutually exclusive with it.
- Very large PRs / many watched files — same per-file truncation disclosure as the gate;
  webhook processing must stay within the platform's check-run timing expectations.
- Self-hosted App instance is down — the required check is simply not posted; document that
  branch protection then waits (the operational tradeoff of self-hosting).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The App MUST classify pull requests from forks, holding the classifier
  credential server-side so it is never exposed to fork-controlled code.
- **FR-002**: The App MUST post verdicts as a native Checks-API check run, and an authorized
  approval MUST update that same check run in place (no second check, no workflow re-run).
- **FR-003**: Approval staleness MUST be anchored to the platform's native commit/check
  association, not a client-supplied timestamp (closes the comment-staleness gap).
- **FR-004**: The App MUST call the existing shared validator core; for identical inputs its
  verdicts MUST be identical to the Actions gate and the local tools (constitution III).
- **FR-005**: The App MUST attribute authorship from platform-verified per-commit identity
  and support a propose-only `agents` role (bot proposes, human approves).
- **FR-006**: Configuration MUST remain in-repo (`.specguard/` + governance overlay) plus
  GitHub's native install screen; the App MUST NOT introduce a SpecGuard-hosted dashboard or
  separate login (constitution VI).
- **FR-007**: Merge-time enforcement MUST remain the only security boundary — the App's
  check run, gated by branch protection, is that boundary; no new bypassable layer is
  treated as security (constitution I).
- **FR-008**: The App MUST be self-hostable (org runs the webhook receiver) with a
  bring-your-own classifier key, consistent with the no-SaaS posture; a managed instance, if
  ever offered, MUST be optional.
- **FR-009**: Webhook handling MUST be idempotent — all verdict state recomputed from the
  commit so repeated deliveries converge to the same result.
- **FR-010**: The App MUST degrade per the `on_error` policy (fail-open default, fail-closed
  opt-in) when the classifier is unavailable, surfacing a visible neutral conclusion.

### Key Entities

- **App Installation**: the per-repo/org grant of permissions; the unit of enablement.
- **Check Run**: the native GitHub check the App creates/updates, commit-anchored — the
  enforcement surface and the approval re-evaluation target.
- **Commit Authorship**: platform-verified per-commit identity (human / App / `[bot]`) used
  for the propose-only agent rule.
- **Webhook Event**: `pull_request`, `pull_request_review`, `check_run` re-requests, and
  installation events the App reacts to.

## Success Criteria *(mandatory)*

- **SC-001**: Fork PRs are classified at the same rate and with the same verdicts as
  equivalent internal PRs (no skip), with zero secret exposure to fork code.
- **SC-002**: An authorized approval flips the existing check run to passed in under 30s with
  no second check run created.
- **SC-003**: For the golden corpus and the existing event fixtures, App verdicts equal
  Actions-gate verdicts (100% parity, constitution III).
- **SC-004**: No SpecGuard-hosted web UI or separate login is introduced (verified by
  install + config flowing only through repo files and GitHub's native screens).
- **SC-005**: Duplicate webhook deliveries produce a single, consistent check-run state.

## Assumptions

- **Hosting**: ships as a self-hostable App (the installing org runs the webhook receiver)
  with bring-your-own LLM key — matching the existing no-SaaS, bring-your-own-credential
  posture. A managed instance is explicitly optional and out of scope for this feature.
- The validator core, models, governance overlay, and provider adapters are reused unchanged;
  this feature is a new *surface* (webhook server + Checks API client), not new verdict
  logic.
- The App reuses `.specguard/` config and the governance overlay exactly as the Actions gate
  does; nothing about the lock/roles/config formats changes.
- **GitLab** parity is acknowledged on the roadmap but is OUT OF SCOPE for this feature — it
  is a separate surface against a different platform API and would be its own spec.
- The Actions-based gate remains supported; the App is an alternative deployment, and running
  both simultaneously as required checks is documented as unsupported (pick one).
- CI tests for the App run without live credentials (mocked webhook payloads + mocked Checks
  API + the existing `FakeAdapter`), consistent with the constitution.
