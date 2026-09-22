# YouTube AI Platform v4.2.1 — Control-Plane Audit & Correction

## Scope

This audit started from v4.2.0 and reviewed the complete v3.9–v4.2 autonomy path: Governance, Agent Runtime, Planner and Learning, together with the existing Autonomous Execution Controller and Workflow Engine that can actually perform production work.

The objective was not to preserve every previously added abstraction. The objective was to ensure that every autonomous action has one clear authorization path, one clear lifecycle, and no hidden bypass.

## Findings in v4.2.0

### 1. Learning was effectively a dead end
`active_strategy()` existed but was not consumed by planning decisions. Learning therefore stored strategy state without influencing the planner. This was rewritten so the planner reads an active strategy only as an advisory agent-selection preference.

### 2. Learning observations were user-writable
The old public learning endpoint accepted success/reward/context data supplied by operators. That allowed the evidence base to be poisoned. The endpoint was removed. Authoritative observations are now created from terminal `AgentTask` outcomes only.

### 3. Agent Runtime had a governance bypass
Task creation could exist outside the central governance admission path, and lifecycle methods were not uniformly tied to a live worker lease. Runtime creation and execution admission are now both governed, and terminal transitions require a live lease token.

### 4. Planner state did not advance reliably
Completed runtime tasks were not consistently reflected into downstream planner readiness, and approval-bound planner nodes did not create a working approval transition. Runtime↔plan synchronization and approval materialization were rewritten.

### 5. Planner and governance had an unsafe default mismatch
The default planner blueprint contained `full_rebuild`, while Governance correctly treated it as a critical blocked action. The default blueprint was rewritten to use bounded, explicit actions that have coherent governance defaults.

### 6. Policy changes could invalidate existing approvals
A run/task approved under one governance policy version could reach execution after that policy became stricter. v4.2.1 stores the governance policy version with the task/approval and re-checks it before execution. Historical approvals can remain for audit but cannot silently grant authority under a newer policy.

### 7. Approval history used a single permanent uniqueness slot
The old execution-run approval uniqueness made it impossible to replace a stale pending approval cleanly. Approval history now supports multiple records with a partial unique constraint only for the current `PENDING` request. Old requests become `SUPERSEDED`.

### 8. Runtime API contained a duplicate keyword binding bug
The task creation route passed `budget_usd` both through `model_dump()` and as an explicit keyword. This was fixed and covered by a dedicated regression contract.

### 9. Runtime task organization could be lost
The task constructor did not explicitly persist the channel organization. It now inherits `organization_id` from the channel before persistence, preserving tenant lineage for budget and audit records.

### 10. Existing production execution was at risk of becoming a second engine
The v4.0 runtime introduced durable task abstractions but did not have a concrete worker consuming them, while the existing `WorkflowEngine` already owns the real production pipeline. Instead of duplicating the renderer, v4.2.1 explicitly keeps Agent Runtime as a control-plane contract and keeps `WorkflowEngine` as the canonical established production executor.

## Corrected canonical logic

```text
GOAL
  ↓
PLANNER
  ↓
GOVERNANCE ADMISSION
  ↓
AGENT TASK
  ↓
HUMAN APPROVAL (when required)
  ↓
FRESH GOVERNANCE RECHECK
  ↓
LEASE
  ↓
ESTABLISHED EXECUTOR / WORKER BOUNDARY
  ↓
SUCCEEDED / FAILED
  ↓
LEARNING OBSERVATION
  ↓
EVALUATION
  ↓
STRATEGY PROPOSAL
  ↓
HUMAN APPROVAL
  ↓
STRATEGY VERSION
  ↓
NEXT PLAN
```

## Safety invariants now enforced

| Area | Rule | Result |
|---|---|---|
| Unknown actions | default to `CRITICAL / BLOCK` | fail closed |
| Task admission | central Governance evaluation required | enforced |
| Pre-execution | current Governance policy rechecked | enforced |
| Approval | must match current policy version | enforced |
| Task terminal state | live lease required | enforced |
| Lineage | parent/dependencies must share channel | enforced |
| Dependency graph | cycles rejected | enforced |
| Planning retry | bounded by `planner_max_retries` | enforced |
| Learning evidence | terminal task outcome only | enforced |
| Learning authority | strategy activation requires human approval | enforced |
| Learning permissions | cannot change governance controls | enforced |
| Kill switch | blocks new governed admissions | enforced |
| Approval target | exactly one of execution run or agent task | enforced in schema |

## What was intentionally removed

- `app/learning_service.tmp` — stray/dead implementation artifact.
- Public operator submission of arbitrary learning observations/rewards.
- Human UI shortcuts for impersonating runtime workers.
- Release tests that incorrectly froze the live application version at `3.8.0`.
- Duplicate/contradictory approval uniqueness semantics.

## Verification results

### Local/static
- `pytest -q`: **324 passed, 4 skipped**
- `python -m py_compile ...`: **PASS**
- `python scripts/full_audit.py`: **PASS**
- control-plane audit section: **all checks true**
- frontend AST audit: **37 files, 0 errors**
- E2E AST audit: **39 files, 0 errors**
- release manifest verification: **PASS after regeneration**
- secret scan: **0 hits**
- duplicate route audit: **0 duplicates**
- migrations: **001 → 031**

### Environment limits
A live `app.main` import was not possible because the environment lacks `asyncpg`. Frontend build dependencies (`node_modules`) are also absent. No claim is made that Docker, PostgreSQL, external AI providers, YouTube OAuth, Stripe or production/staging E2E execution was performed here.

## Final assessment

The v4.0–v4.2 control-plane code was **not** kept unchanged merely because its earlier test suite passed. The high-risk logic was rewritten around explicit state transitions and a single Governance authority. The remaining deliberate boundary is the task-to-concrete-executor adapter: the established Workflow Engine remains the production execution owner rather than creating a second competing runtime.
