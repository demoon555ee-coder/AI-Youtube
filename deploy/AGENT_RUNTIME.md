# Agent Runtime — v4.2.1

Agent Runtime is the durable task-control contract for planner-driven agents. It is not a second unrestricted execution engine. The established `WorkflowEngine` remains the canonical executor for the existing full video pipeline.

## Lifecycle

`PENDING → RUNNING → SUCCEEDED / FAILED`

A task can also be `PENDING_APPROVAL`, `BLOCKED` or `CANCELLED`. `RUNNING` can only be entered after a valid worker lease and a fresh governance admission check.

## Invariants

- Task creation requires `action_type` and passes through Agent Governance.
- Parent tasks and dependency tasks must belong to the same channel.
- Dependency cycles are rejected.
- A task cannot be leased by an agent other than its assigned agent.
- Heartbeat, completion, failure, delegation and handoff require the live lease token.
- Worker concurrency is enforced while the agent row is locked.
- A task is never executed solely because an old approval exists; the current policy is re-evaluated immediately before leasing.
- Budget reservation happens at lease time for non-zero task budgets and unused reservation is released on terminal state.
- Outcomes are published to Learning only after the task reaches a terminal state.
- Plan nodes mirror task lifecycle so downstream dependencies can become ready.
