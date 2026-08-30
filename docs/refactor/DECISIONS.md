# AART Refactor Decision Log

This log records implementation decisions needed to execute the Product Specification. It cannot
override or weaken the Product Specification. If a decision would change product semantics, update
the Product Specification first instead of hiding the change here.

## D-001 — Refactor target
- **Decision:** only `M1F1/aart-cli` is the target repository.
- **Status:** accepted.
- **Consequence:** older AART/Agent Artifacts repositories are read-only reference sources.

## D-002 — Product Specification precedence
- **Decision:** `docs/product-specification/PRODUCT_SPECIFICATION.md` is the sole product source of truth.
- **Status:** accepted.
- **Consequence:** historical plans/specs/design docs cannot override it.

## D-003 — Unattended execution
- **Decision:** agents are expected to run unattended for long periods. Resolve non-product
  ambiguities with the smallest safe invariant-preserving choice, record it and continue.
- **Status:** accepted.

## D-004 — Discovery scope discipline
- **Decision:** useful work discovered outside the mandatory critical path goes to BACKLOG unless
  evidence shows it blocks a mandatory invariant/acceptance gate.
- **Status:** accepted.
