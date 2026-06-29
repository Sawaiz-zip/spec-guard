"""Where the locked goal/scope comes from — the governance-overlay resolver.

`resolve_lock` is the single entry point both the CI gate and the local tools
call to obtain the `ScopeLock` they judge a change against. It selects a source
by a fixed precedence:

    explicit .specguard/lock.json  >  Spec Kit  >  OpenSpec  >  plain (None)

so a repo can be governed by the spec structure it already maintains (constitution
II — overlay, not a new format) without hand-authoring a lock. EVERY read goes
through the base revision (`gitdiff.show_file` / `ref_*` at `base_ref`), never the
working checkout, so a PR can never rewrite the scope it is judged by (constitution
I, FR-008). The derived value is an ordinary `ScopeLock`, consumed by the unchanged
engine — so verdict semantics are identical across sources (constitution III).

Spec Kit derivation is dogfooded against this repository. OpenSpec derivation is
implemented in a later slice (spec 004 US2); until then an OpenSpec repo with no
explicit lock falls through to plain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from specguard.config import LOCK_PATH, ConfigError, parse_lock
from specguard.gitdiff import ref_has_path, ref_list_tree, show_file
from specguard.models import ScopeLock

GovernanceSource = Literal["explicit-lock", "spec-kit", "openspec", "plain"]

# Detection sentinels (directories) at the base ref.
SPECKIT_DIR = ".specify"
OPENSPEC_DIR = "openspec"

# Spec Kit files (relative to repo root).
SPECKIT_CONSTITUTION = ".specify/memory/constitution.md"
SPECKIT_SPECS_DIR = "specs"

# OpenSpec files (relative to repo root).
OPENSPEC_PROJECT = "openspec/project.md"
OPENSPEC_CHANGES_DIR = "openspec/changes"

_OUT_OF_SCOPE_MARKERS = ("out of scope", "out-of-scope", "non-goal", "non-goals")
_IN_SCOPE_MARKERS = ("in scope", "in-scope")


@dataclass
class DerivationContext:
    """Inputs an adapter needs to derive a lock. Not persisted."""

    repo_root: Path
    base_ref: str
    changed_paths: list[str] = field(default_factory=list)


def _read(repo_root: Path, base_ref: str, path: str) -> str | None:
    """Read a framework file at the base ref, raising ConfigError (loud, like a
    malformed lock.json) when the content is not valid UTF-8 text (FR-007)."""
    try:
        return show_file(repo_root, base_ref, path)
    except (UnicodeDecodeError, OSError) as exc:
        raise ConfigError(
            f"{base_ref}:{path}: could not read as UTF-8 text — {exc}"
        ) from exc


def resolve_lock(
    repo_root: Path,
    base_ref: str,
    changed_paths: list[str] | None = None,
) -> tuple[ScopeLock | None, GovernanceSource]:
    """Resolve the active lock and report which source produced it.

    `changed_paths` (the PR/diff file paths) drives the multi-feature union; CI and
    the local surfaces MUST pass the same paths so derivation is identical in both
    (constitution III / FR-005). Empty means constitution-only derivation.
    """
    ctx = DerivationContext(repo_root, base_ref, list(changed_paths or []))

    # 1. Explicit lock wins outright — no framework file is even read (FR-002).
    lock_text = _read(repo_root, base_ref, LOCK_PATH)
    if lock_text is not None:
        return parse_lock(lock_text, f"{base_ref}:{LOCK_PATH}"), "explicit-lock"

    # 2. Spec Kit.
    if ref_has_path(repo_root, base_ref, SPECKIT_DIR):
        derived = _derive_speckit(ctx)
        if derived is not None:
            return derived, "spec-kit"

    # 3. OpenSpec.
    if ref_has_path(repo_root, base_ref, OPENSPEC_DIR):
        derived = _derive_openspec(ctx)
        if derived is not None:
            return derived, "openspec"

    # 4. Plain / unconfigured — unchanged from prior behavior (FR-011).
    return None, "plain"


# ---------------------------------------------------------------------------
# Spec Kit adapter
# ---------------------------------------------------------------------------


def _derive_speckit(ctx: DerivationContext) -> ScopeLock | None:
    """Goal + scope from the constitution and the touched feature spec(s).

    Goal and project-wide out-of-scope come from the constitution; feature specs
    in the directories touched by `changed_paths` refine the scope (R2 multi-feature
    rule). Returns None (→ plain) only when no goal can be derived at all.
    """
    constitution = _read(ctx.repo_root, ctx.base_ref, SPECKIT_CONSTITUTION)

    goal = _speckit_goal(constitution)
    scope_out: list[str] = []
    scope_in: list[str] = []
    if constitution is not None:
        scope_out += _extract_scope_items(constitution, _OUT_OF_SCOPE_MARKERS)
        scope_in += _extract_scope_items(constitution, _IN_SCOPE_MARKERS)

    for feature_dir in _touched_feature_dirs(ctx.changed_paths):
        spec_text = _read(
            ctx.repo_root, ctx.base_ref, f"{feature_dir}/spec.md"
        )
        if spec_text is None:
            continue
        if goal is None:
            goal = _feature_title(spec_text)
        scope_out += _extract_scope_items(spec_text, _OUT_OF_SCOPE_MARKERS)
        scope_in += _extract_scope_items(spec_text, _IN_SCOPE_MARKERS)

    if goal is None:
        return None  # nothing to lock against → fall through to plain
    return ScopeLock(
        goal=goal,
        scope_in=_dedupe(scope_in),
        scope_out=_dedupe(scope_out),
        locked_by=f"spec-kit:{SPECKIT_CONSTITUTION}",
    )


def _speckit_goal(constitution: str | None) -> str | None:
    """Project identity + first principle from the constitution."""
    if constitution is None:
        return None
    title = _first_heading(constitution, level=1)
    if title is None:
        return None
    title = re.sub(r"\bconstitution\b", "", title, flags=re.IGNORECASE).strip(" -—")
    principle = _first_heading(constitution, level=3)
    if principle:
        sentence = _first_sentence_after_heading(constitution, principle)
        # Drop an enumeration prefix like "I. " or "1. " for display only.
        label = re.sub(r"^(?:[IVXLC]+|\d+)\.\s+", "", principle).strip()
        if sentence:
            return f"{title} — {label}: {sentence}"
        return f"{title} — {label}"
    return title


def _touched_feature_dirs(changed_paths: list[str]) -> list[str]:
    """`specs/<feature>` directories that the changed paths fall under (ordered)."""
    dirs: list[str] = []
    for path in changed_paths:
        parts = Path(path).parts
        if len(parts) >= 2 and parts[0] == SPECKIT_SPECS_DIR:
            feature_dir = f"{SPECKIT_SPECS_DIR}/{parts[1]}"
            if feature_dir not in dirs:
                dirs.append(feature_dir)
    return dirs


def _feature_title(spec_text: str) -> str | None:
    title = _first_heading(spec_text, level=1)
    if title is None:
        return None
    return re.sub(
        r"^feature specification:\s*", "", title, flags=re.IGNORECASE
    ).strip()


# ---------------------------------------------------------------------------
# OpenSpec adapter
#
# Built against the documented OpenSpec layout (openspec/project.md + per-change
# proposal.md scope sections); NOT live-validated against a real OpenSpec repo this
# phase (spec 004 research R3). Spec Kit is the dogfooded path; an explicit lock is
# the override when a real OpenSpec layout differs from the documented one.
# ---------------------------------------------------------------------------

_WHAT_CHANGES_HEADING = "what changes"


def _derive_openspec(ctx: DerivationContext) -> ScopeLock | None:
    """Goal from openspec/project.md; scope from the touched change proposals."""
    project = _read(ctx.repo_root, ctx.base_ref, OPENSPEC_PROJECT)
    goal = _openspec_goal(project)

    scope_out: list[str] = []
    scope_in: list[str] = []
    for change_dir in _openspec_change_dirs(ctx):
        proposal = _read(ctx.repo_root, ctx.base_ref, f"{change_dir}/proposal.md")
        if proposal is None:
            continue
        if goal is None:
            goal = _feature_title(proposal)
        scope_out += _extract_scope_items(proposal, _OUT_OF_SCOPE_MARKERS)
        scope_in += _extract_scope_items(proposal, _IN_SCOPE_MARKERS)
        scope_in += _bullets_under_heading(proposal, _WHAT_CHANGES_HEADING)

    if goal is None:
        return None
    return ScopeLock(
        goal=goal,
        scope_in=_dedupe(scope_in),
        scope_out=_dedupe(scope_out),
        locked_by=f"openspec:{OPENSPEC_PROJECT}",
    )


def _openspec_goal(project: str | None) -> str | None:
    if project is None:
        return None
    title = _first_heading(project, level=1)
    if title is None:
        return None
    sentence = _first_sentence_after_heading(project, title)
    return f"{title}: {sentence}" if sentence else title


def _openspec_change_dirs(ctx: DerivationContext) -> list[str]:
    """Change directories that govern: the ones the diff touches, else the
    lexicographically-first change dir (deterministic tie-break — R3)."""
    touched: list[str] = []
    for path in ctx.changed_paths:
        parts = Path(path).parts
        if len(parts) >= 3 and parts[0] == "openspec" and parts[1] == "changes":
            change_dir = f"{OPENSPEC_CHANGES_DIR}/{parts[2]}"
            if change_dir not in touched:
                touched.append(change_dir)
    if touched:
        return touched
    all_files = ref_list_tree(ctx.repo_root, ctx.base_ref, OPENSPEC_CHANGES_DIR)
    dirs = sorted(
        {
            f"{OPENSPEC_CHANGES_DIR}/{Path(f).parts[2]}"
            for f in all_files
            if len(Path(f).parts) >= 3
        }
    )
    return dirs[:1]


# ---------------------------------------------------------------------------
# Tolerant markdown scanning (no markdown library — research.md R1)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*\S)\s*$")


def _heading(line: str) -> tuple[int, str] | None:
    match = _HEADING_RE.match(line)
    return (len(match.group(1)), match.group(2).strip()) if match else None


def _bullet(line: str) -> str | None:
    match = _BULLET_RE.match(line)
    return match.group(1).strip() if match else None


def _first_heading(text: str, level: int) -> str | None:
    for line in text.splitlines():
        parsed = _heading(line)
        if parsed and parsed[0] == level:
            return parsed[1]
    return None


def _logical_lines(text: str) -> list[str]:
    """Re-join hard-wrapped continuation lines so a wrapped bullet/paragraph is one
    logical line. A continuation is an indented, non-blank line that is neither a
    heading nor a bullet (markdown soft-wrap of the line above)."""
    out: list[str] = []
    for raw in text.splitlines():
        is_continuation = (
            raw[:1].isspace()
            and raw.strip() != ""
            and _heading(raw) is None
            and _bullet(raw) is None
        )
        if is_continuation and out and out[-1].strip():
            out[-1] = f"{out[-1].rstrip()} {raw.strip()}"
        else:
            out.append(raw)
    return out


def _first_sentence_after_heading(text: str, heading_title: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        parsed = _heading(line)
        if parsed and parsed[1] == heading_title:
            paragraph: list[str] = []
            for body in lines[i + 1 :]:
                if _heading(body):
                    break
                if body.strip() == "":
                    if paragraph:
                        break
                    continue
                paragraph.append(body.strip())
            if not paragraph:
                return None
            joined = " ".join(paragraph)
            return re.split(r"(?<=[.!?])\s", joined, maxsplit=1)[0].strip()
    return None


def _bullets_under_heading(text: str, heading_substr: str) -> list[str]:
    """Bullets directly under any heading whose title contains `heading_substr`."""
    out: list[str] = []
    lines = _logical_lines(text)
    for i, line in enumerate(lines):
        parsed = _heading(line)
        if not (parsed and heading_substr in parsed[1].lower()):
            continue
        collected: list[str] = []
        for body in lines[i + 1 :]:
            if _heading(body):
                break
            bullet = _bullet(body)
            if bullet:
                collected.append(bullet)
            elif body.strip() == "" and collected:
                break
        out += collected
    return out


def _extract_scope_items(text: str, markers: tuple[str, ...]) -> list[str]:
    """Items associated with a scope marker — the inline `… : a; b; c` form OR the
    heading/line-followed-by-bullets form (never both for one marker, so sibling
    bullets about other topics are not swept in)."""
    items: list[str] = []
    lines = _logical_lines(text)
    for i, line in enumerate(lines):
        if not any(marker in line.lower() for marker in markers):
            continue
        tail = line.rsplit(":", 1)[1].strip() if ":" in line else ""
        if tail:
            # Inline list form: split the post-colon remainder on ';'.
            items += [part.strip(" .") for part in tail.split(";") if part.strip(" .")]
            continue
        # Block form: the marker is a heading / bare label — collect following bullets.
        for body in lines[i + 1 :]:
            if _heading(body):
                break
            bullet = _bullet(body)
            if bullet:
                items.append(bullet)
            elif body.strip() == "" and items:
                break
    return items


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result