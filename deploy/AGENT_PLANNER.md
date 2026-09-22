# Agent Planner — v4.2.1

The Planner turns a goal into a durable dependency DAG. It is a planning layer, not an authorization layer. Governance is evaluated for every node and is evaluated again when the corresponding task is admitted for execution.

## Flow

`Goal → DAG → Capability Match → Governance Admission → Materialize → Lease → Outcome → Downstream Ready`

Approval-bound nodes are materialized once their dependency nodes are complete. They create a real Governance approval request; after approval the task becomes worker-ready.

## Dynamic planning

- Cycle validation happens before persistence of an executable graph.
- Capability matching uses the channel-scoped agent registry.
- Active learning strategy can influence only agent selection preference; it cannot alter governance.
- A non-zero plan budget is a hard ceiling on estimated total plan cost.
- Failed nodes can be replanned only while below the configured retry limit.
- Replanning always re-runs governance and records a planner event.

## State synchronization

`AgentTask` is the execution state source for a materialized node. Runtime terminal states are mirrored into `AgentPlanNode`, which means successful completion unlocks downstream nodes and failures can trigger explicit replanning.
