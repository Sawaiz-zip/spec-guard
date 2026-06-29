# Contract: Framework Adapters & Governance Resolution

The internal interface this feature exposes. SpecGuard is a CLI/Action/MCP tool, so the "contract" is the
`governance.resolve_lock` function and the adapter behaviors the three surfaces depend on — plus the
guarantees verified by tests.

## `resolve_lock(repo_root, base_ref, changed_paths=[]) -> (ScopeLock | None, GovernanceSource)`

The single governance entry point. Replaces direct `show_file(..., LOCK_PATH)` reads in `ci.py` and
`localcheck.load_baseline_governance`. `changed_paths` (the PR/diff file paths) drives the
multi-feature/multi-proposal union; both CI and the local surfaces MUST pass the same paths so derivation
is identical in CI and locally (constitution III / FR-005).

**Guarantees**:

1. **Precedence**: explicit `.specguard/lock.json` > Spec Kit > OpenSpec > plain. The first match wins.
2. **Explicit-lock short-circuit**: if `lock.json` exists at `base_ref`, NO framework file is read, and
   the result is `(parsed_lock, "explicit-lock")`. (FR-002)
3. **Base-ref only**: every file read uses `show_file(repo_root, base_ref, path)`; detection is
   evaluated at `base_ref`. Nothing is read from the working tree / PR head. (FR-008)
4. **Never crashes on missing scope**: a detected framework with no expressible scope yields a lock with
   a derived goal and empty scope lists, not an exception. (FR-007)
5. **Loud on malformed**: an unreadable/garbled required framework file raises `ConfigError` (exit 2 in
   CI), same as a malformed `lock.json`. (FR-007)
6. **Plain unchanged**: no explicit lock and no framework ⇒ `(None, "plain")`, reproducing today's
   unconfigured behavior exactly. (FR-011)
7. **CI↔local identical**: given the same `repo_root`, `base_ref`, and `changed_paths`, the lock derived on
   the CI path and the local path is identical — the surfaces differ only in formatting, never in the
   derived governance. (FR-005, constitution III)
8. **No truncation**: derived `scope_in`/`scope_out` are passed to the classifier in full; scope lists are
   never truncatable. (FR-009)

## Spec Kit adapter

**Input**: `.specify/memory/constitution.md` + the `specs/<feature>/spec.md` files whose directory is
touched by `changed_paths` (all at `base_ref`).

**Output**: `ScopeLock` with:
- `goal`: constitution project identity + first principle (non-empty); refined by a touched feature
  spec's title when present.
- `scope_out`: union of constitution "out of scope" items and touched feature specs' out-of-scope items.
- `scope_in`: union of touched feature specs' in-scope items (may be empty).

**Multi-feature rule**: constitution always contributes; feature specs contribute only for touched
feature dirs; multiple → union; none → constitution alone. Deterministic and order-independent.

## OpenSpec adapter

**Input**: `openspec/project.md`, `openspec/specs/**`, touched `openspec/changes/<id>/proposal.md`
(base_ref).

**Output**: `ScopeLock` with goal from `project.md`; `scope_in`/`scope_out` from the touched proposals'
scope sections (union; deterministic tie-break by dir name).

**Status**: documented-format implementation, not live-validated this phase (R3). The explicit-lock
override is the escape hatch if a real OpenSpec layout differs.

## Reporting contract

`resolve_lock`'s `GovernanceSource` is surfaced to the user:
- **Action**: one line in the job summary (e.g. `Governance source: spec-kit`).
- **MCP/CLI**: a `governance_source` field in the advisory payload / a line in `check` output.

No other surface or UI is added (constitution VI).

## Test contract (what `tests/test_governance.py` must assert)

- **Precedence**: explicit lock wins over Spec Kit/OpenSpec; Spec Kit wins over OpenSpec; none ⇒ plain.
- **Explicit-lock short-circuit**: with `lock.json` present, framework files are not consulted (assert by
  using framework files that, if read, would produce a different scope).
- **Base-ref isolation**: framework files altered ONLY in the head commit do not change the derived lock.
- **Spec Kit derivation**: goal + scope_out parsed from a fixture constitution; scope union across two
  touched feature dirs; constitution-only when no feature dir is touched.
- **OpenSpec derivation**: scope parsed from a fixture proposal; union across touched change dirs.
- **Degrade**: detected framework with empty scope sections ⇒ goal + empty lists, no exception.
- **Malformed**: garbled required file ⇒ `ConfigError`.
- **Parity (derived == hand-authored)**: a derived lock and an equivalent hand-authored lock produce the
  SAME verdict through `engine.evaluate_pr` with a `FakeAdapter` (the constitution-III guarantee). (SC-002)
- **Parity (CI == local)**: for the same `base_ref` + `changed_paths`, the CI route (`ci.py`) and the local
  route (`load_baseline_governance`) derive the same lock and emit the same verdict. (FR-005, analyze F1)
- **No truncation**: a long derived `scope_out` reaches the classifier prompt in full. (FR-009)
- **Backward compatibility**: the existing 187-test suite stays green; plain-mode behavior is unchanged.