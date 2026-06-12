"""SC-001: local check and merge gate produce identical verdicts (constitution III).

Drives every golden-corpus case through engine.evaluate_pr twice — once shaped
exactly as ci.py calls it, once shaped exactly as cli.py calls it — and asserts
classification and outcome match. The two surfaces may format differently;
they may never decide differently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import FakeAdapter, make_classification
from specguard.engine import evaluate_pr
from specguard.gitdiff import diff_from_contents
from specguard.models import Config, PRContext, ScopeLock

CORPUS = Path(__file__).parent / "fixtures" / "corpus"
CASES = sorted(d for d in CORPUS.iterdir() if d.is_dir())


def case_inputs(case_dir: Path):
    expected = json.loads((case_dir / "expected.json").read_text())["classification"]
    lock = ScopeLock.model_validate(json.loads((case_dir / "scope.json").read_text()))
    changed = diff_from_contents(
        "README.md",
        (case_dir / "old.md").read_text(),
        (case_dir / "new.md").read_text(),
    )
    # Deterministic stand-in classification per the labeled expectation: parity
    # is about the engine pipeline, not the (already calibrated) classifier.
    classification = make_classification(
        expected, 0.93, "HIGH" if expected == "SCOPE_CHANGE" else "LOW",
        ["something"] if expected == "SCOPE_CHANGE" else [],
    )
    return lock, changed, classification


def ci_shaped_context() -> PRContext:
    return PRContext(
        pr_number=7, base_sha="abc1234", head_sha="def5678",
        author_login="dev", is_fork=False, repo="acme/widgets",
    )


def local_shaped_context() -> PRContext:
    return PRContext(
        pr_number=0, base_sha="abc1234", head_sha="local",
        author_login="(local)", is_fork=False, repo="(local)",
    )


@pytest.mark.parametrize("case_dir", CASES, ids=lambda d: d.name)
def test_local_and_ci_paths_agree(case_dir):
    lock, changed, classification = case_inputs(case_dir)
    config = Config()

    ci_verdicts = evaluate_pr(
        [changed], lock, config, None, ci_shaped_context(),
        FakeAdapter(responses={changed.path: classification}), lambda: [],
    )
    local_verdicts = evaluate_pr(
        [changed], lock, config, None, local_shaped_context(),
        FakeAdapter(responses={changed.path: classification}), lambda: [],
    )

    assert len(ci_verdicts) == len(local_verdicts) == 1
    assert ci_verdicts[0].outcome == local_verdicts[0].outcome
    assert ci_verdicts[0].reason == local_verdicts[0].reason
    assert (
        ci_verdicts[0].classification.classification
        == local_verdicts[0].classification.classification
    )
