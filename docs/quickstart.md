# SpecGuard Quickstart & Validation Guide

Five-minute setup is in the [README](../README.md#quickstart). This guide covers
running SpecGuard's own checks and validating an installation end-to-end.

## V1. Unit suite (no API key)

```bash
pip install -e ".[dev]"
pytest
```

All tests run against a fake Anthropic client — no network, no key. Covers
config parsing, diff extraction, role resolution, approval matching, engine
outcomes, and the CI entrypoint against fixture event payloads.

## V2. Classifier calibration (real API) — release gate

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python tests/eval/run_eval.py            # optionally --model ... --threshold ...
```

Runs the golden corpus (15 additive + 12 scope-change cases) against the real
classifier and prints a confusion matrix, per-case confidence, false-positive
rate, and cost. The gate:

- **SC-001**: 0 false BLOCKs on additive cases at the default threshold
- **SC-002**: ≥ 90% of scope-change cases flagged

Re-run this after **any** change to the classifier prompt or thresholds.

## V3. Local Action run (no GitHub)

With [`act`](https://github.com/nektos/act) installed:

```bash
act pull_request -e tests/fixtures/events/pr_scope_change.json \
    -s ANTHROPIC_API_KEY -s GITHUB_TOKEN=dummy
```

Expected: the job fails (exit 1) with an `::error` annotation for the
scope-change fixture; re-run with `pr_typo_fix.json` and the job passes with
no annotations. (Replace the `BASE_SHA`/`HEAD_SHA` placeholders in the fixture
with real commits from your checkout first.)

## V4. Sandbox end-to-end (the demo)

In a throwaway GitHub repo:

1. Copy `.specguard/lock.json` (any goal; include `"SSO"` in `scope_out`),
   `config.yml`, and `roles.yml` (yourself as `architect`, a second account as
   a contributor) from the README templates.
2. Add the `ANTHROPIC_API_KEY` secret and the README's consumer workflow.
3. Branch protection: require the `specguard` status check.

Then run these scenarios in order:

| # | Action | Expected |
|---|--------|----------|
| 1 | Second account opens a PR adding an "SSO integration" section to README.md | Check fails: SCOPE CHANGE + confidence + `SSO` matched + "requires approval from architect"; merge blocked |
| 2 | Architect approves via a normal PR review | `pull_request_review` re-runs the check; passes; merge unblocked — no new pushes |
| 3 | New PR fixing a typo in README.md | Check passes; zero annotations; one quiet summary line |
| 4 | Second account's PR edits `.specguard/roles.yml` | Check fails with the protected-violation message (deterministic, no classification) |
| 5 | Delete `roles.yml`; repeat scenario 1 | Check passes with a warning annotation carrying the same classification (solo mode) |
| 6 | Set an invalid `ANTHROPIC_API_KEY`; push to the PR | Check passes with a loud "could not classify" warning (`on_error: warn` default) |

## V5. Dogfood

This repository guards its own spec files: `.github/workflows/specguard.yml`
watches `README.md`, `SPECGUARD_PRODUCT_SPEC.md`, and `specs/**/*.md` against
the scope locked in `.specguard/lock.json`.

---

# Local Tools (Phase 1)

## L1. Local check parity

```bash
pytest tests/test_parity.py
```

**Expected**: every golden-corpus case produces identical classification and
outcome through the local path and the CI path (SC-001).

## L2. Init to first check (under 5 minutes)

```bash
mkdir demo && cd demo && git init -b main
specguard init            # answer the prompts
git add -A && git commit -m "specguard setup"
# edit a watched file, then:
specguard check
```

**Expected**: verdicts plus the advisory notice and the baseline used. Exit
codes mirror the gate: 0 nothing would block, 1 would block, 2 config error.

## L3. Hook never blocks

Install via `specguard init` (plain git hook) or the pre-commit framework
(see README). Commit an out-of-scope spec edit → warning prints, **commit
succeeds**. Unset `ANTHROPIC_API_KEY` → "could not classify" notice, commit
succeeds. Non-spec commits → no output, no delay.

## L4. MCP write-time check

```bash
pip install "specguard-ci[mcp]"
specguard mcp     # connect an MCP client over stdio (see README for config)
```

Invoke `specguard_check_proposed_change` with drafted content for a watched
file → full verdict with `advisory: true` before anything is committed.

## L5. Baseline trust (local mirror of FR-010)

Locally edit `.specguard/lock.json` to allow a currently out-of-scope topic,
add that topic to README, run `specguard check` → still SCOPE CHANGE: config
is read at the committed baseline, which the output names.
