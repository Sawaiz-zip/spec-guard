# Quickstart Validation Guide: PR Spec-File Governance Gate

Runnable scenarios proving the feature end-to-end. Contracts:
[classifier](contracts/classifier.md), [action interface](contracts/action-interface.md).
Entities: [data-model.md](data-model.md).

## Prerequisites

- Python 3.10+, `pip install -e ".[dev]"` from repo root
- For real-API scenarios only: `ANTHROPIC_API_KEY` exported
- For Action scenarios: [`act`](https://github.com/nektos/act) installed, or a sandbox GitHub
  repo with branch protection rights

## V1. Unit suite (no API key) — every merge

```bash
pytest
```

**Expected**: all green. Covers config parsing, diff extraction, roles resolution, approval
matching, engine outcomes (via FakeAnthropicClient), and ci.py against fixture event payloads.

## V2. Classifier calibration (real API) — release gate

```bash
python tests/eval/run_eval.py
```

**Expected output**: confusion matrix over the golden corpus, per-case confidence, total
cost. **Gate (SC-001/SC-002): 0 false BLOCKs on additive cases; ≥ 90% of scope-change cases
flagged** at default `block_threshold: 0.75`. Must be re-run after any change to the
classifier prompt or thresholds.

## V3. Local Action run (no GitHub) 

```bash
act pull_request -e tests/fixtures/events/pr_scope_change.json \
    -s ANTHROPIC_API_KEY -s GITHUB_TOKEN=dummy
```

**Expected**: job fails (exit 1) with a `::error` annotation for the scope-change fixture;
re-run with `pr_typo_fix.json` → job passes with no annotations.

## V4. Sandbox end-to-end (the demo) — before publishing

Setup in a throwaway repo:
1. Copy `.specguard/lock.json` (goal: anything; `scope_out: ["SSO"]`), `config.yml`, and
   `roles.yml` (yourself as `architect`, a second account as `contributors`) from the README
   templates.
2. Add `ANTHROPIC_API_KEY` secret; add the consumer workflow from the
   [action contract](contracts/action-interface.md).
3. Branch protection: require status check `specguard`.

Scenarios (run in order):

| # | Action | Expected |
|---|---|---|
| 1 | Second account opens PR adding an "SSO integration" section to README.md | Check fails; message shows SCOPE CHANGE + confidence + `SSO` matched + "requires approval from architect"; merge button blocked |
| 2 | Architect approves via normal PR review | `pull_request_review` re-runs the check; passes; merge unblocked — no new pushes needed |
| 3 | New PR fixing a typo in README.md | Check passes; zero annotations; one quiet summary line |
| 4 | Second account's PR edits `.specguard/roles.yml` | Check fails with protected-violation message (deterministic, no classification shown) |
| 5 | Delete `roles.yml` from the sandbox; repeat scenario 1 | Check passes with a warning annotation carrying the same classification (solo mode) |
| 6 | Temporarily set an invalid `ANTHROPIC_API_KEY`; push to PR | Check passes with loud "could not classify" warning (`on_error: warn` default) |

## V5. Dogfood — continuous

`.github/workflows/specguard.yml` in this repo guards `SPECGUARD_PRODUCT_SPEC.md` and
`README.md`. **Expected**: every PR to this repo shows SpecGuard verdicts; an intentional
out-of-scope edit to the product spec gets blocked.

## Success-criteria traceability

| Scenario | Validates |
|---|---|
| V2 | SC-001, SC-002 |
| V4.1–V4.2 | SC-004, FR-005, FR-009, FR-010 |
| V4.3 | SC-005 timing, FR-004 |
| V4.4 | FR-007, FR-008 |
| V4.5 | FR-011 |
| V4.6 | FR-012, FR-013 |
| V4 setup ≤ 5 min | SC-003, FR-015 |
