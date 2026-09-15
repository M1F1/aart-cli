# CP-06 — Marketplace Selection, Collections and resolution
Status: VERIFIED

## Goal

Build the canonical consumer marketplace only from validated, published CP-05 registry versions;
represent multi-select intent separately from exact resolution; make Collections versioned and
declarative; retain direct/Collection/dependency ownership; and fail ambiguity or version conflicts
before any install planning.

## Product Specification sections/invariants

Sections 43, 145–149, accepted Consumer screens 02–05, edge cases 165.4–165.5,
165.20 and 165.22, and INV-026–INV-027, INV-124–INV-138, INV-203,
INV-207–INV-215, INV-217–INV-220 and INV-234–INV-236.

## Legacy/current paths

- `compiler/graph.py` builds one source-qualified marketplace artifact per source/identity and
  unversioned same-source Collections.
- `marketplace/model.py` and `marketplace/catalog.py` aggregate configured source health/trust and
  explicitly reject ambiguous unqualified artifact queries.
- `consumer/coordinates.py` and `consumer/resolution.py` parse selectors, expand Collections,
  deduplicate exact coordinates and calculate same-registry dependency closure.
- Existing consumer requests hold resolved coordinates directly; they do not preserve a first-class
  Selection or all ownership reasons.

## Target paths/owners

Frozen canonical Selection, versioned Collection and ownership values in `domain/`; pure approved
multi-registry aggregation and constraint resolution in `application/`; legacy marketplace/compiler
projections remain adapters until public flows migrate.

## Dependencies

CP-05 verified reloadable `RegistryArtifactVersion`, immutable content identity, lifecycle metadata
and approved snapshot identity.

## Non-goals

- No requirement inspection, remediation or install-effect planning (CP-07).
- No runtime inputs/credential handling (CP-08).
- No consumer TUI state machine/screens yet (CP-13).
- No multi-version activation in one scope; V1 selects one active version per identity/scope.

## Characterization / RED evidence

Retain current catalog ambiguity, source qualification, Collection expansion, dependency closure and
consumer request tests. New RED must cover published-only aggregation, different-content and
identical-content cross-registry ambiguity, Selection ordering, exact versus custom Collections,
ownership retention, conflicting constraints, revoked dependencies and cross-registry policy.

## Implementation steps

1. Define frozen versioned Collection, Selection, ownership and resolved-set values.
2. Project validated published registry versions into a deterministic aggregated marketplace.
3. Resolve exact direct selection and Collection constraints to one active version per identity,
   retaining every direct, Collection and dependency ownership reason.
4. Surface multi-registry ambiguity and unsatisfiable constraint sets as structured diagnostics.
5. Make cross-registry dependency traversal an explicit policy input and visible provenance.
6. Adapt the public marketplace/review flow only after the pure contracts are verified.

## Property tests

Registry, selection, Collection/member and input ordering cannot change catalog/resolution output;
adding a conflicting constraint can never silently replace another owner's required version.

## Integration tests

Two validated CP-05 registry snapshots → aggregate published versions → mixed direct/Collection
Selection → exact resolved artifacts with complete ownership reasons.

## E2E/live acceptance

Public marketplace selection/resolution over temporary registry checkouts; full remote-backed
source-to-install topology remains CP-17.

## Quality gates

Focused marketplace/compiler/consumer/CP-05 tests, architecture boundaries, full unit/E2E,
coverage, packaging, docs and secret-shape gates.

## Done

- CP-06 opened from verified commit `e6fa74e`.
- Product and current marketplace/Collection/resolution ownership characterized.
- Added frozen canonical `ArtifactRequest`, `ArtifactSelection`, exact versioned `Collection`,
  Collection-derived custom-selection metadata, typed ownership reasons and exact
  `ResolvedSelection` values. Selection order and duplication are canonicalized before resolution.
- Added approved marketplace snapshots that consume CP-05 `RegistryArtifactVersion` values and
  expose only `PublicationStage.PUBLISHED` entries. Candidate and promoted-local state cannot enter
  the consumer projection; trust remains visible metadata rather than a proof claim.
- Added one pure resolver for direct, bulk, exact Collection and mixed Selection. It supports exact,
  caret and comparator constraints, chooses the highest jointly satisfying approved version and
  enforces one active artifact identity per scope.
- Retained every direct, Collection and dependency ownership reason after deduplication and retained
  exact dependency edges, registry aliases and snapshot identities in the resolved result.
- Added structured failures for unsatisfiable versions, revoked dependencies, missing exact
  Collections, same/different-content multi-registry collisions and denied cross-registry edges.
  Unqualified dependencies prefer their parent registry and cross only under explicit policy.
- Preserved the existing marketplace/catalog/consumer public flow under focused regression and E2E
  tests. Its UI/install-state migration to the canonical ownership result remains CP-12/13 work,
  which is why this slice is `VERIFIED`, not `MIGRATED`.
- Full quality evidence: 1,975 unit tests and 46 E2E tests pass; branch coverage is 83.22% against an
  82% threshold; format, lint, typecheck, validation, packaging, docs and secret-shape gates pass.

## Remaining

- CP-07 consumes the exact resolved set for inspection/policy/planning without reopening version
  choice.
- CP-12 persists and reconciles canonical ownership; CP-13 projects first-class Selection and exact
  Collection state into the accepted consumer screens.
- CP-17 repeats approved aggregation and resolution across separately backed Git remotes.

## Known compromises

- The existing consumer CLI/TUI still projects the characterized legacy catalog/resolver. Keeping
  it supported avoids a partial install-state migration before CP-07–CP-12 define the complete
  canonical plan/receipt/ownership path; it no longer defines the new Selection semantics.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

Legacy graph/catalog resolution remains until public consumer flows use the canonical Selection and
approved-version resolver with equivalent compatibility, trust, offline and lifecycle evidence.

## Handoff

- Current working state: CP-06 canonical domain/application contracts are verified; legacy public
  consumer projection remains supported but is not the target authority.
- Exact next action: open CP-07 and characterize inspection, remediation, policy and planning seams
  before RED tests.
- Do not undo: published-only trust boundary, explicit registry source qualification, CP-05
  immutable version/snapshot identity or existing last-known-good registry activation.
- Tests last run/results: 1,975 unit, 46 E2E and 83.22% branch coverage; full quality green.
- Failure evidence: initial RED imports failed because canonical modules did not exist; subsequent
  format/lint/type checks found only new-code formatting, a callable default and a SemVer tuple type,
  all corrected before the final green run.
