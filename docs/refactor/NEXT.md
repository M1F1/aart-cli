# AART Refactor — Next Work

## Current objective

Open **CP-06 Marketplace Selection, Collections and resolution** on the verified CP-05 approved
registry-version projection.

## Immediate next actions

1. Characterize the existing marketplace catalog/search, coordinate parser, compiler graph,
   Collection and ownership behavior against Product Specification sections 91–99 and 166.
2. Write CP-06 RED tests for multi-registry aggregation, explicit ambiguity, first-class Selection,
   exact Collections versus custom selections, dependency/version conflicts and one active version
   per coordinate/scope.
3. Consume only validated CP-05 `RegistryArtifactVersion` state; do not scan author repositories or
   collapse Candidate state into the consumer marketplace.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no Source Sync promotion;
- no install/remediation execution yet (CP-07 onward);
- no backlog work unless it becomes a proven critical-path blocker.
