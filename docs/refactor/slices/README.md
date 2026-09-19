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

## Current execution

The active stream is [CP-26](cp-26-authoring-and-legacy-removal.md): 13 of 22 tasks done,
14 next, with 18a → 19 → 20 before final gate 21. Read `../NEXT.md` and `../plan.json` for
current status, and `../CONTRACT_ALIGNMENT.md` for the accepted installation revision.

Older slices preserve evidence for the contract they tested. Their VERIFIED labels, shared runtime/
credential assumptions, names and path examples cannot establish compliance with Product
Specification §169. Retain still-valid behavior evidence and replace the withdrawn assumptions in
CP-26.18a/19. CP-20's operator-retest note is historical, not the active next task.
