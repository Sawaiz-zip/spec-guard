# Contract: GitHub Action Interface

Owner: `action.yml` (composite) + `src/specguard/ci.py`.

## Action inputs

| Input | Required | Default | Purpose |
|---|---|---|---|
| `anthropic-api-key` | yes | — | exported as `ANTHROPIC_API_KEY` |
| `github-token` | no | `${{ github.token }}` | Reviews API reads (`pull-requests: read`) |

## Consumer workflow contract (documented in README)

```yaml
name: specguard
on:
  pull_request:
  pull_request_review:        # approval re-evaluation — REQUIRED for enforce mode
permissions:
  contents: read
  pull-requests: read
jobs:
  specguard:                  # job name = the required-check name for branch protection
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}            # REQUIRED: base...head history
      - uses: <org>/specguard-action@v0
        with:
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
```

## Environment consumed by ci.py

| Variable | Source | Use |
|---|---|---|
| `GITHUB_EVENT_PATH` | runner | PR number, base/head SHA, author login, fork flag |
| `GITHUB_EVENT_NAME` | runner | `pull_request` \| `pull_request_review` (both handled identically) |
| `GITHUB_REPOSITORY` | runner | `owner/name` for API calls |
| `GITHUB_STEP_SUMMARY` | runner | verdict table destination |
| `GITHUB_TOKEN` | action input | Reviews API |
| `ANTHROPIC_API_KEY` | action input | classifier |
| `SPECGUARD_MODEL` | optional | model override |

## Outputs

| Channel | Content |
|---|---|
| Exit code | `0` = no BLOCK verdicts; `1` = ≥1 BLOCK (fails the check); `2` = configuration error |
| `::error file={path}::` | one per BLOCK verdict: classification, confidence %, matched out-of-scope topics, required approver role(s) |
| `::warning file={path}::` | one per WARN verdict (low-confidence scope change, solo-mode scope change, classifier_error under on_error=warn, fork-PR skip) |
| `::notice::` | unconfigured-repo setup hint; framework-detected log line |
| Step summary | markdown table of all verdicts in product-spec §F4 format, including quiet ADDITIVE lines |

## Step-summary block format (the §F4 message)

```
❌ specguard — Changes requested
   📄 {file}
   Classification: SCOPE CHANGE (confidence {NN}%)
   Added: "{summary}"
   Locked scope says: out-of-scope [{matched topics}]
   Requires approval from: {@members} ({role})
   {author} does not have scope-change rights on this file.
```

## Behavioral guarantees

- ADDITIVE-only PRs: exit 0, zero annotations, one summary line per file (constitution IV).
- Fork PRs (no secret): exit 0 + one `::warning::` explaining the skip.
- Malformed config: exit 2 with one `::error::` naming file and parse problem.
- Idempotent: same inputs → same verdicts; all state is recomputed per run.
