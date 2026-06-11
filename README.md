<div align="center">

<img src="assets/logo.svg" alt="SpecGuard" width="460" />

<br/>
<br/>

[![License: MIT](https://img.shields.io/badge/License-MIT-6366f1?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Phase%200%20MVP-ef4444?style=flat-square)]()
[![Built with Spec Kit](https://img.shields.io/badge/Built%20with-Spec%20Kit-fbbf24?style=flat-square&logoColor=black)](https://github.com/github/spec-kit)

</div>

---

**CODEOWNERS** knows who can change a file.
**SpecGuard** knows what those changes are allowed to *mean*.

When AI agents and humans both contribute to a repo, the real threat isn't an unauthorized author — it's an unauthorized direction change. SpecGuard catches those at merge time, before they land.

---

## The Problem

```
Agent opens PR:   "refactored README for clarity"
Actual change:     Added a SaaS pricing section
                   to a project scoped as a local CLI tool.

CODEOWNERS:        ✅  author has access
Code review:       ✅  looks fine at a glance
SpecGuard:         ❌  SCOPE CHANGE — 94% confidence
                       requires approval from @architect
```

---

## How It Works

Lock your goal and scope in `.specguard/lock.json`. SpecGuard does the rest on every PR.

```
PR opened
 ├─ Not a watched file ───────────────────── ✅ Pass
 ├─ Protected path, wrong author ──────────── ❌ Block  (no AI involved)
 └─ Watched spec file changed
      └─ Claude classifies the diff
           ├─ ADDITIVE ───────────────────── ✅ Pass   (silent)
           ├─ SCOPE CHANGE, low confidence ── ⚠️  Warn
           └─ SCOPE CHANGE, high confidence ── ❌ Block  (until authorized approval)
```

Approving via GitHub's normal review flow re-evaluates the check automatically — no new commits needed.

---

## Quickstart

**1.** Create `.specguard/lock.json`

```json
{
  "goal": "A CLI tool that converts Markdown to PDF",
  "scope_in":  ["Markdown parsing", "PDF rendering", "CLI flags"],
  "scope_out": ["GUI", "cloud sync", "collaboration features"]
}
```

**2.** Add the workflow

```yaml
# .github/workflows/specguard.yml
name: specguard
on: [pull_request, pull_request_review]
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

**3.** Set `ANTHROPIC_API_KEY` as a repo secret, then require the `specguard` check under branch protection.

> You bring your own API key and choose the model — SpecGuard never bills you directly.
> Set `model:` in `.specguard/config.yml` to use any model you have access to.

---

## Roadmap

| Phase | Status | What ships |
|:---:|:---:|:---|
| **0 — CI Gate** | 🔴 Building | GitHub Action · scope classification · role-based approval · branch protection |
| **1 — Local Tools** | ⚪ Planned | CLI (`specguard init`, `specguard check`) · pre-commit hook · MCP server |
| **2 — GitHub App** | ⚪ Planned | Native Checks API · fork PR support · bot vs human identity · Spec Kit adapter |
| **3 — Advanced** | ⚪ Planned | Section-level locking · monorepo support · multi-provider classifier |

---

## Principles

No false blocks. No new UI. No dashboards.

The only enforceable boundary is merge time — everything else is advisory. A wrong Friday block means uninstall by Monday, so additive changes always pass silently. Hard blocks are deterministic (no AI). Probabilistic verdicts always show their confidence and never block without explanation.

Full constitution: [`.specify/memory/constitution.md`](.specify/memory/constitution.md)

---

<div align="center">

Built with [Spec Kit](https://github.com/github/spec-kit) · Powered by Claude · MIT License

</div>
