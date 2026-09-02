# AART Refactor — Next Work

## Current objective

Continue **CP-14 Maintainer TUI 30–53**. Step 7, retiring legacy authority, is done apart from a
mechanical sweep; **B-044** is the critical work it uncovered. Screen 53 is
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

Step 7 then found why it could remove nothing further: everything it was aiming at was reachable
only through `_run_text`, which is built on `ConsumerApplicationService`. (The aim itself turned out
to be wrong — see D-117 below — but the blocker was real, and it was a missing replacement rather
than missing evidence.) So the text route is now the canonical application:
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

**The exact next action** is B-044, and step 7 is finished apart from one mechanical sweep.

The wizard front-end is gone (D-117): `_run_user_curses_wizard`, `_run_user_text_wizard`,
`_prompt_curation_request`, the `_curses_source_*` screens, and the 22 definitions that became
unreferenced once they were — 1,515 lines. `tui.py` is 2,747 lines, down from 5,705 when step 7
began. Two assertions the removed tests held alone were carried to the reachable surface first
rather than deleted with them: `registry init`'s default compatibility window, restated against the
CLI parser in `tests/registry_cli_test.py`, and the usage-report offer's consent-and-preview
boundaries, which had **no** CLI test at all and are now `tests/reporting_cli_offer_test.py`. Both
were verified red against the defect they exist to catch.

**Do not try to remove `consumer/application.py`, `lifecycle/*` or `setup_engine/*`.** This file
previously said nothing but the wizard reached them; that was wrong. `commands/marketplace.py` — the
public `aart marketplace install|update|uninstall|setup` — composes `ConsumerApplicationService`
directly and runs the setup queue through it, and `tui_marketplace.py`, which the canonical shell
imports, takes `LifecycleItem` and `InstallMode` from `lifecycle/model.py` and
`installation/model.py`. The stack is load-bearing for a public flow. Like `installation/*`, it goes
by symbol if at all, and not by package.

**B-044 was attempted and the attempt is preserved, not merged.** Codex began it and was cut off
mid-work by its own rate limit; the draft is on branch `codex-wip/b-044-draft` (`e40a80d`) with a
full review under B-044. The headline: **all 3,216 unit tests passed with it applied, while it
hardcoded `TrustClass.COMPANY_REVIEWED` into the setup policy check** -- the constant that makes
`_policy_allows`'s untrusted-source refusal unable to fire. Nothing in the suite exercises trust on
that route, which is the same blindness B-044 is about.

**The fixture and the characterization are now built, and they widen the item** (D-120). The
authoring format has no setup section at all — `setup` appears zero times in
`protocol/authoring.py` — so a declaration genuinely enters at packaging. `AuthoredSetup` and
`_with_setup` in `tests/configured_installation_draft_e2e_test.py` add it to the *compiled* package
(`artifact.json`'s `setup` reference, `setup/installer.json`, `SETUP.md`), recompile with
`compile_native_package`, and send the result through the whole real promotion transaction, so every
digest is derived rather than asserted. It is threaded through `_promote_one`,
`_published_registries`, `_published_registry` and `_environment(authored=..., setup=...)`, and
every existing caller is unchanged.

`tests/configured_setup_gap_test.py` is the characterization. Its first test guards the rest by
asserting the approved registry really does carry the declaration and its recipe; the other three
record the defect on **both** front ends.

**What it proved corrects D-118 and this file's earlier ordering.** `aart marketplace install` does
*not* carry setup for an approved registry coordinate: it reaches `_configured_lifecycle`, which
calls `complete_configured_installation` — the same seam `io/consumer_actions.py::_execute_installation`
uses — and reports `session_status: succeeded` with no `setup` key, no diagnostic, and the
configuration file the recipe declares unwritten. Setup runs only on the legacy path, which
`_configured_registry_selection` selects by returning `None` for a direct or local source. Nor is
there an operator recovery: `aart marketplace setup` afterwards refuses with `registry company has
invalid root manifests`, because it resolves through the legacy catalogue and a promoted registry
snapshot carries no root manifests.

So B-044 is one fix at one shared seam, not a TUI wiring gap. The Product Specification names
interactive setup as work AART performs and screens 09/11 summarize an install as "configured MCP
servers, isolated environments ... securely stored credentials", and neither shipped front end does
it. `_canonical_setup_run` and `_complete_canonical_consumer_action` are deliberately retained in
`tui.py` as the material (D-118); they take `ConsumerApplicationService`, `ConsumerReview` and
`ConsumerOutcome` and the canonical path has a receipt instead.

**The working route is proven too** (D-121). `marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest`
takes a declared setup through the CLI on a real machine over the legacy native-local-source route,
which nothing did before, and asserts all four gates on it: `install` names the setup it did not run,
an unreviewed source refuses without `--authorize-untrusted-source`, an authorized plan applies
nothing until its effects are separately approved, and both answers together write the delimited
managed block. It is `skipUnless(darwin)` because `setup.py:562` accepts only `['darwin']` recipes.
Applying the preserved draft's hardcoded `TrustClass.COMPANY_REVIEWED` fails two of the four — the
defect that passed 3,216 tests now has a test.

**The exact next step is the installed-record question**, which is what still blocks the green.
`setup_engine/application.py::_prepare_setup_object` resolves what to configure from the
install-state manifest (`.agent-artifacts/manifest.json`), which only `installation/application.py`
and `lifecycle/application.py` write, and which `io/consumer_machine.py` calls the *legacy* store —
a record it finds there with no canonical receipt becomes an `UnadoptedInstallation` (D-069). The
configured seam writes receipts. Two candidate answers, and the choice between them is an evidence
question, not a taste one:

**A canonical receipt cannot name the object that was installed.** This was measured, not
inferred: after `aart marketplace install` of the fixture Skill, `<data_root>/state/installations/*.json`
holds the coordinate (with version), `payload_digest`, `root` and the deliveries — and no object
digest and no manifest digest. `install_state`'s `ArtifactEvidence` carries all three. The engine
needs the object digest to `read_object` at all and the manifest digest to cross-check what it
compiled, so pointing it at the receipt store is not a matter of reading the same facts from a
different file: the facts are not there.

A second thing that measurement showed: the canonical seam registers **no CAS reference of any
kind** — there is no references file in the data root after a successful install — while the legacy
path registers `ReferenceKind.INSTALLED`. So the object a canonical install materialized from is
unrooted in the store. That is worth a look on its own account, independent of setup.

So the two candidate answers are:

- **Give the canonical receipt the object identity it is missing**, then widen the engine's object
  preparation to name an installed record from the receipt store. This is the honest fix for the
  finding above — a receipt that records what the effects left behind but not which immutable object
  they came from cannot support setup, and arguably cannot support a faithful repair either. It is a
  schema addition to a durable store, so it needs a compatible read of existing receipts. Note the
  other half of the cost: `persist_setup` (`setup_engine/io.py:89`) records that setup ran by taking
  the install-state lock, replacing the record's `setup_state_ref` and moving a CAS reference as one
  compensated unit, and `setup_receipt.locate_setup_record` reads that same pointer for
  `aart marketplace receipt show|verify|undo`. That half is anchored on the manifest too.
- **Have the configured installation also write the install-state record.** This does *not* make
  canonical installs surface as unadopted — `read_consumer_machine` drops a manifest record whose
  coordinate a canonical receipt already answers for (`io/consumer_machine.py:362`), so the
  objection previously recorded here was wrong — and the seam does hold every field truthfully at
  completion, including the `EffectProof` destinations and digests it planned and executed. It is
  the smaller change and the one that makes the whole existing setup subsystem work at once. It is
  also the one that writes new records into the store the strangler is trying to retire.

Every trust, evidence and policy check stays inside the engine either way; a third implementation of
the planning is what produced the hardcoded trust constant in the preserved draft.

Behind that, 571 lines of `tui.py` are still production-orphaned and held only by widget tests —
`_curses_multiselect` and its 29 tests, the receipt screens, `_load_user_wizard_read_model`,
`_curses_install_mode`, `_choice_pane`, `_basket_item`, `_canonical_consumer_source`. That sweep is
mechanical and unblocked; it must skip the two helpers B-044 holds. B-038's remaining half was also
restated: the direct-install residue is in `commands/marketplace.py::_configured_registry_selection`,
a public flow, not in the deleted wizard.

Behind it, step 6 left the surfaces complete: screen 53 is live (D-111) — the typed filter carries
all four facets the Product Specification names, `f` opens it from screen 35, `Space` toggles a
facet row, and screen 35 narrows accordingly — and screens 51–52 are reachable and proven end to
end, with `c` on screen 35 opening Collection Candidates and Enter resolving one against approved
registry state (D-112). What remains in CP-14:

1. **Step 7 is done except for one mechanical sweep.** The wizard front-end is removed (D-113,
   D-116, D-117) and B-039 is closed. What it aimed at beyond that — `consumer/application.py`,
   `lifecycle/*`, `setup_engine/*` — is load-bearing for `aart marketplace` and is not removed.
   B-038's screen-21 half is done (D-114) and its remaining half is restated as a `aart marketplace
   install` question. **B-044 (critical) is what the step actually leaves behind:** the canonical
   shell performs no post-install setup and offers no usage report.
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
