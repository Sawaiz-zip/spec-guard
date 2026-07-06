<div align="center">

<img src="assets/logo.svg" alt="SpecGuard" width="460" />

<br/>
<br/>

[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-SpecGuard%20CI-6366f1?style=flat-square&logo=github)](https://github.com/marketplace/actions/specguard-ci)
[![PyPI](https://img.shields.io/pypi/v/specguard-ci?style=flat-square&color=8b5cf6&label=PyPI)](https://pypi.org/project/specguard-ci/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square)](https://pypi.org/project/specguard-ci/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Built with Spec Kit](https://img.shields.io/badge/Built%20with-Spec%20Kit-fbbf24?style=flat-square&logoColor=black)](https://github.com/github/spec-kit)

**A semantic governance gate for spec files.**
It reads every PR change against your locked project goal and scope — passing additive edits silently, warning on low-confidence shifts, and blocking unapproved direction changes at merge time.

</div>

---

## Contents

- [Why SpecGuard](#why-specguard)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Features](#features)
- [LLM providers](#llm-providers)
- [Local tools](#local-tools)
- [Approving a scope change](#approving-a-scope-change)
- [Govern the specs you already have](#govern-the-specs-you-already-have)
- [Advanced governance](#advanced-governance)
- [Roadmap](#roadmap)
- [Principles](#principles)

---

## Why SpecGuard

In repos where AI agents and humans both contribute, a PR can look fine on the surface while quietly shifting the project's direction. SpecGuard catches that — not by checking *who* made the change, but by understanding *what* the change means against your locked goal and scope.

```
PR:         "refactored README for clarity"
Change:      Added a full SaaS pricing section
             to a project scoped as a local CLI tool.

SpecGuard:   ❌  SCOPE CHANGE — 94% confidence
                 "SaaS pricing" is out of scope
                 requires approval from @architect
```

---

## How it works

Lock your goal and scope once — in `.specguard/lock.json`, or [derived automatically](#govern-the-specs-you-already-have) from your Spec Kit / OpenSpec files. SpecGuard does the rest on every PR:

```
PR opened
 ├─ Not a watched file ───────────────────── ✅ Pass
 ├─ Protected path, wrong author ──────────── ❌ Block  (deterministic, no AI)
 └─ Watched spec file changed
      └─ LLM classifies the diff
           ├─ ADDITIVE ───────────────────── ✅ Pass   (silent)
           ├─ SCOPE CHANGE, low confidence ── ⚠️  Warn
           └─ SCOPE CHANGE, high confidence ── ❌ Block  (until authorized approval)
```

> [!NOTE]
> Approving through GitHub's normal review flow re-evaluates the check automatically — no new commits needed. Merge time is the only enforcement layer; everything else is advisory.

---

## Quick start

**1. Create `.specguard/lock.json`**

```json
{
  "goal": "A CLI tool that converts Markdown to PDF",
  "scope_in":  ["Markdown parsing", "PDF rendering", "CLI flags"],
  "scope_out": ["GUI", "cloud sync", "collaboration features"]
}
```

**2. Add the workflow** — `.github/workflows/specguard.yml`

```yaml
name: specguard
on:
  pull_request:
permissions:
  contents: read
  pull-requests: read
jobs:
  specguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }          # required: base...head history
      - uses: Sawaiz-zip/spec-guard@v0     # https://github.com/marketplace/actions/specguard-ci
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

**3. Add the secret and require the check**

Set `ANTHROPIC_API_KEY` as a repository secret, then require the **`specguard`** check under **Settings → Branches → Branch protection**.

That's it for solo use — scope changes now warn on every PR. To make them **block** until an authorized teammate approves, add a [`roles.yml`](#3-rolesyml--who-may-approve-optional).

> [!TIP]
> Prefer one command? `specguard init` scaffolds all of this for you — lock file, workflow (including the `/specguard approve` command), optional roles/regions, and an optional pre-commit hook. Every generated file is **self-documenting**, so you can configure it without leaving the file.

<details>
<summary><strong>What <code>specguard init</code> generates</strong></summary>

`.specguard/lock.json` — your locked goal and scope:

```json
{
  "goal": "A CLI that converts Markdown to PDF",
  "scope_in": ["Markdown parsing", "PDF rendering", "CLI flags"],
  "scope_out": ["GUI", "cloud sync", "collaboration"]
}
```

`.specguard/config.yml` — behavior; every key is commented out (so the file is inert defaults) and explained inline:

```yaml
# SpecGuard settings — every key is optional. All keys are commented out below,
# so this file changes nothing until you uncomment a key: the values shown ARE
# the defaults. Each comment explains what the key does and its allowed values.

# watch: which files the gate classifies. Anything not matched here is ignored.
# watch:
#   - "README.md"
#   - "CLAUDE.md"
#   - "AGENTS.md"
#   - "ARCHITECTURE.md"
#   - "*.kilo"
#   - ".specguard/**"

# block_threshold: confidence (0.0-1.0) a SCOPE_CHANGE needs to BLOCK. Below it,
# the gate warns instead of blocking. Higher = fewer blocks, more warnings.
# block_threshold: 0.75

# on_error: what to do when the classifier/vendor call fails.
#   warn (default) = pass the PR with a loud "could not classify" warning
#   fail           = block the PR until classification succeeds
# on_error: warn

# provider: which LLM backend classifies. One of:
#   anthropic (default) | openai | gemini | openrouter
# Non-anthropic providers require an explicit `model:` below.
# provider: anthropic

# model: the model id to classify with. claude-sonnet-4-6 is the calibrated
# default; claude-opus-4-8 is blocked by a project guardrail.
# model: claude-sonnet-4-6

# max_diff_chars: diffs larger than this (per file) are truncated before
# classifying, to bound token cost. Must be > 0.
# max_diff_chars: 30000
```

`.specguard/roles.yml` — who may approve (its presence flips warn → block); the rule vocabulary is documented inline:

```yaml
# rules: per file or glob, who may do what. Two rule keys are supported:
#   edit: <role>                     only this role may edit the path
#                                    (deterministic hard block, no AI)
#   scope_changes: {approve: <role>} whose APPROVED review unblocks a
#                                    SCOPE_CHANGE the classifier flags
# Additive, in-scope changes always pass silently — there is no rule to
# configure for them, and no such rule key exists.
roles:
  architect: [your-github-username]
rules:
  ".specguard/**":            # protect the lock/roles files themselves
    edit: architect
  "README.md":                # who may approve scope changes here
    scope_changes: {approve: architect}
```

`.specguard/regions.yml` — optional section locking; ships inert (`files: {}`) with a worked example in the comments:

```yaml
# SpecGuard section locking (optional) — govern only named heading regions of a
# file, leaving the rest free to edit. Under `files:`, map a watched file to the
# headings whose sections should be governed; edits outside them pass quietly.
# files:
#   "ARCHITECTURE.md":
#     - "Goal"
#     - "Out of Scope"
files: {}
```

</details>

<details>
<summary><strong>Full workflow with the <code>/specguard approve</code> comment command</strong></summary>

```yaml
name: specguard
on:
  pull_request:
  pull_request_review:
    types: [submitted]
  issue_comment:                           # /specguard approve comment command
    types: [created]
permissions:
  contents: read
  pull-requests: read
jobs:
  specguard:                               # the required branch-protection check
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: Sawaiz-zip/spec-guard@v0
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}

  reevaluate:                              # an approval re-runs the check in place
    if: github.event_name == 'pull_request_review' && github.event.review.state == 'approved'
    runs-on: ubuntu-latest
    permissions: { actions: write }
    steps:
      - env: { GH_TOKEN: '${{ github.token }}' }
        run: |
          run_id=$(gh api "repos/${{ github.repository }}/actions/workflows/specguard.yml/runs?event=pull_request&head_sha=${{ github.event.pull_request.head.sha }}" --jq '.workflow_runs[0].id // empty')
          [ -n "$run_id" ] && gh api -X POST "repos/${{ github.repository }}/actions/runs/$run_id/rerun"

  comment-approve:                         # /specguard approve re-runs the check
    if: github.event_name == 'issue_comment' && github.event.issue.pull_request && startsWith(github.event.comment.body, '/specguard approve')
    runs-on: ubuntu-latest
    permissions: { actions: write, pull-requests: read }
    steps:
      - env: { GH_TOKEN: '${{ github.token }}' }
        run: |
          head_sha=$(gh api "repos/${{ github.repository }}/pulls/${{ github.event.issue.number }}" --jq '.head.sha')
          run_id=$(gh api "repos/${{ github.repository }}/actions/workflows/specguard.yml/runs?event=pull_request&head_sha=$head_sha" --jq '.workflow_runs[0].id // empty')
          [ -n "$run_id" ] && gh api -X POST "repos/${{ github.repository }}/actions/runs/$run_id/rerun"
```

The comment command grants no authority on its own — it only retriggers the gate, which recomputes authorization from `roles.yml` at the trusted base commit. Anyone may comment; only a real role member clears a block.

</details>

> [!IMPORTANT]
> You bring your own API key and choose the model — SpecGuard never bills you. With the default `claude-sonnet-4-6`, expect roughly **$0.01–0.02 per watched file per push**. The Action provisions its own Python on the runner, so the gate works for repos in **any language**.

---

## Configuration

All config lives in `.specguard/`. Only `lock.json` is required; the rest are optional and default sensibly.

> [!TIP]
> You don't have to write these by hand. `specguard init` offers to scaffold all four files — `lock.json`, `config.yml`, `roles.yml`, and `regions.yml` — and every generated file is **self-documenting**: each key is explained inline, so you can configure it without leaving the file.

### 1. `lock.json` — the goal and scope *(required)*

```json
{
  "goal": "One sentence describing what this project is",
  "scope_in":  ["things that belong"],
  "scope_out": ["things that don't"]
}
```

### 2. `config.yml` — behavior *(optional; defaults shown)*

```yaml
watch: ["README.md", "CLAUDE.md", "AGENTS.md", "ARCHITECTURE.md", "*.kilo", ".specguard/**"]
block_threshold: 0.75        # confidence needed to block (vs. warn)
on_error: warn               # vendor outage: pass with a loud warning ("fail" to block instead)
provider: anthropic          # anthropic | openai | gemini | openrouter
model: claude-sonnet-4-6
max_diff_chars: 30000        # diffs larger than this are truncated before classifying
```

### 3. `roles.yml` — who may approve *(optional)*

Adding this file switches SpecGuard from advisory **warn** mode into enforcing **block** mode.

```yaml
roles:
  architect: [your-github-username]
rules:
  ".specguard/**":                        # nobody outside the role may touch the lock itself
    edit: architect
  "README.md":                            # who can approve scope changes, per file
    scope_changes: { approve: architect }
```

> [!NOTE]
> The presence of `roles.yml` is what switches SpecGuard from advisory **warn** mode to enforcing **block** mode. Without it, scope changes warn but never block.

### 4. `regions.yml` — lock only part of a file *(optional)*

```yaml
files:
  "ARCHITECTURE.md": ["Goal", "Out of Scope"]   # govern these headings; leave the rest free
```

See [Advanced governance](#advanced-governance) for section locking, monorepos, and audit export.

---

## Features

| Area | What you get |
|---|---|
| **Semantic gate** | LLM classifies each watched-file diff as *additive* or *scope change*, with a confidence score and a plain-English reason. |
| **Deterministic blocks** | Protected paths (e.g. the lock itself) are enforced by role, with no AI involved — never a false positive. |
| **Merge-time enforcement** | Runs as a required GitHub branch-protection check; nothing else can block a merge. |
| **Role-based approval** | `roles.yml` maps GitHub logins to roles; one authorized approval clears a block. |
| **Three approval paths** | Native PR review, `/specguard approve` comment, or `specguard approve` CLI — all evaluated by the same rule. |
| **Provider-agnostic** | Anthropic, OpenAI, Gemini, or OpenRouter behind one engine — bring your own key. |
| **Local preview** | `specguard check` runs the exact same engine on your working tree, staged changes, or a branch. |
| **Pre-commit hook** | Advisory scope warnings at commit time (never blocks the commit). |
| **MCP server** | Coding agents (e.g. Claude Code) can check a drafted change *before* writing it. |
| **Framework adapters** | Auto-derive the lock from existing Spec Kit or OpenSpec files. |
| **Section locking** | Govern individual headings of a file while the rest stays free to edit. |
| **Monorepo multi-scope** | A `.specguard/` per package governs each subtree independently in one run. |
| **Audit export** | One JSON record per verdict for compliance trails, on an opt-in env var. |
| **Resilient by default** | Vendor outages pass with a loud warning (`on_error: warn`) rather than blocking your team. |

---

## LLM providers

One shared engine sits behind a provider seam — pick the backend you already pay for. Anthropic ships in the base install; the rest are one extra away.

| `provider:` | Install | API key env var | Example `model:` |
|---|---|---|---|
| `anthropic` *(default)* | `pip install specguard-ci` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openai` | `pip install "specguard-ci[openai]"` | `OPENAI_API_KEY` | `gpt-4o-2024-11-20` |
| `gemini` | `pip install "specguard-ci[gemini]"` | `GEMINI_API_KEY` | `gemini-2.0-flash` |
| `openrouter` | `pip install "specguard-ci[openai]"` | `OPENROUTER_API_KEY` | `anthropic/claude-3.5-sonnet` |

> [!NOTE]
> Non-Anthropic providers require an explicit `model:`. Only **Anthropic + Sonnet 4.6** is calibration-verified against the golden corpus (27/27); other backends work but are unvalidated until you run them through `tests/eval/run_eval.py`. `claude-opus-4-8` is hard-blocked by a project guardrail — no quality gain on this task at ~6× the cost.

---

## Local tools

Everything the merge gate decides, you can preview locally — same engine, same verdicts, advisory only.

```bash
pip install specguard-ci

specguard init                        # guided setup: goal, scope, optional roles/workflow/hook
specguard check                       # what would the gate say about my working tree?
specguard check --staged              # ...about what I'm committing?
specguard check --base origin/main    # ...about this branch as a PR?
```

### Pre-commit hook

Advisory scope warnings at commit time — never blocks a commit (enforcement stays at merge time).

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Sawaiz-zip/spec-guard
    rev: v0.4.1
    hooks: [{ id: specguard-check }]
```

### MCP server for coding agents

Let an agent check a drafted spec change *before* it writes it — drift prevention moves from "blocked PR" to "agent self-corrects mid-draft."

```bash
pip install "specguard-ci[mcp]"
```

```json
// .mcp.json (e.g. for Claude Code)
{ "mcpServers": { "specguard": { "command": "specguard", "args": ["mcp"] } } }
```

The server exposes four tools:

| Tool | Purpose |
|---|---|
| `check_proposed_change` | Full verdict for proposed content; on a block, returns a `redirect` naming the approver role. |
| `check_permission` | May this identity make this class of change to this file? |
| `get_scope_lock` | The active goal and scope. |
| `list_watched_paths` | Which paths are governed. |

> [!IMPORTANT]
> Local results are always advisory — nothing local enforces. Governance config is read from your committed baseline, so editing your own lock locally does **not** change the verdict your PR will actually get.

---

## Approving a scope change

When the gate blocks a change, any **one** authorized approval clears it — three equivalent paths, evaluated by the same rule and recorded identically:

| Path | How |
|---|---|
| **Native PR review** | An authorized role member clicks **Approve** in the GitHub review UI. |
| **Comment command** | An authorized member comments `/specguard approve` on the PR (mobile-friendly); the gate re-runs in place. |
| **CLI** | `specguard approve <pr-number>` from the terminal (needs `GH_TOKEN` / `GITHUB_TOKEN`). |

> [!NOTE]
> Authorization always uses the **server-side GitHub login** against `roles.yml`. Anyone can *trigger* a re-run, but only a real role member can *approve* — a comment or CLI call from outside the role does not clear the block.

---

## Govern the specs you already have

If your repo uses [Spec Kit](https://github.com/github/spec-kit) or [OpenSpec](https://github.com/Fission-AI/OpenSpec), you don't have to hand-author `lock.json` — SpecGuard reads the goal and scope from the files those frameworks already maintain (parsing their public markdown; it never imports their code):

| Source | Where goal/scope comes from |
|---|---|
| **Explicit lock** *(always wins)* | `.specguard/lock.json` |
| **Spec Kit** | `.specify/memory/constitution.md` + the touched `specs/<feature>/spec.md` |
| **OpenSpec** | `openspec/project.md` + the touched `openspec/changes/<id>/proposal.md` scope sections |
| **Plain** | no framework detected — behaves exactly as a hand-written lock |

Selection is automatic from your repo layout, in that precedence order. Every run reports which source it used (`Governance source: …`), and an explicit `lock.json` always overrides framework derivation.

> [!NOTE]
> The **Spec Kit** adapter is dogfooded on this repository. The **OpenSpec** adapter is built against OpenSpec's documented format but not yet validated against a live project — if your layout differs, pin scope with an explicit `.specguard/lock.json`.

---

## Advanced governance

### Lock a section, let the rest float

Govern just a heading region of a file — a goal paragraph or an out-of-scope list — while the FAQ or examples around it stay free to edit:

```yaml
# .specguard/regions.yml
files:
  "ARCHITECTURE.md": ["Goal", "Out of Scope"]
```

Edits outside every declared region pass quietly without reaching the classifier — strictly *less* friction, never more. If a declared heading is renamed or removed, the check fails loudly (never silently un-governed).

### Monorepo: one scope per package

Drop a `.specguard/` into any subdirectory and it governs that subtree independently — its own goal, scope, roles, and regions:

```text
packages/api/.specguard/lock.json   # "API service",  scope_out: [billing]
packages/web/.specguard/lock.json   # "Web app",       scope_out: [payments]
```

A PR touching both packages gets two independent verdicts in one run. Each package's config is written as if its `.specguard/` were the repo root — copy the whole directory between packages and it just works. Files outside any package scope fall back to the repo-root lock.

### Audit export

```bash
SPECGUARD_AUDIT_PATH=audit.json python -m specguard.ci
```

Writes one JSON record per verdict — file, scope, classification, confidence, required approver roles, and every approval seen on the PR — for upload as a workflow artifact. No secrets, no new datastore; a pure formatting pass over data the gate already computed.

---

## Roadmap

| Phase | Status | What ships |
|:---|:---:|:---|
| **0 — CI Gate** | 🟢 Shipped | GitHub Action · scope classification · role-based approval · branch protection |
| **1 — Local Tools** | 🟢 Shipped | CLI (`init`, `check`) · pre-commit hook · MCP server |
| **1.5 — Provider-Agnostic** | 🟢 Shipped | Anthropic · OpenAI · Gemini · OpenRouter behind one engine · Python 3.10+ |
| **2 — Framework Adapters** | 🟢 Shipped | Spec Kit + OpenSpec derivation · explicit-lock override · source reporting |
| **2 — Approval Commands** | 🟢 Shipped | `/specguard approve` comment · `specguard approve` CLI · MCP `check_permission` |
| **2 — GitHub App** | 🟡 Code-complete<br>*(not deployed)* | Optional companion for public repos: governs **fork PRs** (which the Action can't), plus native check runs and bot-vs-human identity. Built and tested; not yet hosted. GitLab is a separate future spec. |
| **3 — Advanced** | 🟢 Shipped | Section-level locking · monorepo multi-scope · audit export |

---

## Principles

**No false blocks. No new UI. No dashboards.**

The only enforceable boundary is merge time — everything else is advisory. A wrong Friday block means uninstall by Monday, so additive changes always pass silently, hard blocks are deterministic (no AI), and probabilistic verdicts always show their confidence and never block without an explanation.

[Architecture & flow diagrams](docs/architecture.md) · Full constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md) · Detailed runbook: [`docs/quickstart.md`](docs/quickstart.md)

---

<div align="center">

Built with [Spec Kit](https://github.com/github/spec-kit) · Powered by Claude · [MIT License](LICENSE)

</div>
