# CP-07 — Inspection, remediation, policy and immutable planning
Status: VERIFIED

## Goal

Consume an exact CP-06 `ResolvedSelection`; represent environment observations as immutable,
secret-free facts; assess and aggregate requirements; derive only capability- and policy-allowed
remediations; and produce one deterministic, risk-classified, reviewable plan without executing an
effect.

## Product Specification sections/invariants

Sections 4, 10–13, 22–36, 40–42, 117, 145, 148 and 152–153; INV-001–INV-007,
INV-028–INV-040, INV-107–INV-110, INV-124, INV-130–INV-132 and INV-149–INV-158.

## Legacy/current paths

- `domain/requirements.py`, `remediations.py`, `effects.py` and `policies.py` define the CP-03
  frozen algebras but are not yet connected by one canonical application plan.
- `consumer/runtime_requirements.py` parses a repository-owned runtime inventory and evaluates
  advisory capabilities without mutating the host.
- `installation/*`, `consumer/application.py`, `setup_engine/*` and `lifecycle/*` contain mature,
  reviewed legacy planning behavior and characterization evidence.
- Existing install plans are per artifact/profile and tied to legacy catalog/install-state values;
  they do not consume the CP-06 ownership-preserving resolved set.

## Target paths/owners

Frozen environment fact and canonical plan values in `domain/`; pure assessment, aggregation,
remediation filtering and install planning in `application/`; read-only host inspection behind an
explicit port/adapter boundary.

## Dependencies

CP-03 five algebras and CP-06 exact `ResolvedSelection`, registry snapshot provenance and ownership
reasons are verified.

## Non-goals

- No secret/config value acquisition or credential provider lifecycle (CP-08).
- No Python environment/package backend implementation (CP-09).
- No MCP launcher/harness vertical slice (CP-10).
- No effect interpreter, mutation, receipt or general current/desired reconciliation (CP-11/12).
- No Fast/Verbose UI implementation (CP-13); both will project this same plan.

## Characterization / RED evidence

Retain CP-03 algebra/property tests, runtime-requirement evaluation, install review/finalize and
policy regression tests. New RED covers fact ordering and absence of secrets, three-state pure
assessment, semantic bulk requirement aggregation, conflicting declarations, capability/policy
intersection, non-interactive failure, forbidden effects, risk escalation, ownership-preserving
effect deduplication and deterministic review identity.

## Implementation steps

1. Add immutable environment facts and typed remediation capabilities.
2. Aggregate equivalent requirements across resolved artifacts while retaining dependants; reject
   one requirement ID with conflicting semantics.
3. Assess requirements against facts as Satisfied, Unsatisfied or Unknown without IO.
4. Derive possible remediations and intersect them with platform capabilities and restrictive
   effective policy, including risk ceiling and non-interactive mode.
5. Deduplicate semantic effects while retaining artifact owners; reject forbidden effects before a
   plan exists.
6. Build one deterministic immutable plan and review digest over resolution, facts/assessments,
   remediation choices, effects, risks and policy identity.
7. Add a smallest read-only local inspector adapter and prove planning itself remains pure.

## Property tests

Requirement, fact, owner, intent and effect ordering cannot change plan identity; restrictive policy
overlays cannot add remediation/effect permissions or raise the plan's permitted risk ceiling.

## Integration tests

Exact multi-artifact resolved Selection → read-only environment inspection → aggregated assessment
→ selected allowed remediation → one immutable plan with all owners and no mutation.

## E2E/live acceptance

Existing public review-before-finalize lifecycle remains characterized; public canonical plan
projection migrates with CP-10/13 after input/runtime contracts exist. Full remote-backed proof is
CP-17.

## Quality gates

Focused domain/runtime-requirement/policy/install/consumer tests, architecture boundaries, full
unit/E2E, coverage, packaging, docs and secret-shape gates.

## Done

- CP-07 opened from verified commit `ca2f641`; product and existing requirement/remediation/policy/
  planning seams characterized.
- `domain/inspection.py`: frozen `EnvironmentFact`, `FactState`, `RemediationCapability` and
  `EnvironmentFacts` with one observation per requirement, canonical ordering, single-line
  validation and no general value channel that could carry a secret.
- `domain/plans.py`: frozen `OwnedRequirement`, `OwnedAssessment`, `PlannedRemediation`,
  `PlannedEffect`, `MutationPlan` and `InstallPlan` with a derived `review_digest` and canonical
  `install_plan_to_data` projection shared by human and machine surfaces.
- `domain/policies.py`: `allowed_network_hosts` and `interactive_remediation` added to
  `EffectivePolicy`/`PolicyOverlay`, composing by intersection and logical AND; `policy_to_data`
  gives the policy a stable identity for plan review.
- `domain/remediations.py` and `domain/effects.py`: missing constructor validation added so no
  remediation or effect can carry an empty or multi-line value into a plan.
- `application/installation_planning.py`: pure `inspect_requirements` (one port crossing),
  `aggregate_requirements`, `assess_requirements`, `allowed_remediations` and
  `prepare_install_plan`. Planning imports no filesystem, process, network, credential or harness
  module.
- `io/environment_inspection.py`: read-only `LocalEnvironmentInspector` observing Python runtime,
  executables and filesystem access; every unsupported observation stays Unknown.

## Remaining

None for CP-07. Credential/config value acquisition (CP-08), Python environment effects (CP-09),
the MCP vertical slice (CP-10) and reconciliation (CP-11/12) carry this plan forward.

## Known compromises

- Credential, network, harness and Python-package requirements can only be assessed as Unknown
  until CP-08/09/10 supply their specialized inspectors. This is fail-closed, not permissive.
- Selected remediations are recorded as reviewed choices; lowering them into concrete effects
  belongs to CP-08/09 where each remediation's interpreter exists.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

Legacy per-item planning remains until CP-10/12/13 carry the canonical plan through public MCP,
lifecycle, review and receipt paths with equivalent compatibility and drift evidence.

## Handoff

- Current working state: CP-07 VERIFIED. Canonical facts → assessment → allowed remediation → one
  immutable plan exists and is additive; no public flow is routed through it yet.
- Exact next action: open CP-08 and separate `ConfigInput` from `SecretInput`, value sources from
  process bindings, and `CredentialReference` from credential values.
- Do not undo: CP-03 algebra separation, CP-06 exact version/ownership/provenance, the
  facts-are-inputs purity of `assess_requirements`/`prepare_install_plan`, the Unknown-by-default
  inspection rule (D-013) or the review-digest preimage (D-015).
- Tests last run/results: full quality green — 1,989 unit, 46 E2E, 83.17% coverage;
  format-check, lint, typecheck, unit, integration, validate, coverage, packaging-check,
  docs-check and secret-shape-check all OK.
- Failure evidence: none.
