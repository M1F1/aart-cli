# CP-04 — Native authoring manifest and canonical compiler
Status: IN PROGRESS

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

Existing native protocol/compiler tests must be read and retained. New RED tests target the gap
between the current native representation and the canonical Artifact algebra.

## Implementation steps

1. Characterize current manifest discovery and payload selection.
2. Define authoring input lowering to canonical ArtifactPackage.
3. Compute ArtifactInputDigest from manifest, selected payload and relevant metadata only.
4. Reject traversal, symlinks/special files and undeclared payload.
5. Preserve deterministic artifact.json + payload projection.

## Property tests

Unrelated repository files do not change ArtifactInputDigest; payload order does not change output.

## Integration tests

Compiler application test over a source snapshot containing multiple explicit manifests.

## E2E/live acceptance

Smallest public CLI/compiler path supported by the existing command surface.

## Quality gates

Focused protocol/compiler tests and all touched-code gates.

## Done

- Slice opened after CP-03 verification.

## Remaining

- Characterization, RED, implementation and evidence.

## Known compromises

YAML must not add a runtime dependency; any supported YAML subset/parser choice must preserve the
zero-runtime-dependency invariant.

## Backlog discoveries

None.

## Blockers

None.

## Legacy removal criteria

Existing native protocol remains until public compiler/registry flows are migrated and verified.

## Handoff

- Current working state: CP-04 opened.
- Exact next action: inspect current native discovery/schema/tree contracts and add gap-focused RED.
- Do not undo: explicit manifest-only discovery and declared payload safety already proven by tests.
- Tests last run/results: CP-03 full gates green.
- Failure evidence: none.
