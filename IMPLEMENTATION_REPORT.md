# SpecGuard — Implementation Report

**Date**: 2026-06-13
**Branches covered**: `001-pr-spec-gate` (merged) · `002-local-tools` (complete, pre-merge)
**Current version**: `specguard-ci 0.2.0` on PyPI

---

## What Is SpecGuard?

When humans and AI agents both contribute to a codebase, a pull request can look harmless on the surface while quietly changing the project's direction. Someone says "just cleaning up the README" but actually adds a SaaS pricing section to what was supposed to stay a local CLI tool.

SpecGuard catches that. You lock your project's goal and scope in a single JSON file. From that point on, every change to your spec files is classified by Claude against that locked goal — and anything that drifts outside scope is flagged or blocked before it merges.

```
PR:      "refactored README for clarity"
Change:   Added a full SaaS pricing section
          to a project scoped as a local CLI tool.

SpecGuard: ❌ SCOPE CHANGE — 94% confidence
              requires approval from @architect
```

There are two phases of implementation. Phase 0 guards the merge gate on GitHub. Phase 1 brings the same protection to the developer's machine before anything is even pushed.

---

## Phase 0 — The GitHub Merge Gate (`001-pr-spec-gate`)

**Status**: Complete. Merged into `main`. Published to PyPI as `specguard-ci 0.1.0`.

### The Idea

Every time a pull request is opened (or a review is submitted), a GitHub Action runs. It looks at what changed in the spec files, sends the diff to Claude, and gets back a verdict: is this an additive change (safe) or a scope change (needs attention)?

Based on that verdict — and who's allowed to approve what — the check either passes silently, warns, or blocks the PR until the right person approves.

### What Was Built

#### `models.py` — The Data Shapes
Defines all the objects the system passes around:
- `ScopeLock` — your locked goal, in-scope topics, out-of-scope topics
- `Classification` — what Claude returned: `ADDITIVE` or `SCOPE_CHANGE`, confidence score, matched topics, explanation
- `Verdict` — the final decision per file: `PASS`, `WARN`, or `BLOCK`
- `PRContext` — info about the pull request (author, files changed, approvals)

#### `config.py` — Reading Your Configuration
Loads three files from your repo's `.specguard/` folder:
- `lock.json` — the locked goal and scope (required)
- `config.yml` — optional settings like which model to use, confidence threshold, watched file globs
- `roles.yml` — optional role assignments (who can approve what kind of change)

#### `gitdiff.py` — Getting the Diff
Talks to the GitHub API to get the actual text of what changed in the PR. Filters down to only the files you've told SpecGuard to watch. Handles truncation for very large diffs.

#### `classifier.py` — Asking Claude
Takes a diff and your locked scope, builds a structured prompt, and sends it to Claude. Parses the response back into a `Classification` object. If Claude's answer is ambiguous, it asks again (re-ask logic). Hard-blocks the `claude-opus-4-8` model from ever being used here (cost guardrail — enforced in code, not config).

#### `roles.py` — Who Can Approve What
Reads the `roles.yml` file and figures out which GitHub usernames are in which roles. Used downstream to determine whether a blocking verdict can be lifted by an existing approval.

#### `engine.py` — The Decision Brain
Takes the classifier's output, the roles config, and the PR's current approvals. Produces the final `Verdict` for each changed file:
- `ADDITIVE` + high confidence → `PASS` (silent)
- `SCOPE_CHANGE` + low confidence → `WARN`
- `SCOPE_CHANGE` + high confidence + no qualifying approval → `BLOCK`
- `SCOPE_CHANGE` + qualifying approval present → `PASS` (unlocked)
- Protected file + wrong author → `BLOCK` (no Claude involved, purely deterministic)

#### `approvals.py` — Checking GitHub Reviews
Fetches the current reviews on the PR from the GitHub API. Checks whether any reviewer is in the role that the engine would require for approval. Used to automatically re-evaluate a blocked check when someone approves the PR.

#### `report.py` — Formatting the Output
Turns the list of verdicts into the GitHub status check body — the text the developer sees when they look at the failing check on their PR.

#### `ci.py` — The Entry Point
The script that GitHub Actions actually runs. Reads environment variables (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, event payload), wires everything together, and exits with the right code.

#### `action.yml` — The GitHub Action Definition
The plug-and-play file any repo drops into `.github/workflows/`. Defines the inputs, permissions, and how to call `ci.py`.

### The Decision Flow

```
PR opened or reviewed
        │
        ├─ File not in watched globs ────────────────────► PASS (skip)
        │
        ├─ File is protected path + author not in role ──► BLOCK (no Claude)
        │
        └─ Watched spec file changed
                │
                └─ Claude classifies the diff
                        │
                        ├─ ADDITIVE ─────────────────────► PASS (quiet)
                        │
                        ├─ SCOPE_CHANGE, low confidence ─► WARN
                        │
                        └─ SCOPE_CHANGE, high confidence
                                │
                                ├─ Approver has reviewed ► PASS (unlocked)
                                └─ No approver yet ──────► BLOCK
```

### Quality Gates Passed

- **27/27 golden corpus cases** — a hand-labeled test set of real diffs, tested against both `claude-sonnet-4-6` and `claude-opus-4-8`. All classified correctly at the 0.75 confidence threshold.
- **All CI tests run without a live API key** — the classifier is mocked in tests; only the eval harness uses real credentials.
- **6/6 sandbox E2E scenarios** — live tested on a real GitHub repo with real PRs.
- **Hard guardrail** — `claude-opus-4-8` is blocked in code. Not a config option. A call that tries to use it raises an error and never reaches the API.

---

## Phase 1 — Local Developer Tools (`002-local-tools`)

**Status**: Complete. All 172 tests passing. Published to PyPI as `specguard-ci 0.2.0`.

### The Idea

Phase 0 catches scope drift at merge time. That's the security boundary. But by then, you've already written the code, pushed the branch, opened the PR, and waited for CI. Phase 1 moves that feedback earlier — to your terminal, your commit, and your AI coding agent — so scope drift is caught before it ever becomes a PR problem.

**Important rule**: these local tools are advisory only. They warn, they never block. The only thing that can actually stop a bad merge is the GitHub check from Phase 0. The local tools just give you a preview of what that check would say.

### What Was Built (on top of Phase 0)

#### `classifier.py` — Adapter Seam Added
The existing Claude API calls were refactored behind a clean interface called `ClassifierAdapter`. This is a Python protocol (like an interface) with one method: `classify(lock, changed_file, config) → Classification`.

The existing logic became `AnthropicAdapter` — the only real adapter that ships. The point is that if you ever want to swap in a different AI provider, you implement this interface and plug it in. The validator core never needs to change.

The `assert_model_allowed` guardrail (the Opus block) lives at the adapter boundary — so every adapter inherits it automatically. You can't write a new adapter that accidentally uses a blocked model.

#### `engine.py` — Updated to Use the Adapter
`evaluate_pr` now takes an `adapter: ClassifierAdapter` argument instead of a raw API client. The verdict logic is completely unchanged. `ci.py` constructs `AnthropicAdapter` and passes it in.

#### `gitdiff.py` — Two New Functions
Added `staged_changes()` and `worktree_changes()` — so the system can now diff against what's in your git index (what you've `git add`-ed) or what's in your working tree (files you've edited but not yet staged). The existing `watched_changes(base, head)` for ref-range diffs was already there.

#### `localcheck.py` — Snapshot Resolution
This is the core of the local check. It takes what mode you're in (staged / worktree / ref-range) and resolves it into:
- A list of `ChangedFile` objects (what actually changed in watched files)
- A `base_ref` (the git commit the check is comparing against — usually `HEAD`)
- The governance config (lock, settings, roles) read from that baseline commit — not from your dirty working tree

That last point matters: if you're editing your own `lock.json`, SpecGuard still shows you what verdict a PR would get based on the *committed* version of the lock, not your local edits. This matches exactly what the merge gate does.

#### `localreport.py` — Terminal Renderer
Formats verdicts for a human reading a terminal, a pre-commit hook, or an MCP tool result. The same `Verdict` objects that Phase 0's `report.py` formats for GitHub are formatted here for the terminal.

Key rendering rules:
- Additive change → one quiet line (no alarm)
- Would-block verdict → "would block until {role} approves" (never pretends approval exists)
- Classifier unreachable → "could not classify — advisory check skipped"
- Every single output includes an advisory notice: "local results are advisory; only the merge-time check enforces"

#### `cli.py` — The `specguard` Command
Three subcommands:

**`specguard init`** — guided setup from scratch. Prompts for your goal, in-scope topics, out-of-scope topics. Writes `.specguard/lock.json`. Optionally writes `config.yml`, `roles.yml`, the GitHub Actions workflow snippet, and a plain git hook script. Refuses to overwrite an existing lock unless you pass `--force`.

**`specguard check`** — runs the full verdict pipeline locally. Flags:
- (no flag) — checks working tree vs HEAD
- `--staged` — checks index vs HEAD (what you'd commit)
- `--base REF [--head REF]` — checks a ref range (what a PR would contain)
- `--json` — machine-readable output
- `--hook` — hook mode: always exits 0, no matter what

Exit codes mirror `ci.py`:
- `0` — nothing would block
- `1` — at least one verdict would block
- `2` — configuration error or missing API key

**`specguard mcp`** — starts the MCP server (see below).

#### `mcp_server.py` — The MCP Server
An MCP (Model Context Protocol) server that AI coding agents can connect to. Runs over stdio — no network listener, no web UI.

Exposes three tools:

**`check_proposed_change(path, proposed_content)`** — the agent passes a file path and the content it's *about* to write. The server diffs that proposed content against the current committed version of the file and runs the full verdict pipeline. The agent gets back the classification, confidence, matched topics, and whether it would block — before any commit exists.

**`get_scope_lock()`** — returns the current locked goal and scope so the agent knows what it's working within.

**`list_watched_paths()`** — returns the glob patterns for files that are governed.

Every tool response includes the advisory notice and, when the repo isn't configured, a helpful message explaining how to run `specguard init`.

The `mcp` SDK is an optional install (`pip install "specguard-ci[mcp]"`). If it's not installed and you try to run `specguard mcp`, you get a clear message telling you exactly what to run.

#### `.pre-commit-hooks.yaml` — Pre-commit Framework Support
Defines SpecGuard as a pre-commit hook. A repo that uses the pre-commit framework can add SpecGuard with two lines of config. Under the hood it runs `specguard check --staged --hook`, which always exits 0.

### The Local Check Flow

```
Developer edits a spec file
        │
        ├─ specguard check ──────────────────────────────► Terminal verdict
        │    (any time, advisory)
        │
        ├─ git commit (hook installed) ──────────────────► Warning shown,
        │    (pre-commit, advisory)                         commit always succeeds
        │
        └─ AI agent writes to a spec file
             (MCP server connected) ─────────────────────► Verdict before write
                                                            Agent can self-correct
```

### Tests Added (Phase 1)

| Test file | What it covers |
|---|---|
| `test_localcheck.py` | Staged vs worktree vs ref-range resolution in throwaway git repos; confirms governance config is read from committed baseline, not dirty working tree |
| `test_cli.py` | Every `init` prompt scenario, every `check` exit code, disclosure present in human and JSON output, hook-mode always-exits-0 matrix |
| `test_mcp_server.py` | All three MCP tool functions with `FakeAdapter` in tmp repos — verdict shape, non-watched path short-circuit, unconfigured repo hint, advisory field on every result |
| `test_parity.py` | All 27 golden corpus cases run through both the CI path and the local path — classification and outcome must be identical |
| `test_classifier.py` | Extended with adapter-protocol conformance tests |

---

## How the Two Phases Connect

```
                    ┌─────────────────────────────┐
                    │         lock.json            │
                    │  (goal + scope, committed)   │
                    └──────────────┬──────────────┘
                                   │ read at baseline
                    ┌──────────────▼──────────────┐
                    │       engine.evaluate_pr     │
                    │   (one shared validator)     │
                    └──┬───────────────────────┬──┘
                       │                       │
           ┌───────────▼───────┐   ┌───────────▼───────────┐
           │     ci.py         │   │    localcheck.py       │
           │  (GitHub Action)  │   │  (local snapshot)      │
           └───────────┬───────┘   └──┬──────────┬─────────┘
                       │              │           │
                ┌──────▼──────┐  ┌────▼────┐ ┌───▼─────────┐
                │  report.py  │  │  cli.py │ │ mcp_server  │
                │  (GitHub)   │  │(terminal│ │  (agents)   │
                └─────────────┘  └─────────┘ └─────────────┘
```

One verdict core. Three rendering surfaces. Classification is identical everywhere for identical inputs — proven by the parity test suite.

---

## What's Shipped

| Artifact | Version | Where |
|---|---|---|
| `specguard-ci` Python package | `0.2.0` | PyPI |
| GitHub Action (`action.yml`) | `v0.2.0` | This repo |
| `.pre-commit-hooks.yaml` | — | This repo (repo root) |
| MCP server | included in `0.2.0` | `pip install "specguard-ci[mcp]"` |

### Test Matrix Summary

| Suite | Tests | Result |
|---|---|---|
| Phase 0 (approvals, CI, classifier, config, engine, gitdiff, roles) | 109 | ✅ All pass |
| Phase 1 (cli, localcheck, mcp_server, parity) | 63 | ✅ All pass |
| **Total** | **172** | **✅ 172/172** |

---

## Key Design Decisions (Plain English)

**Why advisory-only locally?** A local hook that blocks commits trains developers to bypass it (`--no-verify`). A merge gate on the server side can't be bypassed by a dev or an AI agent. So the rule is: warn locally, enforce at merge. Always.

**Why read governance config from the committed baseline?** If you're editing your own lock file, you'd get a circular result — the lock you're changing would affect the verdict on the change itself. Reading from the committed baseline means you see exactly what the merge gate would see. This was discovered as a security finding during Phase 0 sandbox testing.

**Why block Opus 4.8 in code?** It's a cost guardrail. Opus is significantly more expensive. The classification task doesn't benefit from it over Sonnet. Putting the block in code (not config) means no one can accidentally enable it through a misconfigured `config.yml`.

**Why is the MCP server stdio-only?** SpecGuard's constitution (the project's rule book) says no web UI, no dashboard, no new login. The MCP server is a local tool that plugs into wherever the developer already is — their editor or their coding agent. Stdio is the right transport for that.

**Why one package, not separate CLI/MCP packages?** The constitution says one shared validator core. Splitting into separate packages would mean either duplicating the validator or creating a dependency between them. Keeping everything in `specguard-ci` is simpler and enforces the one-core rule structurally.