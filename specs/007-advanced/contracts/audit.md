# Contract: Audit Export

Owner: `src/specguard/audit.py`. Opt-in via `SPECGUARD_AUDIT_PATH` (ci.py only this phase —
see research.md R7).

## `build_audit_entries(verdicts, approvals, pr, as_of=None) -> list[AuditEntry]`

One `AuditEntry` per `Verdict`: `repo`, `pr_number`, `head_sha`, `file`, `scope`, `outcome`,
`reason`, `classification` + `confidence` (from `Verdict.classification` when present),
`required_approver_roles`, the **full** approvals list seen on the PR (`login`, `state`,
`source` — no per-approval timestamp, see research.md R6), and `as_of` (one timestamp for
the whole batch — the PR's head commit time).

No secrets, no API keys, nothing beyond what is already visible in the rendered check/PR.

## `export_audit_json(entries: list[AuditEntry]) -> str`

`json.dumps([e.model_dump() for e in entries], indent=2)`.

## Wiring (ci.py)

```python
if os.environ.get("SPECGUARD_AUDIT_PATH"):
    approvals = get_approvals()  # memoized — no duplicate API call if already fetched
    as_of = fetch_commit_time(pr.repo, pr.head_sha, token)
    entries = build_audit_entries(all_verdicts, approvals, pr, as_of=as_of)
    Path(os.environ["SPECGUARD_AUDIT_PATH"]).write_text(export_audit_json(entries))
```

A consumer's own workflow YAML uploads the file as an artifact
(`actions/upload-artifact@v4`) — SpecGuard introduces no storage of its own (FR-006).

## Guarantees

- Absent the env var: zero behavior change, zero extra API calls (FR-007, SC-005).
- Present: one JSON file, one record per verdict across every scope in the PR, no secrets
  (SC-004).
- Embedding the same payload into the GitHub App's check-run output is a documented,
  deferred follow-up (research.md R7) — not implemented this phase.
