# Agent Learning — v4.2.1

Learning is an evidence and strategy-advisory layer. It does not authorize execution.

## Flow

`Task Outcome → Observation → Evaluation → Proposal → Human Approval → Strategy Version → Planner Selection`

Only authoritative task outcomes are ingested automatically. The public API does not allow an operator to invent a reward, success result or execution context.

## Learnable surface

The current bounded strategy parameter is `selection_priority`, used only as an advisory input when the Planner chooses between agents that already satisfy the requested capability.

Learning cannot change:

- risk tier
- automation mode
- human-approval requirement
- minimum confidence
- maximum cost
- permissions
- kill switches
- governance policy

## Approval

Every strategy proposal starts as `PENDING_APPROVAL`. Activation requires an approved proposal and creates a new immutable strategy version. A minimum evidence count is enforced before proposals can be generated.
