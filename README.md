# SpecGuard

> CODEOWNERS understands file paths. SpecGuard understands what the change *means*.

SpecGuard is a semantic governance layer for spec files in repositories where humans and AI agents collaborate. It runs as a required GitHub Actions status check, classifies every PR change to your watched spec files using Claude, and blocks unapproved scope changes — while passing additive changes silently.

---

## How it works

1. You lock your project goal and scope (in/out lists) in `.specguard/lock.json`
2. A contributor — human or AI agent — opens a PR touching a watched spec file
3. SpecGuard classifies the change: **ADDITIVE** (within scope → passes silently) or **SCOPE CHANGE** (alters goals/direction → blocked until an authorized role approves)
4. An authorized reviewer approves via GitHub's normal review flow → check turns green → merge proceeds

```
PR opened
  └─ Watched file changed?
       ├─ No → pass (nothing to evaluate)
       ├─ Unauthorized editor on protected path → BLOCK (deterministic, no AI)
       └─ Yes → Claude classifies the diff
                 ├─ ADDITIVE → PASS (quiet log line, zero friction)
                 └─ SCOPE CHANGE
                       ├─ confidence < threshold → WARN (never blocks)
                       ├─ no roles defined → WARN (solo mode)
                       └─ confidence ≥ threshold → BLOCK until authorized approval
```

---

## Quickstart (5 minutes)

### 1. Create `.specguard/lock.json`

```json
{
  "goal": "A CLI tool that converts Markdown to PDF",
  "scope_in": ["Markdown parsing", "PDF rendering", "CLI flags"],
  "scope_out": ["GUI", "cloud sync", "collaboration features"]
}
```

### 2. Optionally create `.specguard/roles.yml`

```yaml
roles:
  architect: [your-github-username]
rules:
  ".specguard/**":
    edit: architect
  "README.md":
    scope_changes:
      approve: architect
```

### 3. Add the workflow

```yaml
# .github/workflows/specguard.yml
name: specguard
on:
  pull_request:
  pull_request_review:
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

### 4. Add your Anthropic API key

GitHub → Settings → Secrets → `ANTHROPIC_API_KEY`

### 5. Enable branch protection

Settings → Branches → Require status check: `specguard`

That's it. Open a PR that adds an out-of-scope topic to a watched file → see the block → have an authorized reviewer approve → watch it turn green.

---

## Configuration

### `.specguard/config.yml` (all optional, shown with defaults)

```yaml
watch:
  - README.md
  - CLAUDE.md
  - AGENTS.md
  - ARCHITECTURE.md
  - "*.kilo"
  - ".specguard/**"
block_threshold: 0.75      # SCOPE_CHANGE blocks above this confidence
on_error: warn             # warn = fail-open on API outage; fail = fail-closed
model: claude-opus-4-8     # classifier model
max_diff_chars: 30000      # diff truncation limit (scope lists are never truncated)
```

### Solo mode

No `roles.yml` → SpecGuard runs in warn-only mode. SCOPE_CHANGE classifications surface as warnings but never block merges (a PR author cannot approve their own PR, so blocking would deadlock a team of one).

### No configuration at all

No `.specguard/` directory → check passes with a single setup notice. Never blocks an unconfigured repo.

---

## What it blocks vs. what it doesn't

| Change | Outcome |
|---|---|
| Typo fix in a watched file | PASS — silent |
| Clarification within locked scope | PASS — silent |
| New section on an out-of-scope topic | BLOCK until authorized approval |
| Goal sentence rewritten to change direction | BLOCK until authorized approval |
| Edit to a protected path by unauthorized identity | BLOCK — deterministic, no AI involved |
| Borderline change (confidence below threshold) | WARN — never blocks |
| Classifier unavailable (API outage) | PASS + loud warning (configurable to fail) |
| Fork PR (secrets unavailable) | PASS + notice |

---

## Cost

~$0.03–$0.05 per watched file per PR push on `claude-opus-4-8`. A 5-file PR costs ≤ $0.25. System prompt is cached across files in a single run. Model is configurable.

---

## Development

This project is planned using [GitHub Spec Kit](https://github.com/github/spec-kit).

- Constitution: `.specify/memory/constitution.md`
- Feature spec: `specs/001-pr-spec-gate/spec.md`
- Implementation plan: `specs/001-pr-spec-gate/plan.md`
- Tasks: `specs/001-pr-spec-gate/tasks.md`

---

## License

MIT
