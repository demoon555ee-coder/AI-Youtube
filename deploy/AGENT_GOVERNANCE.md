# Agent Governance & Human Oversight — v3.9

v3.9 inserts a policy-controlled governance boundary between AI optimization decisions and autonomous execution.

## Core controls

- **Risk tiers:** LOW, MEDIUM, HIGH, CRITICAL.
- **Per-action policy:** each executable scope has an independent automation mode, confidence threshold, cost ceiling and human-approval requirement.
- **Per-channel policy:** enable/disable automation, default mode, approval timeout and channel-specific automation settings.
- **Human approval queue:** execution requests can remain `PENDING` until an authorized operator approves or rejects them.
- **Emergency kill switch:** channel-level stop that blocks new autonomous actions immediately; a global environment switch is also available.
- **Governance journal:** every dispatch/evaluation records the policy version, risk tier, requested/effective mode, cost/confidence inputs and the reasons that allowed or blocked the action.
- **Re-evaluation at execution:** approval is not a permanent bypass. The policy and execution guardrails are evaluated again immediately before the expensive action starts.

## Default action policy

| Action | Risk | Default automation | Human approval |
|---|---|---|---|
| `packaging_experiment` | LOW | approve | yes |
| `scene_reedit` | MEDIUM | approve | yes |
| `blueprint_replan` | HIGH | approve | yes |
| `full_rebuild` | CRITICAL | block | yes |

These are safe starting defaults and can be changed by an owner/admin through the governance API.

## API

Read channel policy:

`GET /api/v1/governance/channels/{channel_id}/policy`

Update channel policy:

`PATCH /api/v1/governance/channels/{channel_id}/policy`

Update an action policy:

`PATCH /api/v1/governance/channels/{channel_id}/actions/{action_type}`

Approval queue:

`GET /api/v1/governance/channels/{channel_id}/approvals`

Approve / reject:

`POST /api/v1/governance/approvals/{approval_id}/approve`
`POST /api/v1/governance/approvals/{approval_id}/reject`

Emergency stop:

`POST /api/v1/governance/channels/{channel_id}/kill-switch?enabled=true`

Governance journal:

`GET /api/v1/governance/channels/{channel_id}/journal`

## Why an action was allowed

A `DISPATCH_EVALUATED` event is written before execution and contains:

- policy version;
- action/risk tier;
- requested and effective mode;
- estimated cost;
- decision confidence;
- kill-switch state;
- action policy state;
- maximum permitted cost;
- minimum permitted confidence;
- human-approval requirement;
- human-readable reasons.

This makes the authorization path reconstructable after the fact rather than relying on a single boolean such as `auto_execute=true`.

## Operational rule

A `PENDING` approval cannot be executed. Approval changes the run to `APPROVED`, but execution still re-runs governance and the existing v3.8 permission, tenant, Quality Gate, revision-limit, budget and idempotency checks.

Recommended production posture is to keep high-impact actions behind human approval until their behavior has been observed in staging.
