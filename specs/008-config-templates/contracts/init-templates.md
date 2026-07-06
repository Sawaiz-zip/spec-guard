# Contract: `specguard init` generated templates

The interface this feature governs is the CLI command `specguard init` and the files it writes.
Each generated file must satisfy the contract below.

## Command surface (unchanged)

`specguard init [--force] [--yes]` — interactive scaffold. `--yes` = non-interactive (placeholder
goal, skip optional files). Existing flags and exit codes are unchanged.

## Per-file contracts

### `.specguard/lock.json`
- **MUST** contain `goal`, `scope_in`, `scope_out`.
- **MUST NOT** contain `locked_at` or `locked_by` in the generated file.
- **MUST** parse via `parse_lock` before being written.

### `.specguard/config.yml` (offered)
- Every documented key (`watch`, `block_threshold`, `on_error`, `provider`, `model`,
  `max_diff_chars`) **MUST** appear with an inline explanation of its behavioral effect and its
  allowed values/range.
- Keys **MUST** remain commented out (file is inert / pure-defaults).
- **MUST** parse via `parse_config`.

### `.specguard/roles.yml` (offered)
- **MUST** inline-document `edit` and `scope_changes.approve` and their allowed values.
- **MUST** state that additive changes always pass (no rule needed).
- **MUST** include commented-out examples covering the full supported rule vocabulary.
- **MUST NOT** reference an `additive_changes` (or any other unsupported) rule key.
- **MUST** parse via `parse_roles` (the active, uncommented portion).

### `.specguard/regions.yml` (offered — NEW)
- `init` **MUST** offer to write it, consistent with the config/roles offers.
- **MUST** inline-document the `files:` heading→regions mapping and how section locking narrows
  what is governed.
- **MUST** parse via `parse_regions`.

## Invariants (all files)
- **Never overwrite**: if the target exists, `init` skips it and notes so (FR-009).
- **`--yes` mode**: optional files behave exactly as today (skipped); comments never break the
  non-interactive path.
- **No engine change**: none of these templates alter classification, enforcement, or approval
  behavior (FR-008).

## Verification
Covered by `quickstart.md` scenarios Q1–Q5 and the CLI test assertions described in research R6.
