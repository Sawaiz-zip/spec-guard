---
name: "git"
description: "Git workflow skill — branch management, commits, PRs, rebasing, and conflict resolution following project conventions."
argument-hint: "Optional: specific git operation (e.g. 'new branch', 'pr', 'cleanup', 'undo')"
compatibility: "Requires a git repository"
metadata:
  author: "specguard"
  source: ".claude/skills/git/SKILL.md"
user-invocable: true
disable-model-invocation: false
---

## User Input

```text
$ARGUMENTS
```

Consider the user input before selecting which operation to perform.

## Operations

### Branch

**Create a feature branch** (when user says "new branch", "start feature", or similar):
- Name format: `NNN-short-description` (e.g. `002-classifier-core`)
- Always branch from the latest `main`: `git checkout main && git pull && git checkout -b <name>`
- Report the branch name created

**Switch branch**: `git checkout <branch>` — list available branches first if name is ambiguous

**Delete merged branch**: confirm the branch is merged into main before deleting

---

### Commit

Follow this sequence every time:
1. `git status` — review what changed
2. `git diff` — understand the changes
3. Stage specific files by name — never `git add .` or `git add -A`
4. Write the commit message using the Conventional Commits format:

   ```
   <type>(<scope>): <short summary>

   <optional body — the WHY, not the what>

   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```

   Types: `feat` `fix` `docs` `refactor` `test` `chore` `perf`

5. Always pass the message via heredoc:
   ```bash
   git commit -m "$(cat <<'EOF'
   feat(classifier): add prompt caching with ephemeral cache_control
   EOF
   )"
   ```

**Never**:
- Skip hooks (`--no-verify`)
- Amend published commits
- Commit `.env`, credentials, or binary blobs not already tracked

---

### Pull Request

1. `git log main..HEAD --oneline` — summarize what's on the branch
2. `git diff main...HEAD` — review all changes
3. Push branch: `git push -u origin <branch>`
4. Create PR via `gh pr create`:

   ```bash
   gh pr create --title "<type>: <summary under 70 chars>" --body "$(cat <<'EOF'
   ## Summary
   - <bullet 1>
   - <bullet 2>

   ## Test plan
   - [ ] <validation step>

   🤖 Generated with [Claude Code](https://claude.ai/claude-code)
   EOF
   )"
   ```

5. Return the PR URL

---

### Rebase & Sync

**Sync feature branch with main**:
```bash
git fetch origin
git rebase origin/main
```

Resolve conflicts file by file — never discard changes without showing the user what would be lost.

**Interactive rebase** — not supported (requires interactive terminal). Use fixup commits and `git rebase origin/main` instead.

---

### Undo

| Situation | Safe command |
|---|---|
| Unstage a file | `git restore --staged <file>` |
| Discard uncommitted changes to a file | `git restore <file>` (destructive — confirm first) |
| Undo last commit, keep changes staged | `git reset --soft HEAD~1` |
| Find a lost commit | `git reflog` |

**Never** `git reset --hard` or `git push --force` on `main` without explicit user instruction.

---

### Cleanup

- Delete local branches already merged to main: `git branch --merged main | grep -v main | xargs git branch -d`
- Show branches: `git branch -vv`
- Show log: `git log --oneline --graph --decorate -20`

---

## Rules

- Confirm before any destructive operation (reset --hard, force push, branch delete)
- Prefer creating new commits over amending
- Never push directly to `main` unless the user explicitly says so
- Always verify the remote URL before pushing to a new remote
