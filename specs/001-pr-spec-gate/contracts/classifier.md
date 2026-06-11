# Contract: Classifier I/O

The single Claude API call per watched changed file. Owner: `src/specguard/classifier.py`.

## Request

- Endpoint: Anthropic Messages API via `client.messages.parse()`
- Model: from Config (`claude-opus-4-8` default)
- `thinking: {"type": "adaptive"}`, `max_tokens: 4000`, non-streaming
- `output_format`: the `Classification` Pydantic model (SDK-enforced schema)

### System prompt (byte-stable; `cache_control: {"type": "ephemeral"}`)

Fixed content, in order:
1. Role: independent governance reviewer of spec-file changes (never the authoring agent).
2. Rubric: ADDITIVE = typo/clarification/detail within locked scope; SCOPE_CHANGE = alters
   goals, adds out-of-scope topics, changes domain/direction.
3. Calibration: "When uncertain, prefer ADDITIVE. Reserve SCOPE_CHANGE for changes that
   alter goals, add out-of-scope topics, or shift the project's direction. A change that
   merely *mentions* an excluded topic in order to exclude or clarify it is ADDITIVE."
4. Output field semantics (confidence = probability the classification is correct;
   out_of_scope_topics = matched scope_out entries or novel out-of-scope subjects).

Any edit to this prompt requires re-running the eval harness (constitution gate).

### User message (per file)

```
<scope_lock>
GOAL: {goal}
IN SCOPE: {scope_in, full list}
OUT OF SCOPE: {scope_out, full list}
</scope_lock>

<file path="{repo-relative path}" change="{modified|added|deleted}">
<diff>
{unified diff; hunks with ≤2000 chars surrounding context each;
 whole file instead if old+new < 4000 chars;
 truncated at max_diff_chars with an explicit TRUNCATED marker}
</diff>
</file>
```

Invariant: scope_lock content is NEVER truncated.

## Response

`Classification` (validated by the SDK against this schema):

```json
{
  "classification": "ADDITIVE | SCOPE_CHANGE",
  "confidence": 0.0,
  "risk_level": "LOW | MEDIUM | HIGH",
  "out_of_scope_topics": ["..."],
  "summary": "one line",
  "explanation": "why"
}
```

## Failure contract

| Failure | Behavior |
|---|---|
| 429 / 5xx | SDK auto-retry (max_retries=2) |
| Schema validation failure | one re-ask appending the validation error; then raise `ClassifierError` |
| Any other API error after retries | raise `ClassifierError` |
| `ClassifierError` reaching the engine | verdict `reason="classifier_error"`, outcome per `on_error` (warn→PASS+loud annotation, fail→BLOCK) |

## Test doubles

`FakeAnthropicClient` (tests/conftest.py) returns canned `Classification`s keyed by file
path; raises configurable errors for the failure-path tests. The real call is exercised only
by `tests/eval/run_eval.py`.
