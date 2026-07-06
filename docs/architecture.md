# Architecture & Flow

How SpecGuard turns a pull request into a governance verdict, and how its surfaces share one
validator core.

> Diagrams are exported to PNG (below) and also kept as [Mermaid](https://mermaid.js.org/) source
> in each collapsible — the source is the editable master. To regenerate an image, paste the
> Mermaid into [mermaid.live](https://mermaid.live) and use **Actions → Download PNG/SVG**.

## Contents

- [1. PR gate — decision flow](#1-pr-gate--decision-flow)
- [2. System overview — one core, many surfaces](#2-system-overview--one-core-many-surfaces)
- [3. Approving a blocked scope change](#3-approving-a-blocked-scope-change)

---

## 1. PR gate — decision flow

The path every pull request takes, from opened to verdict. Hard blocks are deterministic (no AI);
only a watched-file scope change reaches the classifier.

![SpecGuard PR gate decision flow](images/pr-gate-flow.png)

**Key points**

- **Merge time is the only enforcement layer** — local tools warn but never block.
- **`PROTECTED_VIOLATION` is deterministic** — computed from path/role rules, no model involved, so it never false-positives.
- **Additive, in-scope changes pass silently** — zero friction by design.
- **`block_threshold`** (default `0.75`) is the confidence a `SCOPE_CHANGE` needs to block; below it, the gate warns instead.

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart TD
    A([PR opened or updated]) --> B{Watched file<br/>changed?}
    B -->|No| PASS1([Pass])
    B -->|Yes| C{Protected path edited<br/>by unauthorized author?}
    C -->|Yes| BLK1([Block · PROTECTED_VIOLATION<br/>deterministic · no AI])
    C -->|No| D[LLM classifies the diff against<br/>the locked goal + scope]
    D --> E{Classification}
    E -->|ADDITIVE| PASS2([Pass · silent])
    E -->|SCOPE_CHANGE<br/>confidence &lt; threshold| WARN([Warn · not blocking])
    E -->|SCOPE_CHANGE<br/>confidence ≥ threshold| G{Authorized approval<br/>on record?}
    G -->|Yes| PASS3([Pass])
    G -->|No| BLK2([Block · until approved])
    BLK2 -. approve via native review · /specguard approve comment · CLI .-> G

    classDef pass fill:#dcfce7,stroke:#16a34a,color:#14532d;
    classDef block fill:#fee2e2,stroke:#dc2626,color:#7f1d1d;
    classDef warn fill:#fef9c3,stroke:#ca8a04,color:#713f12;
    class PASS1,PASS2,PASS3 pass;
    class BLK1,BLK2 block;
    class WARN warn;
```

</details>

---

## 2. System overview — one core, many surfaces

Every surface calls the same validator core and differs only in how the verdict is delivered — so a
change classified in CI is identical to the one shown by the CLI, hook, MCP server, or App.

![SpecGuard system overview: surfaces calling a shared validator core](images/system-overview.png)

**Key points**

- **Enforcing vs. advisory** — the CI Action and GitHub App enforce at merge time; the CLI, pre-commit hook, and MCP server are advisory.
- **Governance resolver precedence** — explicit `.specguard/lock.json` ▸ Spec Kit ▸ OpenSpec ▸ plain files.
- **Provider-agnostic classifier** — Anthropic (calibrated default), OpenAI, Gemini, or OpenRouter behind one output contract.
- **One verdict shape** — `ADDITIVE` / `SCOPE_CHANGE` / `PROTECTED_VIOLATION`, always with a confidence and any required approver role.

<details>
<summary>Mermaid source</summary>

```mermaid
flowchart LR
    subgraph SURF [Surfaces]
        direction TB
        CI[CI Action<br/>merge gate · enforcing]
        APP[GitHub App<br/>fork PRs · native checks]
        CLI[CLI · specguard check<br/>advisory]
        HOOK[pre-commit hook<br/>advisory]
        MCP[MCP server<br/>agents · write-time]
    end

    subgraph CORE [Shared validator core]
        direction TB
        RES[Governance resolver<br/>explicit lock ▸ Spec Kit ▸ OpenSpec ▸ plain]
        CLF[Classifier seam<br/>Anthropic · OpenAI · Gemini · OpenRouter]
        RULE[Roles + regions<br/>authorization · section locking]
    end

    V([Verdict<br/>ADDITIVE · SCOPE_CHANGE · PROTECTED_VIOLATION<br/>+ confidence + required approver])

    CI --> RES
    APP --> RES
    CLI --> RES
    HOOK --> RES
    MCP --> RES
    RES --> CLF
    RES --> RULE
    CLF --> V
    RULE --> V

    classDef core fill:#ede9fe,stroke:#7c3aed,color:#3b0764;
    classDef verdict fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
    class RES,CLF,RULE core;
    class V verdict;
```

</details>

---

## 3. Approving a blocked scope change

Any one authorized approval clears a block. Approval re-runs the gate in place — no new commit
needed — and a fresh push after approval resets to blocked (no stale approvals).

![SpecGuard approval sequence: block, approve, re-run, unblock](images/approval-sequence.png)

**Key points**

- **Three equivalent paths** — native PR review, `/specguard approve` comment, or `specguard approve` CLI.
- **Authorization is server-side** — recomputed from `roles.yml` at the trusted base commit; anyone may *trigger* a re-run, but only a real role member *clears* the block.
- **No stale approvals** — a new head commit after approval starts the gate blocked again.

<details>
<summary>Mermaid source</summary>

```mermaid
sequenceDiagram
    actor Dev as Contributor
    participant GH as GitHub PR
    participant SG as SpecGuard gate
    actor Appr as Authorized role member

    Dev->>GH: push scope-changing edit to a watched file
    GH->>SG: run gate
    SG-->>GH: Block · needs approval from <role>
    Appr->>GH: approve (native review · /specguard approve · CLI)
    GH->>SG: re-run gate (same head commit)
    SG->>SG: recompute authorization from roles.yml at trusted base
    SG-->>GH: Pass · merge unblocked
    Note over SG,GH: a new push after approval resets to blocked (no stale approval)
```

</details>
