# Feature Specification: PR Spec-File Governance Gate (Phase 0 MVP)

**Feature Branch**: `001-pr-spec-gate`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Phase 0 thesis test from SPECGUARD_PRODUCT_SPEC.md §9: the smallest cutting piece — a CI check on pull requests that semantically classifies changes to watched spec files (README.md, CLAUDE.md, AGENTS.md, etc.), auto-passes additive changes, blocks unapproved scope changes until an authorized role approves, and hard-blocks unauthorized edits to protected files."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Scope change blocked until authorized approval (Priority: P1)

A team has locked their project goal and scope (in/out lists) into the repository and defined
roles (e.g., alice = architect). A contributor — human or AI agent — opens a PR that adds an
out-of-scope topic to a watched spec file (e.g., adds "SAML SSO via Active Directory" to a
spec whose locked scope excludes SSO). The merge is blocked with a clear explanation naming
the classification, confidence, the out-of-scope topics detected, and who can approve. When
an authorized person approves the PR through the platform's normal review flow, the check
turns green and the merge proceeds.

**Why this priority**: This is the product's entire reason to exist — the governance gap no
existing tool covers (CODEOWNERS knows paths, not meaning). Without it there is no thesis to
test.

**Independent Test**: In a repository with scope lock + roles configured, open a PR adding an
out-of-scope topic to a watched file → check fails with explanation; submit an approving
review from the authorized account → check passes on re-evaluation; merge button unblocks.

**Acceptance Scenarios**:

1. **Given** a repo with a locked scope excluding "SSO" and roles naming alice as approver,
   **When** charlie's PR adds an SSO section to a watched spec file, **Then** the required
   check fails and the failure message states the classification, confidence, the matched
   out-of-scope topic, and that alice's approval is required.
2. **Given** that blocked PR, **When** alice submits an approving review, **Then** the check
   re-evaluates automatically and passes without anyone editing the PR.
3. **Given** that blocked PR, **When** bob (not in the approving role) approves, **Then** the
   check remains failed and the message still names the role whose approval is required.

---

### User Story 2 - Additive changes pass silently (Priority: P2)

A contributor fixes a typo, clarifies wording, or adds detail that stays within the locked
scope of a watched spec file. The check passes with no friction — no annotations demanding
attention, no approvals, only a quiet log line recording that the change was evaluated and
classified additive.

**Why this priority**: Most changes most days must be this. Zero friction on the additive
path is the adoption requirement (one wrong Friday block = uninstall); it is also
constitution Principle IV.

**Independent Test**: Open a PR that only fixes typos in a watched file → check passes; the
run log contains exactly one per-file line noting the additive classification; no warnings
or errors are surfaced on the PR.

**Acceptance Scenarios**:

1. **Given** a configured repo, **When** a PR corrects spelling in a watched spec file,
   **Then** the check passes and the PR shows no warning or error annotations.
2. **Given** a configured repo, **When** a PR adds an example that elaborates an in-scope
   item, **Then** the check passes quietly.
3. **Given** a PR touching only non-watched files, **When** the check runs, **Then** it
   passes immediately without evaluating any content.

---

### User Story 3 - Protected file edited by unauthorized identity (Priority: P3)

The roles file designates certain paths (e.g., the governance configuration itself) as
editable only by a specific role. A PR authored by anyone outside that role that touches such
a file is hard-blocked — deterministically, regardless of what the change says — with a
message naming the file, the rule, and the role that may edit it.

**Why this priority**: This is the self-protecting lock (the config governing the rules must
not be editable by the agents/contributors it governs). It is deterministic and cheap, but it
depends on the roles model from Story 1.

**Independent Test**: With a rule restricting edits of the governance config directory to the
architect role, open a PR from a non-architect account that modifies a file there → check
fails with a protected-violation message; the same PR from the architect account passes that
rule.

**Acceptance Scenarios**:

1. **Given** a rule "governance config: edit = architect", **When** a non-architect's PR
   modifies a file under that rule, **Then** the check fails with a protected-violation
   message naming the required role, without any semantic evaluation.
2. **Given** the same rule, **When** the architect's own PR modifies that file, **Then** the
   protected rule passes and normal classification proceeds.

---

### User Story 4 - Solo developer warn mode (Priority: P4)

A solo developer locks a goal/scope but defines no roles. The gate evaluates every watched
change and surfaces scope-change warnings with full explanations, but never fails the check —
because a PR author cannot approve their own PR, blocking would deadlock a team of one. The
product still delivers its value as a guardrail against the developer's own agents and drift.

**Why this priority**: Serves the solo persona (spec §5.1) and removes the biggest
onboarding objection, but the thesis test (Story 1) matters more.

**Independent Test**: In a repo with a scope lock but no roles file, open a PR adding an
out-of-scope topic → check passes but a visible warning carries the same classification and
explanation a team would see.

**Acceptance Scenarios**:

1. **Given** a scope lock and no roles file, **When** a PR introduces an out-of-scope topic,
   **Then** the check passes with a warning annotation containing classification, confidence,
   and explanation.
2. **Given** a repo with no governance configuration at all, **When** the check runs, **Then**
   it passes with a single notice explaining how to configure it, and blocks nothing.

---

### Edge Cases

- **Classifier service unavailable**: by default the check passes with a loud "could not
  classify — review manually" warning (fail-open); repos can opt into fail-closed.
  Deterministic protected-file rules still enforce either way.
- **Malformed governance config** (roles/scope/lock files unparseable): the check fails with
  a precise configuration error — a typo must never silently disable governance.
- **Watched file deleted or renamed in the PR**: treated as a semantic change and classified
  (deleting a spec is a direction change candidate), not skipped.
- **PR from a fork** (secrets unavailable to the workflow): check passes with a notice that
  evaluation was skipped; documented limitation of the CI-based phase.
- **Reviewer not identifiable / not in any role**: their approval never satisfies a
  scope-change requirement; treated as no approval.
- **Borderline classification** (confidence below threshold): warn, never block.
- **Very large diffs**: file context may be truncated for evaluation, but the goal and scope
  lists are never truncated; truncation is disclosed in the verdict.
- **Bot/agent PR authors**: mapped to an `agents` role when one is defined; otherwise treated
  as an unknown identity (most restrictive).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST let a repository declare a goal, an in-scope list, an
  out-of-scope list, and a set of watched spec-file paths in versioned files inside the repo.
- **FR-002**: The system MUST evaluate every PR change to a watched file and classify it as
  ADDITIVE (within locked scope) or SCOPE_CHANGE (alters goals/direction or introduces
  out-of-scope topics), with a confidence score, a one-line summary, and a human-readable
  explanation.
- **FR-003**: Classification MUST be performed by an evaluator independent of any agent
  session that authored the change.
- **FR-004**: ADDITIVE changes MUST pass with no user-facing friction beyond a quiet log line.
- **FR-005**: In enforce mode (roles defined), a SCOPE_CHANGE at or above the configured
  confidence threshold MUST block merging until an approving PR review exists from an
  identity holding the authorizing role for that file.
- **FR-006**: A SCOPE_CHANGE below the confidence threshold MUST surface as a non-blocking
  warning carrying the full classification.
- **FR-007**: The system MUST hard-block PRs whose author lacks the role required by an
  `edit` rule on a touched path; this decision MUST be deterministic (no semantic evaluation
  involved).
- **FR-008**: Roles MUST map platform account identities (not locally asserted git metadata)
  to named roles, with per-path rules; the governance configuration paths MUST be
  protectable by their own rules.
- **FR-009**: The system MUST detect qualifying approvals from the platform's native PR
  review mechanism and re-evaluate automatically when a review is submitted.
- **FR-010**: Every blocking or warning verdict MUST display: classification, confidence,
  detected out-of-scope topics, a one-line summary, an explanation, and (when blocking) the
  role(s) whose approval unblocks it.
- **FR-011**: Without a roles file, the system MUST run in warn-only mode (FR-002/FR-004
  behavior unchanged; no failures from SCOPE_CHANGE). With no governance configuration at
  all, it MUST pass with a setup notice.
- **FR-012**: The confidence threshold and the outage policy (fail-open default /
  fail-closed option) MUST be configurable per repository.
- **FR-013**: Configuration parse errors MUST fail the check with an actionable message;
  evaluator outages MUST follow the configured outage policy and always disclose themselves.
- **FR-014**: The check MUST be installable as a required status check so that the platform's
  branch protection makes it unbypassable at merge time.
- **FR-015**: Repository setup (config templates + workflow + branch protection) MUST be
  achievable from the README alone in five minutes or less.

### Key Entities

- **Scope Lock**: the locked goal, scope-in list, scope-out list, who locked it and when.
- **Watch List**: the set of spec-file paths under governance.
- **Role**: a named group of platform identities (humans or agents).
- **Rule**: a path pattern bound to required roles for `edit` (hard) and `scope-change
  approval` (semantic) decisions.
- **Classification**: evaluator output — class, confidence, risk level, out-of-scope topics,
  summary, explanation.
- **Verdict**: per-file outcome (pass / warn / block) with its reason and the classification
  that produced it.
- **Approval**: a platform-native PR review by an identity, resolvable to a role.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero false blocks across the additive golden corpus (~15 additive cases) at
  default settings — release-gating.
- **SC-002**: ≥ 90% of true scope-change corpus cases are flagged (blocked or warned) at
  default settings.
- **SC-003**: A new user goes from README to a working required check (test PR blocked then
  approved) in ≤ 5 minutes of configuration effort.
- **SC-004**: 100% of blocking verdicts display an explanation and the unblocking role;
  qualifying approval flips the check green with no further pushes to the PR.
- **SC-005**: Check completes in under 90 seconds for a PR touching ≤ 5 watched files.
- **SC-006**: Thesis-test signal (spec §9): within 4 weeks of public release, at least one
  feature request or issue is filed by someone outside the project. (Silence ≈ market said
  no, cheaply.)

## Assumptions

- Phase 0 targets one CI/hosting platform (GitHub) via its Actions and required-status-check
  mechanisms; GitLab parity is deferred to the App phase (product spec Phase 2).
- Identity = the PR author's platform account; commit-author vs PR-opener disambiguation and
  agent propose-only enforcement are deferred (product spec §10.2, Phase 2).
- Plain mode only: scope comes from SpecGuard's own lock file; reading Spec Kit
  constitutions / OpenSpec proposals as scope sources is adapter work (Phase 2).
- Section-level (sub-file) locking is explicitly Phase 3 (no prior art; product spec §10.3).
- The repository owner supplies their own AI-evaluator API key as a repo secret. The default
  classifier uses the Anthropic API, but the model is fully configurable — users may switch to
  any model string supported by their chosen provider. Evaluation cost is determined entirely
  by the model the user selects and is borne by the installing repo.
- Risk level (LOW/MEDIUM/HIGH) is displayed for context but does not drive outcomes in
  Phase 0; the confidence threshold is the only probabilistic control.
