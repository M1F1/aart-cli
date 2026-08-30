# CP-13 — Consumer TUI 01–29
Status: IN PROGRESS (steps 1–4 VERIFIED; step 5 partial; step 6 open)

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
  semantic path; CP-06–CP-12 are not yet the TUI's authority.

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
| 05 Review Selection | basket/review boundary exists | Project CP-06 ownership/resolution and unique counts |
| 06 Automatic inspection | current wizard has manual source/profile/scope stages | Run CP-07 inspection automatically when no decision exists |
| 07 Required Inputs | legacy setup queue prompts per step | Aggregate CP-08 input models, reuse valid config and show secret references only |
| 08 Remediation | legacy authorize/setup choices exist | Project capability∩policy remediations only when a decision is required |
| 09 Ready | legacy review exists | Render concise/verbose projections of one immutable plan and one digest |
| 10 Installing | quiet vs step-by-step setup queue exists | Project canonical component/effect progress and partial/interrupted outcomes |
| 11 Success | command/setup outcomes exist | Add outcome actions and canonical execution receipt link |
| 12 Installed | status action filters installed rows | Add persistent health/ownership list for artifacts and Collections |
| 13 Artifact Details | legacy lifecycle/receipt details are separate | Combine canonical health, safe configuration/reference state and intents |
| 14 Collection Details | missing | Aggregate member health and name attention members |
| 15–17 Updates | legacy update action exists | Multi-select canonical update intents, new inputs and restoration outcome |
| 18–19 Uninstall | legacy ownership-aware uninstall exists | Route through CP-12 absent desired state; explain retained artifacts/credentials |
| 20 Verify/Repair | receipt verification exists; canonical repair core is uncalled | Surface minimal CP-11 diff and execute reviewed CP-12 repair |
| 21 Registries | Sources UI is mature but maintainer-oriented | Consumer availability/count/last-sync projection; sync never updates installs |
| 22–24 Credentials | missing | Reference/provider/health/dependants views and governed verify/replace/delete |
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
   `_CursesTerminal` plus `run_consumer`. Screens 02–11 and 15–24 have projections but no assembled
   service wiring (B-024), and `run()` still opens the legacy wizard (B-025).
5a. Persist canonical installed state and finished actions, so screens 12–16 and 25–27 have
   something to project between processes. **DONE** — `domain/receipts.py` gained the parse that
   inverts its own projection, `application/consumer_views.py` gained `receipt_detail_from_data`
   and `activity_from_receipts`, `io/receipt_store.py` is the managed store, and
   `application/receipt_recording.py` decides what a finished action leaves in it (B-026 closed;
   D-044, D-045, D-046).
6. Retire legacy semantic authority only after equivalent public-flow/E2E evidence. **NOT STARTED**
   — blocked on step 5 by design; no legacy authority has been removed.

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

`tests/receipt_recording_test.py` — what a finished action leaves behind, over real reviewed plans
and a fake store: every action reaches the timeline including the ones that failed, an install that
took effect is recorded even when it did not finish, one that took no effect leaves the store
untouched, a completed uninstall forgets rather than rewrites, an interrupted one keeps the record
that describes its residue, and a rolled-back update leaves the previous record standing.

`tests/receipt_store_test.py` — persistence across a process boundary: a receipt written down and
read back is the receipt that was written, including a credential reference whose service and
account contain the separators its printed form uses; six malformed documents are refused rather
than guessed at; records are private (0o600), replaced rather than duplicated, forgotten
individually; a corrupt record is reported rather than silently skipped; and a timeline rebuilt
from disk reads the same as the one projected in memory.

## E2E/live acceptance

`tests/consumer_flow_e2e_test.py` — the CP-12 real installation (owned interpreter, generated
launcher, harness entry, provider-held credential), seen through the consumer screens: Installed
reads ready → the launcher is broken on disk → Installed reads broken and names only the launcher →
Verify/Repair shows the minimal plan and one identity → the repair runs through real interpreters →
the server answers again through its own launcher → the Activity entry and its receipt explain
honest undo → uninstall is ownership-aware and retains the credential. One test renders every
consumer surface and asserts the real secret appears on none of them.

`tests/receipt_persistence_e2e_test.py` — the same real installation, then nothing in memory is
trusted: a second store built fresh over the same directory reads the receipt back off disk, and
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

## Remaining

- Step 5 service wiring for screens 02–11 and 15–24 (B-024).
- Routing the default TTY entry to the canonical application (B-025).
- Step 6: retiring legacy consumer semantic authority, once the above give equivalent public-flow
  evidence.

## Known compromises

- Screens 02–11 and 15–24 draw an explicit "… is not available yet" line in the canonical shell
  rather than silently drawing an empty screen. Their projections exist and are tested; only the
  live service assembly is missing (B-024).
- `run_consumer` is reachable by embedders and tests but is not yet the default TTY entry (B-025).
  No legacy behavior has been changed or removed to make room for it.

## Backlog discoveries

- B-024 — Marketplace and install-flow screens for the canonical consumer shell.
- B-025 — Routing the default TTY entry to the canonical consumer application.
- B-026 — Canonical installation-receipt persistence. **Promoted to the critical path and
  completed**: B-024 cannot assemble Installed, Updates or Activity over a machine whose canonical
  state does not survive a process, and step 6 cannot retire legacy authority whose remaining
  advantage is that it persists.

## Blockers

None.

## Legacy removal criteria

Legacy consumer planning/setup/lifecycle authority is removable only when public text/curses and
machine-output tests prove every accepted flow now consumes the canonical application models.

## Handoff

- Current working state: steps 1–4 complete and verified; step 5 partial; step 6 not started. The
  legacy wizard is untouched and still owns the default TTY entry.
- Exact next action: B-024 — assemble one `ConsumerScreens` builder over the canonical services,
  reading installed state and the timeline from `LocalReceiptStore`, so the shell can draw
  Marketplace and the install flow — then B-025 to route `run()`.
- Do not undo: existing curses layout/search/basket/back/quit characterization; one semantic plan
  for both profiles; Maintainer Mode remains opt-in; `key_event` stays the only place a key's
  meaning is decided; no clock in `application/`.
- Tests last run/results: 2,309 unit + 80 E2E tests, 83.25% coverage, all ten quality gates
  green (`make quality`). CP-12 baseline was 2,196 unit + 65 E2E at 83.25%.
- Failure evidence: three defects found by tests are listed under Characterization / RED evidence.
