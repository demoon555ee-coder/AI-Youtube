# Content Evolution & Versioning

## Principles

- Published/source projects are immutable inputs to a revision.
- Every re-edit creates a new `video_projects` row and a new `content_versions` row.
- `content_root_id` identifies the lineage root; `parent_project_id` identifies the immediate predecessor.
- `revision_number` is allocated under a PostgreSQL advisory transaction lock.
- The original artifact paths are never reused for a revision because every revision gets its own project output directory.
- An alert can trigger at most one automatic revision through the unique `trigger_alert_id` constraint.

## Flow

`post-publish anomaly -> evolution plan -> new project revision -> optional workflow -> quality gate -> explicit publication`

A revision is not automatically published merely because its source video had an anomaly. Publication remains a separate action controlled by the existing YouTube workflow and entitlements.

## Artifact integrity

On successful workflow completion, `ContentArtifact` records capture output artifacts under the configured output root with SHA-256, size, type and immutable metadata. SHA-256 is computed in streaming chunks so large MP4 files are not loaded fully into memory.
