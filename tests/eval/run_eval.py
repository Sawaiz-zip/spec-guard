"""Real-API classifier calibration over the golden corpus (release gate).

Usage:
    ANTHROPIC_API_KEY=... python tests/eval/run_eval.py [--model MODEL] [--threshold T]

Prints a confusion matrix, per-case confidence, the false-positive rate, and
token usage/cost. Exits non-zero if any additive case would BLOCK at the
default threshold (SC-001) or scope-change recall is below 90% (SC-002).

Must be re-run after ANY change to the classifier prompt or thresholds
(constitution: Development Workflow).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import anthropic

from specguard.classifier import ClassifierError, classify
from specguard.gitdiff import diff_from_contents
from specguard.models import Config, ScopeLock

CORPUS = Path(__file__).parent.parent / "fixtures" / "corpus"

# USD per million tokens (input, output) — rough, for the cost line only.
PRICES = {
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


class RecordingClient:
    """Delegates to the real client while accumulating token usage."""

    def __init__(self, real: anthropic.Anthropic) -> None:
        self._real = real
        self.input_tokens = 0
        self.output_tokens = 0
        self.messages = self

    def parse(self, **kwargs: Any) -> Any:
        response = self._real.messages.parse(**kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="override classifier model")
    parser.add_argument("--threshold", type=float, default=0.75)
    args = parser.parse_args()

    config = Config(block_threshold=args.threshold)
    if args.model:
        config = config.model_copy(update={"model": args.model})

    client = RecordingClient(anthropic.Anthropic(max_retries=2))

    cases = sorted(d for d in CORPUS.iterdir() if d.is_dir())
    if not cases:
        print("no corpus cases found", file=sys.stderr)
        return 2

    results = []
    print(f"model={config.model} block_threshold={config.block_threshold}\n")
    print(f"{'case':<36} {'expected':<13} {'got':<13} {'conf':>5}  outcome")
    print("-" * 84)

    for case_dir in cases:
        expected = json.loads((case_dir / "expected.json").read_text())["classification"]
        lock = ScopeLock.model_validate(
            json.loads((case_dir / "scope.json").read_text())
        )
        changed = diff_from_contents(
            "README.md",
            (case_dir / "old.md").read_text(),
            (case_dir / "new.md").read_text(),
        )
        try:
            got = classify(client, lock, changed, config)
        except ClassifierError as exc:
            print(f"{case_dir.name:<36} {expected:<13} ERROR: {exc}")
            results.append((case_dir.name, expected, None, 0.0, "ERROR"))
            continue

        would_block = (
            got.classification == "SCOPE_CHANGE"
            and got.confidence >= config.block_threshold
        )
        if would_block:
            outcome = "BLOCK"
        elif got.classification == "SCOPE_CHANGE":
            outcome = "WARN"
        else:
            outcome = "PASS"
        flag = "" if got.classification == expected else "  << MISMATCH"
        print(
            f"{case_dir.name:<36} {expected:<13} {got.classification:<13} "
            f"{got.confidence:>5.2f}  {outcome}{flag}"
        )
        results.append((case_dir.name, expected, got.classification, got.confidence, outcome))

    # Confusion matrix
    matrix = {("ADDITIVE", "ADDITIVE"): 0, ("ADDITIVE", "SCOPE_CHANGE"): 0,
              ("SCOPE_CHANGE", "ADDITIVE"): 0, ("SCOPE_CHANGE", "SCOPE_CHANGE"): 0}
    for _, expected, got_cls, _, _ in results:
        if got_cls is not None:
            matrix[(expected, got_cls)] += 1

    print("\nConfusion matrix (rows = expected, cols = got):")
    print(f"{'':<14} {'ADDITIVE':>10} {'SCOPE_CHANGE':>14}")
    for row in ("ADDITIVE", "SCOPE_CHANGE"):
        print(
            f"{row:<14} {matrix[(row, 'ADDITIVE')]:>10} "
            f"{matrix[(row, 'SCOPE_CHANGE')]:>14}"
        )

    additive_cases = [r for r in results if r[1] == "ADDITIVE"]
    scope_cases = [r for r in results if r[1] == "SCOPE_CHANGE"]
    false_blocks = [r for r in additive_cases if r[4] == "BLOCK"]
    flagged = [r for r in scope_cases if r[2] == "SCOPE_CHANGE"]
    errors = [r for r in results if r[4] == "ERROR"]

    fp_rate = len(false_blocks) / len(additive_cases) if additive_cases else 0.0
    recall = len(flagged) / len(scope_cases) if scope_cases else 1.0

    print(f"\nfalse BLOCKs on additive corpus: {len(false_blocks)} "
          f"({fp_rate:.0%}) — SC-001 requires 0")
    print(f"scope-change recall: {len(flagged)}/{len(scope_cases)} "
          f"({recall:.0%}) — SC-002 requires >=90%")

    in_tok, out_tok = client.input_tokens, client.output_tokens
    line = f"tokens: {in_tok} in / {out_tok} out"
    if config.model in PRICES:
        in_price, out_price = PRICES[config.model]
        cost = in_tok / 1e6 * in_price + out_tok / 1e6 * out_price
        line += f"  (~${cost:.2f})"
    print(line)

    if errors:
        print(f"\n{len(errors)} case(s) errored — fix before judging the gate")
        return 2
    if false_blocks:
        print("\nGATE FAILED: additive case(s) would BLOCK at default threshold")
        return 1
    if recall < 0.90:
        print("\nGATE FAILED: scope-change recall below 90%")
        return 1
    print("\nGATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
