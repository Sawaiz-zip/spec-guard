# Research & Decisions: Advanced Governance

## R1. Region anchoring mechanism: markdown headings, no new syntax

- **Decision**: a region is named by the exact text of an existing markdown heading
  (`## Out of Scope`'s anchor is `"Out of Scope"`); the region spans from that heading
  through (exclusive) the next heading of equal-or-higher level, reusing the same
  tolerant, no-dependency heading regex `governance.py` already uses for Spec Kit/OpenSpec
  scanning.
- **Rationale**: the spec flags this as needing a prototype with "no prior art." Reusing
  the file's own structure (rather than inventing anchor-comment syntax like
  `<!-- specguard:lock:start -->`) means no new authoring convention and no risk of an
  anchor comment surviving a copy-paste into the wrong place.
- **Alternatives considered**: HTML anchor comments (rejected — a new syntax to teach,
  and comments can drift independently of the content they're meant to bracket); line-number
  ranges in `regions.yml` (rejected — brittle, breaks on any edit above the region).

## R2. Only modified files are region-split (D1)

- **Decision**: an added watched file with region rules declared is governed as a whole
  file (today's behavior); only a *modification* of an existing file is split into regions.
- **Rationale**: "the anchor heading doesn't exist yet" has no clean semantics for a brand
  new file, and none of the spec's acceptance scenarios require it. Keeping regions
  modification-only avoids inventing behavior the spec doesn't ask for.

## R3. A missing anchor fails loudly via the existing ConfigError family (D2)

- **Decision**: `RegionAnchorError(ConfigError)`. No new exception handling anywhere — it
  rides the same `except ConfigError: exit 2` path `ci.py.main()` already has for malformed
  YAML/JSON.
- **Rationale**: FR-002 requires failing loudly rather than silently un-governing a
  declared section. Reusing the established error family means zero new control flow to
  test or get wrong.

## R4. Multi-scope discovers only EXPLICIT locks (D4)

- **Decision**: `scopes.py` walks a changed path's ancestor directories looking for
  `{dir}/.specguard/lock.json` specifically — never Spec Kit/OpenSpec derivation at a
  subdirectory. The repo-root scope alone keeps full `resolve_lock` precedence.
- **Rationale**: combining multi-scope with multi-framework-derivation-per-directory is a
  large combinatorial surface (does a package's Spec Kit `specs/` count if the package
  itself isn't the repo root? what if two packages both vendor `.specify/`?) that no
  acceptance scenario requires. Explicit locks only is unambiguous and sufficient for the
  "several packages, several goals" story.
- **Alternatives considered**: scope = any directory with a `.specguard/` directory at all
  (rejected — would silently activate on a directory that only has, say, a stray
  `config.yml` with no lock, which is confusing); inferring scope boundaries from
  `config.yml`'s `watch` patterns (rejected — conflates "what's watched" with "where is it
  governed from," two different questions).

## R5. Scope-relative paths in per-scope config (D5)

- **Decision**: `scopes.py` strips the scope directory prefix from each `ChangedFile.path`
  before the engine ever sees it, and re-adds it only when building the final `Verdict.file`
  string for display.
- **Rationale**: lets a scope's `.specguard/roles.yml` say `edit: architect` on
  `".specguard/**"` and have it mean *this* scope's `.specguard/`, regardless of where the
  scope lives in the tree — the whole `.specguard/` directory becomes copy-paste portable
  between packages, which is the natural authoring expectation (FR-005).

## R6. Audit timestamp source (D6)

- **Decision**: one timestamp per export batch, from the existing `fetch_commit_time(repo,
  head_sha, token)` — already used for comment-approval staleness — rather than adding a
  new `at` field to `Approval`.
- **Rationale**: extending `Approval` would require updating several existing
  exact-equality test assertions in `test_approvals.py` for a precision gain (exact
  per-approval second) that the spec's acceptance scenarios don't actually need ("who
  approved, when" is satisfied by "as of this commit, observed at this time" plus the
  approval's own `state`/`source`/`reviewer_login`). Lower blast radius, same compliance
  value.
- **Alternatives considered**: per-approval `submitted_at`/`created_at` (rejected this
  phase — real value, but not worth the test churn for a v1; trivial to add later as a
  backward-compatible optional field if real usage demands it).

## R7. Audit export: CI gate only this phase (D7)

- **Decision**: `SPECGUARD_AUDIT_PATH` env var on the Actions gate writes a JSON file;
  embedding the same payload into the App's check-run `output.text` is documented but not
  implemented this phase.
- **Rationale**: matches the project's established pattern of shipping the
  highest-value, lowest-risk slice first and naming the deferred extension explicitly
  (GitLab parity was deferred the same way out of 006). The Actions gate is also where
  "upload an artifact for compliance" is the most natural existing idiom (a workflow step
  the consumer already controls).

## R8. No new golden-corpus cases

- **Decision**: regions/scopes logic is tested with focused unit tests (`test_regions.py`,
  `test_scopes.py`) using inline strings, not new entries in `tests/fixtures/corpus/`.
- **Rationale**: the corpus and `tests/eval/run_eval.py` exist to calibrate the
  *classifier's* judgment quality. Regions/scopes never change what `classify()` does —
  only which diff and which `ScopeLock` reach it. Adding corpus cases would test the same
  classifier behavior the existing 27 cases already cover, at real API cost, for zero new
  signal.
