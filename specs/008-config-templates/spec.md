# Feature Specification: Self-Documenting Configuration Templates

**Feature Branch**: `008-config-templates`

**Created**: 2026-07-06

**Status**: Draft

**Input**: User description: "Self-documenting configuration templates. When a user runs `specguard init`, every generated config file must be self-explanatory so a new user never has to guess or leave the file to understand it. Cover roles.yml key semantics, config.yml behavior explanations, lock.json's unexplained fields, and scaffolding the currently-invisible regions.yml — while keeping every template valid/parseable and not changing the governance engine's behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Understand the config without leaving the file (Priority: P1)

A developer runs `specguard init`, opens the generated `.specguard/roles.yml`, and needs to add a second protected path and a new approver role. Today the file shows one bare example (`scope_changes: {approve: architect}`) with no comments, so they must go read the README or source to learn that `edit` and `scope_changes.approve` even exist or what they mean — and to learn that additive changes are *not* configurable here (they always pass silently). After this feature, the generated file explains every key inline, shows the full set of rule options (commented out), states plainly that additive changes need no rule, and the developer completes the edit correctly without opening any other resource.

**Why this priority**: `roles.yml` is the file that turns advisory warnings into hard blocks — misunderstanding it is the highest-consequence guess a user can make (either it silently does nothing, or it blocks the wrong changes). Making it self-explanatory is the single biggest reduction in "guess around" risk.

**Independent Test**: Run `specguard init`, choose to configure roles, and confirm the written `.specguard/roles.yml` contains inline comments describing each rule key and its allowed values, plus at least one commented-out example of every supported rule option — and still parses cleanly.

**Acceptance Scenarios**:

1. **Given** a fresh repo, **When** the user runs `specguard init` and opts into roles, **Then** the generated `.specguard/roles.yml` documents the meaning of `edit` and `scope_changes.approve` in inline comments, states that additive changes always pass (no rule needed), and includes commented examples of the full rule vocabulary.
2. **Given** the generated `roles.yml`, **When** it is loaded by the existing roles parser, **Then** it parses without error and produces the same enforcement behavior the equivalent uncommented file would.
3. **Given** a user reading only the generated file (no README, no source), **When** they need to add a new protected path, **Then** the inline documentation is sufficient to do so correctly.

---

### User Story 2 - Understand what each setting does before changing it (Priority: P2)

A developer opens the generated `.specguard/config.yml` to make scope changes block instead of warn, or to change how a vendor outage is handled. Today the template lists default *values* with only terse notes. After this feature, each key carries a short explanation of what it *does* — the effect of `on_error: warn` vs `fail`, what `block_threshold` controls, what `watch` governs, what `max_diff_chars` truncates — so the user changes the right key with confidence and no trial-and-error.

**Why this priority**: `config.yml` tunes behavior but is not required for correctness; a confused user can still run safely on defaults. High value, lower blast radius than roles.

**Independent Test**: Run `specguard init`, opt into the settings template, and confirm each key in `.specguard/config.yml` has an inline explanation of its behavioral effect (not just its default value), and the file parses cleanly.

**Acceptance Scenarios**:

1. **Given** a fresh repo, **When** the user opts into the settings template, **Then** every key in `.specguard/config.yml` is accompanied by an inline explanation of its behavioral effect and its allowed values/range.
2. **Given** the generated `config.yml`, **When** it is loaded by the existing config parser, **Then** it parses without error and yields the documented default behavior.

---

### User Story 3 - Discover section locking and demystify the lock fields (Priority: P3)

A developer wants to govern only part of a large file (section locking, shipped in 007), but `regions.yml` is invisible today — `init` never mentions or creates it, so the feature is effectively undiscoverable. They also see unexplained `locked_at`/`locked_by` fields in the generated `lock.json` and don't know whether to fill them in. After this feature, `init` offers a commented `regions.yml` template, and `lock.json`'s metadata fields are either explained or removed so nothing in the generated files is a mystery.

**Why this priority**: Discoverability of an already-shipped feature and removing small points of confusion — valuable polish, but affects fewer users than the core roles/config files.

**Independent Test**: Run `specguard init`, confirm a `regions.yml` option is offered and, when accepted, writes a commented, parseable template; and confirm the generated `lock.json` contains no field a user cannot explain from the file itself.

**Acceptance Scenarios**:

1. **Given** a fresh repo, **When** the user runs `specguard init`, **Then** a `.specguard/regions.yml` template is offered, and when accepted it is written with inline comments explaining the `files:` mapping and how section locking behaves, and it parses cleanly.
2. **Given** the generated `.specguard/lock.json`, **When** a user reads it, **Then** every field present is either self-explanatory or documented, with no undocumented `locked_at`/`locked_by` mystery fields.

---

### Edge Cases

- **A config file already exists**: `init` must not clobber a user's existing `.specguard/*` file to inject comments; existing behavior (skip and note it) is preserved for every file including the new `regions.yml`.
- **Non-interactive `--yes` mode**: comments must never break the non-interactive path; the `--yes` skip/write behavior stays consistent with today.
- **Comment stripping on round-trip**: if tooling ever rewrites these files programmatically, comments may be lost — the documentation targets the human reading the freshly generated file, not a guarantee that comments survive machine edits. Acceptable.
- **JSON cannot carry comments**: `lock.json` is JSON, which has no comment syntax — so its self-documentation must come from removing/renaming mystery fields (or another JSON-valid means), never inline `#` comments that would invalidate the file.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `roles.yml` template written by `specguard init` MUST include inline comments that define each supported rule key — `edit` and `scope_changes` (with its nested `approve`) — and their allowed values, and MUST state that additive changes are not governed by a rule (they always pass silently). It MUST NOT imply the existence of rule keys the parser does not support (e.g. no `additive_changes` key).
- **FR-002**: The `roles.yml` template MUST show the full set of *supported* rule options (via commented-out examples), not only the single example it shows today.
- **FR-003**: The `config.yml` template MUST accompany each setting with an inline explanation of what that setting *does* to behavior, plus its allowed values or range — not merely its default value.
- **FR-004**: `specguard init` MUST offer to scaffold a `.specguard/regions.yml` template, consistent with how it currently offers `config.yml` and `roles.yml`.
- **FR-005**: The `regions.yml` template MUST include inline comments explaining the `files:` heading-to-regions mapping and how section locking narrows what is governed.
- **FR-006**: The generated `lock.json` MUST NOT contain any field a reader cannot understand from the file or its documentation; the currently-unexplained `locked_at`/`locked_by` fields MUST be either documented or removed.
- **FR-007**: Every generated template MUST remain valid and parseable — each MUST round-trip through the existing parser for its file type before being written, exactly as `init` already does for `lock.json` and `config.yml`.
- **FR-008**: This feature MUST NOT change the governance engine's classification, enforcement, or approval behavior; a repo whose config is identical in *meaning* to today's must produce identical verdicts.
- **FR-009**: `specguard init` MUST NOT overwrite an existing `.specguard/*` file to add documentation; the existing skip-and-note behavior MUST be preserved for all offered files, including `regions.yml`.
- **FR-010**: The self-documenting content MUST be accurate and consistent with the actual defaults and behavior defined in the engine (e.g. the documented default `block_threshold`, `on_error`, and watch list must match what the code uses).

### Key Entities

- **Generated config templates**: The text `specguard init` writes for `lock.json`, `config.yml`, `roles.yml`, and (new) `regions.yml`. Each is a human-facing artifact whose primary quality attribute is self-explanation.
- **Rule vocabulary**: The set of `roles.yml` rule keys actually supported by the parser — `edit` and `scope_changes` (with nested `approve`) — whose semantics must be documented inline. Additive changes have no rule key and must be documented as always-passing.
- **Setting**: A `config.yml` key (`watch`, `block_threshold`, `on_error`, `model`, `provider`, `max_diff_chars`) whose behavioral effect must be documented inline.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can correctly add a second protected path and approver to `roles.yml` using only the generated file — no README, source, or external doc needed.
- **SC-002**: 100% of config keys and rule keys in the generated `config.yml` and `roles.yml` have an inline explanation of their effect and allowed values.
- **SC-003**: `regions.yml` (section locking) is discoverable directly from `specguard init`, with zero users needing to read the README to learn it exists.
- **SC-004**: Every generated template parses successfully through its existing parser (0 parse failures across all generated files).
- **SC-005**: No field in any generated file is undocumented or unexplained (0 "mystery" fields such as today's `locked_at`/`locked_by`).
- **SC-006**: The existing test suite passes unchanged — the governance engine's verdicts are provably unaffected by this feature.

## Assumptions

- The audience for self-documentation is the human reading the freshly-generated file; comment survival across programmatic rewrites is not a requirement.
- The `roles.yml` rule vocabulary to document is the set currently supported by the roles parser; this feature documents existing behavior and does not add new rule keys.
- For `lock.json`, "self-documenting" is satisfied by removing or clearly documenting the `locked_at`/`locked_by` fields; a JSON-comment mechanism is out of scope because it would produce invalid JSON.
- `init`'s existing interactive / `--yes` / skip-if-exists flow is the right delivery vehicle; this feature extends that flow rather than replacing it.
- No changes to the CI Action, MCP server, or GitHub App surfaces are required beyond the templates `init` writes.