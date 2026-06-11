<div align="center">

<img src="assets/logo.svg" alt="SpecGuard" width="420" />

<br/>
<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-6366f1?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Phase%200%20MVP-8b5cf6?style=flat-square)]()
[![Powered by Claude](https://img.shields.io/badge/Powered%20by-Claude%20API-orange?style=flat-square)](https://anthropic.com)
[![Built with Spec Kit](https://img.shields.io/badge/Built%20with-Spec%20Kit-blue?style=flat-square)](https://github.com/github/spec-kit)

<br/>

**CODEOWNERS knows who can change a file.**
**SpecGuard knows what those changes are allowed to mean.**

</div>

---

SpecGuard is a semantic governance layer for spec files in repositories where humans and AI agents collaborate. It runs as a required GitHub Actions status check, classifies every PR change using Claude, and enforces your project's locked goal and scope at merge time — the one boundary that cannot be bypassed.

---

## The Problem

In repositories where AI agents and humans both contribute, the threat isn't an unauthorized *author* — it's an unauthorized *direction change*.

```
Agent opens PR: "refactored README for clarity"
Actual change:  Added an entire SaaS pricing section
                to a project scoped as a local CLI tool.
CODEOWNERS:     ✅  (author has access)
Code review:    ✅  (looks fine at a glance)
SpecGuard:      ❌  SCOPE CHANGE — confidence 94%
                    "SaaS pricing" is explicitly out of scope.
                    Requires approval from: @architect
```

---

## How It Works

```
Pull Request opened
│
├─ File not in watch list ──────────────────────────────────► ✅ Pass
│
├─ Protected path + unauthorized author ────────────────────► ❌ Block  (deterministic, no AI)
│
└─ Watched spec file changed
       │
       └─ Claude classifies the diff against your locked scope
              │
              ├─ ADDITIVE (within scope) ──────────────────► ✅ Pass   (silent, zero friction)
              │
              └─ SCOPE CHANGE
                     ├─ Confidence < threshold ─────────────► ⚠️  Warn   (never blocks)
                     ├─ No roles defined (solo mode) ────────► ⚠️  Warn
                     └─ Confidence ≥ threshold ─────────────► ❌ Block  (until authorized approval)
```

When a qualifying reviewer approves the pull request through GitHub's normal review flow, the check re-evaluates automatically — no new commits needed.

---

## Verdict Reference

| Change | Result | Annotation |
|:---|:---:|:---|
| Typo fix or wording clarification | ✅ Pass | Silent — no annotation |
| New detail within locked scope | ✅ Pass | Silent — no annotation |
| Approval from authorized reviewer | ✅ Pass | "Approved by @alice (architect)" |
| Classification below confidence threshold | ⚠️ Warn | Classification + explanation |
| Scope change in solo mode (no roles) | ⚠️ Warn | Classification + explanation |
| API outage | ⚠️ Warn | "Could not classify — review manually" |
| Fork PR — secrets unavailable | ⚠️ Warn | Setup notice |
| New out-of-scope topic introduced | ❌ Block | Class · Confidence · Topics · Required role |
| Goal or direction change | ❌ Block | Class · Confidence · Topics · Required role |
| Protected path, unauthorized author | ❌ Block | Rule · Required role (no AI involved) |
| Malformed governance config | ❌ Error | File · Parse error |

---

## Quickstart

> Five minutes from zero to a working required check.

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
    edit: architect             # only architect may touch governance config
  "README.md":
    scope_changes:
      approve: architect        # architect approval unblocks scope changes
```

Without this file, SpecGuard runs in **warn-only mode** — every change is classified and explained, but nothing is blocked. Ideal for solo developers.

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

**Repository → Settings → Branches → Require status checks → `specguard`**

Now open a PR that introduces an out-of-scope topic. The check will block, explain exactly why, and name who can approve. When they do, the check turns green.

---

## Configuration

`.specguard/config.yml` — all fields optional, shown with defaults:

```yaml
watch:
  - README.md
  - CLAUDE.md
  - AGENTS.md
  - ARCHITECTURE.md
  - "*.kilo"
  - ".specguard/**"

block_threshold: 0.75       # SCOPE_CHANGE blocks above this confidence (0.0–1.0)
on_error: warn              # warn = fail-open on API outage | fail = fail-closed
model: claude-opus-4-8      # any model you have API access to — you own the cost
max_diff_chars: 30000       # diff size cap — scope lists are never truncated
```

---

## Enforcement Modes

| | Solo mode | Enforce mode |
|:---|:---:|:---:|
| **Trigger** | No `roles.yml` | `roles.yml` present |
| **Additive changes** | ✅ Pass silently | ✅ Pass silently |
| **Scope changes (high confidence)** | ⚠️ Warn | ❌ Block until approved |
| **Scope changes (low confidence)** | ⚠️ Warn | ⚠️ Warn |
| **Protected path violations** | — | ❌ Block (deterministic) |
| **API outage** | ⚠️ Warn | ⚠️ Warn *(or ❌ Block if `on_error: fail`)* |

---

## Bring Your Own Model

SpecGuard never bills you directly. You supply your own API key and choose the model — cost is entirely yours to control.

| Config | How to set it |
|:---|:---|
| Model | `model:` in `.specguard/config.yml` or `SPECGUARD_MODEL` env var |
| API key | `ANTHROPIC_API_KEY` repo secret (or your provider's equivalent) |
| Default model | `claude-opus-4-8` — swap to any model you have access to |

**Cost scales with your model choice.** A lighter model (Haiku, Sonnet, or a third-party equivalent) costs proportionally less. The classifier system prompt is cached across all files in a single run — multi-file PRs share that cost.

> Phase 1 will add support for non-Anthropic providers (OpenAI, Gemini, local models) via a pluggable classifier adapter — same structured output contract, your choice of SDK.

---

## Design Principles

SpecGuard is governed by six non-negotiable principles in [`.specify/memory/constitution.md`](.specify/memory/constitution.md):

| # | Principle | What it means |
|:---:|:---|:---|
| I | **Merge-time is the security layer** | Local checks are bypassable; branch protection is not |
| II | **Governance overlay, not a framework** | Reads your files — never replaces your spec format |
| III | **One shared validator core** | Every surface (CI, CLI, hooks) calls the same engine |
| IV | **Zero friction for additive changes** | A false block is a release-blocking defect |
| V | **Deterministic hard blocks, probabilistic advice** | Protected-path rules never touch the LLM |
| VI | **No dashboard, no new UI** | PR interface and terminal only — no new surfaces |

---

## Project Structure

```
.specguard/                        # governance config (in your repository)
├── lock.json                      # locked goal + scope lists
├── config.yml                     # watch list, thresholds, model
└── roles.yml                      # roles → GitHub usernames + path rules

specs/001-pr-spec-gate/            # Spec Kit planning artifacts
├── spec.md                        # feature specification (4 user stories, 15 FRs)
├── plan.md                        # implementation plan + architecture decisions
├── research.md                    # decision rationale (10 resolved questions)
├── data-model.md                  # Pydantic models + config schemas
├── tasks.md                       # 38 dependency-ordered build tasks
├── quickstart.md                  # 5 runnable validation scenarios
└── contracts/
    ├── classifier.md              # Claude API call contract
    └── action-interface.md        # GitHub Action I/O contract

.claude/skills/                    # Claude Code skills for this project
├── git/                           # branch, commit, PR, rebase, undo
└── clean-code/                    # naming, complexity, duplication, types review
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

Built with [GitHub Spec Kit](https://github.com/github/spec-kit) · Powered by [Claude](https://anthropic.com) · MIT License

</div>
