# Quickstart & Validation Guide: Advanced Governance

Contracts: [regions](contracts/regions.md), [scopes](contracts/scopes.md),
[audit](contracts/audit.md). Entities: [data-model.md](data-model.md).

## V1. Unit suite — every merge

```bash
pip install -e ".[dev,mcp,app]"
pytest
```

**Expected**: all green, including `test_regions.py`, `test_scopes.py`, `test_audit.py`,
and the extended cases in `test_engine.py`/`test_ci.py`/`test_app_events.py`. No live
classifier credentials needed (deterministic plumbing, not classifier behavior — research.md
R8).

## V2. Section locking

```bash
mkdir demo && cd demo && git init -b main
mkdir .specguard
cat > .specguard/lock.json <<'EOF'
{"goal": "A docs site generator", "scope_in": ["markdown rendering"], "scope_out": ["SaaS pricing"]}
EOF
cat > .specguard/regions.yml <<'EOF'
files:
  "ARCHITECTURE.md": ["Out of Scope"]
EOF
cat > ARCHITECTURE.md <<'EOF'
# Architecture

## Out of Scope
We will not build a hosted SaaS offering.

## FAQ
Anything goes here.
EOF
git add -A && git commit -m base
sed -i 's/Anything goes here./Anything goes here. Also: ponies./' ARCHITECTURE.md
git commit -am "faq edit"
specguard check --base HEAD~1
```

**Expected**: a single quiet `region_ungoverned` PASS — the FAQ edit never reaches the
classifier. Repeat editing the `## Out of Scope` paragraph instead → classified normally
(SCOPE_CHANGE if it adds out-of-scope content). Rename the `## Out of Scope` heading and
edit it → `RegionAnchorError`, exit 2.

## V3. Monorepo multi-scope

```bash
mkdir -p packages/api/.specguard packages/web/.specguard
echo '{"goal": "API service", "scope_in": [], "scope_out": ["billing"]}' > packages/api/.specguard/lock.json
echo '{"goal": "Web app", "scope_in": [], "scope_out": ["payments"]}' > packages/web/.specguard/lock.json
echo "# API" > packages/api/README.md
echo "# Web" > packages/web/README.md
git add -A && git commit -m base
echo "Billing integration coming soon." >> packages/api/README.md
echo "Just a typo fix" >> packages/web/README.md
git commit -am "two-package change"
specguard check --base HEAD~1
```

**Expected**: two independent verdicts — `packages/api/README.md` flagged against the API
scope's `billing` exclusion, `packages/web/README.md` passing quietly under the web scope.

## V4. Audit export

```bash
SPECGUARD_AUDIT_PATH=/tmp/audit.json python -m specguard.ci   # in an Actions context
cat /tmp/audit.json
```

**Expected**: one JSON record per verdict (file, scope, outcome, classification,
approvals, `as_of`), no secrets.

## Success-criteria traceability

| Scenario | Validates |
|---|---|
| V2 | SC-001, SC-003, FR-001, FR-002 |
| V3 | SC-002, FR-003, FR-004, FR-005 |
| V4 | SC-004, FR-006 |
| V1 (full suite green, untouched single-scope cases) | SC-005, FR-007 |
