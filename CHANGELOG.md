# Changelog

All notable changes to SpecGuard. Versions follow [SemVer](https://semver.org);
each release is tagged and published on [GitHub Releases](https://github.com/Sawaiz-zip/spec-guard/releases).

> **Publishing note:** 0.4.1–0.4.4 are released on GitHub but **not yet on PyPI**
> (latest published: 0.4.0). The composite Action (`action.yml`) intentionally
> stays pinned to `specguard-ci==0.4.0` until a newer version is on PyPI, so the
> live Marketplace Action never breaks.

## [0.4.4] — 2026-08-04

### Fixed
- **MCP write-time tools are multi-scope aware.** `check_proposed_change`,
  `check_permission`, and `get_scope_lock` judged a path against the repo-root
  lock only; in a monorepo they now resolve the path's own package scope,
  matching the merge gate. Added `resolve_scope_for_path`; `get_scope_lock`
  gains an optional `path`. (#17)

## [0.4.3] — 2026-08-04

### Fixed
- **`specguard check` honors monorepo multi-scope.** It resolved governance
  repo-root-only and bailed with "run specguard init" when only per-package
  `.specguard/` scopes existed; it now mirrors the merge gate's per-scope loop —
  each package judged against its own lock/config/roles/regions. (#16)

## [0.4.2] — 2026-08-04

### Fixed
- **Section locking works on the local surfaces.** `regions.yml` was honored only
  by the CI gate: a change outside a governed region false-blocked in
  `specguard check` and the MCP server, and the local renderer crashed on the
  `region_ungoverned` verdict. Both now load and apply regions from the baseline. (#15)

## [0.4.1] — 2026-08-04

### Changed
- Package metadata bumped to 0.4.1 (the self-documenting config templates from
  the 008 work shipped under 0.4.0's tag).

## [0.4.0] — 2026-07-05

- GitHub App (fork-PR governance, native check runs), advanced governance
  (section locking, monorepo multi-scope, audit export), approval commands,
  provider-agnostic classifier, and framework adapters (Spec Kit / OpenSpec).
  See the GitHub release for the full history.

[0.4.4]: https://github.com/Sawaiz-zip/spec-guard/releases/tag/v0.4.4
[0.4.3]: https://github.com/Sawaiz-zip/spec-guard/releases/tag/v0.4.3
[0.4.2]: https://github.com/Sawaiz-zip/spec-guard/releases/tag/v0.4.3
[0.4.1]: https://github.com/Sawaiz-zip/spec-guard/releases/tag/v0.4.1
[0.4.0]: https://github.com/Sawaiz-zip/spec-guard/releases/tag/v0.4.0
