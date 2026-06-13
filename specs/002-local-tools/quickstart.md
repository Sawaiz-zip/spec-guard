# Quickstart Validation Guide: Local Tools (Phase 1)

Runnable scenarios proving the feature end-to-end. Contracts:
[cli](contracts/cli-interface.md), [mcp](contracts/mcp-interface.md),
[adapter](contracts/adapter-protocol.md). Entities: [data-model.md](data-model.md).

## Prerequisites

- Python 3.10+, `pip install -e ".[dev,mcp]"` from repo root
- Real-classification scenarios only: `ANTHROPIC_API_KEY` exported (V2, V4–V6)

## V1. Unit suite (no API key) — every merge

```bash
pytest
```

**Expected**: all green. Covers snapshot resolution (staged/worktree/range), baseline
config reads, init scaffolding round-trips, hook never-blocks matrix, MCP tool functions
via FakeAdapter, adapter-protocol conformance, and existing Phase 0 suites unchanged.

## V2. Parity — local check vs merge gate (SC-001)

```bash
pytest tests/test_parity.py            # corpus-driven, FakeAdapter (every merge)
```

**Expected**: for all 27 golden-corpus cases, `specguard check --base X --head Y`
verdicts equal the CI gate's classification and outcome for the identical diff. 100%.

## V3. Init-to-check in a fresh repo (SC-002)

```bash
mkdir /tmp/sg-demo && cd /tmp/sg-demo && git init -b main
specguard init           # answer prompts: goal, in-scope, out-of-scope
git add -A && git commit -m "specguard setup"
echo "## Pricing tiers" >> README.md   # after creating a README + committing it first
specguard check
```

**Expected**: lock written and validated; `check` runs against baseline HEAD, prints a
verdict and the advisory notice; total under 5 minutes from a cold start.

## V4. Hook never blocks (SC-003)

```bash
specguard init   # accept the pre-commit hook offer (or: pre-commit install)
# stage an out-of-scope edit to a watched file
git commit -m "drift attempt"
```

**Expected**: warning with full classification printed; **commit succeeds anyway**.
Repeat with `ANTHROPIC_API_KEY` unset → "could not classify — advisory check skipped";
commit still succeeds. Repeat with a non-watched file → no output, no delay.

## V5. MCP write-time warning (SC-004)

```bash
specguard mcp    # then connect any MCP client (e.g. Claude Code) over stdio
```

Invoke `check_proposed_change` with a README containing an out-of-scope topic.

**Expected**: SCOPE_CHANGE verdict with confidence/topics/explanation +
`advisory: true`, in under 30 s. `get_scope_lock` / `list_watched_paths` return the
baseline frame with no classifier call. Unconfigured repo → `configured: false` + hint.

## V6. Baseline-trust check (FR-010)

In a configured repo, locally edit `.specguard/lock.json` to allow a currently
out-of-scope topic, then add that topic to README and run `specguard check`.

**Expected**: verdict still SCOPE_CHANGE — config was read at baseline HEAD, and the
output names that baseline. (This is the local mirror of the Phase 0 E2E security fix.)

## Success-criteria traceability

| Scenario | Validates |
|---|---|
| V2 | SC-001, FR-003 |
| V3 | SC-002, FR-001 |
| V4 | SC-003, FR-006 |
| V5 | SC-004, FR-007 |
| V1+V4+V5 | SC-006, FR-005 (disclosure in 100% of outputs) |
| V6 | FR-010 |
| V1 timing assertions | SC-005 |
