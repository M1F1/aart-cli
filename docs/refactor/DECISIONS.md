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

## D-005 — Harden the existing migration seam before moving modules
- **Decision:** retain the existing `agent_artifacts/domain`, application-service and explicit port
  seams as the initial strangler boundary; enforce their dependency direction with tests before
  adding the five canonical algebras. Do not perform a broad package move in CP-02.
- **Status:** accepted.
- **Reason:** current boundary and vertical-path tests prove useful behavior, while the Product
  Specification makes semantic ownership—not a prescribed directory tree—the invariant.
- **Consequence:** legacy subsystem-local models may remain temporarily, but new canonical domain
  code cannot depend on them or on concrete infrastructure/interfaces.

## D-006 — Canonical algebras are additive until a flow migrates
- **Decision:** introduce the five canonical algebras as new frozen domain modules without
  re-exporting or deleting subsystem-local values in CP-03.
- **Status:** accepted.
- **Reason:** source compatibility is not the product contract, but removing legacy flow authority
  before a complete adapted vertical path would violate the strangler migration rule.
- **Consequence:** later slices must adapt real application flows and then remove duplicated legacy
  authority only after acceptance evidence.
