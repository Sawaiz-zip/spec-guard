# Research & Decisions: PR Spec-File Governance Gate (Phase 0)

All NEEDS CLARIFICATION items from Technical Context resolved below, plus the open questions
flagged in SPECGUARD_PRODUCT_SPEC.md §10 that bear on Phase 0.

## R1. Delivery mechanism: GitHub Actions vs GitHub App

- **Decision**: Composite GitHub Action + required status check; full App deferred to
  product-spec Phase 2.
- **Rationale**: Spec §9 explicitly sequences "Actions first (cheaper than a full App)". An
  Action needs no hosting, no webhook infrastructure, no OAuth app review, and branch
  protection makes its exit code unbypassable — sufficient for the thesis test.
- **Alternatives considered**: (a) GitHub App with Checks API — richer UX (re-run buttons,
  neutral conclusions, comment commands) but weeks of infra; (b) status-only API calls from
  a workflow — no benefit over a plain job status. Trade-off accepted: fork PRs can't read
  secrets (skip-with-notice) and re-evaluation rides on `pull_request_review` triggers.

## R2. Classifier model and API usage

- **Decision**: Default model `claude-opus-4-8` (Anthropic SDK), structured output via
  `client.messages.parse()` with a Pydantic `Classification` model, adaptive thinking,
  non-streaming, `max_tokens=4000`. **Model is fully user-configurable** via `model:` in
  `.specguard/config.yml` or the `SPECGUARD_MODEL` environment variable — users bring their
  own API key and choose the model that fits their cost/quality requirements.
- **Rationale**: The default is the most capable Anthropic Opus model because classification
  quality is the product — false positives kill adoption. The key design decision is that
  SpecGuard never mandates a specific model or bills users directly: the API key is a repo
  secret owned by the installing team, and cost scales entirely with their model choice.
  `messages.parse()` removes the JSON-parsing failure mode entirely — the SDK validates
  the response against the Pydantic schema.
- **Cost model**: Cost is the user's, not SpecGuard's. With the default `claude-opus-4-8`,
  expect ~3–5K input + ~500 output tokens per watched file per push; with a lighter model
  (Haiku, Sonnet, or a third-party equivalent) costs drop proportionally. The system prompt
  is byte-stable with `cache_control: {"type": "ephemeral"}` — multi-file PRs in one CI run
  share the prompt cost via the 5-minute cache window.
- **Multi-provider path (Phase 1+)**: Phase 0 uses the Anthropic SDK directly. Phase 1 will
  introduce a `ClassifierAdapter` interface so users can plug in OpenAI, Gemini, or a local
  model — same structured output contract, different SDK under the hood.
- **Alternatives considered**: Hardcoding a cheap default model (rejected — calibration risk
  dominates cost in Phase 0, and users who want cheaper can configure it); raw
  `messages.create` + manual JSON parsing (rejected — reintroduces parse failures that
  `parse()` eliminates).

## R3. Confidence thresholds and outcome mapping

- **Decision**:

  | Classification | Confidence | Enforce mode | Solo mode |
  |---|---|---|---|
  | ADDITIVE | any | PASS (quiet) | PASS (quiet) |
  | ADDITIVE | < 0.60 | PASS + notice line | PASS + notice line |
  | SCOPE_CHANGE | ≥ 0.75 (`block_threshold`) | BLOCK until role approval | WARN |
  | SCOPE_CHANGE | < 0.75 | WARN | WARN |
  | PROTECTED_VIOLATION (deterministic) | n/a | BLOCK | n/a (needs roles.yml) |

- **Rationale**: every boundary biased permissive (constitution IV); only deterministic
  checks hard-block (constitution V). 0.75 is a starting point to be tuned against the eval
  corpus before release; `risk_level` stays display-only because two probabilistic knobs
  cannot be calibrated in a two-week window.
- **Alternatives considered**: risk-level-driven outcomes (rejected for Phase 0 — doubles the
  calibration surface); hard-blocking all SCOPE_CHANGE regardless of confidence (rejected —
  guarantees Friday-merge false blocks).

## R4. Outage policy: fail-open vs fail-closed

- **Decision**: default `on_error: warn` (check passes with a loud "could not classify —
  review manually" annotation); `on_error: fail` opt-in per repo. Config parse errors always
  fail. Deterministic protected-path rules enforce regardless (no API dependency).
- **Rationale**: a vendor outage freezing every merge across every installed repo is a worse
  product failure than one unclassified diff slipping through with a visible warning. Teams
  with stricter postures flip one config key.
- **Alternatives considered**: fail-closed default (rejected — availability coupling to a
  third-party API would be the top uninstall reason); silent skip (rejected — undisclosed
  non-enforcement is worse than either).

## R5. Identity & approval detection without an App

- **Decision**: identity = PR author's GitHub login from the event payload; approvals =
  latest review per reviewer from `GET /pulls/{n}/reviews` with state APPROVED and login in
  the authorizing role; workflow triggers on `pull_request` + `pull_request_review`.
- **Rationale**: logins are server-verified and consistent across payloads and the Reviews
  API. Spec §10.8: local git identity is trivially spoofable and therefore irrelevant —
  enforcement uses platform identity.
- **Deferred**: commit-author vs PR-opener disambiguation, propose-only agent enforcement,
  email→login mapping (all Phase 2/App). roles.yml therefore uses GitHub usernames, not
  emails as in the product spec's draft sketch.

## R6. Diff context strategy

- **Decision**: unified diff + ≤ 2K chars surrounding context per hunk; goal/scope lists
  always sent in full; files < 4K chars sent whole; > 30K-char diffs truncated with
  disclosure in the verdict.
- **Rationale**: spec §6.6 flags the prototype's blind 2K-char file truncation as the thing
  to fix — the diff is the signal, surrounding headings give the classifier location context,
  and the scope lists are the reference frame that must never be cut.

## R7. Calibration methodology (the product risk)

- **Decision**: golden corpus of ~30 labeled cases (≥ 15 additive incl. the adversarial
  "mentions an out-of-scope topic only to exclude it" trap; ≥ 12 scope-change; mixed cases),
  plus `tests/eval/run_eval.py` running the corpus against the real API and printing a
  confusion matrix, per-case confidence, false-positive rate, and cost. Release gate: 0
  false BLOCKs on additive cases at default threshold. Re-run on every prompt/threshold
  change (constitution: Development Workflow).
- **Rationale**: spec §8 names calibration "the actual hard product problem"; making the
  corpus a deliverable (not an afterthought) is the only way a 2-week MVP ships with a
  defensible threshold.

## R8. Solo mode semantics

- **Decision**: no roles.yml → warn-only (SCOPE_CHANGE never fails the check); no `.specguard/`
  at all → pass with a setup notice.
- **Rationale**: GitHub forbids self-approval of one's own PR, so blocking would deadlock a
  team of one; warn-only still delivers the guardrail-against-own-agents value (spec §5.1).
  One code path serves both personas — solo mode is enforce mode minus the block outcome.

## R9. Spec Kit / OpenSpec detection (adapter seam only)

- **Decision**: `detect_framework()` checks for `.specify/` and `openspec/` and logs
  ("OpenSpec detected — adapter coming; using plain mode"). No adapter behavior in Phase 0.
- **Rationale**: keeps the Phase 2 seam visible without scope creep; constitution II forbids
  depending on their internals anyway. (This repo itself now uses Spec Kit, which doubles as
  format research for the future adapter.)

## R10. Distribution

- **Decision**: PyPI package `specguard` + composite action referenced as
  `<org>/specguard-action@v0` (pinned version inside action.yml installs the matching PyPI
  release). MIT license. README is the install surface (5-minute quickstart, SC-003).
- **Alternatives considered**: Docker-based action (slower cold start, no benefit at this
  dependency weight); vendoring the package into the action repo (complicates the Phase 1
  CLI story, same code must be `pip install`-able anyway).
