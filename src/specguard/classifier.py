"""The single Claude API call per watched changed file.

Contract: specs/001-pr-spec-gate/contracts/classifier.md. The system prompt is
byte-stable (cache_control: ephemeral shares it across a multi-file PR within
the 5-minute cache window) — any edit to it requires re-running the eval
harness before merge (constitution gate).
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from specguard.gitdiff import ChangedFile
from specguard.models import (
    Classification,
    Config,
    ScopeLock,
    assert_model_allowed,
)


class ClassifierError(Exception):
    """Classification unavailable after retries — engine applies on_error policy."""


class _SupportsParse(Protocol):
    """The slice of the Anthropic client the classifier uses (real or fake)."""

    messages: Any


SYSTEM_PROMPT = """\
You are SpecGuard, an independent governance reviewer of specification-file \
changes. You are never the author of the change — you review it from outside \
the authoring session.

You receive a repository's locked goal and scope, plus one changed spec file \
with its diff. Classify the change:

- ADDITIVE: a typo fix, wording clarification, formatting change, or added \
detail that stays within the locked goal and scope.
- SCOPE_CHANGE: the change alters the project's goals, adds out-of-scope \
topics, or changes the project's domain or direction.

Calibration: When uncertain, prefer ADDITIVE. Reserve SCOPE_CHANGE for \
changes that alter goals, add out-of-scope topics, or shift the project's \
direction. A change that merely mentions an excluded topic in order to \
exclude or clarify it is ADDITIVE.

Output field semantics:
- confidence: the probability that your classification is correct (0.0-1.0).
- out_of_scope_topics: the scope_out entries the change matches, or novel \
out-of-scope subjects it introduces; empty for ADDITIVE changes.
- summary: one line describing what the change does.
- explanation: human-readable reasoning behind the classification.
"""

WHOLE_FILE_LIMIT = 4000
HUNK_CONTEXT_LIMIT = 2000
TRUNCATION_MARKER = "[TRUNCATED — diff exceeded max_diff_chars]"


def build_user_message(
    lock: ScopeLock, changed: ChangedFile, max_diff_chars: int
) -> tuple[str, bool]:
    """Assemble the per-file user message.

    Returns (message, truncated). The scope_lock block is NEVER truncated —
    only the diff payload is subject to limits.
    """
    payload, truncated = _diff_payload(changed, max_diff_chars)
    scope_in = "\n".join(f"- {item}" for item in lock.scope_in) or "(none listed)"
    scope_out = "\n".join(f"- {item}" for item in lock.scope_out) or "(none listed)"
    message = (
        "<scope_lock>\n"
        f"GOAL: {lock.goal}\n"
        f"IN SCOPE:\n{scope_in}\n"
        f"OUT OF SCOPE:\n{scope_out}\n"
        "</scope_lock>\n"
        "\n"
        f'<file path="{changed.path}" change="{changed.change}">\n'
        "<diff>\n"
        f"{payload}\n"
        "</diff>\n"
        "</file>"
    )
    return message, truncated


def _diff_payload(changed: ChangedFile, max_diff_chars: int) -> tuple[str, bool]:
    if len(changed.old_content) + len(changed.new_content) < WHOLE_FILE_LIMIT:
        old = changed.old_content or "(file did not exist)"
        new = changed.new_content or "(file deleted)"
        payload = f"OLD FILE CONTENT:\n{old}\n\nNEW FILE CONTENT:\n{new}"
    else:
        payload = _cap_hunk_context(changed.diff)
    if len(payload) > max_diff_chars:
        payload = payload[:max_diff_chars] + "\n" + TRUNCATION_MARKER
        return payload, True
    return payload, False


def _cap_hunk_context(diff: str) -> str:
    """Keep every changed line; cap unchanged context at ≤2K chars per hunk."""
    lines_out: list[str] = []
    context_budget = HUNK_CONTEXT_LIMIT
    for line in diff.splitlines():
        if line.startswith("@@"):
            context_budget = HUNK_CONTEXT_LIMIT
            lines_out.append(line)
        elif line.startswith(("+", "-")) or not line.startswith(" "):
            lines_out.append(line)
        else:
            if context_budget >= len(line):
                context_budget -= len(line)
                lines_out.append(line)
            elif context_budget >= 0:
                context_budget = -1
                lines_out.append("  [context trimmed]")
    return "\n".join(lines_out)


def classify(
    client: _SupportsParse,
    lock: ScopeLock,
    changed: ChangedFile,
    config: Config,
) -> Classification:
    """Classify one changed watched file. Raises ClassifierError on exhaustion."""
    # Last-line guardrail before any API call: a blocked model must hard-fail
    # the run (ValueError -> crash/exit 2), never degrade into the on_error
    # policy like a ClassifierError would.
    assert_model_allowed(config.model)
    user_message, truncated = build_user_message(lock, changed, config.max_diff_chars)
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

    classification = _attempt(client, config, messages)
    if classification is None:
        raise ClassifierError(f"{changed.path}: classifier returned no parsable output")
    if truncated:
        classification = classification.model_copy(
            update={
                "explanation": classification.explanation
                + f" [Note: the diff was truncated at {config.max_diff_chars} chars.]"
            }
        )
    return classification


def _attempt(
    client: _SupportsParse,
    config: Config,
    messages: list[dict[str, Any]],
    reasked: bool = False,
) -> Classification | None:
    try:
        response = client.messages.parse(
            model=config.model,
            max_tokens=4000,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=messages,
            output_format=Classification,
        )
    except Exception as exc:  # SDK already auto-retried 429/5xx (max_retries)
        raise ClassifierError(f"classifier call failed: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is not None:
        return parsed  # type: ignore[no-any-return]

    raw_text = _response_text(response)
    try:
        return Classification.model_validate_json(raw_text)
    except ValidationError as exc:
        if reasked:
            raise ClassifierError(
                f"classifier output failed schema validation after re-ask: {exc}"
            ) from exc
        reask_messages = messages + [
            {"role": "assistant", "content": raw_text or "(empty response)"},
            {
                "role": "user",
                "content": (
                    "Your previous response failed schema validation:\n"
                    f"{exc}\n"
                    "Respond again with ONLY a valid Classification object."
                ),
            },
        ]
        return _attempt(client, config, reask_messages, reasked=True)


def _response_text(response: Any) -> str:
    content = getattr(response, "content", None)
    if content:
        parts = [
            getattr(block, "text", "")
            for block in content
            if getattr(block, "type", "") == "text"
        ]
        if parts:
            return "".join(parts)
    return str(getattr(response, "text", "") or "")
