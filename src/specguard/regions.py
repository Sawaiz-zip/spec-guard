"""Section-level locking (007 US1): restrict governance on a watched file to
named heading regions, leaving everything else in the file ungoverned.

Anchors are exact markdown heading text, resolved with the same tolerant,
dependency-free heading scan `governance.py` already uses. A declared anchor
that cannot be located on EITHER side of a modification is a configuration
integrity failure and MUST fail loudly (FR-002) rather than silently leave the
section ungoverned — `RegionAnchorError` subclasses `ConfigError` so it
propagates through the exact same exit-2 path every other malformed-config
error already takes (research.md R3).

Only modified files are region-split (research.md R2) — a newly added file has
no prior anchor to defend, so it is governed as a whole file, unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from specguard.config import ConfigError
from specguard.gitdiff import ChangedFile, diff_from_contents

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


class RegionAnchorError(ConfigError):
    """A declared region anchor could not be located — fails the check loudly."""


@dataclass
class _Span:
    start: int
    end: int


def _locate(content: str, anchor: str) -> _Span | None:
    """The char span of the anchor's heading line through the next heading of
    equal-or-shallower level (exclusive), or end of file. None if not found."""
    lines = content.splitlines(keepends=True)
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line)

    start_idx: int | None = None
    level = 0
    for i, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match and match.group(2).strip() == anchor:
            start_idx, level = i, len(match.group(1))
            break
    if start_idx is None:
        return None

    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        match = _HEADING_RE.match(lines[j])
        if match and len(match.group(1)) <= level:
            end_idx = j
            break
    end_char = offsets[end_idx] if end_idx < len(lines) else len(content)
    return _Span(offsets[start_idx], end_char)


def _remove_spans(content: str, spans: list[_Span]) -> str:
    ordered = sorted(spans, key=lambda s: s.start)
    out: list[str] = []
    cursor = 0
    for span in ordered:
        out.append(content[cursor : span.start])
        cursor = span.end
    out.append(content[cursor:])
    return "".join(out)


def split_into_regions(
    changed: ChangedFile, anchors: list[str]
) -> tuple[list[ChangedFile], bool]:
    """Split a modified file's diff into per-anchor region diffs, plus whether
    any change fell outside every declared region.

    Raises RegionAnchorError when an anchor cannot be located in the OLD or
    the NEW content — a renamed or removed heading must fail loudly, never
    silently un-govern the section (FR-002).
    """
    covered_old: list[_Span] = []
    covered_new: list[_Span] = []
    region_changes: list[ChangedFile] = []

    for anchor in anchors:
        old_span = _locate(changed.old_content, anchor)
        if old_span is None:
            raise RegionAnchorError(
                f"{changed.path}: region anchor '{anchor}' could not be located in "
                "the base version of this file — it was renamed or never matched a "
                "heading exactly"
            )
        new_span = _locate(changed.new_content, anchor)
        if new_span is None:
            raise RegionAnchorError(
                f"{changed.path}: region anchor '{anchor}' was removed from this "
                "file — a declared region must never be silently un-governed"
            )
        covered_old.append(old_span)
        covered_new.append(new_span)

        old_text = changed.old_content[old_span.start : old_span.end]
        new_text = changed.new_content[new_span.start : new_span.end]
        if old_text == new_text:
            continue
        region = diff_from_contents(f"{changed.path}#{anchor}", old_text, new_text)
        region.change = "modified"
        region_changes.append(region)

    outside_old = _remove_spans(changed.old_content, covered_old)
    outside_new = _remove_spans(changed.new_content, covered_new)
    has_outside_change = outside_old != outside_new
    return region_changes, has_outside_change
