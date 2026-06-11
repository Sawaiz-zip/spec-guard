---
name: "clean-code"
description: "Clean code review and refactoring skill — naming, structure, complexity, duplication, and readability for Python projects."
argument-hint: "Optional: file path or specific concern (e.g. 'review engine.py', 'naming', 'complexity')"
compatibility: "Python 3.12+ projects; principles apply to any language"
metadata:
  author: "specguard"
  source: ".claude/skills/clean-code/SKILL.md"
user-invocable: true
disable-model-invocation: false
---

## User Input

```text
$ARGUMENTS
```

If a file path is provided, read and review that file. If no argument is given, review the most recently edited file or ask which file to review.

## Review Checklist

Work through each category. Flag issues with severity: **must fix** / **should fix** / **consider**.

---

### 1. Naming

- [ ] Functions named as verbs: `classify_diff`, not `classifier` or `do_it`
- [ ] Variables named for what they hold, not their type: `watched_files`, not `file_list`
- [ ] Booleans prefixed with `is_`, `has_`, `can_`: `is_fork`, `has_qualified_approval`
- [ ] No single-letter variables outside list comprehensions and loop indices
- [ ] No abbreviations that require domain knowledge to decode
- [ ] Class names are nouns: `Verdict`, `ScopeLock`, not `VerdictHandler`

---

### 2. Functions

- [ ] Each function does one thing — if you need "and" to describe it, split it
- [ ] Length: flag functions over ~30 lines for review
- [ ] Parameters: flag functions with more than 4 parameters — consider a dataclass
- [ ] No boolean flag parameters that change behaviour: split into two functions instead
- [ ] Early returns over nested conditionals
- [ ] No side effects in functions whose name implies a query (e.g. `get_`, `find_`, `is_`)

---

### 3. Comments

- [ ] No comments that restate what the code does — the code says that
- [ ] Comments only for: hidden constraints, non-obvious invariants, workarounds for external bugs
- [ ] No commented-out code — delete it (git has history)
- [ ] No TODO comments without a linked issue or task ID

---

### 4. Complexity

- [ ] Cyclomatic complexity: flag any function with more than 4 branches
- [ ] Nesting: flag more than 3 levels of indentation
- [ ] Long chains: extract intermediate variables with meaningful names
- [ ] Magic numbers/strings: extract to named constants at module level

---

### 5. Duplication

- [ ] Identical logic in two places → extract a function
- [ ] Similar logic with slight variation → consider a parameter or a shared helper
- [ ] Copy-pasted error messages or annotation strings → extract to constants

---

### 6. Error handling

- [ ] Catch specific exceptions, never bare `except:` or `except Exception:` without re-raise
- [ ] Error messages name the file/field that caused the problem
- [ ] Custom exceptions (`ConfigError`, `ClassifierError`) used at system boundaries — not `ValueError` from deep inside a module
- [ ] No swallowed exceptions — at minimum `logger.warning` before continuing

---

### 7. Types (Python-specific)

- [ ] All public functions have type annotations
- [ ] `Optional[X]` written as `X | None` (Python 3.10+ style)
- [ ] Pydantic models used for external data boundaries (API responses, config files)
- [ ] No `Any` without a comment explaining why it cannot be narrowed
- [ ] Return types explicit — no implicit `None` on functions that sometimes return a value

---

### 8. Module structure

- [ ] Imports: stdlib → third-party → local, each group separated by a blank line
- [ ] No circular imports — dependency order: `models` → `config`/`gitdiff` → `classifier`/`roles`/`approvals` → `engine` → `report`/`ci`
- [ ] Module-level code limited to constants and `__all__` — no logic at import time
- [ ] No `from module import *`

---

### 9. Tests (when reviewing test files)

- [ ] Test names describe the scenario: `test_scope_change_below_threshold_warns_not_blocks`
- [ ] One assertion concept per test (multiple `assert` lines fine if testing one thing)
- [ ] No logic in tests (no loops, no conditionals) — if you need a loop, use `@pytest.mark.parametrize`
- [ ] Fixtures in `conftest.py`, not repeated across test files
- [ ] No real API calls in unit tests — `FakeAnthropicClient` only

---

## Output Format

For each issue found:

```
[SEVERITY] Category — Description
File: path/to/file.py, line N
Issue: what is wrong
Fix:   what to change it to (or a concrete suggestion)
```

After listing all issues, provide a **Refactoring Plan** — ordered by impact, highest first — with estimated effort (S/M/L) for each item.

If no issues are found in a category, note it as ✅ and move on.

---

## Rules

- Do not refactor beyond what was requested — flag issues, do not silently rewrite
- Do not add abstractions that are not needed by existing code
- Do not add error handling for scenarios that cannot occur
- When suggesting a rename, show the before and after in context — not just the new name
- Constitution IV applies: clean code must not introduce friction on the additive path
