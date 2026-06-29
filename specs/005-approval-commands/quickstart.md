# Quickstart / Validation: Approval Commands & Agent Containment

Runnable scenarios proving the feature. Tests use `httpx` mock transports + `FakeAdapter`; no live token.

## Prerequisites

- Dev install (`pip install -e ".[dev]"`), `pytest`/`ruff`/`mypy` available.

## Scenario 1 — Comment command clears a block (SC-001)

```bash
pytest tests/test_ci.py -k comment_approval -q
```

**Expected**: green. A PR blocked by a SCOPE_CHANGE passes once an authorized login's `/specguard
approve` comment (posted at/after the head commit) is present in the combined approval source; an
unauthorized commenter's identical comment leaves it blocked.

## Scenario 2 — CLI approve (SC-002)

```bash
pytest tests/test_cli.py -k approve -q
```

**Expected**: green. `specguard approve <pr>` submits an approving review through the (mocked) platform;
the gate then recognizes it. Without a token the command exits 2 and posts nothing.

## Scenario 3 — Three paths agree (SC-003, SC-004)

```bash
pytest tests/test_approvals.py -k "parity or staleness" -q
```

**Expected**: green. For the same PR + roles, an authorized approver clears the block via review, comment,
or CLI; a non-authorized actor clears it via none. A stale (pre-head-commit) comment does not qualify.

## Scenario 4 — Agent containment (SC-005)

```bash
pytest tests/test_mcp_server.py -k "permission or redirect" -q
```

**Expected**: green. `check_permission` answers yes/no per the roles rules; a would-block proposed change
returns a `redirect` naming the required role and the proposal suggestion; an additive change returns the
unchanged payload (no `redirect`).

## Manual end-to-end (optional, needs a real repo + token)

1. Open a PR that makes a scope change to a watched file → gate blocks, names the role.
2. As an authorized role member, comment `/specguard approve` → the gate re-runs and passes.
3. Alternatively run `specguard approve <pr>` as that member → same result via a native review.

## Full gate (the release bar)

```bash
pytest -q && ruff check src tests && mypy src
```

**Expected**: all green, including the new approval-path, CLI, MCP, and ci tests, with the existing suite
unchanged (backward compatibility).
