# Implementation Plan: Framework Adapters (Governance Overlay on Existing Specs)

**Branch**: `004-framework-adapters` | **Date**: 2026-06-29 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-framework-adapters/spec.md`

## Summary

Turn the existing `detect_framework()` seam (today log-only — `ci.py` prints *"adapter coming;
using plain mode"*) into real governance derivation. A new `governance.resolve_lock(repo_root,
base_ref)` becomes the single source of the locked goal/scope, selecting by a fixed precedence:
explicit `.specguard/lock.json` > Spec Kit derivation > OpenSpec derivation > plain (None). Spec Kit
derivation reads `.specify/memory/constitution.md` (project goal + "out of scope" boundaries) and the
feature `spec.md` files touched by the change; OpenSpec derivation reads `openspec/specs/**` and the
active `openspec/changes/<id>/proposal.md` scope sections. Every read goes through `show_file(repo,
base_ref, path)`, so derivation is taken from the **PR base**, never the PR's own checkout — a PR can
never rewrite the scope it is judged by. The derived `ScopeLock` feeds the unchanged engine, so the
Action and the local tools (CLI/MCP) produce identical verdicts regardless of source. No Spec Kit or
OpenSpec code is imported — only their public markdown is parsed.

## Technical Context

**Language/Version**: Python ≥ 3.10 (unchanged). No new syntax.

**Primary Dependencies**: unchanged core (pydantic, pyyaml, httpx, anthropic). **No new dependencies**
— markdown parsing is done with the stdlib (line scanning), not a markdown library, to stay
dependency-light and deterministic.

**Storage**: none. Governance is read from git blobs at the base ref via the existing
`gitdiff.show_file` (`git show <ref>:<path>`).

**Testing**: pytest. New `tests/test_governance.py` (precedence, Spec Kit derivation, OpenSpec
derivation, base-ref isolation, malformed-file handling, empty-scope) + a parity test asserting a
derived lock and an equivalent hand-authored lock yield identical verdicts through the engine. No live
LLM key needed (FakeAdapter), matching the constitution's CI rule.

**Target Platform**: unchanged — runs in GitHub Actions and locally.

**Project Type**: same single package. One new module (`governance.py`) plus a small change to the
three surfaces' lock-loading call sites.

**Performance Goals / Constraints**: derivation is a handful of `git show` reads + line scans — negligible
vs. the LLM call. Derived scope lists are sent to the classifier in full (never truncated), same as a
hand-authored lock. Detection and all file reads are base-ref-scoped.

## Constitution Check

*GATE: evaluated against constitution v1.1.0 — all pass.*

| Principle | Status | How the design complies |
|---|---|---|
| I. Merge-time is the security layer | ✅ | Derivation reads only the **base** revision (`show_file(base_ref, …)`); a PR's own framework-file edits cannot change the scope it is judged by. No new enforcement surface. |
| II. Governance overlay, not a framework | ✅ | This *is* the principle realized: SpecGuard reads Spec Kit / OpenSpec **public file formats**, imports none of their code, and plain mode still works with no framework present. |
| III. One shared validator core | ✅ | All sources produce a `ScopeLock` consumed by the same `engine.evaluate_pr`. The Action and local tools call one `resolve_lock`; verdict semantics are unchanged. |
| IV. Zero friction for additive | ✅ | Verdict logic untouched; additive changes still auto-pass. Derivation only changes where the goal/scope come from. |
| V. Deterministic hard blocks, probabilistic advice | ✅ | PROTECTED_VIOLATION path-rules and identity unchanged; derivation feeds only the semantic (ADDITIVE/SCOPE_CHANGE) comparison. Precedence is deterministic. |
| VI. No dashboard | ✅ | Config + terminal only; the active governance source is reported in existing outputs. |

*No constitution amendment required: §"Additional Constraints" already says SpecGuard reads the file
conventions of Spec Kit / OpenSpec and that plain mode must always work. This feature implements that
existing constraint.*

## Project Structure

```text
specs/004-framework-adapters/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/framework-adapters.md
└── tasks.md   (created by /speckit-tasks)

src/specguard/
├── governance.py     # NEW: resolve_lock() + GovernanceSource; Spec Kit & OpenSpec derivation
├── config.py         # detect_framework() → base-ref aware (framework_at_ref helper); kept as the detector
├── ci.py             # construct lock via resolve_lock(repo, base_sha); report source in summary
├── localcheck.py     # load_baseline_governance() uses resolve_lock(repo, base_ref)
├── mcp_server.py     # (inherits via localcheck) report source in advisory payload
└── models.py         # (unchanged ScopeLock; GovernanceSource is a Literal in governance.py)

tests/test_governance.py   # NEW
pyproject.toml / deps      # UNCHANGED — no new dependency
```

**Structure Decision**: All derivation lives in one new `governance.py` so the three surfaces share a
single dispatch point (`resolve_lock`), mirroring how `make_adapter` centralized provider dispatch in
003. `detect_framework` stays in `config.py` but becomes base-ref aware. No markdown library is added;
parsing is tolerant line-scanning over the public formats (research.md R2/R3).

## Core Design Decisions

### D1. One resolver, fixed precedence

`resolve_lock(repo_root, base_ref) -> tuple[ScopeLock | None, GovernanceSource]`. Order: explicit
`lock.json` → Spec Kit → OpenSpec → plain (`None`, "unconfigured"). First hit wins; an explicit lock
short-circuits before any framework file is read (FR-002). Both `ci.py` and `load_baseline_governance`
call it instead of reading `LOCK_PATH` directly — the only change at the call sites.

### D2. Base-ref isolation is mandatory, not incidental

Every framework file is read with `show_file(repo_root, base_ref, path)` and detection uses a
`framework_at_ref` check (`git ls-tree`/`show` at the ref), **not** filesystem `is_dir()`. This extends
the existing trusted-base rule (localcheck.py docstring; ci.py:92) to framework files (FR-008). A test
asserts that adding/altering framework files only in the head commit does not change the derived lock.

### D3. Spec Kit derivation rule (research.md R2)

- **goal** ← the constitution's project identity + first principle statement; if a touched feature
  `spec.md` has a clear primary objective / Success-Criteria intent, it refines the goal for that
  feature. Never empty (constitution always has a goal line); falls back to the feature spec title.
- **scope_out** ← lines following any case-insensitive "out of scope" marker in the constitution
  (this repo's constitution has "Explicitly out of scope … : a; b; c") unioned with the touched
  feature specs' out-of-scope items.
- **scope_in** ← in-scope/again-scope markers in the touched feature specs; empty if none expressed.
- **Multi-feature rule**: the constitution supplies the project-wide goal + scope_out; feature scope is
  unioned across exactly the `specs/<feature>/` directories whose files appear in the PR diff. If the
  diff touches no feature dir, the constitution alone governs. Deterministic and order-independent.

### D4. OpenSpec derivation rule (research.md R3)

- **goal** ← `openspec/project.md` purpose (or the specs' stated intent).
- **scope_out / scope_in** ← the active `openspec/changes/<id>/proposal.md` scope sections; when
  multiple change dirs exist, the one(s) touched by the PR diff govern (same union rule as D3); ties
  broken deterministically by directory name. Built against the documented OpenSpec format; flagged for
  live validation (no OpenSpec sample repo at build time — mirrors how 003 shipped provider adapters
  against SDK docs). Spec Kit is the live-dogfooded path; OpenSpec is best-effort-correct.

### D5. Degrade predictably, report the source

Framework detected but scope files missing/empty → derive goal with empty scope lists (matches an empty
plain lock) rather than crash (FR-007). Unparseable framework file → a loud `ConfigError`, same class
malformed `lock.json` raises today. The active `GovernanceSource` (explicit-lock | spec-kit | openspec |
plain) is surfaced in the Action job summary and the MCP/CLI advisory payload (FR-010), so a verdict's
provenance is never ambiguous.

### D6. Backward compatibility is a test, not a hope

Repos with an explicit lock or no framework must be byte-identical to today. Guaranteed by: (a) explicit
lock is checked first and unchanged; (b) `None` (plain) path is unchanged; (c) the existing 187-test
suite must stay green; (d) a new parity test pins "derived == hand-authored ⇒ same verdict."

## Complexity Tracking

> No constitution violations — table intentionally empty.
