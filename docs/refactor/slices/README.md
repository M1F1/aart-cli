# Refactor Slice Template

Create one file per critical-path slice.

```text
# CP-XX — Name
Status: NOT STARTED | IN PROGRESS | IMPLEMENTED | VERIFIED | MIGRATED | LEGACY REMOVED | BLOCKED

Goal:
Product Specification sections/invariants:
Legacy/current paths:
Target paths/owners:
Dependencies:
Non-goals:

Characterization / RED evidence:
Implementation steps:
Property tests:
Integration tests:
E2E/live acceptance:
Quality gates:

Done:
Remaining:
Known compromises:
Backlog discoveries:
Blockers:
Legacy removal criteria:

Handoff:
- Current working state:
- Exact next action:
- Do not undo:
- Tests last run/results:
- Failure evidence:
```

A slice file is operational state, not a product specification. If it conflicts with the Product
Specification, fix the slice.
