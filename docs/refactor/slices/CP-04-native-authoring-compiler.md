# CP-04 — Native authoring manifest and canonical compiler
Status: VERIFIED

## Goal

Compile explicit `aart.yaml`/`aart.json` authoring manifests and declared payload files into a
deterministic canonical Artifact package without heuristic repository crawling.

## Product Specification sections/invariants

INV-010 through INV-015, INV-018, INV-201 and related manifest/payload sections 55–70.

## Legacy/current paths

`agent_artifacts/protocol/native_models.py`, `native_schema.py`, `native_tree.py` and
`application/compiler.py` already provide substantial native JSON and canonical tree behavior.

## Target paths/owners

The existing compiler application seam plus the canonical `domain.artifacts` envelope. Format
parsers remain boundary adapters; canonical compilation remains pure after source acquisition.

## Dependencies

CP-03 verified canonical Artifact values and serialization.

## Non-goals

- No Source/Candidate promotion lifecycle (CP-05).
- No consumer installation migration.
- No heuristic scan of README, entrypoint or launcher names.

## Characterization / RED evidence

Existing native protocol/compiler tests were retained. The first CP-04 RED run failed because
`agent_artifacts.protocol.authoring` did not exist. New tests then fixed the contract for exact
manifest basenames, no-manifest/no-candidate behavior, multiple and nested artifact boundaries,
safe includes/excludes, YAML duplicate-key refusal, input digest stability and canonical lowering.

## Implementation steps

1. Characterize current manifest discovery and payload selection.
2. Define authoring input lowering to canonical ArtifactPackage.
3. Compute ArtifactInputDigest from manifest, selected payload and relevant metadata only.
4. Reject traversal, symlinks/special files and undeclared payload.
5. Preserve deterministic artifact.json + payload projection.

## Property tests

Hypothesis varies unrelated repository paths/bytes and input ordering. Neither changes
ArtifactInputDigest or canonical entries. Example-based negative proofs show selected content and
executable-bit changes do change the digest.

## Integration tests

`tests/authoring_compiler_integration_test.py` creates a real author repository, acquires it through
the bounded non-symlink-following local source adapter, and compiles only declared files. The unit
integration also compiles multiple manifests and all five artifact kinds through
`compile_native_package`, the existing canonical validator.

## E2E/live acceptance

The smallest safe current path is real filesystem acquisition → immutable SourceSnapshot →
authoring compiler → canonical native package. A new one-off CLI command was not invented because
the accepted public owner is Source Sync/Candidate lifecycle in CP-05. Git-backed multi-repository
acceptance remains CP-17.

## Quality gates

- 49 focused compiler/native/architecture tests pass before the final negative additions.
- 19 CP-04 authoring/YAML/acquisition tests pass.
- Full unit/coverage run: 1,935 tests pass; total branch coverage 83.45% (threshold 82%).
- Ruff and Mypy pass for all 177 production modules.
- 46 E2E tests pass.
- Format, lint, typecheck, unit, integration, validation, coverage, packaging, docs and secret-shape
  gates all pass.

## Done

- Added exact `aart.yaml`/`aart.json` discovery with no heuristic candidate creation.
- Added frozen authoring and compiled-artifact values plus `AART Native` / `AART Compatible`
  compliance classification.
- Added strict dependency-free YAML block grammar and strict JSON parsing.
- Added safe, manifest-root-relative glob selection; excludes win; nested manifests own isolated
  subtrees; traversal, selected symlinks/special files and reserved output collisions fail.
- Added ArtifactInputDigest over raw manifest bytes, selected file paths/content and executable
  metadata only.
- Lowered all five artifact kinds into deterministic `artifact.json + payload/ + provenance.json`
  and the canonical Artifact algebra.
- Reused the native canonical package validator so registry/install code consumes one protocol.
- Allowed empty canonical compatibility dimensions to represent an omitted/unconstrained author
  dimension rather than fabricating compatibility data.

## Remaining

- Commit CP-04.
- Route Source Sync and Candidate lifecycle through this output in CP-05 before claiming MIGRATED.

## Known compromises

YAML intentionally supports only the finite authoring subset recorded in D-007. External-script
launch compiles as AART Compatible, not AART Native. The generated MCP descriptor contains
canonical runtime/payload placeholders; CP-09/10 own their eventual isolated-runtime and launcher
interpretation.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

Existing native protocol remains until public compiler/registry flows are migrated and verified.

## Handoff

- Current working state: CP-04 VERIFIED; changes ready to commit.
- Exact next action: commit CP-04, create the CP-05 slice file, then add Candidate lifecycle RED.
- Do not undo: raw manifest + declared file digest boundary, nested-manifest isolation, finite YAML
  grammar, compliance distinction or reuse of `compile_native_package`.
- Tests last run/results: 1,935 unit and 46 E2E pass; coverage 83.45%; all repository quality gates
  green.
- Failure evidence: the first full coverage run exposed legacy rejection of empty compatibility;
  the Product Specification author example omits platforms, so the schema and characterization now
  treat empty dimensions as unconstrained. The rerun is green.
