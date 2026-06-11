# SpecGuard — Product Specification & Development Reference

> **Working name:** SpecGuard (alternatives considered: Project DNA, ScopeShield, GoalGuard, DocGovernor)
> **One-liner:** "CODEOWNERS understands file paths. We understand what the change *means* — and who's allowed to mean it."
> **Document purpose:** Complete reference of everything discussed and decided, to be used as the foundation for development with Claude.
> **Date:** June 2026

---

## 1. The Problem

When 2+ people (and/or AI agents like Claude Code, Kilo, Cursor) work on the same project/branch:

1. **Spec files get silently changed.** `.md` files that define the project (README.md, ARCHITECTURE.md, CLAUDE.md, AGENTS.md, constitution.md, .kilo files, plan files) get edited by anyone — human or agent — without oversight.
2. **The domain/end-goal drifts.** A project scoped as "JWT auth with OAuth2" quietly becomes "JWT + SSO + Active Directory" because someone (or some agent) added a section nobody reviewed.
3. **AI agents are stateless and suggestible.** Different Claude/Kilo sessions reinterpret or regenerate specs differently. A poisoned or confused agent can rewrite the project's own governing documents (including its own guardrail files — this is a documented Claude Code security gap, GitHub issue #11226: Edit/Write tools can modify hook scripts regardless of permissions.deny rules).
4. **Existing tools don't understand meaning.** GitHub CODEOWNERS/branch protection knows *file paths*, not *semantics*. It can require approval for any change to README.md but cannot distinguish "fixed a typo" from "changed the project's entire direction."

**Who feels this pain most:** teams at the intersection of (a) multiple humans, (b) multiple AI agents, (c) actual spec discipline. Small today, growing fast with agentic development adoption.

---

## 2. Market Research Summary (verified June 2026)

### 2.1 The category exists: Spec-Driven Development (SDD)

SDD emerged 2025 as the response to "vibe coding" failure modes: intent drift, context decay, unverifiable output. By 2026 every major AI coding tool shipped an SDD flavor.

### 2.2 Direct/adjacent competitors

| Tool | What it is | Stars/Status | What it has | What it lacks |
|---|---|---|---|---|
| **GitHub Spec Kit** | OSS toolkit; spec as source of truth; constitution.md + specify/plan/tasks/implement workflow | 90,000+ stars, 70+ community extensions | Constitution check (LLM self-review), /analyze quality gate, extension hooks via `.specify/extensions.yml` | No identity, no roles, no enforcement; constitution "immutable" by convention only — any agent/human can edit it |
| **OpenSpec (Fission-AI)** | OSS proposal-based SDD; specs/ + changes/ with deltas (ADDED/MODIFIED/REMOVED) | 52,100+ stars, scored highest in Feb 2026 independent eval | Proposal workflow, `validate --strict` (structural), custom schemas (mandate artifacts e.g. threat-model.md), archive merges deltas | "Approval" = user says ok in chat; no identity, no roles; anyone/any agent can run `archive` and rewrite source of truth; validation is structural not semantic |
| **AWS Kiro** | Agentic IDE with structured requirements | Commercial | AWS-native structured specs | AWS lock-in, not a governance layer |
| **Zencoder Zenflow** | Living workflows from specs | Commercial | Drift prevention (code-vs-spec), verification loops, deterministic execution | Focused on code drifting from spec, not governing spec edits; no role hierarchy |
| **Augment Cosmos** | Org-scale agent platform with shared memory | Public preview May 2026 | Organizational context | Platform play, not file governance |
| **BMAD-METHOD, Tessl, Cursor rules** | Various SDD frameworks | OSS/commercial | Workflow structure | Same governance gap |

### 2.3 Guardrails/enforcement tools (the "protect files" side)

| Tool | What it does | Gap vs our product |
|---|---|---|
| **Claude Code native** (PreToolUse hooks + permissions.deny + managed settings) | Hooks can block tool calls; only PreToolUse can deny. Official "block edits to protected files" recipe exists | Local-only, bypassable (documented: Edit/Write can modify hook scripts; deny rules have enforcement bugs #6631/#6699/#11226; `--no-verify` exists); path-based not semantic; per-developer config |
| **Cerbos Synapse** | Centralized, versioned policies for Claude Code tool calls; HTTP hook handler; tamper-resistant audit store | Governs *agent tool calls* generally, not human+agent *spec edits*; no semantic diff classification; not tied to PR merge flow |
| **Rulebricks claude-code-guardrails** | Rule templates (Bash guardrails, file access policy, MCP governance); non-engineers edit rules in UI | Path/command rules, not semantic; Claude Code only |
| **Codacy Guardrails** | Security/quality scanning wired into Claude Code via MCP | Code quality focus, not spec governance |
| **GitHub CODEOWNERS / branch protection** | Path-based required approvals | Binary, path-only, no semantics, no explanation to developer |
| **Confluence/Gitbook/Notion** | Doc permissions | Lives outside the repo; two sources of truth; no git/agent integration |

### 2.4 The verified gap (our niche)

Nobody combines all three:
1. **Per-file/per-section, role-based permission hierarchy for spec files tied to git identity**
2. **Semantic classification of each change** — additive-within-scope vs. scope/domain change — driving *different* approval paths
3. **Cross-tool, agent-agnostic, server-side enforcement** — same policy hits Kilo, Claude Code, Cursor, raw vim+git, and GitHub/GitLab PRs identically

Both leading frameworks (Spec Kit, OpenSpec) built the *workflow* and skipped the *governance*. They assume one trustworthy developer on one machine.

---

## 3. Key Architecture Decisions (with reasoning)

### Decision 1: NO dashboard, NO separate website
- Developers hate leaving their tools; "another login" kills adoption
- Products that won (pre-commit, Husky, Prettier, ESLint, Dependabot) are CLI/Git-native; dashboard-heavy products (SonarQube for individuals, Coveralls) lost
- GitHub/GitLab UI **is** our approval interface

### Decision 2: We do NOT build a spec format or workflow
- That war is over: Spec Kit (90k stars) and OpenSpec (52k stars) won
- We are a **governance overlay**: we *read their file conventions* and *plug into their extension interfaces*
- **Important clarification:** we do NOT use/fork/embed their code. We parse the markdown/YAML files their tools leave in the repo (like ESLint+GitHub cooperate through files). Benefits: no license entanglement, framework-agnostic, resilient to their internal changes (only the public file format matters)
- Also support **plain mode**: raw CLAUDE.md / AGENTS.md / .kilo / arbitrary .md files with no framework

### Decision 3: Three-layer enforcement model
```
   WRITE TIME              COMMIT TIME            MERGE TIME
   (advisory)              (advisory)             (ENFORCED)
┌──────────────────┐  ┌──────────────────┐  ┌─────────────────────┐
│ MCP server in     │  │ git pre-commit    │  │ GitHub/GitLab App    │
│ Claude Code/Kilo  │  │ hook              │  │ required status check│
│ blocks/redirects  │  │ warns (team mode) │  │ blocks merge until   │
│ the agent before  │  │ or self-approve   │  │ authorized approval  │
│ drafting          │  │ (solo mode)       │  │                      │
└──────────────────┘  └──────────────────┘  └─────────────────────┘
   bypassable (fine)     bypassable            CANNOT be bypassed
                         (--no-verify)         (branch protection)
```
- **Critical security truth (verified):** local enforcement is fundamentally bypassable. Claude Code Edit/Write tools can modify hook scripts; `--no-verify` skips git hooks; poisoned CLAUDE.md can redirect agents. Therefore the **server-side check is the security layer**; local layers are developer-experience layers (catch early, explain kindly)
- The GitHub/GitLab App is the product core and the only monetizable enterprise surface

### Decision 4: Shared validation core
One module (`validator`) used by every integration (MCP, hook, CLI, CI, future IDE plugins). Same verdict everywhere, formatted differently per surface.

### Decision 5: Friction philosophy
- **Additive changes within scope: auto-pass with a quiet log entry.** Most changes should be this. Zero friction.
- Friction appears **only** at genuine direction changes
- Locally we **warn, not block** in team mode (blocking commits creates rage and is bypassable anyway); we tell the developer early what will happen at the PR

### Decision 6: Distribution strategy
- Open source core (MIT) on GitHub
- Ship as: Spec Kit extension (via their `extensions.yml` hook mechanism — access to their 70+ extension ecosystem), OpenSpec-compatible mode (gate the `archive` step), MCP server (submit to MCP registry/marketplaces), standalone plain mode
- Revenue: GitHub Sponsors → optional paid tiers later (enterprise self-hosted + support contract, $500–5k/yr; possibly Slack app $5/mo); realistic OSS outcome $1–5k/month if agent-governance wave continues

---

## 4. Core Features (finalized)

### F1. Scope/Goal Locking
- Lock a project goal + explicit scope-in / scope-out lists into a versioned file in the repo (`.specguard/` config, or read from existing `constitution.md` / `openspec/specs/` / `proposal.md` "what's in/out of scope" sections)
- The lock file itself is protected by the role rules (self-protecting)

### F2. Semantic Change Classification (the differentiator)
Every diff to a watched spec file is classified by an **independent** Claude API call (never the same agent session being governed — Spec Kit's flaw is the agent self-reviewing):
- **ADDITIVE** — clarification, typo, detail within locked scope → auto-pass, quiet log
- **SCOPE_CHANGE** — alters goals, adds out-of-scope topics, changes domain/direction → requires approval from authorized role
- **PROTECTED_VIOLATION** — touches locked sections / constitution / roles file by unauthorized identity → hard block
- Output includes: classification, confidence, risk level (LOW/MEDIUM/HIGH), specific out-of-scope topics detected, one-line summary, explanation
- **Biggest product risk lives here:** false positives kill adoption ("blocked my Friday merge over a typo" = uninstalled by Monday). Calibration is months of iteration. Mitigations: additive auto-pass default, confidence thresholds, easy override paths, classifier verdicts always explain themselves

### F3. Role Hierarchy & Identity-Bound Permissions
Roles file checked into the repo (and itself protected):
```yaml
# .specguard/roles.yml
roles:
  architect: [alice@corp.com]
  maintainers: [bob@corp.com, charlie@corp.com]
  contributors: ["*@corp.com"]
  agents: [claude-bot, kilo-bot]

rules:
  ".specify/memory/constitution.md":
    edit: architect
    approve_changes: architect
  "openspec/specs/**":
    additive_changes: maintainers      # auto-pass with log entry
    scope_changes: { propose: anyone, approve: architect }
  "CLAUDE.md":
    edit: maintainers
    agents: propose_only               # agents can NEVER directly edit
  ".specguard/**":
    edit: architect                    # self-protecting
```
- Identities = git identities / GitHub-GitLab accounts (verifiable server-side)
- Agents are first-class identities with restrictable rights (e.g., propose-only)
- Roles model supports per-file and (future) per-section granularity
- **Open design question for development:** section-level locking semantics (e.g., lock the "Scope" heading of a file while allowing edits elsewhere) — the one piece with real design risk and no prior art

### F4. Approval Workflow (where & how)
**No new UI.** Three equivalent approval paths, all recorded identically:
1. **GitHub/GitLab native PR review** (default) — authorized person clicks Approve; our check detects an approving review from a qualifying role → status flips green
2. **Comment command** — `/specguard approve` in the PR thread (mobile-friendly)
3. **CLI** — `specguard approve <pr-number>` (same API underneath)

PR check output (what the developer sees when blocked):
```
❌ specguard — Changes requested
   📄 openspec/specs/auth/spec.md
   Classification: SCOPE CHANGE (confidence 91%)
   Added: "SAML SSO via Active Directory"
   Locked scope says: out-of-scope ["SSO", "AD"]
   Requires approval from: @alice (architect)
   @charlie does not have scope-change rights on this file.
Merge blocked ⛔ (required check: specguard)
```

### F5. Merge Enforcement (the security layer)
- GitHub App / GitLab integration posting a **required status check**; branch protection makes it unbypassable
- Evaluates: (a) is the editor allowed to make this class of change to this file, (b) if SCOPE_CHANGE, does a recorded approval from an authorized role exist, (c) were protected files/sections touched by unauthorized identities
- GitHub Actions / GitLab CI job variant for teams who prefer CI over an App

### F6. Audit Trail
- Every verdict + approval recorded: who changed which spec file, classification, who approved, when
- Lives as (a) specguard log (exportable for compliance/SOC2-style asks) and (b) immutable PR history (which auditors already trust)

### F7. Agent Containment ("keep Claude in a direction")
- MCP server exposes tools to the agent: `get_scope`, `validate_change`, `check_permission`, `lock_scope`, `unlock_scope(reason)`
- Agent learns the locked scope at write time and gets redirected before drafting out-of-scope content ("Want me to draft it as a change proposal instead?")
- Agents flagged in roles.yml as `propose_only` can never produce a mergeable direct edit to protected files — server-side check sees the commit author/PR opener identity
- Overall-domain verification: the classifier always compares against the locked goal, so domain consistency is checked on every spec-file change regardless of which tool made it

### F8. Framework Adapters
- **Spec Kit adapter:** read `.specify/memory/constitution.md` + `specs/<feature>/spec.md|plan.md|tasks.md`; integrate via `.specify/extensions.yml` hooks; protect the constitution for real (it's currently "immutable" by vibes only)
- **OpenSpec adapter:** read `openspec/specs/**` and `openspec/changes/<id>/proposal.md` + deltas; gate the `archive` step — deltas can't merge into source-of-truth specs without recorded approval from an authorized role; reuse their proposal.md scope-in/out sections as the lock source
- **Plain adapter:** CLAUDE.md, AGENTS.md, .kilo files, arbitrary configured .md paths

---

## 5. User Flows (finalized)

### 5.1 Solo developer
Product = smart guardrail against their own agents and their own drift. Terminal + AI tool only, never a website.

Setup:
```bash
$ specguard init
✓ Found openspec/ structure          # or .specify/, or plain mode
✓ Created .specguard/roles.yml (you = owner of everything)
✓ Installed pre-commit hook
✓ Registered MCP server for Claude Code
```
- Write time: agent gets redirected by MCP before drafting out-of-scope content
- Commit time: hook shows "SCOPE CHANGE — you are the owner, confirm? [y/N]" → self-approval is a deliberate speed bump, recorded with git identity
- Push time (optional): same check in CI as safety net for `--no-verify` and cloud-agent commits

### 5.2 Team / Enterprise
- Lead writes roles.yml; org installs GitHub App; branch protection requires the specguard check
- Local layers warn (don't block) and predict the PR outcome
- PR is the enforcement + approval surface (see F4/F5)
- Additive changes pass quietly — most contributors most days never feel the tool
- Enterprise deployment option: self-host the validation service (Docker) inside their network for data control + LDAP/SSO mapping of identities + central audit export; same product, different hosting

### 5.3 Example end-to-end (team)
1. charlie asks Kilo to "add enterprise auth notes" → MCP warns: SSO is out-of-scope, alice owns approval
2. charlie proceeds anyway, commits (hook warns, doesn't block), opens PR
3. specguard check classifies SCOPE_CHANGE, posts explanation, blocks merge, pings @alice
4. alice approves via normal PR review (or `/specguard approve`)
5. check flips green, merge proceeds, audit log records: change, classification, approver, timestamp

---

## 6. Technical Building Blocks (already prototyped in this conversation)

All draft code produced during the conversation (to be rewritten properly during development, but logic is sketched):

1. **`scope_check_validator.py`** — shared core: load/save scope JSON, `validate_change(filepath, old, new)` → Claude API call returning `{aligns_with_goal, risk_level, mentions_out_of_scope[], summary, explanation}`, `format_validation_result()`
2. **`scope_check_integrations.py`** — `GitHookValidator` (staged .md files via `git diff --cached`, old content via `git show :path`, blocks on HIGH), `ScopeCheckCLI` (`lock`/`check`/`status`, exit 1 on HIGH for CI), `GitHubActionValidator` (reads GITHUB_EVENT_PATH, emits `::error`/`::warning` annotations)
3. **`scope-check-mcp-server.py`** — MCP server (stdio) with tools `lock_scope`, `validate_change`, `get_scope`, `unlock_scope(reason)`; persists `.scope-check.json`; registered via `claude mcp add` or claude_desktop_config.json
4. **GitHub Actions workflow** — checkout with `fetch-depth: 0`, run validator on PR, `ANTHROPIC_API_KEY` from secrets
5. **Lock file shape (v0):**
```json
{
  "goal": "JWT-based authentication with OAuth2",
  "scope_in": ["JWT tokens", "Google/GitHub OAuth", "Session management"],
  "scope_out": ["2FA", "Biometric auth", "SSO to AD"],
  "locked_at": "ISO-8601",
  "locked_by": "git identity",
  "locked_files": ["README.md", "ARCHITECTURE.md", "API_SPEC.md"]
}
```
6. **Classifier prompt pattern:** send goal + scope-in/out + file + old + new; demand strict JSON; truncate contents (~2k chars each in prototype — production needs smarter diff-focused context)

To be built fresh (not yet prototyped): the GitHub App itself (webhooks, Checks API, review detection, comment commands), roles.yml parser + identity resolution, section-level locking, OpenSpec/Spec Kit adapters, audit log storage/export, approval-state persistence.

---

## 7. MCP / Skills / Marketplace Context (from early conversation)

- **MCP** = open standard (Anthropic, Nov 2024; donated to Agentic AI Foundation under Linux Foundation, Dec 2025) connecting AI apps to tools/data. Primitives: tools, resources, prompts. Transports: stdio (local, default for Claude Desktop) and streamable HTTP (remote; SSE deprecated)
- **MCP servers do NOT require hosting** — local stdio is fine for our advisory layer; remote hosting only for the enterprise centralized option
- **MCP ≠ n8n:** n8n = predefined workflow automation; MCP = giving AI callable tools. n8n has MCP Server Trigger + MCP Client Tool nodes (irrelevant to this product, was earlier exploration)
- **Skills** (Claude Code) = markdown-defined behaviors/workflows; distributed via Claude Code plugin marketplaces (`claude plugin marketplace add`, marketplace.json on a git host); surface-specific. Our product may ship a companion skill, but MCP + App are the core
- **Marketplaces for distribution:** MCP Registry, Claude Code plugin marketplaces, claude.com/plugins, GitHub itself
- **Monetization reality for MCPs (2026):** no direct payment infrastructure in the spec; viable models = free MCP wrapping a paid service, enterprise support contracts, sponsorships, consulting

---

## 8. Honest Product Assessment (recorded verbatim in spirit)

**Grade: B+.** Good idea, one strong insight, two real risks, one open question.

**Strong:** the governance gap is real and verified; the architecture (enforce at merge, advise locally, no dashboard, distribute through ecosystems) is the shape developers adopt; timing tailwind from multi-agent teams is real.

**Risk 1 — Platform risk:** this is a feature, not a company. GitHub owns CODEOWNERS, branch protection, Copilot, AND Spec Kit; Anthropic could add native spec protection to Claude Code. Build fast, keep ceiling expectations realistic.

**Risk 2 — False positives:** a probabilistic gate on merges must earn trust; one wrong Friday block = uninstall. Classifier calibration is the actual hard product problem, not the architecture.

**Open question — Painkiller vs vitamin:** teams have tolerated doc drift forever; willingness to pay unproven. Becomes a painkiller only at (multi-human × multi-agent × spec-discipline) intersection — small today, growing.

**Verdicts by framing:**
- Venture-scale startup: weak (thin moat, platform risk, unproven WTP)
- OSS + enterprise tier: solid (realistic: respected tool, hundreds–thousands of stars, $1–5k/mo enterprise support potential; upside: acqui-hire/absorption by a player circling the space)
- Two-week thesis test: genuinely good — ship the smallest cutting piece and let reality grade it

---

## 9. Development Plan

### Phase 0 — MVP / Thesis Test (~2 weeks)
**Goal: the smallest cutting piece — a GitHub App (or Action) that classifies spec-file diffs on PRs and blocks unapproved scope changes.**
1. Production-quality validator core (diff-focused context, strict JSON, confidence thresholds, additive auto-pass)
2. GitHub Actions integration first (cheaper than a full App): required check, PR annotation with explanation, approval detection via PR reviews from identities listed in a minimal roles.yml
3. Minimal roles.yml: roles → identities; per-path rules with `additive_changes` / `scope_changes` / `edit` keys
4. Plain mode only (configured .md paths + CLAUDE.md/AGENTS.md defaults)
5. README with the one-liner positioning; MIT license; publish; post (Twitter/HN/Claude community); watch the issue tracker
**Success signal:** strangers file feature requests. Silence + 40 stars = market said no, cheaply.

### Phase 1 — Local DX layer
6. CLI (`init`, `lock`, `check`, `status`, `approve`)
7. Pre-commit hook (warn in team mode, self-approve speed bump in solo mode)
8. MCP server (lock_scope, validate_change, get_scope, check_permission, unlock_scope) + submit to MCP registry

### Phase 2 — Ecosystem adapters
9. Spec Kit extension (extensions.yml hook; protect constitution.md for real)
10. OpenSpec mode (gate `archive`; reuse proposal.md scope sections as lock source)
11. Proper GitHub App (webhooks + Checks API + `/specguard approve` comment command); GitLab equivalent

### Phase 3 — Enterprise (only if Phase 0–2 show traction)
12. Section-level locking (the open design problem)
13. Self-hosted Docker validation service; LDAP/SSO identity mapping; audit export
14. Slack approval bot (optional); support contracts

### Explicitly out of scope (decided against)
- ❌ Web dashboard / separate website / separate login
- ❌ Building our own spec format or proposal workflow
- ❌ Forking/embedding Spec Kit or OpenSpec code
- ❌ Code-vs-spec drift detection (Zencoder's battle, not ours — we govern *edits to the spec*)
- ❌ SaaS subscription as the primary model

---

## 10. Edge Cases & Open Questions (flagged for development)

1. **"Alice is on vacation"** — need approval delegation/fallback chains in roles.yml (e.g., `approve: [architect] -> [maintainers after 48h]`)? Decide during Phase 2.
2. **Agent opened the PR itself** — commit author vs PR opener identity; bot identities must map to `agents` role; propose-only agents → PR can exist but never merge without human role approval.
3. **Section-level locking semantics** — markdown heading-based regions? Anchor comments? No prior art; prototype in Phase 3.
4. **Classifier context window** — full file vs diff + surrounding context; cost per check; caching identical diffs.
5. **Confidence threshold tuning** — what confidence auto-passes vs escalates; per-repo configurability; override audit ("approved despite HIGH").
6. **Roles file bootstrap problem** — first commit of roles.yml itself; solved by App config or org-level default.
7. **Monorepos** — multiple lock scopes per repo (per-directory `.specguard/`).
8. **Identity spoofing locally** — git author is trivially fake locally; irrelevant because enforcement uses server-side platform identity (GitHub/GitLab account), which is the whole point of Decision 3.

---

## 11. Quick Reference — External Docs

- MCP docs: https://modelcontextprotocol.io / https://docs.claude.com/en/docs/mcp
- Claude Code hooks/permissions: https://code.claude.com/docs/en/permissions (note deny-rule enforcement bugs #6631, #6699, #11226)
- Spec Kit: https://github.com/github/spec-kit (extension point: `.specify/extensions.yml`)
- OpenSpec: https://github.com/Fission-AI/OpenSpec (gate point: `openspec archive`)
- Claude Code plugin marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
- GitHub Checks API (for the App): https://docs.github.com/en/rest/checks

---

*End of specification. Start development at Phase 0, step 1: the validator core.*
