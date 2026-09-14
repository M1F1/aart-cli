# TODO

> [!WARNING]
> Historical record of the completed `M1F1/agent-artifacts` 1.0 program, kept as evidence. It is
> preserved below and its GitHub issues are not this repository's. The first section of this file
> is now the current manual-acceptance list for `aart-cli`; it is a test/fix queue, **not** product
> authority.
> Current authority is [`docs/product-specification/PRODUCT_SPECIFICATION.md`](docs/product-specification/PRODUCT_SPECIFICATION.md),
> and the active work is tracked in [`docs/refactor/NEXT.md`](docs/refactor/NEXT.md).

## Current `aart-cli` manual-acceptance TODO

This is the single list for problems found while walking the real Registry → Marketplace →
Install → Update → Repair → Uninstall scenario. New findings go into **Open** immediately. A fix
moves to **Fixed — awaiting manual retest** and is checked only after the operator reproduces the
original steps and confirms the result.

The repeatable procedure and stage checkpoints are in
[`docs/testing/END_TO_END_ACCEPTANCE.md`](docs/testing/END_TO_END_ACCEPTANCE.md).

Each new entry records:

- the screen or public command;
- exact reproduction steps;
- expected and observed behavior;
- severity (`blocking`, `high`, `medium`, or `low`);
- whether it blocks the current end-to-end stage;
- the fixing commit once accepted.

### Fixed — awaiting manual retest (CP-20)

- [ ] **QA-044 — Registry Maintainer contradicts the connected Registry with local-project state.**
      Surface: Registry Maintainer. Severity: high. The frame can show a valid connected Registry
      and then say there is no Registry to rebuild because it silently switches subjects to the
      current project; its remediation also leaks the internal name `Screen 46`. Expected: label
      connected Registry snapshots and the local Registry workspace separately, name the current
      project explicitly, and offer `Initialize Registry` without any internal screen identifier.
      CP-20 step 2 owns the fix and manual retest.
      Fix: connected snapshots and the local Registry workspace now have separate labelled blocks;
      an absent local marker names the current project and offers Initialize Registry in product
      language. Evidence: `tests/cp20_tui_clarity_test.py`, `tests/maintainer_registry_view_test.py`.

- [ ] **QA-045 — Doctor exposes an internal screen identifier as the repair subject.**
      Surface: Doctor/Automatic Inspection. Severity: high. `nothing canonical is installed here
      as 29-doctor` is implementation-state leakage, not a diagnosis. Expected: repair/reload uses
      the visibly focused installed coordinate and never renders a route identifier. CP-20 step 2.
      Fix: Doctor repair is row-owned and refuses when no visible repairable issue is focused.
      Evidence: `tests/cp20_tui_clarity_test.py`, `tests/consumer_navigation_test.py`.

- [ ] **QA-046 — Automatic Inspection presents inconclusive harness observations as a failed quiz.**
      Surface: Fast installation workflow. Severity: high. A page showing `0 of 4` and four
      `unknown` harness requirements asks for no decision and reads like failure immediately before
      a successful install. Expected: inspection still builds the immutable plan, but Fast mode
      advances directly to the first genuinely required input/remediation decision or Ready.
      CP-20 step 2.
      Fix: inspection still contributes to the immutable plan, while Fast mode advances directly
      to Required Inputs, Remediation or Ready. Evidence: `tests/consumer_install_flow_shell_test.py`.

- [ ] **QA-047 — Success requires backing out of a completed installation wizard.**
      Surface: installation Success. Severity: high. Expected: Enter on Done completes the wizard
      and returns directly to Marketplace; View installed and View receipt remain explicit choices.
      CP-20 step 2.
      Fix: Success binds Enter/Done to Marketplace without changing its explicit detail routes.
      Evidence: `tests/consumer_navigation_test.py`, `tests/consumer_application_e2e_test.py`.

- [ ] **QA-048 — Section rules and Settings groups run together vertically.**
      Surface: shared section layout and Settings. Severity: medium. Expected: one blank line on
      both sides of section text, one blank between Settings groups, and one blank before the
      Maintainer Mode explanatory sentence. CP-20 step 2.
      Fix: the shared section primitive owns blank lines on both sides, and Settings renders its
      groups as separate blocks. Evidence: `tests/tui_layout_test.py`, `tests/consumer_views_test.py`.

- [ ] **QA-049 — The manual MCP cannot exercise credential input and management.**
      Surface: disposable manual acceptance fixture. Severity: high. Expected: the fixture
      publishes an installable dummy MCP with a declared safe test credential, drives the required
      input/credential views, and never commits or prints the supplied value. CP-20 step 4.
      Fix: the disposable Registry publishes `dummy-mcp@1.0.0` with required `dummy-token`; only a
      provider reference is planned and the server reports presence, never content. Evidence:
      `tests/manual_test_lab_test.py`, `tests/configured_installation_action_e2e_test.py`.

- [ ] **QA-050 — A connected Registry cannot be disconnected from Marketplace in the TUI.**
      Surface: Registries. Severity: high. Expected: the focused Registry has a reviewed Disconnect
      action that removes its connection and AART-managed snapshot, clears it as default if needed,
      and leaves installed artifacts and receipts untouched. CP-20 step 3.
      Fix: `d` opens an exact origin/ref review and confirmation rechecks the source identity before
      removing configuration and its managed snapshot. Evidence: `tests/consumer_registry_disconnect_test.py`.

- [ ] **QA-051 — Manual acceptance inherits repositories and app state from earlier runs.**
      Surface: manual-test setup. Severity: blocking for reproducible acceptance. Expected: one
      command builds a fresh lab with new clones, isolated HOME/XDG, a unique `manual/<run-id>`
      branch in every repository and all prerequisites; one reset command deletes only that
      marker-owned local lab. GitHub-specific passes use the same unique branch namespace in
      dedicated test repositories and never reset/force-push shared branches; remote cleanup is a
      separate exact reviewed action. CP-20 step 5.
      Fix: `make manual-test-setup` creates three fresh working repositories and local bare remotes
      under isolated homes; `make manual-test-reset` deletes only the exact marker-owned root.
      Evidence: `tests/manual_test_lab_test.py` and a real setup/reset smoke.

- [ ] **QA-052 — AART has no safe command-line factory reset.**
      Surface: CLI administration. Severity: high. Expected: a CLI-only reset lists exact AART-owned
      configuration/data/cache targets, requires two deliberate confirmations, refuses unsafe
      targets, restores the app to no connections/settings, and leaves projects, harness files,
      other applications' credentials and unrelated files untouched. CP-20 step 6.
      Fix: CLI-only `aart reset` lists the exact plan/digest, requires `RESET AART` and
      `DELETE AART STATE`, and refuses unsafe/symlinked targets before deleting anything.
      Evidence: `tests/factory_reset_test.py` including Hypothesis target properties.

- [ ] **QA-053 — No screen says which directory the session was launched from.**
      Surface: every canonical shell frame. Severity: medium. Reproduction: launch `aart` from any
      directory and read any screen. Observed: nothing on the frame names the directory, so an
      install or a Registry edit gives no way to tell whether it is about to land in a manual-test
      lab or in the real project. Expected: the frame names the launch directory as persistent
      chrome, on every screen. Blocks the end-to-end stage: no.
      Fix: the composition boundary resolves the launch directory once, the state carries it, and
      the frame prints `Working in <path>` directly under the heading; home is written `~` and an
      over-long path drops leading segments so the directory's own name always survives.
      Evidence: `tests/workspace_context_line_test.py`, including a Hypothesis property that a
      shown path is bounded and keeps its final segment.

- [ ] **QA-054 — The manual acceptance procedure tests the CLI, not the TUI.**
      Surface: `docs/testing/END_TO_END_ACCEPTANCE.md` and the manual lab. Severity: medium.
      Observed: stages 1-3 are entirely CLI and GitHub setup, stage 4 adds author Sources through
      the CLI although adding a Source is itself a Maintainer screen, and the CP-20 head advertising
      `make manual-test-setup` was never reconciled with a body that still exports
      `$AART_MAINTAINER_HOME`. The default lab also publishes both fixtures, so the whole Maintainer
      run — Initialize Registry, Add Source, Sync, Candidates, validation, promotion, commit — is
      already done by the setup script and an operator walking those screens re-reads a result
      instead of producing one. Expected: a TUI-first walkthrough over a Registry that starts empty.
      Blocks the end-to-end stage: no.
      Fix: `make manual-test-setup-empty` builds the lab with the author sources published and the
      Registry repository empty, and `docs/testing/TUI_MANUAL_WALKTHROUGH.md` walks both roles
      through the screens, naming the one `git push` the TUI deliberately does not do (161.7).
      Evidence: `tests/manual_test_lab_test.py`, plus a driven text-TUI run reaching
      `[n] Initialize` on the empty Registry.

### Open

#### CP-23 — fourth manual TUI run (2026-09-14)

PLANNED. The complete tasks, evidence requirements and acceptance criteria are in
[`CP-23`](docs/refactor/slices/CP-23-actionable-tui-workflows.md); `docs/refactor/plan.json` is the
machine-readable task list. No product fix is claimed by creating this plan.

- [x] 01 — Explain Source Sync after Add Source.
- [x] 02 — Separate Candidate table and focused identity summary.
- [x] 03 — Use `v` for file diffs; remove obsolete `f`/`d` instructions.
- [x] 04 — Remove Validation's redundant Policy shortcut; retain Enter progression.
- [x] 05 — Remove TUI push and explain manual publication before Registry Sync.
- [x] 06 — Make Success controls functional, including exact receipt and supported Undo.
- [x] 07 — Show the focused Marketplace artifact description.
- [x] 08 — Explain proposed Remediation effects and separate Continue from facts.
- [x] 09 — Refresh Candidate state immediately and durably after local promotion.
- [x] 10 — Select one or multiple eligible harnesses explicitly.
- [x] 11 — Fix Artifact Details controls and compatibility messaging.
- [ ] 12 — Make Credential Action selectable and wire permitted actions.
- [ ] 13 — Carry explicit credential purpose/acquisition guidance from Source to installation.
- [ ] 16 — Owner request: user variables and credentials area per artifact/harness (ConfigInput at install, files at the installed location, credentials only in the provider, edit per harness or all).
- [ ] 14 — Enforce the shared skeleton without in-TUI exceptions; verify `v` on every screen.
- [ ] 15 — Targeted mutations, scoped mutmut, full gates and manual acceptance.

#### CP-22 — closed by the operator (2026-09-14)

The entries below retain the third manual run's findings and implementation history. The owner
closed CP-22 explicitly (D-248); new defects/refinements belong to CP-23. Closure does not assert
a fresh gate run or individual manual success for every earlier case. Historical full quality
evidence is on `d60bdd5`; the bootstrap stage-history enhancement remains in BACKLOG.

- [x] **QA-087 — every view fills the skeleton differently, and actions share a block with the
      view's status.** Surface: every screen. Severity: high. Observed: on Registries the one
      actionable row `> [ Add Registry ]` stands in the same block as four lines of prose about
      registries; on the Dashboard the first-run panel sits above the navigation rows inside their
      block. *"nigdy akcja i menu do wyboru nie powinno byc w jednym bloku z statusem widoku"*;
      *"kazdy widok powinien miec ta strukture … bo teraz co widok jest inaczej mam wrazenie"*.
      Expected: one structure for every view — trail, actions, cursor description, view status,
      `working at`, keys — enforced in code rather than by convention, *"zeby nie bylo zbyt wielu
      wyjatkow od reguly"*.
      Partly landed (2026-09-11): the skeleton is a type (`Frame`, `4869c10`) whose field order is
      the layout, with the arrangement derived from the declaration and held as properties over
      generated frames; the source answers `actions` rather than one undifferentiated body, and
      both dashboards are split — rows alone, guidance and counts as view status, the
      `Navigation:` labels gone (`D-243`). Registries, Settings, Doctor, Registry Maintainer and
      Add Registry have followed; on the first form the operator settled that a form is no
      exception — *"Wszystko pod pola (jak reszta)"* — so the fields stand alone and every
      explanatory line reads below the rule, key prompt last. Add Source, Initialize Registry,
      Scan Repository and Rebuild Registry followed through one table, `_FORM_PROSE`, and
      `MIXED_SCREENS` is now empty. Review/result screens subsequently landed in CP-22 step 14;
      the new control/prose gaps are tracked in CP-23.

- [x] **QA-088 — a form described in prose the keys the footer advertises two lines below.**
      Surface: Add Registry, Add Source, Initialize Registry, Scan Repository, Rebuild Registry.
      Severity: medium. Observed: every form closed with a line such as *"Type to edit; Backspace
      removes; Space toggles default; Enter advances."* while the legend directly below it already
      offered `[Enter]` and `[Space]` — *"duzo z tego powinno byc w klawiszach u dolu a nie w
      informacji"*, and of the Rebuild screen's own version, *"ta informacja jest zbedna"*.
      Expected: a key the screen accepts belongs in the block that exists to answer that.
      Landed (2026-09-11): the sentence is gone from all five forms; `key_bindings` gives a form
      `[Type] Edit`, `[Backspace] Delete` and `[Enter] Next / continue`, and `_FORM_TOGGLE_LABELS`
      names what Space changes per screen so the word the prose carried is not lost with it.

- [x] **QA-098 — Registry Maintainer says what a registry *is*, never where it is in its life.**
      Surface: Registry Maintainer (46). Severity: high. Observed: the screen has no rows at all,
      so the registry this project publishes is prose rather than something the cursor can be on,
      and nothing on it names the repository, the branch the snapshot was taken from, whether that
      branch exists on the remote, or whether anything is waiting to be pushed. Expected: the
      registry is a row — `> manual-registry` with its sha, so two checkouts of the same name on
      different branches or remotes are told apart — and the cursor description carries the repo
      URL, the branch, the state of the remote branch and what is unpushed; and the screen says
      plainly that a change only becomes available once it is pushed, and that AART will not push
      it for you. A maintainer may later subscribe to a remote branch; a user only ever subscribes
      to a repository's `main`. Fixed in CP-22 step 17 (`D-247`): `MaintainerRegistryWorkspaceView`
      and `MaintainerPublicationState` in the application layer, `read_registry_workspace` reading
      the checkout's own knowledge of its remote with no network, and screen 46 carrying the row
      and its lifecycle description. The initialization stage report remains in `BACKLOG.md`.
      The earlier unfinished message is not a pending clarification after closure (D-248);
      concrete later publication requirements are CP-23 task 05.

- [x] **QA-097 — Settings has four rows that change behaviour and no row that says what it changes.**
      Surface: Settings (28). Severity: medium. Observed: `[v]` opens nothing for `Detail level`,
      `Default scope` or `Show available updates`, so the reader toggles a setting to find out what
      it does. Expected: every row the cursor can sit on describes itself under `[v]`, like the
      rebuild stages do since `QA-089`.

- [x] **QA-096 — a view's status reads as a paragraph, and starts its sentences both ways.**
      Surface: every screen. Severity: medium. Observed: separate statements about the view are
      drawn as consecutive lines, so three unrelated facts read as one wrapped sentence; and the
      first word is capitalised on some (`No authoring Sources are configured.`) and not on others
      (`the current project is not a Registry, so there is nothing here to rebuild`). Expected:
      each statement is a list item — `- ` with a blank line between items, always, including when
      there is only one — and every statement is a sentence: capital first letter, full stop.

- [x] **QA-095 — an explanation that never changes is drawn on every frame.**
      Surface: Registry Maintainer (46). Severity: low. Observed: `Connected Registry snapshots` /
      `These approved snapshots determine what Marketplace can offer.` stands in the status block
      in both profiles, although it describes what a registry snapshot is rather than what this
      project's is. Expected: it collapses under `[v]` like every other explanation (`QA-070`).

- [x] **QA-094 — Registry Maintainer says the project is not a Registry twice.**
      Surface: Registry Maintainer (46). Severity: medium. Observed: the same fact is stated once
      as the state of the local workspace and once as the notice left by an action, so the reader
      is told twice and can tell neither statement is the same one.

- [x] **QA-093 — what an action left behind shares a block with the action.**
      Surface: Rebuild Registry (46h), and every screen that carries a notice. Severity: high.
      Observed: `actions` composes the notice into the block reserved for what the cursor can act
      on, so `the current project is not a Registry, so there is nothing here to rebuild` is drawn
      among the five stages a reader is choosing between. Expected: the notice is a block of its
      own, after a rule — it is neither a row, nor what the cursor points at, nor the state of the
      view, so it is a block the skeleton does not have yet.

- [x] **QA-092 — a heading that repeats what the lines below it already say.**
      Surface: Maintainer Dashboard (30). Severity: low. Observed: `Maintainer overview` labels
      four counts and a list of recent activity, none of which needs telling that it is an
      overview — the same fault `QA-067` removed from `Navigation:`.

- [x] **QA-091 — a screen with no rows still drew its report inside the actions block.**
      Surface: every result, review and refusal screen. Severity: medium. Observed: `actions`
      returned whatever `_body` produced whether or not the cursor had anything to move over, so
      an install result and a stopped run were drawn in the block reserved for what can be acted
      on. Expected: the rule, not a list — a screen with no rows has no actions block.
      Landed (2026-09-11, `D-244`): `actions` reads the row model and returns nothing when there
      are no rows; `status` carries the body, the view's own statement and then the notice.

- [x] **QA-090 — a confirmation screen never said what it was confirming.**
      Surface: Review Registry, Review Source, Review Init, Review Rebuild, Refresh, Disconnect.
      Severity: high. Observed: between a filled-in form and an irreversible action the screen drew
      one line — *"Press Enter to connect this registry."* — over a legend that already offered
      `[Enter] Confirm`, so it said nothing at all about what was about to happen. Expected: 161.4
      — a screen states what it is and what state it is in without the reader deriving either.
      Landed (2026-09-11): `_review_facts` states the subject from the draft the reader just filled
      in; a stopped run replaces it rather than joining it, since the plan it described was
      discarded when the run stopped (`QA-033`).

- [x] **QA-089 — a row carried its own explanation, so five choices read as five sentences.**
      Surface: Rebuild Registry (46h). Severity: medium. Observed: every row read
      `Lock only: pin everything the registry references`, gluing the choice to its purpose, so
      the list could not be scanned as a list. Expected: bare labels above the rule and the
      purpose of the row under the cursor in the block `[v]` opens — *"z czego to wyjasnienie
      powinno oczywiscie byc collapsed albo uncollapsed jak sie klika v"*.
      Landed (2026-09-11): the labels are bare and `description` answers `REGISTRY_STAGE_PURPOSE`
      for the selected row, so the explanation follows the cursor and obeys `[v]` like every other
      cursor description (`QA-070`).

- [x] **QA-086 — `working at` floated above the terminal's blank space instead of sitting on the
      footer.** Surface: every screen. Severity: medium. Observed: the frame padded a short screen
      immediately above the key legend's rule, so the launch directory was pushed to the top of
      that gap and a variable stretch of nothing stood between it and the keys — *"chce zeby
      working at bylo tu - to sie tyczy wszystkich widokow"*. Expected: the directory is the
      footer's caption, flush on its rule, with the padding above it.
      Landed (2026-09-11): `screen_frame` takes the line as `context=` and draws it flush on the
      footer rule; `footer_start` reaches back over whatever stands flush there, so the padding
      lands above the caption and the terminal keeps it on screen when a long body is clipped.
      `D-242`, revising `D-235`.

- [x] **QA-085 — A lab that loses its marker can be neither reset nor set up over.**
      Surface: `make manual-test-setup-empty`, `make manual-test-reset`. Severity: high. Observed:
      setup refused with `refusing to remove unmarked directory: /private/tmp/aart-cli-manual-lab`,
      and so did reset, because setup resets first. The operator's `rm -rf` on that path then
      failed too — `Permission denied` on every `SKILL.md`, `server.py`, `mcp.json` and object-store
      file — leaving the lab still there and still unowned.
      Cause, measured: an installed payload is delivered read-only, **directories included**
      (`dr-x------` on `.claude/skills/manual-check`), so nothing inside can be unlinked until the
      write bit comes back. `reset_lab` knows this and restores it as it goes; a bare `rm -rf` does
      not. An earlier `rm -rf` therefore removed what it could — the marker among it — and stopped
      at the first artifact root, which is exactly how the directory became unowned.
      Expected: the refusal names a recovery that works, and a reset that fails partway leaves the
      lab still owned.
      Landed (2026-09-11): `reset_lab` empties the root and removes the marker only once nothing
      else is left, so a removal that fails partway through always leaves a lab that is still
      owned and still resettable. Refusing an unmarked directory stays right — it is not the
      tool's to delete — but the refusal now prints `chmod -R u+w <root> && rm -rf <root>` with
      the exact path, and `docs/testing/END_TO_END_ACCEPTANCE.md` carries the same line under
      *If the lab loses its marker*. `tests/manual_test_lab_test.py` runs both commands against a
      real read-only lab, the blunt one to show it fails and the printed one to show it works, so
      the recovery is checked rather than described.

#### CP-21 — second manual TUI run (2026-09-10)

Raw operator notes: `nowe bledy i znaleziska.txt` (untracked). Every item below is transcribed from
that run; the screen transcripts in it are the reproduction.

- [x] **QA-064 — `[v] Fast / Verbose` does nothing on the Dashboard.**
      Surface: Dashboard, and every screen whose footer advertises it. Severity: medium.
      Observed: the footer offers `[v] Fast / Verbose` and pressing it changes nothing visible.
      Expected: either the key changes what the screen shows, or the screen stops advertising it.
      A binding in the footer is a promise. Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-233`): `[v]` now toggles the cursor-description region on every
      screen; Fast hides it and Verbose shows it. This is the visible half of `QA-070`.

- [x] **QA-065 — Screens draw two section rules with nothing between them.**
      Surface: Dashboard, Registries, and other list screens. Severity: medium. Observed: the
      operator's transcript shows a rule, one explanatory line, a rule, then a second rule
      immediately — an empty section drawn as if it had content. The help block is also present
      before `?` is pressed, so `?` appears to do nothing.
      Expected: an empty section is not drawn at all, and the help block appears only on `?`.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-232`): a rule separates two regions that both spoke, so an
      empty section cannot draw one. Help was already gated on `?` and is now a region of its own.

- [x] **QA-066 — The screen title and the working directory are run together.**
      Surface: every screen. Severity: medium. **Revises `QA-053`/`D-224`.** Observed: the header
      is `AART / Activity` immediately followed by `Working in <path>`, which reads as one wrapped
      line rather than two facts. Expected, in the operator's words: title, one blank line, the
      context line, then the rule. Note this partly reverses the placement `QA-053` chose, and
      `QA-069` moves the line entirely; settle both together rather than separately.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-235`): settled with `QA-069` — the directory left the
      header, so there is no second header line to run together with the first.

- [x] **QA-067 — There is no standard screen skeleton, so every screen composes itself.**
      Surface: all TUI screens. Severity: high. Observed, in the operator's words: *"teraz to jest
      wolna amerykanka odnosnie UI"* — sections, spacing and the key legend sit at different
      heights on different screens, and text touches its rules with no breathing room.
      Expected: one skeleton every screen fills, in this order — title; blank; rule; **menu /
      list section**; rule; **cursor-description section** (what the thing under the cursor is and
      what can be done with it); rule; **view-status section** (state of the whole view: counts,
      errors, remaining steps) which is omitted entirely when it has nothing to say; then the
      footer. One blank line above and below every block of text next to a rule.
      Blocks the end-to-end stage: no. Owns `QA-065`, and `QA-070` is the toggle over its second
      section.
      Landed (2026-09-10, `D-232`): `screen_frame` composes title, menu/list, cursor description,
      view status and footer in that order, and one `frame` puts every screen through it.

- [x] **QA-068 — The key legend is not anchored to the bottom and mixes two kinds of key.**
      Surface: every screen. Severity: high. Observed: on short screens the legend floats directly
      under the body with the rest of the terminal blank beneath it; screen-specific and universal
      keys share one line.
      Expected: the legend is always the last thing on the screen, with screen-specific keys on a
      line **above** the universal ones (`[Esc] Back  [?] Help  [q] Quit`).
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-234`): `anchor` pads above the footer so the legend sits on
      the bottom rows, and screen keys are on the line above the universal ones.

- [x] **QA-069 — The working directory belongs in the footer, above the keys.**
      Surface: every screen. Severity: medium. **Revises `QA-053`/`D-224`.** Observed: the operator
      now wants the top line to carry only the TUI path and the launch directory to sit in the
      footer, separated from the key legend by a rule. Expected: `working at <path>`, a rule, then
      the key lines. Decide together with `QA-066`.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-235`): `working at <path>` is its own region immediately
      before the key legend, separated from it by the skeleton's rule.

- [x] **QA-070 — The cursor-description sections should be one toggleable mode.**
      Surface: all TUI screens. Severity: low. Observed: the operator asked for the per-cursor
      explanations to be switchable by a key rather than always present — plausibly what
      `[v] Fast / Verbose` was meant to be (`QA-064`).
      Expected: one key toggles the description sections across screens, and the footer names it
      honestly. Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-233`): `[v]` is the toggle, which also settles `QA-064`.

- [x] **QA-071 — Nested views do not name their parent.**
      Surface: Sources, Candidates, and every screen reached from a dashboard. Severity: medium.
      Observed: the header reads `AART / Sources`, which is not where the operator is.
      Expected: `AART / Maintainer Dashboard / Sources`, and the same for every nested view.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-236`): the heading is the trail from the session's own
      history, so `AART / Maintainer / Sources` names the parent it was reached through.

- [x] **QA-072 — Esc after a finished sequence re-enters the wizard it just completed.**
      Surface: Sources, Marketplace, and every list reached after a completed sequence. Severity:
      high. Observed: after finishing Initialize Registry the operator lands on Sources; pressing
      Esc walks back into the wizard that has already run instead of returning to Maintainer
      Dashboard. The same happens from Marketplace after an install.
      Expected: a completed sequence is not on the back stack. Esc from a list goes to the
      dashboard that owns it. Related to `QA-027`, which fixed the forward exit but not this.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-237`): `navigate` rewinds when the target is already on the
      stack, so a sequence that ends by returning somewhere is off it by the act of
      returning — no list of "finished" journeys is needed. Esc from a list is a second
      rule, read from the declared navigation, and guarded so it never invents a forward
      step to a dashboard nobody has opened.

- [x] **QA-073 — Backing out of Candidate Diff or Validation loses the Candidate.**
      Surface: Candidate Diff (37), Validation (38). Severity: high. Observed: pressing Esc from
      Diff produces `That Candidate is not available.`, and from Validation
      `That Candidate's validation is not available.` — the workflow chrome still draws the whole
      sequence above a screen that has lost its subject.
      Expected: going back keeps the Candidate. A screen that genuinely cannot resolve one says so
      without drawing the sequence as if it were still in it. Related to `QA-037`.
      **Fixed (2026-09-10, `D-232`).** Optional Candidate inspections remain out of the progress
      chrome, but their explicit reverse edges preserve the workflow subject. This covers
      Lifecycle, Provenance and Version Conflict returning directly to Candidate Details, their
      nested reverse edges, and Validation Details returning to Validation. When Back crosses from
      Validation to a screen whose projection needs a bare Candidate identity, the reducer reduces
      the selected `candidate:check` row to its Candidate ID; unrelated Back navigation still
      clears focus. The complete reverse journey now renders the same Candidate instead of either
      unavailable message. Three targeted mutations and the relevant scoped `mutmut` mutants were
      killed.
      Evidence: `tests/maintainer_candidate_shell_test.py` covers all Candidate side-view edges;
      `tests/maintainer_validation_views_test.py` covers the whole Details → Validation → Diff
      journey, every `ValidationCheck`, and the negative dashboard boundary. Blocks the end-to-end
      stage: no.

- [x] **QA-074 — A validation that passed does not advance, and promotion is hidden behind `p`.**
      Surface: Validation (38), Validation Details (39). Severity: high. Observed: on Validation
      Details every check reads `Passed`, Enter does nothing, and only Esc leaves — into the
      broken Validation screen of `QA-073`. Promotion requires knowing to press `p`, which no
      section states.
      Expected, in the operator's words: a passed validation says so, and Enter continues to
      Policy. If the extra key press is a deliberate guard against clicking through a promotion,
      the view-status section must say that the next step needs a deliberate action, and name it.
      **Fixed (2026-09-10, `D-232`).** Validation Details now projects Policy Review as its Enter
      destination and advertises `[Enter] Policy`; this consumes the already-composed validation
      evidence and performs no validation or promotion effect. The `p` shortcut on Validation is
      retained but truthfully labelled `Policy`, not `Promote`. The production-composition walk now
      reaches Policy by opening a check and pressing Enter again. Two targeted mutations and six
      focused `tui_consumer.py` `mutmut` mutants were killed.
      Evidence: `tests/maintainer_validation_views_test.py` and the maintainer production
      composition E2E. Blocks the end-to-end stage: no longer.

- [x] **QA-075 — "No Registry is connected." reads as a failure while one is being created.**
      Surface: Registry Maintainer (46). Severity: medium. Observed: immediately after a successful
      five-stage initialization the screen reports `No Registry is connected.` above a completed
      run. The operator worked out that it refers to *subscribed* Registries, but only by guessing.
      Expected: the connected-snapshots block says what it is empty *of*, and — given `QA-059` —
      names publishing and subscribing as the next step. Overlaps `QA-060`.
      Blocks the end-to-end stage: no.
      Done (2026-09-10): `render_maintainer_registries` now says `No Registry is subscribed in this
      project yet.` and, when the project is itself a Registry workspace, adds that a Registry
      created here becomes connectable once it is published to its branch and subscribed to.
      Covered by `tests/empty_state_truthfulness_test.py::EmptyConnectedRegistriesTest`.

- [x] **QA-076 — A promoted artifact still shows as a `New` Candidate.**
      Surface: Candidates (35). Severity: high. Observed: `skill/manual-check@1.0.0` was installable
      from Marketplace while Candidates still listed it as `New`, with no indication it had been
      promoted and published.
      Expected: a Candidate whose version the target Registry has published reads as promoted, not
      as new work. The state exists (`CandidateState.PROMOTED`) — check whether the screen reads a
      stale scan rather than re-deriving against the Registry, and whether `QA-062`'s history
      separation changes what it sees. Blocks the end-to-end stage: no.
      Done (2026-09-10, `D-239`): unchanged artifact and Collection Candidates are re-derived
      against the target Registry's approved versions. An exact coordinate, Candidate ID and
      content-digest match changes `New` to `Promoted`; a content disagreement remains
      `registry-version-immutable`; unrelated Registry entries do nothing. Rejected and terminal
      history is deliberately retained unchanged, preserving INV-239 and avoiding illegal domain
      transitions. `QA-062`'s promoted/current separation remains intact.
      Evidence: `tests/maintainer_version_conflict_test.py` and
      `tests/maintainer_collection_history_test.py`; two deliberate semantic mutations killed.
      The scoped `make mutants` run generated 472 mutants and killed 353; none survived in the
      registry matching helpers or the new refresh branches.

- [x] **QA-077 — `authoring Source 31-sources is not configured and enabled`.**
      Surface: Sources (33). Severity: high. Observed: both Sources flipped to `Stale` and the
      screen printed that line. `31-sources` is an internal screen identifier being used as a
      Source alias — the same class of leak as `QA-045`. The operator could not tell what had
      failed or what to do.
      Expected: the message names the real alias, says why it is stale, and offers the fix.
      No internal screen identifier ever reaches the operator. Blocks the end-to-end stage: no.
      Done (2026-09-10): measured end to end -- a dashboard's rows *are* screens, so navigating
      away carried `focus="31-sources"` (`MaintainerScreen.SOURCES.value`) into the next screen,
      where it survived `SET_ROWS` and reached `prepare_configured_source_sync` as a `SourceAlias`.
      Fixed at source: `is_screen_identifier` in `consumer_views.py`, and `_navigate` drops a focus
      that is one. Covered by `tests/screen_identifier_leak_test.py` (6 tests + 86 subtests, one
      per declared route).

- [x] **QA-078 — A Skill reports three harnesses unsupported, then installs for all four.**
      Surface: Artifact Details, Installing, Success. Severity: high. Observed: Artifact Details
      listed `profile 'codex' is not supported; supported profiles: claude` for codex, opencode and
      tabnine; the install then reported `✓ delivery:claude`, `✓ delivery:codex`,
      `✓ delivery:opencode`, `✓ delivery:tabnine`. Both cannot be true.
      Expected: either the manifest's `compatibility.harnesses` limits delivery and the extra three
      are not written, or the artifact really is deliverable everywhere and Artifact Details stops
      claiming otherwise. The operator's question stands: what about a plain Markdown Skill makes
      three harnesses unsupported? Blocks the end-to-end stage: no.
      Diagnosed whole (2026-09-10, `D-231`), implementation deferred to step 8 in the setup path
      established by step 3. The two
      screens read different sources: `evaluate_compatibility` (`compiler/graph.py:791`) answers
      Details from the manifest's `compatibility.profiles`, `_deliveries`
      (`io/artifact_placement.py`) answers the plan from the request and never reads the manifest.
      Nothing about Markdown makes three harnesses unsupported — the author declared one, and only
      one screen listened. An absent `compatibility` block and an explicit `[]` are the same `()`
      after `allow_empty=True`, so empty means unconstrained. Narrowing inside `placement_for` was
      built and backed out: it works and delivers, but the receipt then records the narrowed set
      while the host still carries every measured harness, and `configured_consumer_completion`
      refuses with `configured-setup-invalid: setup requires one exact configured installation
      receipt`, so the `CONFIGURED` marker is never written. The narrowing belongs where the offer
      is made — the consumer setup and remediation path step 3 established — not inside the
      placement that serves it. `measured_host_profiles_test.py` and `git_backed_runtime_e2e_test.py`
      currently assert the defect and must be corrected with the fix.
      Done (2026-09-11, `D-241`). The deferral's premise expired: step 3 turned out to be the
      promotion path, so the setup path it was waiting for never existed. The refusal it had been
      backed out on was the *second half of the same defect* -- setup iterated every measured
      harness and asked the receipt store about harnesses the install never touched. A setup step
      is owed for a harness the artifact actually reached, and `receipt_profiles` already says
      which those are, from recorded effects rather than from the request. With that, the
      narrowing lands in `placement_for` at one point, reusing the `_skippable` asymmetry: a
      measured harness is left out, a typed one is refused by name, and the refusal uses the same
      `supported_label` formatter as Artifact Details so the two screens cannot word one fact two
      ways. Fixtures that declared one harness while asserting delivery to several were freed where
      their file's subject was the measured-versus-requested asymmetry, each with a comment naming
      where the narrowing is held instead.
      Covered by `tests/declared_harness_narrowing_test.py`; whole suite 3915 passed.

- [x] **QA-079 — Install never asks which harness to install for.**
      Surface: Marketplace install sequence. Severity: medium. Observed: the artifact was delivered
      to every harness without the operator choosing.
      Expected: the review names the harnesses that will receive the artifact and lets the operator
      narrow them, or states plainly why the set is not a choice. Related to `QA-078`.
      Blocks the end-to-end stage: no.
      Done (2026-09-11, `D-241`) by the second half of that expectation, which is the true one: the
      set is derived from the machine and the manifest together -- every measured harness the
      artifact declares support for -- so there is nothing left to choose. Screen 09 now reads
      `Harnesses: tabnine (every harness this machine measured that the artifact declares support
      for).`, read off the plan's own effects so it cannot disagree with what runs.
      Covered by `tests/install_review_names_harnesses_test.py`.

- [x] **QA-080 — Remediation lists "configure harness" three times with no way to act on it.**
      Surface: Remediation. Severity: high. Observed:
      `4 thing(s) need preparing first / configure harness (configuration mutation)` repeated three
      times plus `configure credential (credential mutation)`. Nothing says which harness, what
      would change, or how the operator is meant to configure one. The operator's reaction:
      *"jak mam skonfigurowac harness?? nie rozumiem"*.
      Expected: each row names its subject and what will be written; identical rows are either
      distinguished or collapsed. Blocks the end-to-end stage: no.
      Done (2026-09-11, `D-241`) in both halves. Most of the duplication was `QA-078`: setup was
      planned for every harness the machine measured, so three of those four rows were about
      harnesses the artifact never reached. Those are gone. Where several rows legitimately remain,
      each now names its subject -- `configure harness: claude (configuration mutation)` -- read
      off the summary the projection already builds, so no view field has to be filled in per kind.
      Covered by `tests/remediation_row_subject_test.py`.

- [x] **QA-081 — Credential entry drops out of the TUI into a raw shell prompt and fails.**
      Surface: MCP install, credential step. Severity: **blocking**. Observed: the TUI stayed on
      screen while `security` printed `password data for new item:` directly after the footer,
      producing the line `[q] Quitpassword data for new item:`. The install finished
      `✗ credential:dummy-token`, then `launcher`, `harness:claude`, `harness:opencode` and
      `harness:tabnine` all `missing`, and `Undo unavailable`.
      **Characterized (2026-09-10).** `MacKeychainProvider.store` with no carrier — the default, and
      deliberately so — runs `security add-generic-password -w` with `capture=not interactive`,
      i.e. `capture=False` (`agent_artifacts/io/credentials.py:389-436`). The subprocess therefore
      inherits the terminal and prints its prompt over whatever curses last drew. Not seeing the
      value is correct and must stay (161.8/161.9, INV-206/INV-207: this process never learns the
      secret); handing the drawn screen to a subprocess is the defect.
      Nothing in the codebase releases the terminal: `curses.endwin`, `def_prog_mode` and
      `reset_shell_mode` appear nowhere, and the whole session runs inside one `curses.wrapper`
      (`agent_artifacts/tui.py:876`) while the credential write happens far below it, in
      `CredentialExecutor.apply` (`agent_artifacts/io/execution.py:882`).
      Expected: an effect that needs a person at the terminal says so, and the terminal adapter
      releases and restores the screen around it — so the provider still owns the prompt and AART
      still never sees the value, but the prompt gets a clean screen and the TUI repaints after.
      **Fixed (2026-09-10).** The seam is a loan, not a redraw. `CredentialEffectInterpreter`
      takes an optional `terminal_handover` and wraps only `provider.store` in it, so the screen is
      released before the provider speaks and taken back afterwards whatever it answered — and
      reading or removing a credential, which says nothing to anybody, never disturbs the screen.
      `_CursesHandover` in `agent_artifacts/tui.py` is the adapter: `def_prog_mode` + `endwin` on
      the way in, `reset_prog_mode` + a full repaint on the way out. It is composed unbound and the
      curses runner binds the screen to it, so the text terminal and the CLI keep prompting exactly
      as they did. The loan travels beside `interactive_credentials` through
      `LocalConsumerActions` → `complete_configured_installation` → `interpreters_for`. AART still
      never sees the value. Three targeted mutations killed; see `tests/credential_terminal_handover_test.py`.
      Blocks the end-to-end stage: no longer.

- [x] **QA-084 — The manual lab drives macOS into offering to reset a keychain.**
      Surface: manual lab + credential step. Severity: **blocking**, and hazardous. Observed: during
      the credential step macOS raised `Keychain Not Found — A keychain cannot be found to store
      "dummy-token." / Cancel / Reset To Defaults`. An offer to reset a keychain must never be
      reachable from a manual test.
      **Characterized (2026-09-10).** `_home` in `scripts/manual_test.py` creates `.config`,
      `.local/share` and `.cache` in the lab home and nothing else; there is no
      `Library/Keychains` under either lab home, confirmed on the operator's own lab. `security`
      then finds no default keychain and offers to create one by resetting.
      `MacKeychainProvider` can already be pointed at an explicit keychain file — `keychain` is a
      field and `_suffix()` appends it (`agent_artifacts/io/credentials.py:262,279`) — but nothing
      outside the constructor can set it: there is no environment or configuration path to it, and
      the provider reaches the flow as an injected port.
      **Fixed (2026-09-10), and with no product change at all.** Measured rather than assumed:
      `security` does resolve the default keychain from `HOME`, and the missing piece was only that
      the lab home had nowhere for one to live. `_keychain` in `scripts/manual_test.py` now creates
      `Library/Keychains/aart-manual.keychain-db` with an empty password, creates
      `Library/Preferences` (without it `default-keychain -s` silently forgets the choice), makes it
      the default and the search list, and unlocks it — so the credential write lands in the lab,
      the operator's real keychain is never a candidate, and `reset` takes it away with the
      directory. Verified in both lab homes, and verified that the real default keychain is
      unchanged by a setup. The empty password protects nothing and is not a secret. Three targeted
      mutations killed.
      Blocks the end-to-end stage: no longer. Split out of `QA-081`, which was the product half.

- [x] **QA-082 — Feature request: AART should push a reviewed Registry commit to a branch.**
      Surface: Registry commit (45), and the CLI equivalent. Severity: medium.
      **Decided by the product owner on 2026-09-10; 164.7 has been amended and the work is
      unblocked (`D-228`).** Having to leave AART to type `git push` is the defect: the same bytes
      were just reviewed, validated and committed here. AART now pushes the reviewed registry
      commit, on an explicit action, to a remote branch the maintainer configures — any branch but
      the registry's default one. A push to, merge into or fast-forward of the default branch is
      refused by AART itself, by name, rather than left to the forge's branch protection. A
      consumer subscribing to a registry reads its default branch, so what a consumer can install
      is still what somebody merged. To build: the configured publication branch (maintainer
      setting, with no default-branch value accepted), the push effect and its receipt, the refusal
      and its test, and the Registry Commit screen's action. Supersedes the open question in
      `QA-055`.
      Done (2026-09-10, `D-228`/`D-240`): screen 45 is two explicit effects in sequence. `p` opens
      the publication target, Enter reviews it -- `Ready to push the reviewed commit to
      origin/review/registry`, `Nothing will be merged` -- and a second Enter pushes, leaving a
      receipt that names what moved and that nothing was merged. The default branch is refused by
      name. The screen is a form only while that target is open (`D-240`), so `q` still quits
      before it and is a legal branch character inside it.
      Covered by `tests/registry_publication_test.py`, `tests/registry_publication_io_test.py`,
      `tests/registry_publication_branch_test.py`, `tests/registry_push_cli_test.py`,
      `tests/maintainer_promotion_shell_execution_test.py` and the acceptance walk
      `maintainer_composition_e2e_test.py::test_validated_promotion_is_committed_then_published_to_a_review_branch`,
      which pushes into a real bare repository and asserts the default branch did not move.
      **Half-built (2026-09-10).** Landed: `agent_artifacts/domain/publication.py` decides the rule
      from two strings — what was requested and what a subscriber reads — so `refs/heads/main`,
      `HEAD` and a case variant are refused as the default branch under other spellings rather than
      as three separate targets. `application/registry_publication.py` binds one reviewed revision
      to one branch on one remote, with no `force`, `merge`, `fast_forward` or `delete` field to
      set. `io/registry_publication.py` pushes `<revision>:refs/heads/<branch>` — the reviewed
      commit, not whatever `HEAD` has become — and makes the refusal a second time from the remote's
      own advertised `HEAD`, because a configured ref can disagree with the remote it names.
      Evidence: 30 tests over a real bare remote, two of them Hypothesis properties, one asserting
      the remote's `main` is byte-for-byte where it was. Five targeted mutations killed; `make
      mutants` found four more (the adapter's guard branches and its held-commit check) and those
      are closed too.
      **Still to do:** the publication branch as a maintainer setting rather than an argument, the
      Registry Commit screen's action, and the receipt's place in the frame. All three are in
      `tui_maintainer.py` and the maintainer views. Step 3 has landed, so they are next.
      Blocks the end-to-end stage: no.

- [x] **QA-083 — Repeated "Maintainer" in nested Maintainer titles.**
      Surface: Maintainer screens. Severity: low. Observed: the operator asked not to repeat
      "maintainer" in a title when the whole view is already the Maintainer's. Weigh against
      `QA-071`, which adds the parent to the breadcrumb; the two must produce one scheme, not two.
      Blocks the end-to-end stage: no.
      Landed (2026-09-10, `D-236`): a dashboard passed through drops the word, so
      "Maintainer" is said once however deep the view goes.


- [ ] **QA-056 — A promotion cannot be completed from the CLI without fabricating its evidence.**
      Surface: `aart registry promote`. Severity: medium. **Unconfirmed — verify during the CLI
      run.** Observed in code: `registry promote` requires `--validation-report DIGEST` and
      `--policy-result DIGEST`, and no CLI command emits either; `validation_report_digest` is
      derived in the application layer and displayed only by the Maintainer screens. An operator
      following a CLI-only route therefore either reads the digests off the TUI, which makes the
      route not CLI-only, or invents them, which defeats the evidence the flags exist to carry.
      Expected: either a command that emits the validation/policy evidence for scanned Candidates,
      or an explicit statement that Candidate promotion is a TUI-only transaction. Blocks the
      end-to-end stage: no. Workaround in use: `registry vendor`, which needs no external evidence.
      Confirm at: `docs/testing/END_TO_END_ACCEPTANCE.md` step 3.

- [ ] **QA-057 — The CLI route had no way into the lab's environment.**
      Surface: manual acceptance tooling. Severity: low. Observed: `manual_test.py open` starts the
      TUI, and the CLI procedure told the operator to paste four environment variables in front of
      every command — unreadable, and a mistyped HOME runs a manual test against real state.
      Expected: one entry point that puts a shell inside the lab.
      Fix: `make manual-test-shell-maintainer` / `make manual-test-shell-consumer` open an
      interactive shell with the lab's isolated HOME/XDG and the role's working directory.
      Evidence: `tests/manual_test_lab_test.py::...a_lab_shell_is_described_for_each_role...`.

- [x] **QA-055 — The end of the promotion path states the publication boundary but never closes it.**
      Surface: Registry commit (screen 45). Severity: low. **Unconfirmed — to verify during the next
      manual run.** Observed in code, not yet at the terminal: the screen prints `Git push: no` and,
      once applied, `Canonical-branch publication remains external.` Both are true statements of the
      161.7 boundary, and neither tells the operator what is still theirs to do. The promotion
      sequence therefore ends on a screen that says what AART did not do rather than naming the one
      remaining step. Expected: the terminal screen of the sequence closes the path — the reviewed
      commit is local, and publishing it is a push the maintainer performs — without AART pushing
      or offering to. Blocks the end-to-end stage: no.
      Confirm at: `docs/testing/TUI_MANUAL_WALKTHROUGH.md` step 8.
      Done (2026-09-10) by `QA-082`, which the product owner decided differently from the guess
      recorded above: the path closes by AART performing the push to a review branch, not by
      naming a step left to the operator. `Git push: no` and `Canonical-branch publication remains
      external.` are gone; the screen now says publication has not happened yet and offers `p`.

- [x] **QA-062 — An author editing an already-published version crashed Source Sync.**
      Surface: `reconcile_source_scan` (`agent_artifacts/application/maintainer.py`). Severity:
      high. Found while answering how Sync detects upstream change. Observed, in the lab: after a
      version is published, the next Sync records its Candidate as `promoted`; when the author then
      edited a payload file without bumping the version, reconciliation called
      `supersede_candidate` on that promoted record and the domain raised
      `ValueError: published registry state, not its candidate history, owns promotion` — an
      exception, not a `Result`, that no boundary catches, so it reached the caller as a crash. The
      Collection path did the same thing with a bare `replace`, silently overwriting a published
      record instead of raising.
      Fix: a manifest now has at most two live records, kept apart — the promoted one, which states
      what the registry contains and is never moved by a scan, and the Candidate under review, which
      is the only one superseded. A new Candidate names whichever of the two it descends from, so
      the conflict still points at the record it collides with, and the answer to the edit stays the
      one already modelled: `invalid` with `registry-version-immutable`.
      Verified in the lab: unchanged → `promoted` and stable across repeated Syncs; payload edited
      at the same version → `invalid` with `registry-version-immutable`, linked to its predecessor;
      version bumped → `changed`, ready to promote.
      Evidence: `tests/maintainer_version_conflict_test.py::PublishedCandidateSupersessionTest`,
      `tests/maintainer_collection_history_test.py::...a_promoted_collection_record_is_not_superseded...`.
      Mutations killed: putting promoted records back in the current map; dropping the ancestor
      link to a published predecessor; letting Collections supersede a promoted record.

- [x] **QA-061 — The default lab's Registry disagreed with the Sources it claimed to have vendored.**
      Surface: `scripts/manual_test.py`. Severity: high. Observed: the very first maintainer Source
      Sync of an untouched lab reported both fixtures `invalid` with
      `Published coordinate/version already contains different canonical content` — a real product
      refusal, fired by a fixture that disagreed with itself. Two causes, both in the lab: the
      manifest was written to the author repository as `json.dumps(manifest, indent=2)` and handed
      to the Registry as `json.dumps(manifest)`, which are different bytes and therefore a different
      `input_digest`; and the fixtures were pre-promoted under the aliases `manual-skill-source` /
      `manual-mcp-source` while both walkthroughs tell the operator to configure `manual-skill` /
      `manual-mcp`, and a Candidate's identity includes its Source alias.
      Fix: one `_manifest_text` rendering used in both places, and the fixture aliases are the ones
      the walkthroughs configure.
      Evidence: `tests/manual_test_lab_test.py::...the_first_sync_of_an_untouched_lab_finds_the_registry_already_agrees`,
      which drives the operator's own first Sync rather than comparing bytes.

- [x] **QA-063 — One malformed manifest fails the whole Source, with no path in the message.**
      Surface: Source Sync. Severity: medium. **Confirmed by measurement.** Observed:
      setting `artifact.version` to `not-a-version` in one manifest made the entire Sync fail with
      `invalid SemVer: 'not-a-version'` — no manifest path, no artifact name, and every other
      artifact in that Source went unscanned. `CandidateState.INVALID` exists precisely so a bad
      artifact can be reported as a bad Candidate; a Source-wide abort spends it. Expected: the
      malformed manifest becomes an `invalid` Candidate naming its path, and its neighbours still
      scan.
      **Confirmed (2026-09-10).** Measured, not assumed: with `good/aart.json` at
      `1.0.0` and `bad/aart.json` at `not-a-version`, `compile_author_snapshot` returns `Err` and
      the healthy artifact is discarded — the abort is real. The diagnostic *does* carry
      `location.path='bad/aart.json'`; it is the rendering that drops it, so the operator saw only
      `invalid SemVer: 'not-a-version'`.
      Landed: `compile_author_manifests` compiles each manifest on its own merits and answers with
      `(artifacts, refusals)`, where a `ManifestRefusal` holds the manifest path beside its
      diagnostics; a fault in the tree itself (uncanonical or duplicated path) still refuses whole,
      because no manifest could own it. `compile_author_snapshot` is now a strict wrapper over it,
      so adoption and publication keep refusing whole — which is right there.
      **Landed whole (2026-09-10, `D-230`).** `compile_author_source`, the watching boundary, is now
      tolerant, and a refusal has somewhere to go: `SourceSyncExecutionResult.refusals` carries it,
      `MaintainerSourceSyncResultView.refusals` projects it as `(path, reason)`, and the Sync result
      screen renders `Could not read N manifests:` with the path on each line. `manifest_count`
      counts refusals beside the candidate states, so the arithmetic on the screen still closes — a
      manifest seen and not compiled is still a manifest seen.
      The malformed manifest is reported beside the scan rather than stored as an `invalid`
      Candidate, deliberately: a Candidate is persisted and reconciled, and a refusal has no compiled
      artifact behind it to promote, validate or publish, so a Candidate row would mean a
      Candidate-history schema bump for a record that can never advance. Nothing persists a refusal;
      the next Sync re-derives it. Both halves of the finding are met — the neighbours scan, and the
      message names the file.
      Four targeted mutations, all killed; the fourth (turning a schema refusal into a silent skip)
      survived first and is what
      `tests/source_partial_compilation_test.py::test_a_manifest_whose_schema_cannot_be_read_is_refused_rather_than_skipped`
      exists for.
      Evidence: `tests/source_partial_compilation_test.py` (7) and
      `tests/source_sync_refusal_report_test.py` (5).
      Blocks the end-to-end stage: no.

- [x] **QA-059 — The TUI walkthrough went from Add Source straight to Sync, which cannot work.**
      Surface: `docs/testing/TUI_MANUAL_WALKTHROUGH.md`, and the Sources screen's own refusal.
      Severity: high. Found during the operator's manual TUI run. Observed: pressing `s` on Sources
      refused with `Source Sync needs an explicit default target registry`, both Sources sat at
      `0 manifests`, and Candidates was empty. `prepare_configured_source_sync`
      (`agent_artifacts/io/maintainer_sync.py:135`) requires `configuration.default_registry` and
      then a *synchronized approved snapshot* of it, because Sync classifies each Candidate as new,
      updated or unchanged against what the target Registry already approved. In an empty-registry
      lab the Registry the maintainer just initialized exists only as a local commit, so it must be
      pushed and subscribed to before Sync has any baseline — and the walkthrough put its only push
      after promotion.
      Fix: new step 3, *Publish the Registry and subscribe to it*, between Create the Registry and
      Add the author Sources; later steps renumbered, and the post-promotion push is now named as
      the second one.
      Verified against a copy of the operator's own lab: push → `source add --kind registry-git
      --default` → `prepare_configured_source_sync` returns `Ok` for both Sources, and completing
      it reports `manifests=1` per Source where it previously refused.

- [x] **QA-060 — The Source Sync refusal names a fix the screen offers no route to.**
      Surface: Sources (screen 33). Severity: medium. **Unconfirmed — judge it during the run.**
      Observed: the refusal says `configure an enabled default registry, then review Source Sync
      again`. From Sources there is no route to Registries, and nothing says that the Registry the
      operator initialized minutes earlier is not yet subscribable because it has not been pushed.
      A maintainer who has just created a Registry is told to configure a different thing without
      being told that the thing they made is the thing to configure. Expected: the refusal names
      the two steps in the order they must happen, or the screen offers the route. Blocks the
      end-to-end stage: no.
      Done (2026-09-10, `D-238`): the refusal now advises `publish the Registry to its branch,
      subscribe to it in this project, then configure it as the enabled default target`, matching
      the `QA-075` wording on the screen next door. It is deliberately one remediation line, not
      three: `Diagnostic` sorts remediation into a set, so alphabetical order is the only order
      several lines can have and it is the wrong one (`D-238`).
      Covered by `tests/empty_state_truthfulness_test.py::SourceSyncWithoutADefaultRegistryTest`;
      mutation: reversing the clauses turns the ordering test red.

- [x] **QA-058 — A space typed into the Initialize Registry form made a usable identity unusable.**
      Surface: Initialize Registry (screen 46a). Severity: high. Found during the operator's manual
      TUI run. Observed: `manual-registry` / `Manual Registry` was refused with `this is not a
      usable registry identity`. The form's own status bar advertises `[Space] Toggle`, but on a
      text row a printable key is text, so pressing Space there types a space into the answer; the
      identity was then judged with it, and `_SLUG_RE`/`_one_safe_line` reject any surrounding
      whitespace. The refusal named none of the three answers and its single advice line was
      truncated mid-word by the content measure, so the operator had nothing to act on.
      Fix: `RegistryInitDraft.settled()` drops the whitespace around the three text answers at the
      action boundary — after typing, so `Manual Registry` stays typeable — and the review, digest
      and run all use the settled draft. `registry_identity_refusal` now judges each answer beside
      two known-good ones and names the faulted fields, one short line of advice each.
      Evidence: `tests/maintainer_registry_init_test.py::RegistryIdentityWhitespaceTest`,
      `::RegistryIdentityRefusalTest`, and
      `::MaintainerRegistryInitActionTest::test_a_stray_space_around_an_answer_still_reviews_the_registry`.
      Mutations killed: dropping `.strip()` on the identifier; keeping unfaulted fields in the
      refusal; naming only the first faulted field.

- [ ] **QA-027 — A finished sequence has no way out but pressing Esc repeatedly.**
      Stage: after any completed Maintainer action
      Surface: Source Sync Result (34), and every result screen with no forward route
      Severity: high
      Blocks current stage: no
      Reproduction: Sources → `s` → review → Enter → Source Sync Result. Now try to add or sync
      another Source
      Expected: Enter on a result screen returns to the list the sequence started from — Sources
      for a Source action, Registry for a registry action — so the next one can begin
      Observed: Enter does nothing; the only way back is Esc, Esc, Esc through the history
      Operator's words: "jak przechodzę przez dodanie source to nie wiem jak się mam cofnąć do
      ekranu głównego... na koniec journey w danej sekwencji Enter powinien wracać do pierwszego
      ekranu danej sekcji, np. jak dodaję source i wszystko poszło dobrze, to kolejny Enter cofa
      mnie do pierwszego ekranu Source, żeby dodać kolejne"
      Note: screen 45 already does exactly this (`Enter` after the receipt goes to screen 46).
      The rule exists; it is applied to one screen instead of all of them.
      Additional manual evidence: completing the Candidate promotion sequence also leaves the
      operator backing through every intermediate screen to reach Candidates. The owning-list
      return must cover completed Candidate workflows, not only Source Sync.
      Fix: Source Sync Result binds Enter to Sources — the list that journey started from — and
      the route is declared in the navigation map, because a key that navigates somewhere the map
      does not allow is a key that does nothing. Registry Maintainer gains `c Candidates`, so the
      screen a finished promotion lands on is one key from the next promotion instead of an Esc
      for every screen just walked. Screen 45's own Enter still goes on to Registry, which is the
      precedent this generalizes rather than replaces (`D-210`).
      Evidence: `tests/terminal_result_return_test.py` holds the key, the declared route, the
      footer label, the move it really makes, both halves of the finding, and that a review still
      waiting for its confirmation is not treated as a result.
      Retest: Sources → `s` → review → Enter → Source Sync Result → Enter should land on Sources;
      after a promotion, `c` from Registry Maintainer should reach Candidates.

- [ ] **QA-028 — Add Source opens holding the previous Source's answers.**
      Stage: adding a second authoring Source
      Surface: Add Source (31a); the same shape applies to Add Registry (21a) and Initialize
      Registry (46a)
      Severity: medium
      Blocks current stage: no
      Reproduction: add one Source, then press `a` on screen 31 again
      Expected: an empty form, so it is obvious a **new** subscription is being created
      Observed: every field still holds the previous Source's values, and nothing on screen says
      whether confirming edits the old subscription or creates another one
      Operator's words: "jak próbuję dodać nowe source to mam wartości z poprzedniego, co jest
      nieintuicyjne, bo nie wiem czy właśnie usuwam to stare i zamieniam na nowe wartości, czy
      dodaję całkowicie nowe source"
      Note: the draft is carried in `ConsumerUiState` and never reset on entry. `QA-018` requires
      a **refused** form to keep what was typed, so the reset belongs on entering the form, not on
      leaving it.
      Fix: `_navigate` empties the draft the entered form owns, and only that one, so opening Add
      Source does not discard a half-typed Add Registry. It is read on forward navigation only,
      which is exactly what separates opening a new form from returning to a refused one —
      `_declined_preparation` goes back through the session history and never reaches this
      (`D-211`). Add Registry and Add Source also state, in words, that they add another one and
      change nothing already connected, which is the question the operator actually asked.
      Evidence: `tests/form_draft_lifecycle_test.py` holds the empty form, the other drafts left
      alone, the refused form still holding everything typed (`QA-018`/`D-184`), Esc back onto a
      form keeping it, and the new sentence on both add forms.
      Retest: add one Source, press `a` on screen 31 again, and confirm the form is empty; then
      let a preparation refuse and confirm the typed values are still there.

- [x] **QA-029 — Screens are a wall of text; the action prompt is not separated from the body.**
      Stage: every review screen
      Surface: Source Sync (33), Source Sync Result (34), and reviews generally
      Severity: medium
      Blocks current stage: no
      Reproduction: open Sources → `s` and read screen 33 top to bottom
      Expected: the facts, then a blank line, then the one line that says what a key press will
      do — so `Press Enter to synchronize.` is findable without reading the whole screen
      Observed: eight dense lines with no vertical grouping, `Press Enter to synchronize.` being
      the ninth in the same block
      Operator's words: "`Press Enter to synchronize.` powinno być oddzielone, żeby było widoczne";
      "nie podoba mi się, że jest tak wiele tekstu w opisach, to się wszystko gubi i jest
      nieczytelne, powinno być więcej pustych linii pomiędzy wierszami tekstu"
      Note: related to `B-048` (refusal lines are not wrapped). This is the positive half — the
      screens need a stated layout rule, not one more line each.
      Fix: `D-212`. The rule is stated once, in the pure layout kernel, and applied at the seams
      every screen already passes through rather than screen by screen. `tui_layout.separate`
      joins blocks with exactly one blank line and drops a block that turned out to be empty;
      `tui_layout.action_prompt` puts the facts, one blank line, then the single line saying what
      a key press will do, and nothing after it. `is_action_prompt` recognises that line from the
      line itself — a sentence naming a key — so `CanonicalScreenSource.lines` can lift whatever
      prompt a screen wrote and re-place it last, under the notice it is about. Four review
      prompts were reworded to stop saying "below" about a plan that is now above them, and the
      two Source Sync screens were regrouped into what it is / where it stands / what it will do /
      the evidence.
      Evidence: `tests/action_prompt_layout_test.py` — the rule as a sweep over every Consumer and
      Maintainer screen (with and without a notice on it), a Hypothesis property that a join never
      doubles a blank and never loses a line, and the three maintainer reviews the sweep cannot
      reach without their typed views, in every presentation profile.
      Mutation (`D-091`): dropping the blank in `action_prompt`, joining without a blank in
      `separate`, keeping a block's trailing blank, restoring the old `(*body, "", *notice)` order
      in `lines`, and un-grouping either Source Sync screen each turn the suite red.
      Retest: open Sources → `s`. Screen 33 should read as four groups with `Press Enter to
      synchronize.` alone at the bottom; press Enter and screen 34 should be grouped the same way.
      Then open Registry → Rebuild → pick a stage → Enter: the plan comes first and the prompt is
      the last line under it.

- [x] **QA-030 — The Candidates list does not hold its columns.**
      Stage: reviewing Candidates after a sync
      Surface: Candidates (35); check the other tabular lists for the same defect
      Severity: medium
      Blocks current stage: no
      Reproduction: sync two Sources so the list holds both `mcp/aart-e2e-mcp` and
      `skill/verification-before-completion`, then open screen 35
      Expected: `STATUS`, `ARTIFACT`, `VERSION`, `SOURCE` stay aligned; a name too long for its
      column is truncated, and the row under the cursor is shown in full below the list
      Observed: the header is aligned but a long artifact name pushes `VERSION` and `SOURCE` out
      of their columns, so the rows no longer line up with the header
      Operator's words: "powinno wszystko być w kolumnach, a nie taki przepchany tekst; powinno
      najwyżej ucinać nazwy, ale jak się najedzie kursorem, to pod spodem jest całość"
      Evidence:
      ```
      STATUS               ARTIFACT                 VERSION       SOURCE
      > New                mcp/aart-e2e-mcp         1.0.0         aart-test-mcp
        New                skill/verification-before-completion 1.0.0         superpowers-test
      ```
      Fix: `D-213`. The header is now a row of the same grid rather than a hand-spaced string, and
      every row is laid out by `tui_layout.columns`, so a name longer than its column is cut there
      instead of pushing the columns after it out of line. Cutting is honest because the row under
      the cursor is repeated in full underneath, in a `field_block`; that block is also where the
      verbose per-row evidence line went, since a detail line under every row was part of the
      density being reported. Screen 47's selectable rows had the same defect without a header and
      were put on the same grid.
      Evidence: `tests/tabular_list_columns_test.py` — the operator's own two rows, an oversized
      name that must be cut, the focused row repeated in full, an unfocused one that must not be,
      and a Hypothesis property that the grid holds for any set of names within the content measure.
      Mutation (`D-091`): hand-spaced padding, a header outside the grid, no focused block, the
      first row expanded instead of the focused one, and double-space concatenation on screen 47
      each turn the suite red.
      Retest: sync both Sources, open Candidates (35), and move the cursor. Every column reads down;
      a long name ends in `…` and appears in full under `Under the cursor:`.

- [x] **QA-031 — Promotion baseline refusal does not explain the unpublished Registry change.**
      Stage: promoting the second Candidate during the real Registry walkthrough
      Surface: Registry Diff (43)
      Severity: high
      Blocks current stage: yes, until the preceding Registry commit is published and synchronized
      Reproduction: promote `skill/verification-before-completion@1.0.0` into the local Registry,
      leave that commit on `qa/publish-v1` without publishing it, then review promotion of
      `mcp/aart-e2e-mcp@1.0.0` against the Registry still synchronized from remote `main`
      Expected: the safety refusal remains, but it identifies the local unpublished Registry
      change and explains the sequence in product terms: publish/review the prior change, update
      the checkout, synchronize the Registry, then review this promotion again
      Observed: screen 43 first shows a complete five-path transaction, then says only `registry
      workspace does not match the synchronized approved baseline` and `synchronize or restore the
      registry checkout`. It does not say what differs or that the preceding promotion is the
      difference, so the operator cannot tell whether to publish, discard, rebuild or synchronize
      Evidence: the lab checkout is clean at local `cc7c01d` on `qa/publish-v1`, containing the
      Skill promotion; `origin/main` and the synchronized Registry are still at `027ba7f`. The
      refusal is therefore correct, but its diagnosis and TUI recovery are not actionable.
      Note: do not weaken the baseline equality check. The future increment must first distinguish
      an unpublished local promotion, a stale checkout, the wrong workspace root and unrelated
      drift; no `aart ...` command text may enter the TUI.
      Fix: `D-214`. The configured promotion seam now observes the real Git checkout only when the
      exact snapshot comparison refuses. A clean descendant is named as unpublished work and gives
      the Git review/merge → local update → Registry synchronization sequence; a clean ancestor,
      uncommitted managed-path drift and a different Git origin each receive their own diagnosis.
      Evidence: `tests/registry_baseline_diagnosis_test.py` builds all four states in temporary Git
      repositories. Removing the observed diagnosis from the configured promotion call turns all
      four red; the 1612-test focused set plus 639 subtests is green.

- [ ] **QA-032 — A Registry produced by TUI promotion fails its generated GitHub Actions.**
      Stage: publishing the first promoted artifact through Registry PR #1
      Surface: generated `.github/workflows/aart-registry.yml`
      Severity: blocking
      Blocks current stage: yes, unless the known false-negative checks are consciously bypassed
      Reproduction: promote `skill/verification-before-completion@1.0.0` through the TUI, push the
      resulting clean commit and open a PR; observe both `registry-quality (minimum)` and
      `registry-quality (latest)`
      Expected: the generated CI validates the same versioned approved-Registry representation the
      canonical TUI promotion writes, and a public consumer would accept
      Observed: both jobs run the legacy workspace commands. `registry validate` reports a missing
      unversioned `artifact.json` plus stale `aart.lock.json`/`aart.index.json`; `registry lock`,
      `build`, `audit` and `test` fail for the same representation mismatch
      Evidence: public `source add --kind registry-git` over remote branch `qa/publish-v1` accepts
      exact commit `cc7c01d` as healthy, while generated run `34341007222` fails. This is B-057's
      remaining command disagreement reaching the real publication gate, so it is critical now.
      Note: the fix belongs in the generated workflow/template and its public validation command,
      not in weakening promoted-Registry validation or teaching promotion to write a second legacy
      representation.
      Fix: the six generated verbs now dispatch on the representation they are given instead of
      assuming the authoring workspace (`D-208`). `is_promoted_registry` recognizes the approved
      shape by `registry/versions/`; `validate` drops the compiled-lock requirement for it because
      its version records already carry those digests; `build` rebuilds exactly the two derived
      catalogs; `lock` becomes a read-only prepared curation, because approved versions are pinned
      by their own records; and `publish` chains the same build, validate and audit without a lock
      half. The generated workflow and its verbs are unchanged, so registries already scaffolded
      keep working.
      Evidence: `tests/promoted_registry_maintenance_e2e_test.py` builds the workspace through the
      public `registry init` → `registry scan` → `registry promote --yes` chain and runs the six
      verbs the generated workflow runs, in its order. It also holds that maintenance never writes
      `aart.lock.json` or `aart.index.json` (`B-057`: one representation, not both), that `build`
      restores a damaged catalog, and that a damaged version record is still refused.
      Retest: promote through the TUI, push the resulting commit and open the Registry PR; both
      `registry-quality` jobs must pass over the promoted representation.

- [ ] **QA-025 — Re-running a registry's generated files exists in the TUI but rejects its output.**
      Stage: after promoting, adopting or editing anything in the registry checkout
      Surface: Registry Maintainer → Rebuild (46h/46i)
      Severity: blocking
      Blocks current stage: yes; skip Rebuild during discovery
      Reproduction: promote a Candidate through the TUI, then choose `b`, `Everything, in order`,
      Enter to review and Enter to run
      Expected: the canonical `lock → build → validate → audit` maintenance sequence accepts the
      same versioned Registry representation the TUI promotion writes
      Observed: `lock` immediately refuses because legacy `artifact.json` is missing, so no later
      stage runs. The action has a TUI home, but the underlying authority is incompatible with the
      Registry it is supposed to maintain.
      Retest outcome: FAILED on the real promoted Registry. The earlier focused fixture proved the
      route and ordering but never supplied canonical promotion output. Reopened under B-099 and
      joined to QA-032/B-057 in CP-19 step 9.
      Fix: Rebuild's port is `refresh_registry_workspace`, which runs the same four verbs through
      the same curation authority the CLI uses, so the representation dispatch of `QA-032` repairs
      it at the same seam rather than in a second place (`D-208`).
      Evidence: `test_screen_46_rebuilds_the_registry_a_promotion_left_behind` calls that port over
      a really promoted checkout and holds that all four stages pass in canonical order.
      Retest: promote a Candidate through the TUI, then `b` → `Everything, in order` → Enter →
      Enter, and confirm the run completes.

- [ ] **QA-033 — A refused run remains on a stale confirmation screen.**
      Stage: Registry maintenance after a canonical promotion
      Surface: Review Rebuild (46i) after execution has already stopped
      Severity: high
      Blocks current stage: no; pressing Esc twice still reaches Registry Maintainer
      Reproduction: Registry Maintainer → `b` → choose the whole rebuild → Enter to review → Enter
      to run; let `lock` refuse because the canonical promoted Registry has no legacy
      `artifact.json`
      Expected: the screen clearly becomes a finished/refused result, removes the confirmation
      prompt and offers one honest route back to Registry Maintainer or to prepare a fresh retry
      Observed: the body says the run stopped, but the title remains `Review Rebuild`, the header
      still says `press Enter to start it`, and the footer still advertises `Enter Confirm`. The
      action adapter has already cleared its pending run, so another Enter can only answer
      `nothing was prepared for this action; review it again`.
      Note: QA-032 explains this particular lock refusal, but the stale terminal state is a
      separate reducer/result-screen defect and must hold for every failed action.
      Fix: a refused run now says so. `_failed` emits `ACTION_FAILED` instead of an empty
      `ACTION_RECORDED`, which the reducer could only read as no transition at all; the reducer
      clears the plan and records `failed_action`, so the review it was confirmed from becomes that
      attempt's terminal result without moving off the refusal (`D-209`). The footer offers
      `Enter Back to list` instead of `Enter Confirm`, Enter navigates to the screen that owns the
      run, and the heading says the run did not happen. Leaving the screen ends the terminal state,
      so the next review is a review again.
      Evidence: `tests/failed_action_terminal_state_test.py` holds all of it across four confirmed
      action kinds, not Registry rebuild alone, plus the frame the operator actually read and the
      `QA-024` claim that an unconfirmed review still asks for its confirmation.
      Retest: run a Registry action that refuses, and confirm the screen becomes a result with one
      route back and no confirmation prompt.

- [x] **QA-035 — Dashboard sections have no visual hierarchy.**
      Stage: reading the main Dashboard
      Surface: Dashboard navigation, focused-option explanation and status summary
      Severity: medium
      Blocks current stage: no
      Expected: Navigation, the focused item's explanation and the AART status summary are visibly
      separate regions, using a restrained separator and whitespace; Recent activity is separated
      from the counters
      Observed: `About Updates:`, its sentence, the AART summary, counters and activity run together
      as one text block. The operator proposed a simple horizontal divider around the focused-item
      explanation rather than more labels.
      Fix: `D-216`. The focused explanation is now bounded by the shared restrained rule, without
      an extra `About` label, and Recent activity is a separate summary block.

- [x] **QA-036 — Multi-step workflows do not show progress or what comes next.**
      Stage: Candidate review/promotion and every other wizard-like sequence
      Surface: page title/chrome across the workflow
      Severity: high
      Blocks current stage: no, but operators cannot orient themselves safely
      Expected: every multi-step flow shows a compact path such as Candidate → Details → Diff →
      Promotion Review, marks completed/current/upcoming steps with clear status icons and derives
      it from the same navigation state as the reducer
      Observed: only the current title, for example `AART / Promotion Review`, is visible. The user
      cannot tell how they arrived, what was accepted or what remains.
      Fix: `D-215`. Workflow routes are application declarations checked against the live
      navigation graph. The frame projects visited/current/upcoming screens as `✓`/`▸`/`·`, wraps
      the Candidate path at the shared content measure and stays absent on owning lists.

- [x] **QA-037 — Esc in the Candidate workflow loses the Candidate context.**
      Stage: backing up from Candidate review/promotion
      Surface: Candidate detail/diff/validation/promotion history
      Severity: high
      Blocks current stage: intermittently; the flow must be restarted from Candidates
      Reproduction: enter a Candidate's workflow, advance through review screens, then press Esc
      Expected: return to the preceding step with the same focused Candidate and already-observed
      state
      Observed: the previous screen reports `That Candidate is not available.` The back stack keeps
      the screen but loses or replaces the stable Candidate focus.
      Fix: `D-215`. Back keeps the stable focus only when both screens belong to the same declared
      workflow; ordinary detail-to-list browsing retains the old focus-clearing behavior. Every
      reverse edge of Candidate promotion is covered, including a rendered prior screen.

- [x] **QA-038 — The `?` help view is a dense multi-command grid.**
      Stage: asking for keyboard help from any screen
      Surface: global help overlay
      Severity: medium
      Blocks current stage: no
      Expected: one key or closely related key pair per line, with consistent `[Key] Action`
      formatting and enough spacing to scan vertically
      Observed: multiple unrelated commands share each line (`enter`, `esc`, install, repair and
      uninstall among them), so the help is harder to read than the footer it expands.
      Fix: `D-216`. `Keyboard help` renders one `[Key] Action` (or one related key pair) per line.

- [x] **QA-040 — Registry rows are an unreadable wall of text.**
      Stage: reviewing configured availability
      Surface: Registries (21)
      Severity: medium
      Blocks current stage: no
      Expected: one visually bounded row/card per configured item, blank space between items and a
      clear separation between identity/status and explanatory detail
      Observed: aliases, artifact counts, action prose and Source-vs-Registry explanation run
      together. Three configured items become a long paragraph with no reliable row boundary.
      Fix: `D-216`. Add Registry and every configured row are separate compact cards; identity is
      the card head and its facts are indented beneath it.

- [x] **QA-041 — The contextual footer is functionally correct but visually fragmented.**
      Stage: every screen after QA-026
      Surface: `Keys here` / `Keys always` shell chrome
      Severity: medium
      Blocks current stage: no
      Expected: a compact footer with a subtle separator and keycaps such as `[Enter] Open`, with
      local and global actions adjacent and consistently aligned
      Observed: `Keys here` and `Keys always` are separated by a large empty region, repeat labels
      and read as unrelated blocks. The hierarchy is noisy despite the correct contextual content.
      Fix: `D-216`. One shared separator introduces adjacent, width-bounded `[Key] Action` lines;
      contextual bindings still precede global ones without the two repeated headings.

- [x] **QA-042 — Connected rows on Registries do not display the cursor.**
      Stage: selecting a Registry to synchronize or inspect
      Surface: Registries (21)
      Severity: high
      Blocks current stage: no, but actions can target an item the operator cannot identify
      Reproduction: move down from `[ Add Registry ]` across connected rows
      Expected: the focused connected row carries the same visible `>` marker as Add Registry
      Observed: only `[ Add Registry ]` renders the cursor. Connected rows are rendered without
      focus, so the user cannot see which alias will receive `s` or Enter.
      Fix: `D-216`. The screen passes its stable row identity into the card renderer; exactly the
      focused Registry head receives `>`.

### Fixed — awaiting manual retest (earlier batches)

- [ ] **QA-039 — Vendored and Referenced promotion modes are unexplained.**
      Stage: choosing how a Candidate enters a Registry
      Surface: Promotion Mode and Promotion Review
      Severity: high
      Blocks current stage: no, but the choice changes what the Registry owns and can install
      Expected: concise definitions and consequences for both modes, the currently selected mode,
      and a key label that says what `m` changes
      Observed: the screen named `vendored` or `referenced` without explaining ownership, payload
      availability or the upstream relationship, and labelled `m` only as `Mode`.
      Fix: `D-217`. The domain now owns the consequences of both promotion modes. Promotion Review
      projects both choices, marks the active one, labels Vendored as the enterprise default and
      explains Registry ownership, install availability and upstream dependence before confirmation.
      The footer names `m` as `Toggle mode`.
      Evidence: projection and renderer tests were RED on the missing choices and explanation. A
      semantic mutation removing Vendored's enterprise-default fact turns the exact explanation
      test red; the focused 1513-test family is green.
      Retest: open a Candidate promotion review, read both complete choices, press `m`, and confirm
      that only the selected marker changes while both consequence explanations remain visible.

- [ ] **QA-043 — Registries exposes authoring Sources as actionable rows and leaks an internal error.**
      Stage: browsing consumer Registry connections
      Surface: Registries (21)
      Severity: high
      Blocks current stage: no
      Reproduction: configure one `registry-git` plus authoring Sources, then open Registries
      Expected: the Registry screen contains Registry connections only; authoring Sources remain on
      Maintainer Sources and cannot advertise a Registry-only detail action here
      Observed: authoring Sources appeared as connected rows with `Actions: details`, but Enter could
      not open them and exposed `no connected registry here is 21-registries`.
      Fix: `D-218`. The screen-21 projection now admits only `registry-git` connections. Its sync
      request always targets the visible Registry row rather than stale navigation focus; Source
      records remain available through their own Maintainer surface.
      Evidence: an authoring Source placed before a Registry cannot hide the later Registry, and a
      Hypothesis property holds the sync target for every single-line stale focus. Mutating the
      filter from `continue` to `break`, or removing Registry Sync from the row-owned actions, turns
      the corresponding test red. The focused 1513-test family is green.
      Retest: configure Registry and authoring Source entries, open Registries, and confirm only the
      Registry connection appears and `s` refreshes the visibly focused Registry.

- [ ] **QA-034 — A Git-merged promotion never becomes visible in Marketplace.**
      Stage: first clean Consumer after Registry PR #1 was merged and synchronized
      Surface: Marketplace in TUI and `marketplace list --json`
      Severity: blocking
      Blocks current stage: yes; install/update/repair acceptance cannot start
      Reproduction: merge the TUI promotion commit into the configured Registry's `main`, connect
      a clean consumer to that branch, then open Marketplace
      Expected: merging into the configured approved branch is the publication boundary, so the
      promoted artifact becomes an approved Marketplace offer
      Observed: Source health is `healthy` at merged commit `f37d182`, and the synchronized tree
      contains the version, manifest and payload, but Marketplace returns `artifacts: []`. The
      durable record still says `publication: promoted-local`; the consumer admits only
      `PublicationStage.PUBLISHED`, and no public Git publication path changes that field.
      Evidence: even the first merged Skill is absent, independently of the not-yet-published MCP
      and adopted Skill. CP-17's Git-backed fixture called `publish_registry_version` internally
      before materializing its repository, so it never exercised this missing public transition.
      Fix: publication is now read where INV-242 puts it — presence on the branch the consumer
      configured — instead of waiting for a durable field no public workflow writes.
      `load_published_registry_versions` applies the transition once, at the four consumer read
      seams (offers, selection, installation re-read, offline readiness); the maintainer's own
      workspace, source validation and promotion planning keep the record as written (`D-207`).
      Evidence: `tests/git_publication_transition_e2e_test.py` promotes with the real transaction,
      commits the second promotion to a review branch, merges it with `git merge --no-ff`,
      synchronizes and reads Marketplace and an install receipt. It was RED at
      `[] != ['company/skill/code-review@1.2.0']`, the exact symptom reported here.
      Retest: connect the clean Consumer to the merged Registry `main`, `source sync`, open
      Marketplace, and confirm the promoted Skill is offered and installable.

- [ ] **QA-026 — The footer does not name the keys the current screen actually has.**
      Stage: every screen; found while walking Maintainer Mode
      Surface: shell chrome, every screen
      Severity: high
      Blocks current stage: no, but it makes every other finding harder to report
      Reproduction: open any screen with its own actions — 21 (`a`, `s`), 31 (`a`, `s`), 46
      (`n`, `b`, `s`, `u`), 35 (`f`, `c`), 37 (`f`) — and read the footer
      Expected: the footer lists the keys usable **here**, view-specific ones first, then the
      global movement/back/help/quit set
      Observed: the footer was one fixed legend. A screen's own keys lived in a body line the
      screen happened to draw, or nowhere at all.
      Fix: yes — contextual letter bindings now carry their displayed meaning beside the event
      they produce, and both `key_event` and the footer read that one table. Structural keys derive
      from the reducer's searchable/selectable/form/review sets. Local actions are drawn first,
      global movement/back/help/quit second; a screen no longer advertises Space when it cannot
      select anything. Screen 46's duplicate body-level `Actions:` header is gone (D-202).

- [ ] **QA-024 — Two review screens could not be confirmed, and no review drew its plan.**
      Stage: adding a Source and initializing a registry from the TUI
      Surface: Add Source review (31b), Initialize Registry review (46b)
      Severity: blocking
      Blocks current stage: yes
      Reproduction: fill in Add Source or Initialize Registry, continue to the review, press Enter
      Expected: the review shows the plan, and Enter runs it
      Observed: the review showed its prompt with nothing under it, and Enter did nothing at all —
      the flows could be typed and reviewed but never confirmed
      Evidence: `key_event`'s confirmation list never named those two screens, and `_ANSWERABLE`
      hand-listed five review screens while deriving the request screens, so any review or result
      screen off that list drew no notice
      Fix: yes — both screens confirm, and the notice set is now derived from both action tables
      instead of hand-listed. Found by walking the keys in a headless shell rather than by another
      adapter test, which is also how the wrong row reached the first rebuild request (`D-201`).
- [ ] **QA-022 — The TUI could not install any MCP artifact once Codex was measured.**
      Stage: installing the MCP from Marketplace in the persistent shell
      Surface: Marketplace → Install (screens 05–10)
      Severity: blocking
      Blocks current stage: yes
      Reproduction: select any `mcp` offer in the TUI on a machine whose measured harness set
      includes Codex, and open the install review
      Expected: the plan registers the server with the harnesses that can host one at this scope
      Observed: the whole placement was refused with `no measured MCP target for harness 'codex'
      at project scope`, so no MCP artifact could be installed for Claude or Tabnine either
      Evidence: the shell's profiles are the union of every measured table (`D-193`), and Codex
      registers servers only at user scope (`D-196`); `placement_for` refused a profile it could
      not place, which is correct for `--profile` and wrong for a set nobody asked for
      Fix: yes — `placement_for` now takes `profiles_requested`, the shell passes `False`, and a
      measured harness that cannot host this kind at this scope is left out of that artifact's
      plan instead of refusing it. A harness no table names is still refused by name, and a
      Selection every profile left out is still refused (D-198, 13 tests).
- [ ] **QA-023 — Settings offers an installation scope the TUI then ignores.**
      Stage: installing at user scope from the shell
      Surface: Settings (screen 28) → Marketplace → Install
      Severity: high
      Blocks current stage: yes, for user-mode acceptance
      Reproduction: set `Default scope: User` on screen 28, then install any artifact
      Expected: the artifact lands under the user's home
      Observed: it landed in the project; the preference was persisted, redrawn and never read
      Evidence: composition built the installation host with `Scope.PROJECT` hard-coded
      Fix: yes — the host's scope is derived from the stored preference at the point of use, so it
      applies in the session that changed it; each review records the host it was prepared against
      and its confirmation acts on that one; the maintainer registry root no longer follows the
      installation scope (D-199, 1 end-to-end test through the real shell).

- [ ] **QA-011 — Canonical installation cannot target OpenCode.**
      Stage: installing the Skill and MCP into the locally installed OpenCode 1.18.29
      Surface: Marketplace/TUI and `marketplace install --profile opencode`
      Severity: high
      Blocks current stage: yes, for OpenCode acceptance; no, for Claude/Tabnine
      Reproduction: select an artifact declaring OpenCode compatibility or request profile
      `opencode` explicitly
      Expected: reviewed effects use OpenCode's measured Skill, AGENTS.md and MCP configuration
      contracts
      Observed: TUI targets only Claude/Tabnine; the CLI refuses every canonical target as
      unmeasured and writes nothing
      Evidence: OpenCode 1.18.29 is installed locally; all `domain/harness.py` target lookups for
      OpenCode refuse, while the dormant `profiles/builtin.py` values are not canonical authority
      Fix: yes — Skills, instructions and MCP are measured and installable at both scopes
      (`.opencode/skills/<name>`, `.config/opencode/skills/<name>`, `AGENTS.md`,
      `.config/opencode/AGENTS.md`, the `mcp` key of `opencode.json` and
      `.config/opencode/opencode.json`), and OpenCode is selectable in the TUI through the union
      harness set (D-194, 9 tests, two of which run the installed OpenCode). MCP needed a new
      `McpEntryShape` because a local server here is `{"type": "local", "command": [...]}` rather
      than a command string beside `args`. Guidelines and hooks stay refused by name because that
      build documents no guidelines directory and its event model was not measured.
      Verified end to end (D-197): an authored server compiled, published, planned, installed and
      then started from the vector that landed in `opencode.json`, and `marketplace install
      --profile opencode --yes` landing a Skill in `.opencode/skills/<name>`. That verification
      found and fixed a reader defect that made every OpenCode MCP install end partially-applied.
- [ ] **QA-012 — Canonical installation cannot target Codex.**
      Stage: installing the Skill and MCP into the locally installed Codex CLI 0.152.0
      Surface: Marketplace/TUI and `marketplace install --profile codex`
      Severity: high
      Blocks current stage: yes, for Codex acceptance; no, for Claude/Tabnine
      Reproduction: select an artifact declaring Codex compatibility or request profile `codex`
      explicitly
      Expected: reviewed effects use Codex's measured Skill roots, layered `AGENTS.md` and
      native `mcp_servers` configuration contracts
      Observed: TUI targets only Claude/Tabnine; the CLI has no canonical Codex target and refuses
      the requested placement without writing
      Evidence: Codex CLI 0.152.0 is installed locally; Codex is absent from every canonical target
      table and from the dormant built-in profile registry
      Fix: partial — Skills and instructions are measured and installable at both scopes
      (`.codex/skills/<name>`, `AGENTS.md`, `.codex/AGENTS.md`), and harness selection now derives
      from every measured table rather than from `MCP_TARGETS` alone, so Codex is selectable
      (D-193, 10 tests, two of which run the installed Codex). The expectation above named
      `.agents/skills`; measurement found that is the cross-vendor interop root Codex also migrates
      other agents from, and `.codex/skills` is its own. MCP stays refused by name because Codex
      writes its own MCP configuration now (D-196, B-096 closed): `codex mcp add`/`remove`/`list
      --json` were measured leaving an operator's comments, unrelated keys and other servers
      byte-identical, so the user-scope target delegates to them and a missing Codex is named
      rather than reported as registered. Verified end to end: Codex lists the server the install
      registered and the launcher it was handed starts the author's server. User scope only —
      `codex mcp add` offers no project flag, so project scope is still refused by name. Hooks are
      measured and still refused (B-097): `codex
      features list` reports them stable and enabled, but they are configured through a path in
      `config.toml`, project-local hooks are disabled until the operator trusts the project, and
      every new or changed hook is held for interactive review — a file AART wrote would not run.

- [ ] **QA-021 — Registry cannot one-off scan YAML manifests and vendor selected artifacts.**
      Stage: optional artifact-scoped onboarding from an external repository
      Surface: Maintainer → Registry
      Severity: high
      Blocks current monitored-Source stage: no; this is a second required onboarding model
      Reproduction: provide the Superpowers URL/ref without adding it as a configured Source, then
      try to discover its `aart.yaml` files and select one Skill for Registry ownership
      Expected: `Scan Repository` finds only explicit YAML/JSON manifests, presents selectable
      artifacts, and vendors only each selected manifest's `payload.include` files with pinned
      provenance; the repository is not saved as a Source
      Observed: `registry scan` reads YAML but only prints a local-checkout result, `discover` looks
      for conventional shapes, and `vendor` ignores YAML and requires repeated metadata flags
      Evidence: no public command or TUI action composes author-manifest discovery with selected
      vendoring; existing commands each stop at a different boundary
      Fix: complete — `io/registry_adoption.py` composes scan → selection → atomic vendored
      adoption with pinned provenance and saves no Source (D-187, 14 tests). Maintainer Registry
      exposes that flow as `s` Scan Repository: form 46c, selectable result 46d and exact local
      adoption review 46e (D-188, 8 tests). Adopted packages retain the moving branch/tag as
      immutable namespaced provenance (D-189). The read-only check distinguishes unchanged,
      changed, missing, unreachable and invalid manifests, and prepares a new immutable version
      only after an upstream version bump (D-190, 8 tests), reached as `u` Check upstream on
      screens 46f/46g (D-191). `aart registry adopt` and `aart registry check-upstream` are the
      machine-complete CLI projection: scan/review/apply phases, `--expect` verified whenever
      given, sorted listings (D-192, 8 tests).

- [ ] **QA-016 — A new Registry cannot be initialized through Maintainer TUI.** Screen 46 now
      offers `n` Initialize Registry with its own id/name/reporting/commit form (46a) and an exact
      review (46b) that names all five stages. One confirmation runs init → lock → build → validate
      → audit, fail-fast, through the same curation service and planning gates the CLI drives, and
      draws stage by stage what each did. The local commit is opt-in and part of the review digest;
      nothing is ever pushed or merged. B-090/D-186.
- [ ] **QA-015 — Audit of a valid empty Registry reports non-actionable warnings as problems.** The
      provenance-coverage and installation-risk findings are now `info` notes when the registry
      holds neither an external reference nor an owned package, and warnings again as soon as
      either exists. `registry init` also stopped warning that the usage-reporting templates were
      inert, because D-180 no longer writes them. B-089/D-181.
- [ ] **QA-014 — Successful `registry init --yes` output is overwhelming and repetitive.** The
      outcome no longer repeats the warnings its review just stated, drops the `observed:` line
      when it equals the headline's own count, and the follow-up commands are the AART pipeline
      without the `git diff` line that re-listed every reviewed path. `--json` still carries review
      and outcome in full. B-088/D-182.
- [ ] **QA-019 — Git Source rejects a symlink without naming what is unsafe or how to proceed.**
      The refusal is unchanged and still fail-closed; it now names the entry kind it observed —
      symbolic link, submodule, unsupported Git mode, unsafe path or excessive depth — and carries
      remediation for each. The link target is never printed. A submodule is also no longer
      reported as a malformed listing. B-093/D-183.
- [ ] **QA-018 — A refused Registry connection leaves the user stranded on Review Registry.** A
      declined preparation now returns to the screen the action was asked from — for Add Registry
      the form, with the typed values intact — and clears the pending action, so a later Enter
      cannot reach a confirmation. The refusal is drawn on that screen, because `_ANSWERABLE` now
      derives the request origins from `_ACTION_REVIEW`. B-092/D-184.
- [ ] **QA-017 — TUI exposes raw CLI remediation commands after adding a Registry.** `Diagnostic`
      gained `interactive`, the same next step written for somebody already inside the application;
      `_refusal` renders that, or the remediation steps that name no command. The duplicate alias,
      duplicate origin, changed-identity and unsynchronized-source refusals all carry prose. A
      sweep over every screen asserts no frame draws an `aart <verb>` command, and a Hypothesis
      property holds the universal half. CLI and JSON keep their exact remediation. B-091/D-185.
- [ ] **QA-010 — Consumer TUI cannot synchronize a configured Registry.** Screen 21 now routes `s`
      to its own Refresh Registry action with a review (21c) that names the ref to be fetched,
      states that a refresh is not an artifact update, and warns that a failed fetch keeps the
      snapshot already held. Execution goes through `sync_configured_sources`, the same transaction
      as `aart source sync`. B-084/D-179.
- [ ] **QA-013 — `registry init` generates unused usage-reporting automation by default.** The
      usage-reporting Issue Form and its two workflows are now generated only when
      `--usage-reporting-repository` names a destination, and the generated README describes the
      registry that was actually created. B-087/D-180.
- [ ] **QA-020 — A YAML authoring repository cannot enter the monitored Source → Candidate flow.**
      Authoring-Source admission is now manifest discovery rather than native-package validation:
      `source add --kind source-git` admits a repository that declares at least one explicit
      `aart.yaml`/`aart.json`, keeps the native-package rule for a tree that declares
      `aart-source.json`, and still refuses a tree that declares neither. Transport, identity,
      symlink, special-file and last-known-good boundaries are unchanged. An authoring Source
      contributes no Marketplace offers and cannot empty the consumer's Marketplace. B-094/D-176.
- [ ] **QA-009 — Maintainer TUI cannot add an authoring Source.** Screen 31 now offers `a` Add
      Source with its own alias/kind/location/ref form (31a), an exact Review (31b) and confirmed
      execution through the canonical source-add transaction. It accepts only `source-git` and
      `source-local`; `registry-git` stays screen 21a's. B-083/D-177.
- [ ] **QA-001 — The TUI does not advertise its navigation keys.** The permanent footer now names
      arrows, Enter, Space, Esc, help and quit, and remains pinned below long content. B-077/D-168.
- [ ] **QA-002 — Esc returns to the previous screen noticeably slowly.** The curses escape-prefix
      delay is now bounded at 50 ms. B-078/D-169.
- [ ] **QA-003 — Dashboard destinations do not explain what they mean.** Moving the cursor now
      shows a short description of the highlighted destination. B-079/D-170.
- [ ] **QA-004 — An empty first run does not explain AART or what to do next.** A first-run panel
      now appears above navigation and points to Registry onboarding. B-080/D-170.
- [ ] **QA-005 — Old user subscriptions look like built-in registries.** The two persisted August
      subscriptions and their managed snapshots were removed through `aart source remove`; a fresh
      public list is empty. B-081.
- [ ] **QA-006 — Registry cannot be added from the TUI.** Screen 21 now provides Add Registry with
      alias, credential-free Git URL, branch/tag, default choice, exact Review and confirmed
      connection through the canonical source-add transaction. B-082/D-171.
- [ ] **QA-007 — The permanent legend omits Space.** It now states `Space select/toggle`.
- [ ] **QA-008 — First-run setup guidance is visually buried below navigation.** It now appears
      first as a distinct `SETUP REQUIRED` callout above the menu.

### Confirmed

Move an entry here only after manual retest, preserving its checkbox, result date and fixing commit.

---

Backup implementation tracker for that program. Its GitHub issues were the source of truth for
discussion and status *there*; in this repository they are neither, and nothing here should be
kept aligned with them.

## Post-1.0.0 follow-ups

Execution order, acceptance criteria, and handoff steps live in
[`docs/plan/PLAN-post-v1-catalog-boundary.md`](docs/plan/PLAN-post-v1-catalog-boundary.md).

- [ ] Create/link a new post-1.0 GitHub issue for CB01 before its review PR. Issue #27 is the
      completed historical 1.0 program, not the source of truth for this follow-up.
- [ ] Expose the full canonical non-interactive lifecycle for agents: qualified marketplace
      install, update, uninstall, and setup. `aart source add/list` and `aart marketplace list`
      bootstrap and inspect the marketplace, while retained `list/install/update/setup --source`
      commands are explicit 0.1 compatibility adapters.
- [ ] Add a configuration-scoped lock and expected-digest compare-and-swap write path for source
      additions and source-selection changes. A fresh re-read after sync is not enough to prevent
      a concurrent configuration writer from being lost.
- [ ] Update the registry-owned `agent-artifacts` and `author-aart-installer` skills in a separate
      `M1F1/agent-artifacts-registry` PR: rewrite the stale embedded-catalog instructions, bump
      both artifact versions to `2.0.0`, remove invalid legacy provenance, and regenerate lock and
      index through registry gates. The same PR must teach `author-aart-installer` the only
      supported recipe revision — `schema_version`/`protocol_version` both `2`, the required
      package-root `SETUP.md` written before the recipe, and the
      `# AART manual setup: see ../SETUP.md` header on any custom entrypoint. Worked packages to
      copy from: `tests/fixtures/setup-routes/`.
- [ ] Define a new versioned release contract before the next AART release. Preserve the immutable
      `v1.0.0` schema-freeze/release evidence rather than rewriting it for post-release changes.

## [#27 — AART 1.0: federated artifact compiler and optional registries](https://github.com/M1F1/agent-artifacts/issues/27)

Product requirements:
[`docs/product/PRD-aart-1.0.md`](docs/product/PRD-aart-1.0.md). Technical contract:
[`docs/design/SPEC-aart-1.0.md`](docs/design/SPEC-aart-1.0.md). Task sequencing and quality gates:
[`PLAN.md`](PLAN.md). Durable execution state: [`PROGRESS.md`](PROGRESS.md).

### Architecture and release

- [x] Separate the AART compiler/tool repository from operational artifact registries.
- [x] Define a federated marketplace with zero or more direct sources/registries and an optional
      default registry.
- [x] Define native references, materialized foreign imports, and direct source subscriptions.
- [x] Treat importers as deterministic Maintainer-time migration/curation tools, never consumer
      runtime conversion.
- [x] Write the AART 1.0 PRD and technical specification.
- [x] Start implementation versions at `1.0.0a1`; do not tag `1.0.0` before the release gates pass.
- [x] Freeze the 1.0 schemas, publish compatibility/migration/release evidence, and finalize stable
      `1.0.0` only through the fail-closed REL01 checklist.

### Protocol and compiler

- [x] Implement strict JSON schemas for native sources, artifacts, provenance, and collections.
- [x] Implement strict registry, native entry, committed lock, and compiled index schemas.
- [x] Implement strict JSON schemas and canonical writers for user configuration and organization
      policy.
- [x] Implement the strict canonical installation manifest v2 schema and migration evidence model,
      documented in
      [`docs/state/installation-state-v2.md`](docs/state/installation-state-v2.md).
- [x] Implement strict schema-v1 structured command outcomes and shared terminal summaries.
- [x] Implement SemVer bounds, protocol/capability negotiation, and canonical JSON/tree digests.
- [x] Implement qualified marketplace resolution and ambiguity diagnostics without silent source
      shadowing.
- [x] Resolve user selections as source-qualified marketplace coordinates at CLI/TUI application
      boundaries; ambiguous unqualified identities fail closed.
- [x] Implement deterministic registry-input hashing, graph validation, index generation, and
      frozen registry lock resolution.
- [x] Implement typed deterministic compiler phases, accumulated diagnostics, immutable candidate
      planning, injected effect ports, and publication gating.
- [x] Supply the concrete source/compatibility/effects graph compiler on the phase framework.
- [x] Implement the closed built-in importer registry plus deterministic legacy-catalog conversion,
      provenance, loss/ambiguity checks, and stale-output validation.
- [x] Implement promotion of native direct sources into registries and locked importer reruns.
- [x] Add registry quality gates for format, validate, lock, build, audit, diff, and compatibility
      tests, documented in
      [`docs/registry/maintainer-commands-v1.md`](docs/registry/maintainer-commands-v1.md).

### Federated sources and managed store

- [x] Add user configuration for zero or more local/Git source and registry aliases, with at most
      one optional default registry.
- [x] Add organization policy for recommended/required sources, allowed Git hosts/prefixes, setup
      capabilities, minimum user-scope trust, custom setup, and reporting destinations.
- [x] Extend policy and marketplace consumption with exact company-reviewed source identity and
      effective trust evidence.
- [x] Enforce operation-specific scope/trust/setup gates in the installation and setup tasks.
- [x] Implement Git mirrors, immutable validated snapshots, atomic current pointers, health/doctor,
      concurrency control, and offline last-known-good behavior.
- [x] Implement the content-addressed artifact object store with digest verification, safe GC, and
      install/setup references.
- [x] Merge configured sources deterministically without silent shadowing and display effective
      source/trust for every artifact.

### Consumer and TUI migration

- [x] Add a source-aware canonical Copy prepare/review/finalize boundary over qualified marketplace
      items and verified immutable CAS objects, documented in
      [`canonical-copy-v1.md`](docs/installation/canonical-copy-v1.md).
- [x] Apply canonical file, tree, managed-block, and JSON merge effects transactionally; pin
      manifest-v2 evidence and a durable installed-object reference with structured no-op,
      conflict, failure, and rollback outcomes.
- [x] Add durable managed file/tree Symlinks to exact immutable CAS payloads, mixed copied merges,
      explicit atomic retarget/reference replacement, link-state evidence, and opt-in verified
      `mutable-local` developer links, documented in
      [`canonical-symlink-v1.md`](docs/installation/canonical-symlink-v1.md).
- [x] Resolve Install/Update from qualified source subscriptions and immutable objects.
- [x] Keep Copy as default and make managed Symlink target immutable store content; sync alone must
      not retarget installed artifacts.
- [x] Add canonical local status, fetch-free check, recorded-subscription update, explicit upstream
      prune, proven-effect uninstall, per-selection outcomes, scope isolation, and CAS-reference
      release, documented in
      [`canonical-lifecycle-v1.md`](docs/installation/canonical-lifecycle-v1.md).
- [x] Migrate project/user manifests, scope/profile compatibility, managed merges, uninstall proof,
      setup state, and structured outcomes to manifest v2.
- [x] Add the Sources/health stage to the persistent TUI while preserving Backspace state, basket,
      Review/Finalize, descriptions, modes, scopes, and explicit outcomes, documented in
      [`source-management-v1.md`](docs/tui/source-management-v1.md).
- [x] Migrate the User TUI to qualified federated marketplace rows, canonical multi-item
      Review/Finalize requests, verified registry security evidence, persistent cart navigation,
      and explicit no-op/partial/offline/setup outcomes, documented in
      [`consumer-marketplace-v1.md`](docs/tui/consumer-marketplace-v1.md).
- [x] Migrate canonical Maintainer TUI actions to digest-bound local-checkout plans for registry
      init/scaffold, native promotion/update, controlled foreign conversion, lock/build,
      validate/audit/diff, and explicit outcomes; retain the legacy catalog workflow without
      automatic commit/push or consumer-store writes, documented in
      [`maintainer-curation-v1.md`](docs/tui/maintainer-curation-v1.md).
- [x] Bind reviewed macOS setup recipes to source trust and artifact/recipe/plan digests, retain the
      exact CAS object, execute custom code from a verified private copy, and preserve separate
      payload/setup outcomes, documented in
      [`canonical-setup-v1.md`](docs/installation/canonical-setup-v1.md).
- [x] Keep reporting disabled without an explicit destination; route configured reports only to
      the policy-approved registry service; preview exact redacted events; isolate provider
      failures; and supply bounded registry validation/aggregation/dashboard templates, documented
      in [`usage-reporting-v1.md`](docs/reporting/usage-reporting-v1.md).

### Installation-risk assessment

- [x] Add a zero-runtime-dependency baseline that reports deterministic object/rules-digest-bound
      installation-risk evidence, explicit coverage and remediation, documented in
      [`baseline-v1.md`](docs/security/baseline-v1.md), without certifying an artifact.
- [x] Add a versioned out-of-process JSON protocol for independently installed analyzers; never
      auto-install them or import them into the AART process.
- [x] Add optional adapters/suites for applicable open-source analyzers while preserving the
      stdlib-only AART runtime.
- [x] Add digest-bound evidence indexes, freshness handling, deterministic bundle aggregation,
      and policy gates based on worst/unknown status rather than average alone, documented in
      [`attestations-v1.md`](docs/security/attestations-v1.md). Cryptographic signing remains a
      separately versioned future protocol.
- [x] Show provider, rules version, evidence age, coverage, risk range, and remediation details in
      CLI/TUI marketplace, review, maintainer, and outcome views.
- [x] Test malicious provider output, timeout, crash, stale/mismatched evidence, partial bundle
      coverage, offline behavior, and policy enforcement.

### Repositories, migration, and verification

- [x] Create the public `M1F1/agent-artifacts-registry` reference marketplace during SEP01, only
      after the deterministic export and public-content preflight pass.
- [x] Provide a confidential-content-free `aart registry init` bootstrap and minimum/latest CI
      template for a company registry.
- [x] Provide deterministic, reviewable conversion of the current top-level 0.1.x catalog into a
      canonical native source.
- [x] Promote the converted top-level 0.1.x catalog into the canonical registry layout during the
      reviewed SEP01 migration.
- [x] Add reviewed dry-run/apply/backup/rollback migration primitives for existing 0.1.x
      installation state; MIG01 supplies the final public compatibility orchestration.
- [x] Test direct-source-only, multi-registry, company-plus-team, native-reference, foreign-import,
      collision, trust, offline, concurrency, Copy/Symlink, setup, and reporting fixtures.
- [x] Test local editable and local-wheel installation without an embedded operational registry or
      checkout-relative runtime data.
- [x] Prove deleting/recreating the Python environment does not break managed artifact symlinks.
- [x] Run registry CI with the minimum supported and latest compatible AART versions.

## Completed 0.1.x TUI and installation UX

## [#15 — TUI: add User/Maintainer entry paths and maintainer workflows](https://github.com/M1F1/agent-artifacts/issues/15)

- [x] Make User/Maintainer selection the first screen in both curses and text TUI modes.
- [x] Explain each path in one line:
  - User installs, updates, and removes artifacts from subscribed/recorded catalog sources.
  - Maintainer can do the same and also curate the catalog and its upstreams.
- [x] Keep the existing profile-aware install/update/uninstall flow in User mode.
- [x] Record enough source/subscription identity for updates without asking for the repository
      again.
- [x] Add guided Maintainer workflows for:
  - adding one upstream from a GitHub URL;
  - scanning a repository/path and selecting detected artifacts to import;
  - optionally adding imported artifacts to a bundle;
  - checking all or selected tracked upstreams;
  - previewing and applying upstream updates;
  - validating the catalog before and after mutations;
  - showing artifact counts, tracked/untracked state, validation failures, and upstreams needing
    attention.
- [x] Make the active catalog checkout/source explicit and reject ambiguous catalog mutations.
- [x] End maintainer mutations with next steps such as reviewing the diff and running validation;
      never commit automatically.
- [x] Reuse Request objects and existing command/core logic instead of duplicating it in the TUI.
- [x] Cover role selection, clean quit, invalid catalog context, and upstream workflows in tests.
- [x] Document the distinction between reviewed consumer updates and maintainer catalog updates.

## [#16 — TUI: show a one-line description for every installable artifact](https://github.com/M1F1/agent-artifacts/issues/16)

- [x] Add a normalized description field to Artifact and populate it in every catalog parser.
- [x] Read descriptions from:
  - Markdown frontmatter for skills, guidelines, and memory;
  - JSON descriptors for MCP servers and hooks;
  - the existing bundle description field.
- [x] Require a non-empty, single-line, user-facing description during catalog validation.
- [x] Add concise, value-oriented descriptions to every shipped artifact and fixture.
- [x] Show descriptions for artifact and bundle rows in both TUI frontends.
- [x] Keep each selector row to one visual line, truncate with an ellipsis on narrow terminals,
      and provide a way to view the full text.
- [x] Expose the same description in human and JSON list output.
- [x] Retain descriptions after compatibility filtering and in update/uninstall views when source
      metadata is available.
- [x] Test all artifact types, bundles, invalid descriptions, narrow terminals, and JSON output.
- [x] Document description authoring conventions for catalog maintainers.

## [#17 — TUI: provide explicit outcome summaries for every action](https://github.com/M1F1/agent-artifacts/issues/17)

- [x] Introduce a shared structured action-result/summary contract; do not parse command stdout in
      the TUI.
- [x] Always leave a visible final summary after curses exits and in the text fallback.
- [x] Report, at minimum:
  - install: installed/reinstalled, copied, symlinked, skipped, and failed targets;
  - update: selected, changed, already current, skipped, conflicted, and failed targets;
  - uninstall: removed, already absent/not matched, preserved user content, and failures;
  - maintainer actions: scanned/imported/checked/updated upstream counts;
  - cancellation or empty selection: explicitly state that no changes were made.
- [x] Make a successful no-op explicit, for example: “Updated 0 artifacts; all 5 selected
      artifacts are already up to date.”
- [x] Distinguish an empty selection from an already-up-to-date selection.
- [x] Preserve appropriate non-zero exit codes for conflicts, partial failures, and errors.
- [x] Keep warnings and recovery instructions visible alongside the summary.
- [x] Provide equivalent counts and item lists in human and JSON output.
- [x] Test successful, no-op, empty, conflict, partial-success, and failure paths in both TUI modes.

## [#18 — TUI: let users choose copy or symlink install mode](https://github.com/M1F1/agent-artifacts/issues/18)

- [x] Add an Install-only mode screen to curses and text TUI:
  - Copy (recommended): install an independent snapshot;
  - Symlink: live-link supported directory artifacts to a local catalog.
- [x] Keep Copy as the default.
- [x] Pass the choice through Request.install_mode/the existing CLI link behavior.
- [x] Explain that Symlink is local-source-only and currently applies to linkable skills/hooks;
      merged and file artifacts still use copy semantics.
- [x] Reject remote-only symlink sources before mutation and explain how to select a local source.
- [x] Disable/hide individual non-linkable rows with a reason instead of failing late.
- [x] Disclose mixed bundle behavior before confirmation, including linked/copied counts.
- [x] Show source, destination scope/path, harness, and mode on the confirmation screen.
- [x] Report the actual mode used for each artifact in the completion summary.
- [x] Preserve recorded modes during update and remove only managed links during uninstall.
- [x] Test default Copy, Symlink, navigation, source validation, non-linkable artifacts, mixed
      bundles, manifest metadata, update, and uninstall.

## [#19 — Support project-scoped and user-global installs per harness](https://github.com/M1F1/agent-artifacts/issues/19)

- [x] Add a core/CLI scope option such as `--scope project|user`; keep Project as the default.
- [x] Let the TUI select scope before loading install/status/update/uninstall choices.
- [x] Explain the choices:
  - Project configures only the current repository;
  - User configures the selected harness for the current user.
- [x] Model explicit project and user destinations per harness and artifact type; do not derive
      global paths by blindly prepending the home directory.
- [x] Verify supported user-global paths against current official harness documentation.
- [x] Explicitly mark unsupported harness/type/scope combinations and explain them in the TUI.
- [x] Keep separate project and user manifests/state so update and uninstall never cross scopes.
- [x] Store resolved destinations, harness, source/subscription, install mode, and managed effects,
      but never secrets.
- [x] Reject ambiguous combinations such as `--scope user` with `--project` before mutation.
- [x] Show resolved absolute destinations and ask for confirmation before user-global writes.
- [x] Prevent multi-harness operations from overwriting another harness's state.
- [x] Test with a temporary fake home/state directory; never touch real global harness config.
- [x] Preserve existing project behavior when scope is omitted.
- [x] Document project/user precedence and scoped install/update/uninstall examples.

## [#20 — Support queued per-artifact interactive setup installers on macOS](https://github.com/M1F1/agent-artifacts/issues/20)

- [x] Define and validate a reviewed, per-artifact macOS setup convention, for example an
      `install.sh` plus metadata for OS support, purpose, and credential/help URLs.
- [x] Only run scripts shipped with the reviewed artifact source; never auto-run a script directly
      from an unreviewed network response.
- [x] After core artifact installation, queue setup-capable selected artifacts and run their
      installers sequentially in the foreground.
- [x] Allow each installer to:
  - explain the configuration it will perform;
  - show a direct credential/help URL and wait for the user;
  - read secrets without echoing them;
  - store secrets in macOS Keychain;
  - create only explicit, managed, idempotent configuration/snippets;
  - verify setup and return a meaningful exit status.
- [x] Account for subprocess limitations: scripts cannot export variables into the parent TUI;
      use a durable Keychain plus managed shell/harness lookup and explain restart requirements.
- [x] On failure/cancellation, preserve earlier successes, mark setup incomplete, and continue to
      the next installer unless the user stops the queue.
- [x] Distinguish “installed and configured” from “artifact installed, setup incomplete.”
- [x] List every incomplete installer with a safe retry command and offer a preselected TUI retry.
- [x] Add a first-class CLI setup/retry runner using the same validation and state tracking.
- [x] Never put credentials in argv, manifests, logs, stdout, or JSON output.
- [x] Before execution, show artifact name, reviewed source identity, script path, and requested
      effects, then require explicit consent.
- [x] Use a controlled working directory, documented minimal environment, and safely quoted paths.
- [x] Record only non-secret status, installer version/hash, timestamps, and exit status.
- [x] On non-macOS systems, do not execute the installer and show a clear unsupported message.
- [x] Test with fake installers and a fake Keychain command: success, hidden input, failure,
      cancellation, continue/stop, idempotent retry, and secret redaction.
- [x] Add a representative MCP setup fixture or reviewed example (Atlassian preferred).
- [x] Document the trust model, authoring contract, retry flow, and the role of SETUP.md as
      optional reference rather than the primary guided setup path.

## [#21 — TUI: add onboarding, progress stepper, back navigation, and persistent selections](https://github.com/M1F1/agent-artifacts/issues/21)

- [x] Start text and curses sessions with a concise controls/onboarding screen.
- [x] Derive an accessible, non-color-only progress stepper from the applicable User or Maintainer
      stage graph and keep it usable in narrow terminals.
- [x] Model navigation, confirmations, basket values, notices, and curses cursor/scroll positions
      in one immutable `WizardSession` shared by both frontends.
- [x] Support one-stage Back on every applicable screen (`KEY_BACKSPACE`, `127`, and `8` in
      curses; `b`/`back` in text) without dispatching or losing valid selections.
- [x] Preserve the artifact/bundle/upstream basket across Review/Edit and selectively remove only
      choices invalidated by earlier edits, with a visible reason.
- [x] Show complete Review facts from issues #15–#20, including descriptions, source, scope,
      destinations, projected install modes, warnings, structured outcomes, and setup queue.
- [x] Make Finalize the sole consumer/upstream apply boundary; keep curses teardown before command
      dispatch and setup execution.
- [x] Preserve Maintainer validation/dry-run preview while moving catalog apply behind Finalize.
- [x] Confirm quit when the basket is non-empty and explicitly report that cancellation made no
      changes.
- [x] Cover pure transitions/rendering, text and curses adapters, Maintainer flows, real lifecycle
      E2E, and all repository quality gates.
- [x] Document onboarding, navigation, basket persistence, Review, and Finalize behavior.
