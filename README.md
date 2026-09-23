# YouTube AI Platform v4.2.4

This release is a control-plane correction of the v3.9–v4.2 autonomy layers. The core product, existing Workflow Engine and production pipeline remain intact; the governance, planning, runtime and learning layers now share one lifecycle and authorization contract.

## Control-plane contract

`Goal → Planner → Governance Admission → Agent Task → Lease → Established Executor Boundary → Outcome → Learning → Human-approved Strategy → Next Plan`

The v4.2.1 control plane deliberately does **not** introduce a second production renderer beside the existing `WorkflowEngine`. Agent tasks are durable planning/execution contracts; connecting a task to a concrete worker or existing workflow remains an explicit integration boundary. This avoids two competing execution engines owning the same video job.

## What was corrected
- Agent task creation always passes through Agent Governance.
- Governance is re-checked immediately before a lease is granted.
- A governance policy version is stored with each task; stale approvals cannot authorize a newer policy.
- Lease ownership is required for heartbeat, completion, failure, delegation and handoff.
- Parent/dependency lineage is channel-safe and dependency cycles are rejected.
- Planner states and runtime task states are synchronized.
- Approval-bound plan nodes create real human approval requests.
- Learning evidence is created only from authoritative task outcomes.
- Learning can influence only bounded agent-selection preference. It cannot modify governance, permissions, budgets, approval requirements, risk tiers or kill switches.
- Historical approval records are preserved; outdated requests are marked `SUPERSEDED`.
- Direct Agent Runtime and Learning operator shortcuts were removed from the UI.

## Authoritative boundaries

### Governance
Governance is the only authorization authority for autonomous action. Unknown action types fail closed as `CRITICAL / BLOCK`.

### Planner
The Planner builds a DAG, matches capabilities, records governance admission, tracks versions and replans only failed nodes under a bounded retry limit.

### Runtime
Agent Runtime owns durable task state, leases, lineage and budget reservations. It is a control-plane contract, not a competing renderer.

### Learning
Learning observes terminal task outcomes, proposes bounded strategy changes, and requires explicit human approval before activation.

## Verification boundary

Release verification is now enforced in CI rather than inferred from the isolated development environment.

- main CI run **#165** for commit `0641dc8` — **PASS**
- backend Python 3.12/3.13 — **PASS**
- frontend build and AST checks — **PASS**
- PostgreSQL 15/16 integration matrix on Python 3.12/3.13 — **PASS**
- staging Docker + health smoke + real Remotion runtime smoke + browser E2E — **PASS**
- release audit — **PASS**
- current schema on production boot — `036_enforce_content_version_timestamps`
- production API and Web deployments for commit `0641dc8` — **SUCCESS**

External provider credentials remain environment-dependent. The platform therefore keeps provider routing/readiness explicit and never fabricates missing credentials. Production automation requires the dedicated `worker-release` service to remain healthy, because workflow execution, autopilot scheduling, post-publish monitoring and maintenance loops run there.
