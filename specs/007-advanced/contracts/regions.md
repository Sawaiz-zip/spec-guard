# Contract: Section-Level Locking

Owner: `src/specguard/regions.py`. Optional file: `.specguard/regions.yml`.

## `RegionsConfig`

```yaml
files:
  "ARCHITECTURE.md": ["Goal", "Out of Scope"]
```

`files: dict[str, list[str]]` — path (scope-relative) → exact heading-text anchors. Parsed
by `config.parse_regions(text, source) -> RegionsConfig | None` (same shape as
`parse_config`/`parse_roles`: malformed YAML/schema → `ConfigError`; absent file → `None`).

## `split_into_regions(changed: ChangedFile, anchors: list[str]) -> tuple[list[ChangedFile], bool]`

Only called for `changed.change == "modified"` files with a `regions.yml` entry. For each
anchor:

1. Locate the heading in `changed.old_content` AND `changed.new_content` (exact text match
   after the leading `#`s). **Either side missing → `RegionAnchorError`** (a `ConfigError`
   subclass — same exit-2 path as any other malformed config).
2. The region spans from the heading line through (exclusive) the next heading of
   equal-or-shallower level, or end of file.
3. If the old and new region text are identical, skip (nothing changed there).
4. Otherwise build a region `ChangedFile` with `path = f"{changed.path}#{anchor}"`.

Returns `(region_changed_files, has_outside_change)` — the second element is `True` when the
content outside every declared span differs between old and new.

## Engine integration

`engine.evaluate_pr(..., regions_config: RegionsConfig | None = None)`. For a file with a
`regions_config` entry:

- Each region `ChangedFile` is classified and verdicted exactly like a normal file (full
  pipeline: ADDITIVE/SCOPE_CHANGE, threshold, approvals).
- If `has_outside_change`, ONE additional `Verdict(outcome="PASS",
  reason="region_ungoverned", classification=None)` is appended — no classifier call.
- A file with no declared regions, or an added/deleted file, is governed as a whole file
  exactly as before (regions are a pure narrowing, never a widening, of what gets checked).

## Failure contract

| Condition | Behavior |
|---|---|
| anchor missing on either side of a modification | `RegionAnchorError` → propagates to `ci.py main()`'s existing `except ConfigError` → exit 2, `::error::` |
| `regions.yml` malformed | `ConfigError` at parse time, same as `lock.json`/`roles.yml` |
| no `regions.yml` | whole-file governance, unchanged from Phase 0–2 |
