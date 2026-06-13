# Contract: MCP Server Interface

Owner: `src/specguard/mcp_server.py`. Transport: stdio only. Started by `specguard mcp`
or `python -m specguard.mcp_server`, cwd = the governed repository. Requires the
`specguard-ci[mcp]` extra (import-guarded with that exact install hint).

Server name: `specguard`. All tool results include `advisory: true` and the disclosure
text; when the repository has no scope lock at the baseline, tools return
`configured: false` plus a setup hint instead of erroring.

## Tools

### `check_proposed_change`

The write-time guard: classify a change the agent is *about to make* — before any
commit, diff, or PR exists.

| Input | Type | Notes |
|---|---|---|
| `path` | str | repo-relative path of the file the agent intends to write |
| `proposed_content` | str | full intended new content |

Behavior: baseline content = `show_file(HEAD, path)` (empty for new files); builds a
`ChangedFile` via the existing `diff_from_contents`; non-watched path → returns
`watched: false`, no classification, no API call; watched → full verdict through the
shared engine (zero approvals, FR-011 rendering).

Result shape:
```json
{
  "configured": true,
  "watched": true,
  "advisory": true,
  "baseline": "HEAD (a1b2c3d)",
  "verdict": {
    "file": "README.md",
    "outcome": "BLOCK",
    "would_block_until": ["architect"],
    "classification": {
      "classification": "SCOPE_CHANGE",
      "confidence": 0.94,
      "risk_level": "HIGH",
      "out_of_scope_topics": ["SaaS pricing"],
      "summary": "...",
      "explanation": "..."
    }
  },
  "notice": "Advisory only — the merge-time check is the enforcing layer."
}
```

### `get_scope_lock`

No inputs. Returns the baseline `ScopeLock` (goal, scope_in, scope_out, locked_at,
locked_by) so agents can consult the frame *before* drafting — the cheapest drift
prevention of all (no classifier call).

### `list_watched_paths`

No inputs. Returns the effective watch globs from the baseline config and whether
roles enforcement is configured (`enforce_mode: bool`) — lets agents know which files
are governed without trial-and-error.

## Failure contract

| Condition | Behavior |
|---|---|
| repo unconfigured at baseline | `configured: false` + setup hint (never an exception) |
| missing `ANTHROPIC_API_KEY` | `classified: false` + "could not classify — advisory check skipped" |
| `ClassifierError` | same as missing key (warn-shaped result, never a tool error) |
| blocked model configured | hard error — the guardrail (001 R2a) is NOT soft-failed |
| not a git repository | tool error naming the problem |

## Testing

Tool functions are plain functions invoked directly in tests with a `FakeAdapter` and a
tmp git repo — no live transport, no MCP client, no API key (constitution: mocked CI).
