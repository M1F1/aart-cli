# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 5: promotion and the registry write path. Screen 41
is live and refuses what the review refused; screens 42–47 — mode, registry diff, registry
validation, commit and bulk promotion — are what remain, and they are the first Maintainer screens
that write approved registry state.

Screens 30–41 are live in the production shared shell:

- screen 30 and screens 31–32 compose configured authoring Sources, durable health and only an exact
  matching Candidate-history observation (D-093–D-095);
- `s` on a focused Source enters typed screen-33 review, and Enter executes only its digest;
  execution rechecks registry and Source baselines, compiles exact `aart.yaml`/`aart.json`
  manifests, and atomically writes/rereads Candidate history under the Source instance lease;
- local Sources carry `local:<snapshot-sha256>` rather than invented Git commits (D-096), and
  screen 34 renders the persisted readback and reports no registry mutation (D-097, INV-200);
- screen 35 lists active Candidates keyed by stable Candidate ID and narrowed by the typed
  `MaintainerCandidateFilter`; screen 36 is the full authoring detail; screen 37 is semantic diff
  first with the bounded raw file diff behind the `f` toggle (D-098, INV-202);
- screens 38–40 project one validation run per active Candidate: screen 38 lists every named check
  with its own outcome, Enter opens screen 39 for one check with its declared and expected values,
  and `p` opens screen 40, which says which policy decided what. Rows are
  `"<candidate-id>:<check>"` pairs and the policy judgement travels with the run rather than being
  re-derived while drawing (D-099, D-100);
- screen 41 reviews what promoting one Candidate would write: the target registry and its baseline,
  the mode, the digests of the validation report and effective policy that the audit record will
  carry, and a review digest binding all of it. A Candidate the run refused shows the refusal in
  place of the digest, and nothing here writes (D-101).

Evidence: `tests/maintainer_candidate_shell_test.py`, `tests/maintainer_candidate_views_test.py`,
`tests/candidate_validation_test.py`, `tests/maintainer_validation_views_test.py`,
`tests/maintainer_composition_test.py` and a real temporary production installation in
`tests/maintainer_composition_e2e_test.py`, which now walks from the consumer dashboard through the
diff into validation and out to the policy review.

## Exact next action

Start RED tests for the promotion write path, screens 42–45:

1. Screen 42 chooses the promotion mode. The mode is already inside the review digest (D-101), so
   changing it must produce a different review to confirm, not silently reuse the previous one.
2. `execute_candidate_promotion` applies exactly one reviewed promotion, the way
   `execute_source_sync` does: it rechecks the reviewed digest, the Candidate state and the approved
   registry baseline before writing, and refuses if any of them moved. `plan_bulk_promotion`,
   `project_promotion` and `finalize_promotion` in `application/promotion.py` already exist and are
   what should be driven — do not write a second planner.
3. Screen 43 is the registry diff the plan produces, screen 44 its validation and screen 45 the
   commit. `validate_promoted_registry` already exists for screen 44.
4. Published coordinate/version content is immutable: a digest conflict is reported, never repaired
   in place (INV-203/239), and superseded records stay durable audit history (INV-229).
5. Local-origin Candidates must keep their `local:<snapshot-sha256>` provenance through promotion
   rather than passing through the Git-only registry-index projection by disguise (D-096). This is
   the piece most likely to be got wrong quietly.
6. Bulk promotion (screen 47) rebinds every retained approved record to the snapshot its own
   transaction produces, as metadata only, with the published package proven byte-identical — the
   defect B-037 fixed. Do not reintroduce a per-transaction rebind that leaves older versions
   unreadable.

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
