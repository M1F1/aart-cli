# CP-05 — Source, Candidate, Registry and Promotion lifecycle
Status: VERIFIED

## Goal

Route maintainer Source Sync through the verified native authoring compiler, preserve Source,
Candidate and approved Registry as distinct domains, and implement deterministic candidate review
and vendored promotion without implicit push or publication.

## Product Specification sections/invariants

Sections 72–90, accepted Maintainer screens 31–53, accepted edge cases 165.1–165.3,
165.17, 165.24–165.28, and INV-016–INV-025 plus INV-199–INV-209, INV-216–INV-219,
INV-229, INV-238–INV-242.

## Legacy/current paths

- `agent_artifacts/sources/*` and `application/sources.py` safely acquire, validate, publish and
  retain last-known-good source snapshots.
- `agent_artifacts/registry_maintenance/*` plans reviewed registry mutations and never pushes.
- `agent_artifacts/curation/*` supports review/finalize maintainer operations and existing native
  vendoring/reference flows.
- Registry protocol v1 is identity-oriented and does not yet own the accepted Candidate lifecycle
  or versioned vendored artifact history.

## Target paths/owners

Frozen candidate/registry lifecycle values and pure transitions in the canonical domain;
application Source Scan and promotion services over CP-04 `CompiledAuthorArtifact`; existing source
acquisition and reviewed registry-write ports remain imperative-shell adapters.

## Dependencies

CP-04 verified explicit discovery, canonical compilation, ArtifactInputDigest and complete canonical
package entries.

## Non-goals

- No consumer marketplace selection/resolution (CP-06).
- No install/remediation policy engine (CP-07 onward).
- No maintainer TUI screen implementation yet (CP-14).
- No push, PR authorization or remote publication side effect.

## Characterization / RED evidence

Retain current source last-known-good, native registry planning, curation review/finalize and
no-push tests. New RED must fix lifecycle state transitions, digest-aware rejection, superseding,
source removal, immutable coordinate/version conflicts, semantic diff and one-transaction vendored
bulk promotion before implementation.

## Implementation steps

1. Define frozen Source observation, Candidate state, approved registry version/lifecycle and
   promotion audit values.
2. Reconcile one compiled source scan against candidate history and approved registry state without
   mutating registry content.
3. Validate/reject/supersede candidates with deterministic state transitions and semantic diffs.
4. Plan vendored versioned canonical packages and registry snapshot changes as one reviewed bulk
   transaction; reject same coordinate/version with different content.
5. Keep local promotion, local commit and canonical-branch publication distinct; never push.
6. Model deprecation/revocation as mutable lifecycle metadata separate from immutable payload.
7. Integrate the existing source acquisition boundary and add the smallest maintainer CLI scan flow.

## Property tests

Unchanged input digests preserve rejection and do not create candidate churn; candidate ordering and
bulk selection ordering do not change semantic scan/promotion results; different content can never
occupy an existing published coordinate/version.

## Integration tests

Pinned source snapshot → CP-04 compiler → candidate reconciliation → validation → vendored promotion
plan → reviewed local registry mutation, with approved registry content unchanged during scan.

## E2E/live acceptance

Public maintainer scan/validation/promotion command path over temporary Git-backed author and
registry repositories. Full cross-repository lifecycle remains CP-17.

## Quality gates

Focused source/registry/curation/compiler tests, architecture boundaries, full unit/E2E, coverage,
packaging, docs and secret-shape gates.

## Done

- CP-05 opened after CP-04 commit `42b764e`.
- Product and current source/registry ownership characterized at the slice boundary.
- Added frozen Candidate IDs, findings, lifecycle states, semantic diffs and pure
  validate/approve/reject/supersede/source-removed/promoted transitions.
- Reconciled pinned CP-04 compiled observations against Candidate history and approved registry
  versions. Source Scan returns no registry mutations, preserves unchanged rejection exactly and
  treats selected-input changes as reviewable successors.
- Added versioned vendored canonical packages under
  `artifacts/{kind}/{name}/{version}/`, explicit weaker `references/` records, durable version,
  index, snapshot and promotion-audit records, and hard immutable coordinate/version conflicts.
- Added deterministic bulk PromotionPlan review digests and one rollback-capable filesystem output
  call. The port exposes no commit, push, merge or publication operation.
- Added approved-version reload/validation, including canonical package tamper detection.
- Added separate reviewed publication/deprecation/revocation metadata plans that prove payload
  bytes and approved content snapshot identity do not change.
- Added public `aart registry scan` and exact-ID `aart registry promote` review/local-apply flows.
  Promotion reviews by default; `--yes` applies locally and explicitly reports no commit or push.
- Preserved existing bounded source acquisition, last-known-good snapshots and legacy
  curation/registry behavior under focused regression tests.
- Full quality run: 1,959 unit tests and 46 E2E tests pass; branch coverage 83.23% (82% threshold);
  format, lint, typecheck, validation, packaging, docs and secret-shape gates pass.

## Remaining

- CP-06 must consume the approved `RegistryArtifactVersion` projection for consumer marketplace
  aggregation without reading Candidate or author-source state.
- CP-14 must project the same scan/review/promotion semantics into accepted Maintainer screens.
- CP-17 must repeat the public lifecycle across separate Git remotes and external publication
  boundaries.
- Legacy `promote-native`, vendor and curation authority remains supported until replacement
  coverage proves it removable; this slice does not claim legacy removal.

## Known compromises

- Candidate review history is an application input and pure durable value, but the first public CLI
  flow re-observes exact Candidate IDs rather than introducing a second hidden local database.
  Maintainer durable history UI/storage belongs to CP-14; approved registry records are durable now.

## Backlog discoveries

None; optional hosted discovery, advanced signing and richer TUI work remain existing backlog items.

## Blockers

None.

## Legacy removal criteria

Existing curation/native reference paths remain until their documented use cases are migrated to
Candidate/versioned promotion, CP-14 exposes equivalent maintainer interaction, and CP-17 proves
the replacement across Git remotes. Only then may their commands and protocol records be removed.

## Handoff

- Current working state: CP-05 verified; canonical public scan and local promotion paths use the new
  Candidate/Registry lifecycle while legacy curation paths remain supported.
- Exact next action: open CP-06 and characterize existing marketplace/Collection/resolution behavior
  before writing the approved-version aggregation RED tests.
- Do not undo: CP-04 manifest/payload input-digest boundary; digest-aware Candidate rejection;
  distinct approved-content/workspace digests; local promotion versus publication separation; or
  existing last-known-good source semantics.
- Tests last run/results: 1,959 unit and 46 E2E pass; coverage 83.23%; all ten quality gates green.
- Failure evidence: the first full run found bare required-argument command hints; fixed to
  `registry scan --help`. The second found a CP-04 credential-shaped test fixture that became
  tracked after its prior quality run; assembled it through `tests.credential_fixtures`. The final
  complete run is green.
