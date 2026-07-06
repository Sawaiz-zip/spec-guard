# Quickstart & Validation: Self-Documenting Configuration Templates

Prerequisites: `pip install -e ".[dev]"`; a scratch git repo for the interactive runs.

## Q1. Every generated file parses (SC-004)

```bash
pytest tests/test_cli_init.py -k parses
```

**Expected**: `init` writes `lock.json`, `config.yml`, `roles.yml`, and `regions.yml`, and each is
loaded back through its parser (`parse_lock`/`parse_config`/`parse_roles`/`parse_regions`) with no
error.

## Q2. `roles.yml` is self-documenting and accurate (US1 / SC-002)

```bash
mkdir /tmp/sg-demo && cd /tmp/sg-demo && git init -b main
specguard init          # answer prompts; opt into roles
cat .specguard/roles.yml
```

**Expected**: inline comments define `edit` and `scope_changes.approve`, a commented-out block shows
the full supported vocabulary, and a line states additive changes always pass. **No** mention of an
`additive_changes` key.

## Q3. `config.yml` explains behavior, not just defaults (US2 / SC-002)

```bash
cat .specguard/config.yml
```

**Expected**: each key carries a "what it does + allowed values" comment (e.g. `on_error`:
warn = pass with a loud warning, fail = block). File still parses and is behaviorally the defaults.

## Q4. `regions.yml` is discoverable and documented (US3 / SC-003)

**Expected**: `specguard init` offered to write `.specguard/regions.yml`; when accepted it contains
a commented `files:` example explaining heading→regions section locking and parses via
`parse_regions`.

## Q5. `lock.json` has no mystery fields (US3 / SC-005)

```bash
cat .specguard/lock.json
```

**Expected**: exactly `goal`, `scope_in`, `scope_out` — no `locked_at`/`locked_by`. Still parses via
`parse_lock`.

## Q6. No engine regression (SC-006 / FR-008)

```bash
pytest -q
```

**Expected**: the full existing suite passes unchanged — verdicts are provably unaffected.

## Traceability

| Scenario | Validates |
|---|---|
| Q1 | SC-004, FR-007 |
| Q2 | US1, FR-001/002/010, SC-001/002 |
| Q3 | US2, FR-003, SC-002 |
| Q4 | US3, FR-004/005, SC-003 |
| Q5 | US3, FR-006, SC-005 |
| Q6 | FR-008, SC-006 |
