# CP-03 — Five core algebras
Status: VERIFIED

## Goal

Introduce the canonical frozen Artifact, Requirement, Remediation, Effect and Policy values with
shared identifiers, provenance, compatibility, risk/capability metadata and deterministic safe
serialization.

## Product Specification sections/invariants

INV-002 through INV-010, INV-028 through INV-040, INV-051 through INV-054, INV-071, INV-107
through INV-109.

## Legacy/current paths

`agent_artifacts/model.py`, `policy.py`, setup requirement/remediation vocabulary, install operation
models and subsystem-local outcome types remain characterization/migration inputs.

## Target paths/owners

New frozen values under `agent_artifacts/domain/`; application planners consume them only after the
algebra contracts are verified.

## Dependencies

CP-02 dependency seam is verified.

## Non-goals

- No manifest parser/compiler migration (CP-04).
- No concrete credential value or provider IO (CP-08).
- No effect execution or lifecycle migration in this slice.

## Characterization / RED evidence

Add new algebra contracts before implementation. Existing subsystem values demonstrate behavior
but do not define the canonical API.

## Implementation steps

1. Define Artifact envelope, compatibility, capabilities and provenance.
2. Define Requirement variants and assessment states.
3. Define Remediation variants linked to requirement identifiers.
4. Define semantic Effects with risk and explicit capabilities.
5. Define restrictive Policy values and composition.
6. Provide deterministic, secret-safe canonical projections.

## Property tests

Hypothesis covers policy monotonicity, stable canonical ordering, effect risk preservation and
round-trip-safe JSON-shaped projections. Hypothesis remains dev/CI-only.

## Integration tests

Existing application paths are not migrated until the canonical core is verified.

## E2E/live acceptance

Deferred to the first migrated vertical slice.

## Quality gates

Focused algebra/property tests; format, lint, typecheck, validate, docs and secret-shape.

## Done

- Slice opened after CP-02 verification.
- Added frozen Artifact envelope with semantic kind separate from format/protocol, compatibility,
  capabilities, payload digest and provenance.
- Added Requirement variants and explicit Satisfied/Unsatisfied/Unknown assessments.
- Added Remediation variants that reference requirements without performing effects.
- Added semantic Effect variants with ordered risk classes and explicit inspectable/idempotent/
  reversible/independently-repairable capabilities.
- Added restrictive EffectivePolicy/PolicyOverlay composition.
- Added deterministic JSON-shaped projections that contain references, never secret values.
- Added Hypothesis as a dev-only dependency and property tests for allow-list intersection,
  deny-list union and stable artifact projection.

## Remaining

No CP-03 implementation remains. Application flows still use legacy/subsystem values until later
vertical slices adapt them; this slice is VERIFIED, not MIGRATED.

## Known compromises

None.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

Legacy values remain until migrated public flows use the canonical algebras and relevant acceptance
evidence passes.

## Handoff

- Current working state: CP-03 canonical algebra contracts are verified and additive.
- Exact next action: CP-04 RED tests for explicit manifest discovery and canonical compilation.
- Do not undo: CP-02 boundary enforcement.
- Tests last run/results: 1,916 unit tests pass (1 skip), 46 E2E tests pass, coverage 83.51%,
  packaging/format/lint/type/validate/docs/secret-shape gates pass.
- Failure evidence: none yet.
