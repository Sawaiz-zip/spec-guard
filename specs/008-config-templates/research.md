# Research: Self-Documenting Configuration Templates

Design decisions resolved before implementation. No open NEEDS CLARIFICATION.

## R1 — `lock.json` metadata fields (`locked_at` / `locked_by`)

**Decision**: Keep both fields on the `ScopeLock` model; **omit** them from the freshly-generated
`lock.json` (write only `goal` / `scope_in` / `scope_out`). Document their meaning in the
`config.yml`/README config reference, not in the JSON.

**Rationale**: The fields are not dead — `governance.py` populates `locked_by` with the derivation
source (`spec-kit:<constitution>`, `openspec:<project>`) and `tests/test_governance.py` asserts on
it; corpus fixtures also set both. Removing them from the model would break framework derivation.
But writing `"locked_at": null, "locked_by": null` into a fresh file is a mystery to the reader
(FR-006) and JSON cannot carry an explanatory comment. Both fields are `Optional[...] = None`, so
a `lock.json` that omits them parses identically. Omitting is the only way to make the *generated*
JSON self-explanatory while keeping model support and behavior unchanged (FR-007, FR-008).

**Alternatives considered**: (a) Drop from the model — rejected, breaks adapters/tests. (b) Keep the
null lines and add a sibling `_comment` field — rejected, pollutes the schema and still looks odd.
(c) Switch `lock.json` to JSON5/YAML to allow comments — rejected, changes the file format and the
parser contract, far beyond this feature.

## R2 — `roles.yml` documentation content

**Decision**: Emit the working example (unchanged in effect) plus inline comments defining the real
rule vocabulary and a block of commented-out examples covering every supported option. The real
vocabulary is exactly two rule keys: **`edit`** (deterministic: who may edit a path) and
**`scope_changes`** with nested **`approve`** (which role's approval unblocks a SCOPE_CHANGE).
Explicitly state that **additive changes always pass and need no rule**.

**Rationale**: The `Rule` model (`models.py`) has only `edit` and `scope_changes.approve`. There is
**no `additive_changes` key** — documenting one (as the old product-spec prose implies) would send
users chasing a setting that does not exist. Accuracy is FR-001/FR-010.

**Alternatives considered**: Documenting `additive_changes` for symmetry — rejected as factually
wrong. A separate `docs/` reference instead of inline comments — deferred; the user's selected scope
is self-documenting *templates*, and inline is what removes the "leave the file to understand it"
problem.

## R3 — `config.yml` template

**Decision**: Keep every key **commented out** (so the file stays inert and pure-defaults, exactly
as today), but expand each line into "what it does + allowed values/range", not just the default
value. Example: `on_error` gets "on classifier/vendor failure: `warn` = pass with a loud warning
(default), `fail` = block the PR".

**Rationale**: Commented-out keys mean the generated file changes no behavior (a key typo can't
silently alter the gate), satisfying FR-008 by construction. The gap today is explanation, not
values — so we enrich comments and keep the inert form.

**Alternatives considered**: Writing live (uncommented) default values — rejected: if a default
changes later, a materialized value would silently diverge from the engine default and could alter
behavior; inert comments track the engine.

## R4 — `regions.yml` scaffolding

**Decision**: Add a `REGIONS_TEMPLATE` constant and a new prompt in `_offer_optional_files`,
mirroring the existing `config.yml`/`roles.yml` offers (interactive yes/no, skip-if-exists, skip in
`--yes`). Round-trip the template through `parse_regions` before writing.

**Rationale**: `REGIONS_PATH` and `parse_regions` already exist (007); the only gap is discovery.
Reusing the established offer pattern keeps `init`'s UX consistent and honors FR-009 (never
overwrite).

**Alternatives considered**: Always writing `regions.yml` unconditionally — rejected, most repos
don't need section locking; keep it opt-in like roles/config.

## R5 — Scope boundary: canonical config-reference doc

**Decision**: Out of scope for 008. The generated files themselves are the source of truth for this
feature. A standalone `docs/configuration.md` was one of the improvement options but was **not**
selected; the README's existing Configuration section already gives an external reference.

**Rationale**: Keep the feature tightly matched to the selected scope (self-documenting templates).

## R6 — Testing approach

**Decision**: Add CLI tests that (1) run `init` non-interactively/through the offer helpers into a
temp git repo, (2) assert each generated file **parses** through its parser, (3) assert
documentation markers are present (e.g. the `edit`/`scope_changes`/"additive changes always pass"
strings in `roles.yml`; a behavioral phrase per `config.yml` key; the `files:` explanation in
`regions.yml`), and (4) assert the generated `lock.json` contains no `locked_at`/`locked_by`. The
existing suite must stay green unchanged (FR-008 / SC-006).

**Rationale**: Directly encodes the success criteria; needs no live API key (constitution quality
gate). Marker assertions are brittle-by-design tripwires so future template edits can't silently
drop the documentation the feature promises.
