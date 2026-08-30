# AART Refactor — Next Work

## Current objective

Open **CP-07 Inspection, remediation, policy and immutable planning** on the verified CP-06 exact
resolved Selection.

## Immediate next actions

1. Read Product Specification requirement/remediation/policy/planning sections and characterize the
   existing runtime-requirement, setup, install-planning and policy seams.
2. Write CP-07 RED tests for immutable environment facts, pure requirement assessment, finite
   allowed remediation derivation, restrictive policy composition and minimal risk-classified
   Mutation/Install plans.
3. Accept only an exact CP-06 `ResolvedSelection`; inspection cannot select versions, and planning
   cannot perform filesystem, process, network, credential or harness effects.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no Source Sync promotion;
- no remediation/install execution yet (CP-07 plans only);
- no runtime input or credential value handling yet (CP-08);
- no backlog work unless it becomes a proven critical-path blocker.
