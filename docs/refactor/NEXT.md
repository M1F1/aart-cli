# AART Refactor — Next Work

## Current objective

Open **CP-05 Source, Candidate, Registry and Promotion lifecycle** on the verified CP-04 compiler
output.

## Immediate next actions

1. Commit the verified CP-04 slice as a reviewable checkpoint.
2. Create `docs/refactor/slices/CP-05-source-candidate-registry.md` before CP-05 code changes.
3. Define frozen Source/Candidate lifecycle states and semantic candidate diff over
   `CompiledAuthorArtifact`.
4. Route source synchronization through explicit manifest discovery without promotion or registry
   mutation.
5. Add immutable coordinate/version, rejection/superseding and vendored-promotion RED tests before
   implementing CP-05 transitions.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no Source Sync promotion;
- no consumer marketplace aggregation yet;
- no backlog work unless it becomes a proven critical-path blocker.
