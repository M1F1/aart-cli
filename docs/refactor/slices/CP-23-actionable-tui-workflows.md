# CP-23 — Actionable TUI workflows after the fourth manual run

Status: IN PROGRESS — TASKS 01–05 DONE; TASK 06 NEXT

Date: 2026-09-14. Authority: the product owner's manual screen reports and request to create CP-23
and close CP-22, followed by the all-screen audit and credential guidance requirements.
Product contract: Product Specification §§154–157 and 167; decisions D-248–D-250.

## Goal and scope

Make the reported Maintainer and Consumer screens explain the next step, expose working controls,
and show the actual lifecycle state. Preserve CP-22's shared frame: actionable rows, cursor detail,
view status and notices occupy separate blocks; the footer advertises the keys that work.
The follow-up expands compliance to every TUI screen/state, not only the reported examples.
`v` shows/hides the current row's description consistently; required input guidance and material
risks remain visible in Fast as part of the form/review's information, not hidden cursor detail.
There are no screen-specific skeleton exceptions for normal views that remain inside the TUI.
Forms, credential entry/review, MCP views, help, errors and results fill the same named blocks.
Only a necessary handoff outside the TUI (such as a secure provider or MCP interaction) may use
an external fallback; returning restores the shared frame and session state.

The evidence log records implemented work; the remaining tasks below are acceptance requirements.
CP-22 is closed by the operator. Its historical test evidence remains historical, and its remaining
bootstrap stage-history enhancement stays in BACKLOG. The current reports are CP-23's acceptance
inputs, including regressions in areas previously considered implemented.

## Execution rules

Work one bounded step at a time. Characterize the real composed screen and key path before changing
it; keep data, pure transitions and explicit IO boundaries separate. Record before/after frames,
targeted semantic mutations and relevant regression evidence per step. Use Hypothesis for universal
selection/navigation/projection claims. Run scoped `make mutants ONLY=<changed module.py>
TESTS="<relevant test files>"`; read and classify survivors. Do not weaken gates or broaden existing
screen exception lists. Do not touch the operator's existing manual lab or untracked notes.

Specification references: §§16–19, 85, 116–123, 145–146, 152, 154–157, 161.2–161.9, 164.2–164.7,
165.17, 165.25–165.28, 167; INV-007–009, 016–023, 052–057, 061–068, 124–138,
149–168, 187–198, 199–206, 229, 239–242.

## Ordered tasks and acceptance criteria

### 01 — Explain Source Sync after adding a Source

- After successful Add Source, name the Source and explain that Source Sync discovers artifacts
  and creates/refreshes Candidates. Adding the connection alone does not discover candidates.
- Keep an actionable Sync entry and the explanation in their respective frame blocks. Preserve
  the added Source as focus, rather than accidentally synchronizing another row.
- Explain new upstream versions through the same discovery step; do not imply Source Sync
  promotes artifacts, synchronizes the consumer Registry, or updates installed artifacts.
- Cover add success, no prior sync, returning to Sources, repeat sync and add failure.

### 02 — Separate the Candidates table from the focused Candidate detail

Keep columns `STATUS  ARTIFACT  VERSION  SOURCE`. Under a separator show `Artifact`, `Version`,
`Source`, `Status` for the row under the cursor, without the `Under the cursor:` heading, when
Verbose is enabled. `v` collapses that description in Fast and restores it in Verbose; this follows
the owner's later global clarification (D-250). Use the existing frame slots, not embedded
separators in a table renderer.
Test two Sources, cursor movement, filtering, empty results and a narrow terminal.

### 03 — Use Verbose for Candidate file diffs

Fast shows semantic changes and the secondary changed-file list. `v` reveals the existing bounded,
redacted file diffs and toggles back to the same summary. Remove the `f` binding and both obsolete
`Press f ...` / `d returns to summary` prompts from this screen. Put
`Press v to view bounded redacted file diffs` below its own separator, as in the supplied frame;
the footer must agree with the actual binding. Keep the review stepper and Enter progression.
Assert switching detail changes neither Candidate identity nor review/validation state; test
redaction, truncation and repeated toggling without IO during rendering.

### 04 — Remove the redundant Policy shortcut from Validation

Remove `[p] Policy` and its screen-specific dispatch. Preserve Enter through the existing
Validation/check-detail → Policy → Promotion Review path, including warnings and failures.
No shortcut removal may bypass policy evaluation or required evidence. Test the complete Enter
journey and the absence of a hidden active `p` binding.

### 05 — End TUI promotion at the local commit; publication is manual

The owner explicitly reverses D-228. Remove TUI push configuration, publication actions and
advertised/hidden key routes that can dispatch a push. Retain local validation, review and commit.
After success explain: push the Registry branch manually; complete PR/review/merge into the
consumer-visible branch where required; update the local checkout; synchronize Registry to observe
that approved state. Source Sync and Registry Sync remain distinct.

Audit Registry Commit, Registry Maintainer, initialization guidance, help and failure recovery for
contradictory promises. Never call a merely pushed review branch consumer-visible Published.
Characterize any non-TUI publication contract before changing shared code; this request removes
the TUI capability and does not by itself delete a supported CLI API.
Use a recording transport to prove no TUI event path pushes; preserve the exact approved-baseline
check and local promotion commit. Update the manual walkthrough to the external Git step.

### 06 — Make installation Success actions real and explain their destinations

The displayed names mean: `View installed` opens Installed, `View receipt` opens the exact
operation's Activity/receipt detail, `Undo` starts a separate review only when the recorded effects
support it, and `Done` returns to Marketplace and leaves the completed wizard. They are currently
printed by `render_transaction_success` / `render_success`; the key table currently gives Success
only `Enter → Done`. Treat the text as a discovered control gap, not proof of functional buttons.

Offer working selectable rows or advertised contextual keys, separate from outcome prose. Keep
Undo unavailable when safe reversal is unsupported; no old credential values may be retained.
Test every offered destination, exact receipt identity, unavailable Undo, cancellation and Esc
after completion. Navigation alone must not replay installation or execute Undo.

### 07 — Describe the focused Marketplace artifact

Show the selected row's approved artifact description below the list when Verbose is enabled;
`v` collapses it in Fast, consistently with the other cursor descriptions (D-250). Read existing
canonical metadata from the approved Registry projection, not runtime network content or a guessed
description. Preserve the manifest/schema boundary; determine which existing description/summary
field carries it before adding a new field. Supply truthful fallback text when metadata is absent.
Test different descriptions, cursor movement, search, multi-selection, missing metadata, wrapping
and Collection previews. No render-time filesystem/network reads.

### 08 — Describe Remediation as the changes AART proposes

Replace `2 thing(s) need preparing first` with language such as `AART will make these changes`
and outcome-oriented descriptions of the actual plan (configure Claude integration, store a
credential securely). Preserve credential impact and other material risks in Fast; put internal
effect/risk terminology in Verbose where appropriate. Avoid claiming a broad isolation guarantee
that the actual plan cannot establish.

`Continue` must be a working control in the actions block/legend, not a bracketed string mixed
into information. Routine derived changes need not create a mandatory Remediation stop when no
decision is required (§161.5 / INV-197); the final review still discloses them. Test the credential
and harness scenario, genuine choices, automatic cases and review-before-mutation.

### 09 — Refresh Candidate state after promotion

Reproduce the reported `New` row after successfully committing the same Candidate. Trace durable
Candidate history, promotion audit, the synchronized approved snapshot and screen recomposition;
the root cause is not yet established. CP-21 already refreshed unchanged Candidates during Source
Sync, which does not prove immediate post-promotion refresh.

After local promotion show `Promoted locally` (or equivalent explicit lifecycle detail), never
`New` or consumer-visible `Published`. Preserve audit/history and prevent a promoted Candidate
remaining eligible for duplicate promotion. On restart derive the same state from durable evidence.
After manual publication and Registry Sync, reconcile against the approved version without
discarding rejected/superseded history. Test immediate return, restart, failed promotion, repeat
Source Sync, multiple Sources/Candidates, same-version content conflicts and genuinely new versions.

### 10 — Let the user choose installation harnesses

Always expose target choice for Skill installation, including exactly one eligible harness; permit
multiple selections when several are eligible. Reuse a shared target-selection model for other
supported kinds where applicable. The eligible set comes from declared compatibility, platform,
scope and policy; the selected subset is explicit user intent. Do not confuse all detected
harnesses with all requested targets. Preserve choices across Back and Fast/Verbose changes.

Review, execution and receipts must describe exactly the selected compatible targets. No mutation
may occur with an empty target set. A stale/ineligible explicit choice is refused visibly rather
than silently replaced. Cover one/many/zero eligible targets, multi-artifact compatibility,
cancel/back, policy restrictions and actual isolated filesystem delivery to the chosen harnesses.
Use properties for subset/persistence guarantees. Preserve D-241's rule that setup follows actual
recorded delivery; supersede only its claim that no picker is needed.

### 11 — Repair Artifact Details controls and compatibility wording

Remove `Actions: select, install, verbose.` as decorative prose. Expose actual selection/install
controls and retain `v`; controls may use the footer or rows, but every offered action must work.
The current key table already has `i → Install`; characterize which advertised actions are missing
instead of treating the entire screen as inert. Selection must keep the focused artifact identity.

Show supported/eligible harnesses clearly. Unsupported *detected but unselected* harnesses should
not read as requirements the user has to repair; explicitly requested unsupported targets still
produce an actionable refusal. Verify this agrees with task 10. Test Space/select, install from
details without a prior Marketplace tick, back-navigation, and no compatible target.

### 12 — Make Credential Action navigable

Create real selectable Verify/Replace rows from the projected permitted actions; Delete appears
only when allowed by usage/policy. The existing screen has no rows while its renderer prints
`[ Verify ]` and `[ Replace ]`, which is a concrete composition gap. Enter opens/executes the
appropriate read-only action or reviewed mutation workflow. Footer, cursor and help must agree.

Keep usage, replacement consequences and provider status below the action rows. Test navigation,
Verify, Replace review/cancel/apply, in-use Delete refusal and unused Delete where supported.
Provider prompts remain secure; the old value is never read/displayed and no secret reaches
history, plans, receipts or tests. Verify each action keeps the correct credential reference after
the cursor moves among actions. Use isolated provider fakes/test keychains only.

### 13 — Carry explicit credential guidance from Source to the installation prompt

The author declares what each credential is and how to obtain it alongside its `SecretInput` in
the source repository's `aart.yaml` / `aart.json`. Reuse the existing `InputGuidance` contract:
human label, description, acquisition instructions/link (`obtain_from`), optional format hint,
and relevant permissions/scopes explained in guidance. Do not add a parallel credential-help
sidecar or require maintainers to edit generated canonical metadata by hand.

Trace author manifest → parser/compiler → Candidate validation/review → canonical `artifact.json`
→ vendored Registry → consumer input view → actual secure-entry prompt. Approved Registry
enrichment may refine guidance (§154.3); installation consumes that approved snapshot without
reading the live Source or fetching help content. Help remains metadata, not provider selection,
credential binding, executable validation or a source of secret values.

At the moment a value is requested, show its human name, what it is needed for, where/how to
obtain it and any declared permission/format guidance. Essential acquisition help is visible in
Fast too, before the secure prompt, including when the terminal is temporarily lent to the
provider. A label such as `dummy-token` or `macos-keychain` alone is insufficient. Verbose may
add provider/reference/binding detail but must not be needed to discover what to enter.
Inside TUI this uses the standard information block; it does not insert explanatory text between
action/input rows or bypass the Verbose cursor-description gate. A provider handoff is outside
TUI rendering, not permission to define a second credential-screen skeleton.

Existing evidence: `domain/inputs.py::InputGuidance` already carries these fields;
`application/candidate_validation.py::_secret_metadata` warns when acquisition guidance is absent.
Determine which propagation/display links are incomplete before adding types. Preserve existing
valid manifests: missing guidance produces an actionable author validation warning and an honest
consumer fallback directing the user to the artifact maintainer; do not invent a token URL or
silently impose a new hard schema requirement. New documented examples and the disposable MCP
fixture must demonstrate complete guidance (including that its token is disposable test text).
Support acquisition instructions for manually issued credentials without assuming every credential
has a public self-service URL. Reuse descriptive fields unless a schema change is justified.

Acceptance: real source-to-Registry-to-install coverage proves guidance survives compilation and
promotion and is visible immediately before credential entry. Test multiple distinct credentials,
shared inputs and conflicting acquisition instructions without losing owner context, existing
credentials that need no prompt, replacement during installation, missing guidance, long text and
narrow terminals, terminal-control/unsafe-URL rejection, and secret redaction. Cover both frontends
with isolated providers; never retrieve/store real secret values for a test. A targeted mutation
dropping guidance from the pipeline or prompt must fail the test that claims to hold it.

### 14 — Audit and enforce the frame and Verbose contract on every TUI view

Inventory the actual Consumer/Maintainer screen catalogs, routes, conditional states and both
frontends. Produce a checked matrix in this slice's evidence (screen/state, actionable rows,
description, status/notice, working keys, Fast/Verbose, text/curses result). Include populated/empty,
filtered, loading, failure, refusal, review, confirmation, success, modal/help, conditional input
forms and new target-selection screens. An empty generic fixture alone does not prove a screen
with content follows the contract. Catalog changes must fail coverage until their cases are added.

Enforce the shared order through the existing Frame: trail and applicable stepper → actions →
cursor description (Verbose only) → view status → action notices → blank padding → `working at`
caption flush with the footer rule → actual keys. Omit empty regions rather than drawing empty
rules. Do not mix bracketed control prose with facts, repeat the header in the body, add per-screen
separator hacks, or expand `MIXED_SCREENS`. Preserve the footer in clipped/narrow terminals.
Every standard in-TUI view must use this shared composition; no special-case screen, alternative
frame, bypass renderer or exception allow-list may satisfy the task. Optional empty regions and
an applicable workflow stepper are rules of the shared frame, not per-screen layout exemptions.
Forms, credential/MCP screens, help and normal modal states are included. Inventory any actual
external fallback separately with its handoff reason and restoration test; it cannot excuse an
in-TUI screen from the matrix. All newly added hints, including task 03's `v` hint, use an existing
shared block rather than a new one-off frame region or hard-coded separator.

For every describable row, `v` reveals the description of the row currently under the cursor;
moving the cursor updates it, and `v` again collapses it. Descriptionless screens must not retain
stale detail from another screen or invent an empty pane. Fast/Verbose switches preserve selection,
focus, drafts, input values, pending review identity and navigation; drawing/toggling does not
dispatch mutations, read secrets or fetch data. On Candidate Diff the same presentation toggle
also reveals the bounded file evidence defined in task 03, not a second independent toggle.
Required input help, blockers, material risk and concise mutation review remain visible in Fast.

Test advertised keys against dispatch, every offered row against an actual action, and the
same composed frame through text and curses paths. Field-edit mode must still allow entering a
literal `v` in text fields; document/test when the global command applies instead of consuming
user input. Use Hypothesis for frame ordering and toggle/persistence laws, with populated concrete
screen cases and representative real workflow runs. Audit findings that violate this contract
are in-scope repairs, not backlog; record and fix them before marking this task complete.

### 15 — Close the batch with evidence and manual acceptance

Run the relevant focused suites per task, targeted semantic mutations, scoped advisory mutmut and
appropriate Hypothesis properties. After implementation run full `make quality` and separate
`make integration`; preserve the actual results, skips and limitations. Walk real Git-backed
Source → Candidate → local commit → manual publication → Registry Sync → Marketplace → selected
harness installation → guided credential entry → Success/receipt → credential lifecycle.
Include task 14's complete screen/state matrix. Render concrete before/after frames
through the production composition and check both text and curses behavior where applicable.

Update this slice, plan.json, NEXT, MIGRATION_STATUS, decisions, backlog and the manual walkthrough.
Mark IMPLEMENTED after code/gates; mark VERIFIED only when the required acceptance evidence exists.

## Dependencies and next action

Begin at task 01. Tasks 02–04 share presentation/navigation seams and should be sequential. Task 05
defines publication wording for task 09. Task 10 defines target intent used by task 11 and revisits
task 08's final plan summaries. Task 13 extends the input path; task 14 audits all completed/new
screens. Task 15 runs after all fourteen product/audit tasks; none is silently
deferred to backlog. Additional unrelated findings go to BACKLOG with evidence.

## Initial inspection evidence (read-only)

- `tui_maintainer.py`: `Under the cursor:` and the `f`/`d` diff guidance remain present.
- `application/consumer_ui.py`: `f` on Candidate Diff, `p` on Validation, only `Enter → Done` on
  Success, and `i → Install` on Artifact Details are present in `_SCREEN_BINDINGS`.
- `tui_consumer.py`: Remediation, Success, Artifact Details and Credential Action render action
  labels as prose; `CanonicalScreenSource.rows` supplies no Credential Action rows.
- `io/consumer_actions.py` and placement/completion seams must be inspected during target-selection
  implementation; no root-cause or delivery fix is claimed in this planning change.
- No production code, user configuration, Registry, Keychain or lab data changed in this segment.

## Evidence log

2026-09-14: plan created; CP-22 closed by the owner's explicit instruction. No CP-23 product task
has run yet. `make docs-check secret-shape-check`, `git diff --check` and a structural JSON check
passed for the original plan: CP-22 had 17/17 completed steps; CP-23 had 13 unique pending steps.
The follow-up adds credential guidance and all-screen compliance, moving final verification to
task 15. No full product suite or completed all-screen audit is claimed by this planning segment.

Follow-up planning checks passed: `make docs-check secret-shape-check`, `git diff --check` and
structural JSON validation (CP-22 remains closed; CP-23 contains 15 unique pending tasks). The
owner's no-exceptions clarification is part of task 14 and the canonical contract, not an optional
backlog enhancement. No production code or operator lab state changed.

### Task 01 — Source onboarding and return focus (2026-09-14)

Done. D-251 records the choices. Gate evidence is at the end of this section.
The previous run left the alias/notice changes and two tests in the working tree, with stale
planning-only handoff prose. This segment completed their verification and the return-path repair.

Before, Add Source returned a timestamp and no result notice. With `a-authors` already connected,
adding `z-authors` returned a frame whose cursor stood on `a-authors`; `[s] Sync` therefore acted
on that earlier Source. After, completion carries `z-authors`, the shared row loader restores it,
and the existing notice block explains explicit discovery. Actual production-composed excerpts
(temporary paths elided; table metadata omitted here for brevity):

```text
Before:
> a-authors — Synced
  z-authors — Synced
────────────────────────────────────────────────────────────────
[a] Add Source   [s] Sync   [Enter] Open   [v] Fast / Verbose

After:
  a-authors — Synced
> z-authors — Synced
────────────────────────────────────────────────────────────────
- Source z-authors added.

- Run Source Sync to discover artifacts and create or refresh Candidates, including new upstream versions. Adding a Source only connects it.

- Source Sync does not promote Candidates or update installed artifacts.
────────────────────────────────────────────────────────────────
[a] Add Source   [s] Sync   [Enter] Open   [v] Fast / Verbose
```

`Synced` here is the existing snapshot-acquisition status, not evidence of Candidate discovery:
the new E2E test proves Candidate history is absent and the count zero until explicit Source Sync.
Source connection still acquires/validates its pinned snapshot. No acquisition behavior changed.

The same test then went red on a real second defect: Source Details → Esc cleared the alias,
which selected `a-authors` on return. Both that edge and Sync review → Details now retain the
subject through the existing reverse-edge set, without adding optional detail stages to the
stepper. The workflow cancels a Sync review, returns to Sources, synchronizes `z-authors`, repeats
unchanged, changes the authored version to `1.1.0`, and discovers that version. It checks actual
Candidate history, leaves `a-authors` undiscovered, and preserves the approved Registry and empty
consumer project. Failure coverage checks that refused addition offers no success/discovery notice.

Evidence:

- `maintainer_source_addition_test.py`, `maintainer_source_onboarding_e2e_test.py`,
  `consumer_ui_state_test.py`, `maintainer_navigation_test.py`, `source_upstream_movement_e2e_test.py`
  and `screen_block_structure_test.py`: **83 passed, 193 subtests passed**.
- Hypothesis generates empty/nonempty row sets and present/absent cursor/focus identities; reload
  preserves current row → subject → first-row precedence, all other state, and emits no commands.
- Six targeted mutations killed: remove focus fallback (**3 tests red**); drop Details → Sources
  subject preservation (**1 red**); drop Sync → Details preservation (**1 red**); return a timestamp
  instead of the Source alias (**2 red**); remove discovery guidance (**2 red**); merge the success
  heading and discovery statement into one paragraph (**1 red**). Each run restored
  the original file in `finally`; the focused suite passes with production code restored.
- Before/after text frames came from the production shell with real isolated Source connections.
  Restoring the former completion response at runtime reproduces the wrong cursor and missing
  notice. No human terminal acceptance or complete curses/screen audit is claimed; those remain
  tasks 14–15.
- The first advisory UI-module mutation run reproduced B-111 (`differing_executors`) before any
  mutants ran. Rerun against the example/E2E tests, keeping Hypothesis in the ordinary gates and
  targeted mutation run. No health check or quality threshold was disabled.
- The initial action-module run exposed six notice-format/text survivors, including joining the
  three statements without their paragraph boundaries. The real composed-frame assertion now
  holds the three separate statements. A sixth deliberate mutation proves that claim is
  load-bearing. Changing mutation scope reproduced B-110; moving the generated checkout aside
  fixed it. A cached repeat also retained old results after a test-only edit, so final IO evidence
  is from a freshly generated mutation checkout.
- Final scoped advisory evidence: UI **1,961 total / 550 killed / 1,345 survived / 66 no tests**;
  actions **2,170 total / 246 killed / 278 survived / 1,646 no tests**. No timeout/suspicious cases.
  `_set_rows` has no survivor; the six Source notice survivors are closed. The remaining
  Source-addition survivor skips the pre-existing offers refresh when fixtures' approved offers
  are unchanged. B-114 classifies it and the other out-of-scope shared-module findings. The exact
  successful scopes were:

```sh
make mutants ONLY=agent_artifacts/application/consumer_ui.py TESTS="tests/maintainer_source_addition_test.py tests/maintainer_source_onboarding_e2e_test.py tests/maintainer_navigation_test.py"
make mutants ONLY=agent_artifacts/io/consumer_actions.py TESTS="tests/maintainer_source_addition_test.py tests/maintainer_source_onboarding_e2e_test.py"
```

Gate evidence (2026-09-14, Claude taking over from Codex): `make quality` on the working tree
passed format-check, lint, typecheck, unit (**3,978 tests OK, 1 skipped**; the integration gate
was skipped as a subset of unit) and validate. The run was stopped during coverage at the owner's
instruction: per-task verification runs only the gates that verify the change, and the full suite
(including coverage and a separate `make integration`) belongs to task 15.

### Task 02 — Candidates table and focused detail (2026-09-14)

Done. D-252 records the choices. The table renderer returns only the grid; screen 35's cursor
description supplies the focused Candidate, so the shared frame places it below its own rule in
Verbose and omits it in Fast. `Under the cursor:` is gone.

Before, both profiles drew `Under the cursor:` and the four fields inside the table's block (Verbose
added Candidate and Target registry there). After, production-composed through `frame` with two
Sources and four Candidates:

```text
Verbose:
   STATUS  ARTIFACT           VERSION  SOURCE
>  New     mcp/github-mcp     1.0.0    authors
   New     skill/code-review  1.0.0    authors
   New     mcp/jira-mcp       2.0.0    vendors
   New     skill/triage       2.0.0    vendors

────────────────────────────────────────────────────────────────

  Artifact         mcp/github-mcp
  Version          1.0.0
  Source           authors
  Status           New
  Candidate        23e725aa…
  Target registry  company

────────────────────────────────────────────────────────────────

[f] Filters   [c] Collections   [Enter] Open   [/] Search   [v] Fast / Verbose
[↑/↓] Move   [Esc] Back   [?] Help   [q] Quit

Fast: the same table and footer, with no detail block and no extra rule.
```

Evidence:

- `tests/maintainer_candidate_detail_test.py` (new, 10 tests): the Verbose frame has the table, a
  rule and the four labels in order; Fast has none; `v` twice keeps the same row, restores the
  identical Verbose frame and dispatches only `PERSIST_SETTINGS`; every row across both Sources is
  described as the cursor moves; search narrowing to one row and to none; a stale cursor on a
  row excluded by the search is not described; the curses path at 40×20 keeps the footer whole,
  clips the detail, and draws no line wider than the terminal; a long name is described in full
  within `CONTENT_MEASURE`; and a Hypothesis property that detail exists exactly when the cursor
  names a listed Candidate and the table is always header + one line per Candidate.
- `tests/tabular_list_columns_test.py`: the full-name claim moved from the table to the detail.
- Focused run: candidate detail/filters/shell, tabular columns, block structure, skeleton, key
  legend, composition E2E, promotion, workflow progress and every `tui_*`/`cp20_tui` module:
  **328 tests OK**. `make format-check lint typecheck`: OK.
- Four targeted mutations, all killed: description branch returns nothing (**6 red**); description
  reads the unfiltered list (**1 red** — it first survived, which is why the stale-cursor test
  exists); detail put back inside the table (**5 red**); Status field dropped (**2 red**).
- Per the owner's instruction, per-task verification runs only the verifying gates. Scoped
  `make mutants` for `tui_maintainer.py`/`tui_consumer.py` and the full suite are left to task 15.
  No human terminal retest is claimed.

### Task 03 — Candidate file diffs behind `v` (2026-09-14)

Done. D-253 records the choices. `f`, its event and the `file_diff` state are gone; Verbose is
the projection that adds the bounded redacted diffs.

Before (Fast), production-composed: the prompt stood inside the file list and the footer offered
two toggles.

```text
- File changes (secondary):
  ~ artifact.json — modified
  ~ payload/server.py — modified
  ~ provenance.json — modified
  Press f to view bounded redacted file diffs; d returns to summary.
────────────────────────────────────────────────────────────────
[f] Files   [v] Fast / Verbose
```

After, Fast, then after one `v` (tail of each frame, long JSON lines cut here for width):

```text
- File changes (secondary):
  ~ artifact.json — modified
  ~ payload/server.py — modified
  ~ provenance.json — modified

- Press v to view bounded redacted file diffs.

────────────────────────────────────────────────────────────────

[v] Fast / Verbose
[↑/↓] Move   [Esc] Back   [?] Help   [q] Quit

- Bounded redacted file diffs:
  [payload/server.py]
    --- before/payload/server.py
    +++ after/payload/server.py
    @@ -1 +1 @@
    -print('old')
    +print('new')
  …

- Press v to hide the bounded redacted file diffs.
```

Evidence:

- `tests/maintainer_candidate_diff_verbose_test.py` (new, 9 tests): Fast has the semantic summary
  and file list but no diff text, no `Press f`/`d returns`, and the hint as its own last statement;
  Verbose adds the diffs and the hide hint; the footer offers `[v]` and no `[f]`, and `f` maps to
  no event; `v` twice restores the identical frame while focus, screen, history and review digest
  stay put and only `PERSIST_SETTINGS` is dispatched; drawing either projection opens no file; a
  Hypothesis property over 0–7 presses (files shown exactly when Verbose, identity unchanged); a
  planted credential assignment is redacted in the Verbose render; a 400-line change stays within
  the 200-line bound and repeated toggling alternates exactly two frames.
- `maintainer_validation_views_test.py`: Enter on the diff reaches Validation with the same focus
  in both profiles. `maintainer_candidate_shell_test.py`: `f` still opens filters on screen 35 and
  means nothing on 37. `maintainer_composition_e2e_test.py`: the real session presses `v` instead of
  `f`. `contextual_key_legend_test.py`: screen 37 advertises `[v] Fast / Verbose`.
- Focused run: 212 tests across the diff, shell, validation, composition E2E, Candidate detail,
  UI state, block structure, skeleton, workflow progress, navigation, back stack, lifecycle,
  CLI-command leak and identifier leak modules, plus 112 `tui_*`/`cp20_tui` tests and the key legend
  tests: all OK. `make format-check lint typecheck`: OK.
- Five targeted mutations, all killed: file diffs shown in Fast (**6 red**); hint merged into the
  file list (**1 red**); hide hint dropped (**1 red**); an `f` binding restored on screen 37
  (**2 red**); diff lines left unredacted in the projection (**1 red**).
- Scoped `make mutants` and the full suite are left to task 15 (owner instruction). No human
  terminal retest is claimed.

### Task 04 — Validation without the `p` shortcut (2026-09-14)

Done. D-254 records the choice; B-115 records a shadowed branch the mutation run exposed.

Before, screen 38's footer read `[p] Policy   [v] Fast / Verbose` ahead of the global keys, and `p`
navigated straight to Policy Review. After, the footer offers `[Enter] Open   [v] Fast / Verbose`
and `p` means nothing there. Enter still opens a check, and Enter on the check opens Policy Review.

Evidence:

- `maintainer_validation_views_test.py`: `test_validation_offers_no_p_shortcut` checks the
  composed footer, `key_bindings` and `key_event`. `test_enter_walks_a_failing_check_to_the_policy_that_judges_it`
  uses real key events from a Validation screen showing `Unmet requirements: live-acceptance`
  through the failing check's detail to Policy Review, which still says `Approval required`.
- `maintainer_composition_e2e_test.py`: the two real walks (Source Sync → promotion commit, and
  diff → promotion review) press Enter twice where they pressed `p`; both still commit/review.
  `contextual_key_legend_test.py` no longer expects `[p] Policy`.
- Focused run: validation views, key legend, composition E2E, promotion shell execution, workflow
  progress, back stack, block structure and CLI-command leak modules: **130 tests OK**.
  `make format-check lint`: OK (no production types changed).
- Targeted mutations: restoring the `p` binding (**1 red**); pointing screen 39's Enter binding
  at Promotion Review, skipping policy (**5 red**, including the new walk and both E2E walks). A
  first mutation of the `source.detail` branch left the key walk green because that branch is
  shadowed (B-115). The binding is the path a key takes, so the binding mutation is the evidence.

### Task 05 — TUI promotion ends at the local commit (2026-09-14)

Done. D-255 records the choice; B-116 records the default-branch reader left without a caller.

Characterized first: after the commit, screen 45 said `Git publication: not yet published; press p
to choose a review branch`. `p` opened a remote/branch form, Enter prepared a
`RegistryPublicationCommand` through the handler's default-branch port, and a second Enter pushed
through `publish_registry_commit`. The CLI `aart registry push` uses the same application/IO
modules through its own path.

After: the TUI vocabulary has no publication action, event, draft, state flag or handler port. The
committed screen lists push → pull request/merge where required → update checkout → Registry Sync,
never says "published", and does not mention Source Sync. `p` maps to no event and the footer
offers none. Registry initialization and screen 46's push sentence no longer overpromise (D-255).
The CLI contract and its tests are untouched.

Evidence:

- New `registry_commit_manual_publication_test.py` (9 tests):
  - wording in both profiles, with the manual steps in order and within `CONTENT_MEASURE`;
  - no "published", `press p` or Source Sync after the commit;
  - the view, projection and renderer carry no publication fields or arguments;
  - the initialization intro;
  - the UI vocabulary and `LocalConsumerActions` signature;
  - `p`/`P`, including the legend;
  - a Hypothesis property: no key sequence on committed screen 45 emits `REQUEST_ACTION`/`CONFIRM_ACTION`
    or a `PREPARE_ACTION`/`EXECUTE_ACTION` command.
- Recording transport: `maintainer_composition_e2e_test.py`'s real walk now wraps `subprocess.run`
  for the whole shell session. After the commit it presses `p`, `P` and types `review/registry`,
  then asserts that a `git commit` argv was recorded and no argv contains `push`. The bare
  remote's refs are exactly `refs/heads/main` at the pre-promotion revision. The bulk walk asserts
  the manual-steps text.
- Reworked: `maintainer_promotion_shell_execution_test.py` drops the form tests. It keeps `q`/`?`/`v`
  after the commit and adds Enter → Registry. `maintainer_promotion_execution_test.py` ends at
  the local commit, and `registry_workspace_lifecycle_test.py` carries the scoped sentence.
- Focused runs: the five changed modules (**54 OK**); 25 modules touching screen 45, init prose,
  legends or the workspace (**369 OK**); UI state/actions, shell, application E2E, skeleton and
  the CLI `registry_publication*`/`registry_push_cli` modules (**172 OK**).
  `make typecheck format-check lint`: OK.
- Targeted mutations, all killed:
  - `p` requesting an action on committed 45 (**red**, including the Hypothesis property alone,
    which shrinks to `['p']`);
  - steps out of order (**2 red**);
  - steps dropped (**5 red**, including both E2E walks);
  - init promising Registry Commit publication (**1 red**);
  - the promotion handler running `git push --dry-run` after the commit (**1 red**, the recording
    transport).
- Walkthrough step 8 is now the external Git step. Scoped `make mutants` and the full suite are
  left to task 15. No human terminal retest is claimed.
