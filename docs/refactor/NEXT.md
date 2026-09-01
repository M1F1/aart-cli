# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 4: implement the Validation and Policy Review screens
38–40 over the Candidates screens 35–37 now expose.

Screens 30–37 are live in the production shared shell:

- screen 30 and screens 31–32 compose configured authoring Sources, durable health and only an exact
  matching Candidate-history observation (D-093–D-095);
- `s` on a focused Source enters typed screen-33 review, and Enter executes only its digest;
  execution rechecks registry and Source baselines, compiles exact `aart.yaml`/`aart.json`
  manifests, and atomically writes/rereads Candidate history under the Source instance lease;
- local Sources carry `local:<snapshot-sha256>` rather than invented Git commits (D-096), and
  screen 34 renders the persisted readback and reports no registry mutation (D-097, INV-200);
- screen 35 lists active Candidates keyed by stable Candidate ID and narrowed by the typed
  `MaintainerCandidateFilter`; screen 36 is the full authoring detail; screen 37 is semantic diff
  first with the bounded raw file diff behind the `f` toggle (D-098, INV-202).

Evidence: `tests/maintainer_candidate_shell_test.py`, `tests/maintainer_candidate_views_test.py`,
`tests/maintainer_composition_test.py` and a real temporary production installation in
`tests/maintainer_composition_e2e_test.py`, which now walks from the consumer dashboard to screen 37.

## Exact next action

Start RED tests for screens 38–40:

1. Project a validation run as an ordered pipeline of **named** checks over one Candidate, each
   carrying its own outcome, rather than a flat findings list. Screen 38 lists the checks a
   Candidate ran and how it stands; screen 39 is the detail of one named check.
2. Keep warnings and errors distinct all the way to the screen (164.6). An error is not a severe
   warning: `assess_candidate` already refuses to call a Candidate READY when any finding is an
   error, and the projections must not collapse the two into one severity column.
3. Make policy the thing that decides whether a warning blocks promotion, and make
   policy-required manual approval the explicit `CandidateState.APPROVAL_REQUIRED` state rather
   than an ordinary warning that a renderer treats specially. `domain/policies.py` and
   `assess_candidate(..., manual_approval_required=...)` are the existing seams; screen 40 shows
   which policy decided what.
4. Reach screens 38–40 from screen 36 through the shared reducer, from the composition already
   read once. Validation state is projected, never recomputed during drawing, and never inferred
   from a Candidate's state enum alone.

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
- Candidate list narrowing stays typed application state; screen 53 edits `MaintainerCandidateFilter`
  when it lands rather than introducing a second filter model (D-098).
- When screens 41–47 land, local Candidate promotion must preserve D-096 local provenance instead of
  passing through the currently Git-only registry-index projection by disguise.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
