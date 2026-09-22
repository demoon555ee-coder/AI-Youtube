# Creative Director v3.5

Creative Director converts scene-level creative evidence into a bounded intervention plan. Valid actions are `replace_visual`, `tighten`, `extend`, `text_overlay`, `audio_mix`, `transition`, `keep`, and `manual_review`.

Only `replace_visual` and `tighten` are executable automatically in v3.5. Other actions are explicit manual-review instructions and are never silently dropped.

Every decision is persisted in `creative_director_decisions` with the source analysis, maximum change budget, score, plan, and execution summary. The source project and its artifacts remain immutable.

The API requires `content:write`. A saved director plan can be referenced when creating a targeted re-edit revision.

Provider selection is server-side: browser clients cannot submit raw provider credentials or arbitrary provider endpoints. The API uses the project routing plan.
