# Quickstart Validation Guide: Provider-Agnostic & Python 3.10

Contracts: [provider-adapters](contracts/provider-adapters.md). Entities:
[data-model.md](data-model.md).

## V1. Unit suite, no keys (every merge)

```bash
pip install -e ".[dev]"
pytest
```

**Expected**: all green, including `test_providers.py` (factory selection, config validation,
env-var mapping, cross-provider Opus guardrail) — none of which needs a provider SDK or key.

## V2. Python 3.10 compatibility (SC-001)

```bash
python3.10 -m venv /tmp/sg310 && /tmp/sg310/bin/pip install -e ".[dev]"
/tmp/sg310/bin/python -m pytest
```

**Expected**: full suite passes on 3.10 (and 3.11) exactly as on 3.12. CI runs the matrix.

## V3. Switch providers (SC-002) — needs that provider's key

```yaml
# .specguard/config.yml
provider: openai
model: gpt-4o-2024-11-20
```

```bash
pip install "specguard-ci[openai]"
export OPENAI_API_KEY=sk-...
specguard check
```

**Expected**: watched-file changes classified through OpenAI with verdicts identical in shape
to the Anthropic path. Repeat with `provider: gemini` (`pip install "specguard-ci[gemini]"`,
`GEMINI_API_KEY`) and `provider: openrouter` (`OPENROUTER_API_KEY`, vendor-namespaced model).

## V4. Guardrail across providers (SC-003)

```bash
# config.yml: provider: openrouter, model: anthropic/claude-opus-4-8
specguard check
```

**Expected**: hard error — blocked by the Opus 4.8 guardrail at config load, before any call.

## V5. Haiku works but is opt-in (SC-004)

```bash
ANTHROPIC_API_KEY=... python tests/eval/run_eval.py --model claude-haiku-4-5-20251001
```

**Expected**: completes (no unsupported-parameter error — thinking is omitted for Haiku),
reports 0 false BLOCKs but ~83% recall → GATE FAILED on recall. Confirms Haiku is a valid
selectable model but correctly NOT the default.

## Success-criteria traceability

| Scenario | Validates |
|---|---|
| V1, V2 | SC-001, FR-004, FR-005 |
| V3 | SC-002, FR-001, FR-003 |
| V4 | SC-003, FR-002 |
| V5 | SC-004, FR-006, FR-007 |
