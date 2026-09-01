# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 3: implement Candidate list, detail and semantic diff
screens 35–37 over the durable Source Scan history now established by screens 33–34.

Screens 30–34 are live in the production shared shell:

- screen 30 and screens 31–32 compose configured authoring Sources, durable health and only an exact
  matching Candidate-history observation (D-093–D-095);
- `s` on a focused Source enters typed screen-33 review, and Enter executes only its digest;
- preparation is read-only and binds the Source/history baseline plus the configured default
  registry's approved snapshot;
- execution rechecks registry and Source baselines, uses `SourceSyncPorts`, compiles exact
  `aart.yaml`/`aart.json` manifests, reconciles and atomically writes/rereads Candidate history while
  the Source instance lease remains held;
- local Sources carry `local:<snapshot-sha256>` rather than invented Git commits (D-096);
- screen 34 renders the persisted readback and explicitly reports no registry mutation (D-097,
  INV-200).

Evidence: RED-first reducer/application/local-provenance tests and a real temporary production
installation in `tests/maintainer_composition_e2e_test.py`. The complete E2E gate is 207 tests green;
focused unit, format, lint and typecheck gates are green. Broad discovery's six environment-only
keychain/uv failures were rerun with their required permissions and are green.

## Exact next action

Start RED tests for screens 35–37:

1. Project immutable Candidate rows from every composed authoring Source's exact durable
   `SourceScan`: status, artifact, version and Source. Keep active records distinct from retained
   lifecycle history and make filters typed application state, not renderer string logic.
2. Add Candidate Detail with identity, kind/version, Source alias and revision, manifest path,
   input/payload/canonical digests, runtime/transport/inputs/dependency description and findings.
   Navigate by stable Candidate ID so duplicate artifact names across Sources cannot collide.
3. Add semantic Candidate Diff against the locator's prior Candidate and/or approved registry
   version. Semantic changes are primary; raw canonical file diff is an explicit secondary view and
   bounded for terminal rendering (INV-202).
4. Extend production Maintainer composition to carry the exact scans it already reads once; do not
   rescan, recompile, reread or infer Candidate state during drawing. Corrupt history still refuses
   the whole observation.

## Critical boundaries for this slice

- Product Specification is the sole product authority.
- Source, Candidate, Registry and Marketplace remain distinct values and screens (INV-199).
- Source Sync never promotes and never mutates approved registry state (INV-200).
- Discovery remains exact `aart.yaml`/`aart.json` only (INV-201).
- Maintainer review is semantic diff first and raw file diff only on demand (INV-202).
- Published coordinate/version content is immutable; digest conflicts are explicit, never repaired
  in place (INV-203/239).
- Superseded, rejected and source-removed records remain durable audit history (INV-229).
- Secret values never enter views, state, plans, receipts, logs, fixtures or committed files.
- `key_event` remains the only key interpreter; there is one reducer and one persistent stdlib TUI.
- Machine state is assembled once outside draw functions; application projections have no IO/clock.
- When screens 41–47 land, local Candidate promotion must preserve D-096 local provenance instead of
  passing through the currently Git-only registry-index projection by disguise.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
