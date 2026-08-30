# AART Refactor Migration Status

> Source of truth for **where implementation currently is**.
> Product truth lives only in the Product Specification.

## State model

`NOT STARTED → IN PROGRESS → IMPLEMENTED → VERIFIED → MIGRATED → LEGACY REMOVED`

`BLOCKED` may be used with explicit evidence and unblock condition.

| Slice | Status | Evidence | Legacy authority remaining |
|---|---|---|---|
| CP-00 Canonical planning baseline | VERIFIED | Bootstrap commit `5515e11`; docs/secret/validation gates pass | Historical docs remain non-authoritative reference |
| CP-01 Repository characterization | VERIFIED | 242-row traceability matrix; 32 boundary + 86 focused tests pass; 1,903-test baseline recorded | Current implementation remains behavior evidence |
| CP-02 Clean architecture seam | VERIFIED | Architecture boundary tests; frozen domain scan; format/lint/typecheck/validate/docs/secret gates green | Legacy orchestration remains outside the new seam for strangler migration |
| CP-03 Five core algebras | VERIFIED | Frozen five-algebra modules; Hypothesis monotonicity/determinism properties; full gates green | Legacy/subsystem models remain flow authority until later adapters migrate |
| CP-04 Authoring manifest/compiler | VERIFIED | Explicit JSON/YAML discovery; five-kind canonical compilation; input-digest properties; real-filesystem integration; 1,935 unit + 46 E2E tests, 83.45% coverage and all quality gates green | Existing native/source commands remain public-flow authority until CP-05 routes Source Sync through the compiler |
| CP-05 Source/Candidate/Registry | NOT STARTED | — | — |
| CP-06 Marketplace/Selection/Collections | NOT STARTED | — | — |
| CP-07 Inspection/Remediation/Policy/Plan | NOT STARTED | — | — |
| CP-08 Inputs/Credentials | NOT STARTED | — | — |
| CP-09 Python environments/dependencies | NOT STARTED | — | — |
| CP-10 MCP stdio vertical slice | NOT STARTED | — | — |
| CP-11 Reconciliation engine | NOT STARTED | — | — |
| CP-12 Installed lifecycle | NOT STARTED | — | — |
| CP-13 Consumer TUI | NOT STARTED | — | — |
| CP-14 Maintainer TUI | NOT STARTED | — | — |
| CP-15 Edge-case hardening | NOT STARTED | — | — |
| CP-16 Doctor/supportability | NOT STARTED | — | — |
| CP-17 Git-backed live acceptance | NOT STARTED | — | — |
| CP-18 Migration/release gate | NOT STARTED | — | — |

## Update rule

Never mark a slice beyond the strongest evidence actually present.
`IMPLEMENTED` means code exists; `VERIFIED` requires relevant tests; `MIGRATED` means callers/flows
use the new path; `LEGACY REMOVED` requires the old authority/path to be safely removed.
