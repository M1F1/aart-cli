# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**, now at step 7: retiring legacy authority. Screen 53 is
live — the typed Candidate filter carries status, kind, Source and target registry, and `f` opens it
from screen 35 (D-111). Screens 48–50 are live: lifecycle uses exact history plus registry evidence, provenance retains typed
Git/local pins and compiler output, and immutable version conflicts require a new version
(D-108–D-110). Step 5 is complete: screens 41–47 are live, including a coherent bulk
transaction and truthful local Source provenance (D-107, closes B-041). Screens 41–44 review,
choose, plan and validate without writing; explicit confirmation on screen 45 is the first
Maintainer action that writes approved registry state, screen 46 reads the registry back, and screen
47 assembles a whole selection into one such transaction.

Screens 30–47 are live in the production shared shell:

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
  snapshot before and after, and the transaction digest. Git and local-source Candidates both reach
  this plan; their audit provenance uses distinct typed fields (D-107).
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
- a local filesystem Source now syncs, validates, promotes and commits through the live shell. Its
  audit is `local-snapshot` plus a typed SHA-256 snapshot digest, never a value squeezed into the
  legacy Git-revision field. Existing Git-only audit records remain readable (D-107, closes B-041).

Evidence: `tests/maintainer_candidate_shell_test.py`, `tests/maintainer_candidate_views_test.py`,
`tests/candidate_validation_test.py`, `tests/maintainer_validation_views_test.py`,
`tests/maintainer_composition_test.py`, `tests/maintainer_promotion_execution_test.py`,
`tests/maintainer_promotion_io_test.py`, `tests/maintainer_promotion_shell_execution_test.py`,
`tests/maintainer_registry_view_test.py`,
`tests/maintainer_bulk_promotion_test.py`, `tests/maintainer_bulk_transaction_test.py` and a
real temporary production installation in `tests/maintainer_composition_e2e_test.py`, which now
walks from the consumer dashboard through screen 45 and commits the promoted registry locally,
separately walks screen 47 to commit two Candidates as one transaction, and takes a real local
Source from sync through a typed-provenance promotion commit.

## Exact next action

CP-14 step 6 is complete, and step 7 has started: the legacy curses wizard shell is removed
(D-113). `_run_curses` and the two setup shims it alone called are gone, along with the seven tests
that existed only to drive it; `run()`, `_run_text` and the wizard's curses primitives stay. B-039
is partly closed. The acceptance evidence pre-existed — `run()` never reached `_run_curses`, and
ERR05 is pinned on the canonical `run()` by `tests/tui_fallback_boundary_test.py` — so no new test
was needed for the removal.

B-038's screen-21 half is closed too (D-114). Screen 21 was reachable and drawing nothing: nothing
on the composition path projected the configured sources, so a machine with a configured registry
opened on an empty list and a dashboard reading "0 registries". `read_consumer_offers` now carries
the projected rows, `screens_from` takes them, and a row that is not a registry says so and offers
`details` only instead of a sync whose advertised effect it cannot have.

Step 7 then found why it could remove nothing further: every remaining target —
`consumer/application.py`, `lifecycle/*`, `setup_engine/*`, and B-038's legacy direct-install from a
native Source — was reachable only through `_run_text`, which is built on
`ConsumerApplicationService` and through it on that whole stack. The blocker was a missing
replacement, not missing evidence. So the text route is now the canonical application:
`_TextTerminal` adapts the shell's two-method terminal port to `write`/`read`, `run()` composes once
for whichever terminal answers, and its entire legacy tail is gone (D-115). ERR05 permits a text
fallback for one condition — the terminal cannot host curses — and says nothing about the product
changing.

That unblocked the removal, which is done: `_run_text`, `_runtime_source_stage_context`,
`_dispatch_result` and the 26 further definitions that became unreferenced once it was gone are
deleted, with the tests that existed only to drive them — about 2,200 lines, and `tui.py` down from
5,705 to 4,262. Each removed test's capability was checked against a public flow first: scaffolding
against `aart registry scaffold`, source maintenance against the `aart source` commands, vendoring
against its flags half, ERR04's legacy install state against four other modules, ERR06 refusals
against the canonical shell's drawn notice (D-116).

**The exact next action** is the last of step 7. `ConsumerApplicationService` survives only because
the curses wizard *stages* still compose it (`_run_user_curses_wizard` and the widgets around it),
covered by 36 tests in `tests/tui_wizard_curses_test.py`. Retire those stages against the same
public-flow evidence, and `consumer/application.py` follows, and with it `lifecycle/*` and
`setup_engine/*`, which nothing else reaches. Note that `installation/*` is *not* purely legacy —
its model is imported across the canonical `application/` layer — so it goes by symbol rather than
by package, if at all. B-038's remaining half falls out of the same removal. Do not remove the text
*route*: no-TTY is a supported environment, and it is now the canonical application.

Behind it, step 6 left the surfaces complete: screen 53 is live (D-111) — the typed filter carries
all four facets the Product Specification names, `f` opens it from screen 35, `Space` toggles a
facet row, and screen 35 narrows accordingly — and screens 51–52 are reachable and proven end to
end, with `c` on screen 35 opening Collection Candidates and Enter resolving one against approved
registry state (D-112). What remains in CP-14:

1. **Step 7: retire the legacy consumer/maintainer authority CP-13 left standing** — but only
   behind the public-flow evidence D-091 requires, one route at a time. B-031's screens now exist
   and are reachable (D-112), so the Collection half of that evidence is in place. B-039's shell
   half is done (D-113) and B-038's screen-21 half is done (D-114); the semantic half of each is
   what remains.
2. Preserve D-089/B-037 whenever promotion planning is touched: retained approved records rebind to
   the transaction snapshot as metadata only, and published package bytes do not change.

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
- Local Candidate promotion preserves D-096 through the discriminated audit provenance in D-107;
  the legacy Git field accepts Git revisions only.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
