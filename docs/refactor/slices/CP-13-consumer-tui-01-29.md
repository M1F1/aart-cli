# CP-13 — Consumer TUI 01–29
Status: IN PROGRESS (steps 1–4 VERIFIED; step 5 TTY migrated/public commands pending; step 6 open)

## Goal

Reuse the existing persistent stdlib/curses frontend while routing consumer-facing Marketplace,
install and installed-lifecycle behavior through the canonical CP-06–CP-12 models. Implement the
accepted screen catalog 01–29 with Fast as the default and Verbose as a projection of the same
selection, plan, state and outcome.

## Product Specification sections/invariants

Sections 149–163; INV-149–INV-168 and INV-169–INV-198, with the accepted screen catalog and
navigation map in sections 161–162.

## Legacy/current paths

- `tui.py` is a large but well-characterized text/curses wizard with shared selection widgets,
  search, basket persistence, Review/finalize separation, receipt views and maintainer routes.
- `tui_marketplace.py` projects the legacy/federated catalog with filters, compatibility, security
  and detailed evidence.
- `wizard.py` owns stage state and Back/quit/basket behavior.
- `consumer/application.py`, `installation/*`, `lifecycle/*` and `setup_engine/*` remain the public
  flag-command semantic path. The characterized legacy wizard remains the default TTY until the
  canonical shell has live lifecycle commands and preserves existing installed state (D-062).

## Target paths/owners

- `application/consumer_views.py`: immutable screen/view models projected only from canonical
  Selection, resolution, plan, input/reference, health, reconciliation and receipt values.
- `tui_consumer.py`: pure Fast/Verbose renderers and consumer navigation state.
- `tui.py`: imperative keyboard/curses shell and the strangler wiring to the canonical application
  services; no planning in drawing functions.

## Dependencies

CP-06 through CP-12 are verified; legacy TUI navigation/search/layout characterization is green.

## Screen coverage at slice start

| Accepted screen(s) | Existing evidence | Gap to canonical acceptance |
|---|---|---|
| 01 Dashboard | no dashboard; wizard opens with role/action stages | Add persistent consumer home, counts, attention and recent activity |
| 02 Marketplace | aggregated rows, search, filters and multi-select exist | Use canonical Selection/Collections; add Fast/Verbose toggle without intent mutation |
| 03 Artifact Details | technical marketplace pane/detail record exists | Add Fast outcome/input guidance and canonical Verbose provenance/requirements |
| 04/04A Collection | Collection row expands to members before legacy review | Add summary, contents selection and visible exact→custom semantic transition |
| 05 Review Selection | basket/review boundary exists | **DONE** `render_review_selection` names direct/Collection/derived selection and the unique resolved artifacts |
| 06 Automatic inspection | current wizard has manual source/profile/scope stages | **DONE** `render_inspection` reports requirement states and never asks; Verbose adds the measurement |
| 07 Required Inputs | legacy setup queue prompts per step | **DONE** `render_required_inputs` over the plan's inputs; an existing secret reads `Configured securely` |
| 08 Remediation | legacy authorize/setup choices exist | **DONE** `render_remediation` surfaces only the decisions and what will not be touched |
| 09 Ready | legacy review exists | **DONE** `render_ready` compresses to outcomes, names every risk and remediation, and discloses the same plan in Verbose (D-049) |
| 10 Installing | quiet vs step-by-step setup queue exists | **DONE** `render_progress` marks each component; the raw effect kind appears only in Verbose |
| 11 Success | command/setup outcomes exist | **DONE** `render_success` adds View installed / View receipt / Done |
| 12 Installed | status action filters installed rows | Add persistent health/ownership list for artifacts and Collections |
| 13 Artifact Details | legacy lifecycle/receipt details are separate | Combine canonical health, safe configuration/reference state and intents |
| 14 Collection Details | missing | **DONE** Installed lists Collections above artifacts; Enter opens whichever the cursor names |
| 15–17 Updates | legacy update action exists | **DONE** Updates lists only artifacts whose health is `update`; 16 reuses `render_required_inputs`, 17 `render_progress` |
| 18–19 Uninstall | legacy ownership-aware uninstall exists | **DONE** 18 draws `render_lifecycle_plan` (retention and why), 19 `render_progress` |
| 20 Verify/Repair | receipt verification exists; canonical repair core is uncalled | **DONE** draws the minimal `LifecyclePlanView` and its review identity |
| 21 Registries | Sources UI is mature but maintainer-oriented | Consumer availability/count/last-sync projection; sync never updates installs |
| 22–24 Credentials | missing | **DONE** reference rows with accepted health words (D-048), provider/consumers/actions detail, and an action screen that names what a removal would affect |
| 25–27 Activity | individual receipt view/undo exists | Add user-action timeline; keep technical receipt detail and capability-honest undo |
| 28 Settings | missing | Fast/Verbose preference, scope, update visibility, Maintainer Mode toggle |
| 29 Doctor | missing | Add navigation/summary entry; CP-16 owns full global implementation |

## Characterization / RED evidence

RED-first throughout. Each screen group failed on a missing projection or renderer before it
existed; three defects were found by tests rather than by reading:

- a partial desired state made a healthy component look unexpected (fixed in CP-11, D-033);
- a detail screen drew "Nothing is installed here" for an installed artifact, because loading it
  replaced the row set and the cursor no longer named anything (D-043);
- Enter could not reach the receipt behind an activity entry, because the source required a cursor
  row on a screen that has none.

## Implementation steps

1. Define canonical consumer navigation/profile/screen view models and Fast/Verbose projection.
   **DONE** — `application/consumer_views.py`, `application/consumer_ui.py`, `tui_consumer.py`.
2. Add Dashboard, Marketplace/artifact/Collection and install-flow projections. **DONE**.
3. Add Installed/update/uninstall/verify/repair projections over CP-11/12 state/outcomes. **DONE**.
4. Add Registries, Credentials, Activity, Settings and Doctor-entry projections. **DONE** —
   Activity/receipts (25–27) closed the last gap in the catalog.
5. Wire the persistent curses shell and public commands without duplicating planning.
   **PARTIAL** — the loop, the keymap and a canonical screen source exist and are driven headlessly
   (`run_consumer_shell`, `key_event`, `CanonicalScreenSource`); the curses adapter in `tui.py` is
   `_CursesTerminal` plus `run_consumer`. Every accepted screen 01–29 now draws from canonical
   views: Marketplace and Collections from offers (D-047), 05–11 from a `ConsumerPlanView`, 14–20
   from installed state and lifecycle views, 22–24 from credential records (D-048, D-049). A real
   machine is assembled once into a `ConsumerMachine` and turned into screens by `screens_from`
   (D-051), proven end to end from a real installation read back by a second process (B-024
   closed). The flow that produces a live plan now exists: `ConsumerFlow` holds an
   `InstallationProposal` with the review projected from it, `begin_installation` builds one and
   `record_installation` attaches what ran, refusing an outcome from a plan the flow never proposed
   (D-059). `PlannedInstallation` carries `declared`, so a review shows what somebody will be asked
   for rather than only what was already answered. `io/consumer_machine.py` now reads canonical
   durable records and fresh local observations once (D-060). A public routing attempt proved the
   missing boundary: the reducer cannot request lifecycle actions, the composed source has no
   configured Marketplace, and existing public installations live in the project/user manifest.
   The route was reverted under D-062 and B-025 remains open until those facts are addressed.
   **ACTION BOUNDARY DONE** — `ConsumerActionKind` and the reducer's `PREPARE_ACTION` /
   `EXECUTE_ACTION` commands now carry only Selection/focus and the exact prepared review identity.
   `key_event` is still the only key interpreter. `run_consumer_shell` crosses one injected handler
   boundary, observes the running screen before synchronous execution, replaces its immutable
   source from a matching prepared/recorded update, and fails closed if an action has no handler
   (D-063). A production handler is not connected yet: doing so by looping singular lifecycle
   recording would violate the one-transaction receipt contract, promoted as B-030.
5a. Persist canonical installed state and finished actions, so screens 12–16 and 25–27 have
   something to project between processes. **DONE** — `domain/receipts.py` gained the parse that
   inverts its own projection, `application/consumer_views.py` gained `receipt_detail_from_data`
   and `activity_from_receipts`, `io/receipt_store.py` is the managed store, and
   `application/receipt_recording.py` decides what a finished action leaves in it (B-026 closed;
   D-044, D-045, D-046).
6. Retire legacy semantic authority only after equivalent public-flow/E2E evidence. **NOT STARTED**
   — blocked on step 5 by design; no legacy authority has been removed.

`tests/consumer_session_test.py` — the assembly rules nothing else can decide: an installed record
becomes a row whose health is measured rather than assumed from the record existing, artifacts a
Collection owns aggregate into that Collection, a credential's dependants are the installations
whose receipts name it, one nothing uses is still listed owing nothing and offering delete, an
unresolvable credential is counted as needing attention, and an empty machine is an empty machine
rather than an error.

## Property tests

`tests/consumer_properties_test.py` — over generated canonical install plans, input mixes and
timelines: profile switching never changes Selection, machine projection or review digest; Fast
names every risk the plan carries and every remediation decision; no arrangement of inputs gives a
credential a value field; exact Collection and customized selection never share an identity; a
timeline reads newest-first and loses nothing.

## Integration tests

`tests/consumer_interaction_test.py` — real terminal key codes, named the way the curses adapter
names them, through the reducer: arrows/vi keys, Space selection, Enter into details, Esc back,
`/` search (including that `q` types a q while the filter is open), `v` disclosure, `?` help, and
the quit prompt where only the answer keys act.

`tests/consumer_shell_test.py` — the persistent application driven through its own loop with a
scripted terminal: rows load per screen, filters narrow and restore them, details stay about the
row they were opened from, and `v` redraws the same screen with more disclosed.

`tests/consumer_ui_actions_test.py` and `tests/consumer_action_shell_test.py` — accepted action
transitions now have RED→green evidence: Marketplace `i` prepares the whole Selection; empty or
invalid-context actions do nothing; a prepared review identity is the only identity Ready may
execute; Installed emits typed repair/uninstall requests; a recorded install clears Selection and
opens Success. The real persistent loop swaps in the prepared and recorded snapshots supplied by
one injected handler, draws Installing before crossing the execution boundary, rejects mismatched
handler responses and fails closed when the handler is absent.

`tests/consumer_machine_read_test.py` and `tests/tui_consumer_entry_test.py` — a second process reads
the whole machine from durable records, detects missing runtime and launcher state, preserves an
uninspectable credential as unknown, and fails on an unreadable receipt. The composition helper
passes the managed state and harness roots correctly, while bare TTY remains on the characterized
wizard until the canonical shell can execute actions without hiding existing installs (D-060,
D-062).

`tests/consumer_marketplace_shell_test.py` — screens 02–04a over a real built marketplace: the list
holds artifacts and Collections together, Enter opens the right screen for whichever the cursor is
on, a Collection preview lists its members as its rows, unticking one makes the selection custom
with an identity of its own, and re-ticking every member is the exact Collection again.

`tests/consumer_install_flow_shell_test.py` — screens 05–11 and 14–24, reached by walking the
accepted navigation map from the Dashboard rather than by handing a state to a renderer: no screen
in the catalog is still unavailable, inspection reports without asking, Required Inputs says
`Configured securely` and never the word value, Ready compresses outcomes while Verbose discloses
the same plan, progress is meaningful until Verbose names the effect kind, Updates lists only what
has one, a credential is a reference view with an action screen that names what a removal would
affect, and an installed Collection aggregates its members.

`tests/receipt_recording_test.py` — what a finished action leaves behind, over real reviewed plans
and a fake store: every action reaches the timeline including the ones that failed, an install that
took effect is recorded even when it did not finish, one that took no effect leaves the store
untouched, a completed uninstall forgets rather than rewrites, an interrupted one keeps the record
that describes its residue, and a rolled-back update leaves the previous record standing.

`tests/receipt_store_test.py` — persistence across a process boundary, including that ownership is
recorded beside the receipt, that a rewrite which says nothing about ownership keeps the owners the
record had, that one saying nobody owns it means it, and that an ownership kind this build cannot
name is refused rather than dropped (D-050): a receipt written down and
read back is the receipt that was written, including a credential reference whose service and
account contain the separators its printed form uses; six malformed documents are refused rather
than guessed at; records are private (0o600), replaced rather than duplicated, forgotten
individually; a corrupt record is reported rather than silently skipped; and a timeline rebuilt
from disk reads the same as the one projected in memory.

`tests/installation_transaction_receipt_test.py` — one reviewed Selection becomes one durable
record. A two-artifact transaction produces one Activity receipt naming the Selection and both
members, round-trips through the stored document and rebuilds a single timeline entry, and writes
one installed record per member. The refusals are the point: a member that applied and has no
receipt is refused rather than forgotten, the same artifact cannot be given two receipts, a member
that applied is still recorded when a later member fails, a member that never ran stays named as
`not-attempted`, and a transaction nobody finished cannot be undone.

## E2E/live acceptance

`tests/artifact_installation_e2e_test.py` — the authored package of D-056/D-058, drawn. The same
run that installs a compiled and published artifact is read out of the running consumer shell by the
accepted navigation routes: 05 names the coordinate, 06 the four requirements this machine measured,
07 the two declared inputs with the secret shown as configured and no value anywhere, 09 the risks
and the review identity, and 11 the install that actually ran. None of them says "Nothing has been
planned yet", and the real secret appears on none of them.

`tests/consumer_session_e2e_test.py` — nothing is handed a view. A real installation is recorded
with who asked for it; a second process reads that record back, inspects the machine, assembles it
once and draws the screens. The Dashboard counts what is really installed and opens with what just
happened, Installed names the Collection and the artifact, a launcher broken afterwards is what the
screen and the Doctor say, the Collection's health is its members', Credentials names the
installation that depends on it, and no screen this machine draws contains the real secret.

`tests/consumer_flow_e2e_test.py` — the CP-12 real installation (owned interpreter, generated
launcher, harness entry, provider-held credential), seen through the consumer screens: Installed
reads ready → the launcher is broken on disk → Installed reads broken and names only the launcher →
Verify/Repair shows the minimal plan and one identity → the repair runs through real interpreters →
the server answers again through its own launcher → the Activity entry and its receipt explain
honest undo → uninstall is ownership-aware and retains the credential. One test renders every
consumer surface and asserts the real secret appears on none of them.

`tests/receipt_persistence_e2e_test.py` — the same real installation, then nothing in memory is
trusted. A second process reads the owners off disk, releases only the direct request and the real
MCP server still answers through its own launcher; releasing the last owner removes both the
artifact and the record; and repairing an artifact does not release the Collection that owns it.
Also: a second store built fresh over the same directory reads the receipt back off disk, and
the desired state, the review digest, the repair of a launcher broken after the write, the timeline
and the uninstall are all decided from that read-back receipt. The server answers again through its
own launcher after a repair planned from disk alone, and no stored file contains the real secret.

## Done

- Canonical screen contract re-read; existing TUI and test surfaces inventoried above.
- All 29 accepted consumer screens have canonical projections and Fast/Verbose renderers.
- Activity/receipts (25–27) implemented, including capability-honest undo (D-040).
- Pure keymap and cursor/search/focus interaction state (D-041, D-042, D-043).
- Persistent application loop over injected ports, with a curses adapter that is `draw` + `getch`.
- Property, keyboard-integration, headless-shell and real-installation E2E evidence, above.
- Canonical persistence for installed state and finished actions, with a producer in a real
  reviewed, scope-locked flow (B-026 closed; D-044, D-045, D-046).
- The bridge step 5 was missing: `application/installation_proposal.py` lowers one
  `PlannedInstallation` into both the `InstallPlan` a person reviews and the `LifecyclePlan`s that
  run it, deriving the review from a real reconciliation so a credential already present and wrong
  is replaced rather than stored, and refusing to construct when the two disagree (D-052). The
  payload became a component an install establishes and a repair can keep (D-053). Proven end to
  end: an empty machine, one reviewed plan, and a server that afterwards answers its harness
  through its own generated launcher, with the receipt read back by a second store.
- The write half of the manifest -> install-description step: `protocol/authoring.py` reads the §91
  `inputs` array and the §107/§108 `python.dependencies` descriptor, so an author's declarations
  survive compilation as `RuntimeInput` and `PythonDependencySpec` values. Every one is built
  through the domain constructor and its refusal is reported as a manifest diagnostic, so a secret
  with a default, guidance carrying a plausible example credential, or an environment variable
  written as an assignment is refused by the rule that already existed rather than by a second copy
  of it (D-054). A manifest naming an entrypoint, descriptor or lock its payload does not ship is
  refused at compile time (D-055).
- The read half, which closes the gap: `InstallDescription` holds what an artifact declares and
  nothing about any machine; `read_install_description` reads it back out of a compiled package's
  `aart.authoring` extension with the parsers that wrote it; and
  `application/artifact_installation.py` joins it to a root, an interpreter, input value sources,
  harness targets and a policy to produce the `PlannedInstallation` D-052 lowers (D-056). Proven
  end to end from an author's repository: compiled, written to a store as bytes, read back by a
  process that has not seen the repository, installed, and answering its harness afterwards with
  the arguments, the configuration value and the launch-time secret the manifest declared. The
  package travels through the content-addressed object store on the way, and a package that never
  recorded what it needs is refused rather than read as needing nothing (D-058).
- A defect that first install surfaced: the `runtime-dependencies` component was never observed, so
  every healthy artifact with dependencies reported unobserved drift forever. It is now reported
  through the environment that holds it, with the observation saying what it did not check (D-057,
  B-029).
- New receipts remember the base interpreter needed to inspect runtime health after restart while
  old receipts remain readable (D-060), and the composition helper builds one machine from durable
  receipts, actions and local inspection. The attempted default route was reverted when
  characterization showed the shell is not yet an actionable replacement (D-061, D-062).

## Remaining

- Aggregate the proposal's lifecycle executions and record one transaction receipt (B-030), then
  implement the production action handler over `begin_installation`, CP-12 execution, durable
  recording and machine reload.
- Compose configured Marketplace and preserve/adapt existing kind-neutral project/user install
  state before retrying the default route.
- Route public commands through the same handler/application boundary.
- Step 6: retiring legacy consumer semantic authority, once the above give equivalent public-flow
  evidence.

## Known compromises

- The install flow's screens draw "Nothing has been planned yet." only when no flow is held. A flow
  now exists and is drawn end to end, but no public entry point starts one: the E2E supplies it, a
  command does not yet. The fallback line for a screen with no body at all is kept as a guard
  against drawing a blank frame; no accepted screen reaches it.
- `PlannedInstallation.declared` is checked against what is bound only when it is recorded. A plan
  built without it keeps the old behavior rather than failing, which is what let the field be added
  without rewriting every construction site; the one that matters is filled by
  `plan_artifact_installation` from the package's own description.
- The canonical shell now emits and transports install/update/repair/uninstall action requests, but
  its current composition has no production handler, configured Marketplace offers or adapter for
  existing project/user installation records. The singular lifecycle receipt cannot be used as the
  bulk transaction receipt (B-030). The legacy public entry remains until those replacement facts
  are proven (D-062, D-063).

## Backlog discoveries

- B-024 — Marketplace and install-flow screens for the canonical consumer shell. **Closed**: every
  accepted screen draws from canonical views and a real machine assembles into them.
- B-025 — Routing the default TTY entry to the canonical consumer application. **Open** after the
  first route exposed missing action, Marketplace and existing-state boundaries (D-062).
- B-026 — Canonical installation-receipt persistence. **Promoted to the critical path and
  completed**: B-024 cannot assemble Installed, Updates or Activity over a machine whose canonical
  state does not survive a process, and step 6 cannot retire legacy authority whose remaining
  advantage is that it persists.
- B-027 — Poetry-locked artifacts have no installer backend, so `type: poetry` is refused by name
  rather than approximated by installing the loose project the lock exists to prevent.
- B-028 — Cross-checking an input's binding against the transport at authoring time. Deliberately
  declined: the launcher generator is the single authority on what a binding can deliver (D-023,
  D-024), and a second copy of that rule in the parser would be the one nobody updates.
- B-029 — Verifying installed distributions against the declared descriptor, rather than reporting
  dependencies through the environment that holds them (D-057).
- B-030 — Aggregate installation execution and one transaction receipt. **Promoted to CP-13:** the
  production handler cannot fragment one reviewed Selection into N actions without violating
  INV-130/INV-138.

## Blockers

None.

## Legacy removal criteria

Legacy consumer planning/setup/lifecycle authority is removable only when public text/curses and
machine-output tests prove every accepted flow now consumes the canonical application models.

## Handoff

- Current working state: steps 1–4 complete and verified; step 5 has a durable machine reader,
  action-capable reducer and an injected/fail-closed shell boundary, but no production handler;
  step 6 has not started. The legacy wizard and command authority remain public by design (D-062,
  D-063).
- Exact next action: implement B-030's aggregate execution/receipt with single-and-bulk tests, then
  use it in the production handler. Compose configured Marketplace and preserve existing
  project/user install records before retrying B-025 and routing public flag commands one seam at a
  time.
- Do not undo: existing curses layout/search/basket/back/quit characterization; one semantic plan
  for both profiles; Maintainer Mode remains opt-in; `key_event` stays the only place a key's
  meaning is decided; no clock in `application/`.
- Tests last run/results: 2,484 unit + 101 E2E tests, 83.44% coverage, all ten quality gates green
  (`make quality PYTHON=python3`). CP-12 baseline was 2,196 unit + 65 E2E at 83.25%.
- Failure evidence: three defects found by tests are listed under Characterization / RED evidence.
