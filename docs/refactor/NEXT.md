# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, step 5: bulk promotion. Screens 41–47 are live. Screens
41–44 review, choose, plan and validate without writing; explicit confirmation on screen 45 is the
first Maintainer action that writes approved registry state, screen 46 is where a Maintainer reads
the registry back afterwards, and screen 47 assembles a whole selection into one such transaction.
Only B-041 (local provenance through promotion) still stands between this and a complete step 5.

Screens 30–46 are live in the production shared shell:

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
  place of the digest, and nothing here writes (D-101);
- screen 42 chooses the promotion mode with `m`. Both modes are composed once, so choosing one
  selects an already-projected review rather than making one while drawing, and the choice changes
  the review digest that would be confirmed (D-102);
- screen 43 shows the registry transaction a confirmed promotion would apply: the paths it would
  write and their change kinds (bounded at 200 rows, with the full count stated), the registry
  snapshot before and after, and the transaction digest. A Candidate from a local Source is refused
  by name here rather than deep inside the planner (B-041).
- screen 44 shows the already-composed validation of the projected registry, including the exact
  Candidate-validation and policy evidence that authorizes the promotion. Drawing it performs no
  reads, planning or writes;
- screen 45 shows the exact local write and deterministic commit subject. Confirmation refuses if
  the Candidate, synchronized approved baseline, checkout or screen-43 plan moved, and a real
  temporary checkout proves the write, readback validation and local Git commit while having no
  remote to push to (D-103);
- screen 46 reads the registry back: validity as the named check that every approved version carries
  a promotion approval record, artifact counts by kind, the approved snapshot and revision, the
  local checkout compared against it, and recent promotions ordered by walking the audit snapshot
  chain rather than by any clock (D-104). After a local commit the checkout is legitimately ahead of
  the synchronized approved snapshot and the working-tree line says so. Enter on screen 45 confirms
  only while an action is pending and otherwise continues to screen 46.
- screen 47 lists what one registry's bulk transaction may carry, because a transaction has exactly
  one target registry and Candidates scanned for another are not offered rather than refused after
  selection. Promotability is read off the run screens 38–40 showed, and a Candidate the run refused
  is named with its reason (D-105). `Space` selects, through the reducer's existing typed selection.
  `Enter` turns that selection into **one** transaction — one `plan_bulk_promotion`, one registry
  snapshot, one local commit — and hands it to screens 44 and 45, the same validation and commit
  screens a single promotion is reviewed on (D-106). Screen 47's one forward route is screen 44,
  not screen 43, because a bulk selection has no single-Candidate diff to open. Confirmation
  re-checks that the selection is still a subset of what screen 47 composed, and a promotion
  recomposes the Maintainer views afterwards because the commit moved the checkout.

Evidence: `tests/maintainer_candidate_shell_test.py`, `tests/maintainer_candidate_views_test.py`,
`tests/candidate_validation_test.py`, `tests/maintainer_validation_views_test.py`,
`tests/maintainer_composition_test.py`, `tests/maintainer_promotion_execution_test.py`,
`tests/maintainer_promotion_io_test.py`, `tests/maintainer_promotion_shell_execution_test.py`,
`tests/maintainer_registry_view_test.py`,
`tests/maintainer_bulk_promotion_test.py`, `tests/maintainer_bulk_transaction_test.py` and a
real temporary production installation in `tests/maintainer_composition_e2e_test.py`, which now
walks from the consumer dashboard through screen 45 and commits the promoted registry locally, and
separately walks screen 47 to commit two Candidates as one transaction.

## Exact next action

The bulk transaction is live and proven end to end: two ticked Candidates reach a real Git checkout
as one commit and one registry snapshot (`test_bulk_promotion_writes_both_candidates_in_one_commit`).
What remains before step 5 may be called complete:

1. **Resolve B-041.** Local-origin Candidates must keep their `local:<snapshot-sha256>` provenance
   through promotion rather than being disguised as Git commits. Give the promotion audit record a
   place for local provenance, then replace the by-name refusal in planning with supported
   provenance and restore the two direct refusal tests that were dropped with it. This is the last
   blocker on step 5.
2. Retained approved records must remain readable after a bulk transaction: rebind every retained
   record to the transaction's snapshot as metadata only, with published package bytes unchanged
   (D-089/B-037). Do not reintroduce a per-transaction rebind that leaves older versions
   unreadable.
3. Keep published coordinate/version content immutable: digest conflict is a refusal, never an
   in-place repair (INV-203/239), and superseded records remain durable audit history (INV-229).
4. Then step 6: screens 48–53, followed by step 7, retiring legacy authority only behind the
   acceptance evidence D-091 requires.

Noticed while proving the walk, not fixed here: screen 47 draws its "N selected" footer once of its
own and once from the shell chrome, so the count appears twice. Recorded in `BACKLOG.md`.

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
