<div align="center">

# SpecGuard

**Semantic governance for spec files — built for teams where humans and AI agents collaborate.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Status: Phase 0](https://img.shields.io/badge/Status-Phase%200%20MVP-orange.svg)]()

</div>

---

CODEOWNERS enforces who can change a file.
SpecGuard enforces **what** those changes are allowed to mean.

It runs as a required GitHub Actions status check. When a pull request touches a watched spec file, SpecGuard classifies the change against the repository's locked goal and scope — then either passes it silently, surfaces a warning, or blocks the merge until an authorized reviewer approves.

---

## How it works

Lock your project goal and scope in a single JSON file. SpecGuard does the rest.

```
Pull Request opened
│
├── File not in watch list ─────────────────────────────► Pass
│
├── Protected path + unauthorized author ───────────────► Block  (deterministic)
│
└── Watched file changed
      │
      └── Claude classifies the diff against locked scope
            │
            ├── ADDITIVE (within scope) ────────────────► Pass   (silent)
            │
            └── SCOPE CHANGE
                  ├── Confidence below threshold ────────► Warn   (never blocks)
                  ├── No roles defined (solo mode) ──────► Warn
                  └── Confidence ≥ threshold ────────────► Block  (until authorized approval)
```

When a qualifying reviewer approves the pull request, the check re-evaluates automatically — no new commits needed.

---

## Quickstart

Five minutes from zero to a working required check.

### 1 — Lock your scope

Create `.specguard/lock.json`:

```json
{
  "goal": "A CLI tool that converts Markdown to PDF",
  "scope_in": ["Markdown parsing", "PDF rendering", "CLI flags"],
  "scope_out": ["GUI", "cloud sync", "collaboration features"]
}
```

### 2 — Define roles *(optional — enables enforce mode)*

Create `.specguard/roles.yml`:

```yaml
roles:
  architect: [your-github-username]

rules:
  ".specguard/**":
    edit: architect                      # only architect may edit governance config
  "README.md":
    scope_changes:
      approve: architect                 # architect approval unblocks scope changes
```

Without this file, SpecGuard runs in **warn-only mode** — classifications and explanations are surfaced as PR annotations, but nothing is blocked.

### 3 — Add the workflow

Create `.github/workflows/specguard.yml`:

```yaml
name: specguard
on:
  pull_request:
  pull_request_review:          # re-evaluates when an approval is submitted
permissions:
  contents: read
  pull-requests: read
jobs:
  specguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: Sawaiz-zip/spec-guard@v0
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

### 4 — Add your API key

**Repository → Settings → Secrets and variables → Actions → New repository secret**

Name: `ANTHROPIC_API_KEY`

### 5 — Require the check

**Repository → Settings → Branches → Add rule → Require status checks → `specguard`**

Open a pull request that introduces an out-of-scope topic to a watched file. The check will block, explain exactly why, and name who can approve. When they do, the check turns green.

---

## Verdict reference

| Change | Result |
|---|---|
| Typo fix or clarification within locked scope | Pass — no annotation |
| New detail that elaborates an in-scope item | Pass — no annotation |
| New section on an out-of-scope topic | Block — requires authorized approval |
| Goal or direction change | Block — requires authorized approval |
| Protected path edited by unauthorized identity | Block — deterministic, no AI call |
| Classification confidence below threshold | Warn — annotation only, never blocks |
| API outage | Pass + warning *(configurable to fail-closed)* |
| Fork PR — secrets unavailable | Pass + notice |
| No `.specguard/` directory | Pass + setup notice |

Every blocking verdict displays the classification, confidence percentage, matched out-of-scope topics, a plain-language explanation, and the role whose approval will unblock it.

---

## Configuration

`.specguard/config.yml` — all fields optional:

```yaml
watch:
  - README.md
  - CLAUDE.md
  - AGENTS.md
  - ARCHITECTURE.md
  - "*.kilo"
  - ".specguard/**"

block_threshold: 0.75       # SCOPE_CHANGE blocks above this confidence (0–1)
on_error: warn              # warn = fail-open on outage | fail = fail-closed
model: claude-opus-4-8      # classifier model (any Anthropic model string)
max_diff_chars: 30000       # diff size limit — scope lists are never truncated
```

---

## Cost

Approximately **$0.03–$0.05 per watched file per PR push** using `claude-opus-4-8`. A pull request touching five spec files costs under $0.25. The classifier system prompt is cached across all files in a single run, so multi-file PRs share the prompt cost.

The model is configurable — teams with stricter cost requirements can switch to a lighter model after validating calibration on their corpus.

---

## Design principles

SpecGuard is governed by six non-negotiable principles documented in [`.specify/memory/constitution.md`](.specify/memory/constitution.md):

1. **Merge-time enforcement is the only security layer.** Local layers are bypassable; branch protection is not.
2. **Governance overlay, not a framework.** SpecGuard reads your files — it does not replace your spec format.
3. **One shared validator core.** Every surface (CI, CLI, hooks) calls the same engine.
4. **Zero friction for additive changes.** A false block is a release-blocking defect.
5. **Deterministic hard blocks, probabilistic advice.** Protected-path rules never touch the LLM. Classifier verdicts always show their confidence.
6. **No dashboard, no new UI.** The PR interface and terminal are the only surfaces.

---

## Project structure

```
.specguard/              # governance config (lives in your repository)
├── lock.json            # locked goal + scope lists
├── config.yml           # optional: watch list, thresholds, model
└── roles.yml            # optional: roles → GitHub usernames + path rules

specs/001-pr-spec-gate/  # Spec Kit planning artifacts
├── spec.md              # feature specification
├── plan.md              # implementation plan
├── research.md          # decision rationale
├── data-model.md        # entity definitions
├── tasks.md             # 38 ordered build tasks
└── contracts/           # classifier + action interface contracts
```

---

## License

MIT — see [LICENSE](LICENSE).
