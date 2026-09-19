# CP-23 — Actionable TUI workflows after the fourth manual run

> **Historical evidence / CP-26 revision:** Product Specification §169 and D-332–D-335 supersede
> earlier naming, runtime-placement and cross-installation input-sharing assumptions in this record.
> VERIFIED below refers to the contract tested then. Current implementation/proof belongs to
> CP-26.18a/19/20; see `../CONTRACT_ALIGNMENT.md` and `../INVARIANT_TRACEABILITY.md`.

Status: CLOSED BY THE OWNER, 2026-09-16 — TASKS 01–16 DONE IN CODE; THE MANUAL ACCEPTANCE WALK AND A GREEN STANDALONE `make integration` (B-108) WERE NEVER RECORDED

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

**Historical contract, superseded by Product Specification §164.7, D-312 and CP-26.18.** This
records what CP-23 implemented and verified at the time. It is not the current product direction:
explicit Push is restored on Registry Maintainer's local-workspace row, not on the promotion success
screen.

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

### 16 — Manage user configuration and credentials per artifact and harness (owner request)

Added by the owner on 2026-09-14, after task 10. It runs after tasks 12 and 13, which it builds on,
and before the task 14 audit, which must include its screens. The owner's words:

> chcialbym dolaczyc nowy task - zarzadznie secretami i zmiennymi charakterystycznymi dla
> uzytkwnika per np mcp takimi jak nazwa uzytwkonika czy url strony z https zeby o to tez pytal
> aart w trakcie instalacji i umieszczal taki plik konfiguracyjny w miejscu do ktorego zostanie
> zainstalwoany artefakt i nastepnie zeby z poziomu TUI mozna bylo tym zarzadzac, najlepiej zeby
> credentiale i takie zmienne byly uporzadkowane w kontekscie mcp czy innych artefaktow ktore z
> nichj korzystaja, wiec niech bedzie zakladka zbioraoa user variables and credentials, ktore sa
> zczytywane z zainstalowych artefaktow czy stanu keychaina, ale nigdy ofc nie przychowywane w
> aplikacji czy plikach aplikacji (credentials) podobnie jak zmienen niech one beda na dysku w
> sciezkach zainstalowanych artefaktow, ale mozna bedzie je modyfkowac z poziomu aart, zeby nie
> babrac sie w jsonach [...] oczywiscie jakiekolwiek zmiany w kechain beda sie mozna powiedziec
> dzialy poza aplikacja, czyli tak jak obecnie isntaluje sie mcp to jest zejscie do cli zeby je
> ustawic za pomoca api kechaina cli

> no i to bedzie fajne bo bedzie mozna je zmieniac te zmienne dla wszystkich harnessow ofc, mozna
> jeszcze wybrac dla ktorych harnesow je zminic i one zawsze beda w kontekscie harnesow, czyli
> mozna je zminiec per jeden harnes ale tez per wszystkie harnesy

Requirements:

- **Installation asks for non-secret configuration.** Values such as a user name or an `https`
  site URL are `ConfigInput`s (§91–92.2). Installation asks for them just as it asks for credentials
  today. Today screen 07 refuses with "waiting for answers this screen cannot collect yet"; that
  refusal is replaced by a working input form using the standard frame.
- **Where values live.**
  - Non-secret values are written to a configuration file at the installed artifact's own location
    (its installation root, per harness where the projection differs), never to AART's application
    state files.
  - Credentials are never stored in AART or its files. They stay in the secret provider (for
    example macOS Keychain), and AART holds only the `CredentialReference`.
  - §96 permits AART-owned local config state, and this owner choice narrows it to the artifact's
    installed location. Record that as a decision and, if needed, a Product Specification revision
    like §167.
- **Separate entities, shown side by side.** The owner clarified on 2026-09-14:
  > i don't want to merge secrets and non secrets into one variable concept i just want them to be
  > near each other in TUI to configure them, but they are different entitites with different way
  > to establish and install them

  Configuration values and credentials keep their own types, their own way of being established
  and their own installation effects. Only their placement in the TUI is shared.
- **One area: "User variables and credentials".**
  - The area is grouped by the artifact that uses each value (MCP or other kinds).
  - It is read from the installed artifacts' configuration files and from the provider's reference
    state.
  - Credential values are never read, displayed or kept.
  - INV-067 still holds: configuration and credentials are two visibly distinct sections with
    different handling guarantees, never one generic "variables" list.
  - It extends, rather than duplicates, the accepted Credentials views (§161.8, task 12).
- **Editing from the TUI, per harness.**
  - A configuration value can be changed for one harness, for a chosen set of harnesses, or for
    every harness the artifact is installed into. Values are always shown in the context of their
    harnesses. The choice reuses task 10's harness-selection model.
  - A change is a reviewed, receipted mutation that touches only the dependent projections
    (INV-179: a configuration change is not a reinstall).
- **Credentials change outside the application.** Setting or replacing a credential stays a
  provider handoff, like today's MCP install: the terminal is lent to the Keychain CLI/API and the
  frame is restored afterwards. The TUI starts it and then verifies the reference, and never
  handles the value (INV-180).
- **Tests:**
  - install-time configuration and credential collection with real isolated files written to the
    chosen harnesses' installed locations;
  - no configuration in AART state, and no secret anywhere on disk, in plans, receipts or logs;
  - editing one harness, several or all, with only dependent projections changed;
  - the grouped area projected from installed artifacts and provider references;
  - a stale or missing configuration file reported honestly;
  - Hypothesis properties for per-harness scope selection and secret redaction;
  - isolated provider fakes only.

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
screens. Task 15 runs after all fifteen product/audit tasks (including owner-added task 16); none is silently
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

Done as CP-23 history. D-255 records the choice and B-116 records the default-branch reader left
without a caller; Product Specification §164.7, D-312 and CP-26.18 later supersede the no-TUI-Push
product direction by placing explicit Push on Registry Maintainer's local-workspace row.

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

### Task 06 — Installation Success actions are real (2026-09-14)

Done. D-256 records the choice; B-117 records the missing reviewed installation undo.

Characterized first: `render_transaction_success` printed `[ View installed ] [ View receipt ]
[ Done ]` (plus `[ Undo ]` when the projection said available) as prose. Success had one screen
binding, `Enter → Done`. Esc walked back through history into Installing and a Ready screen still
asking to confirm the install that had just run.

After: the three names are Success's rows, and each is its own Enter target with a matching Enter
label. The outcome is the view's status with no button prose. A Verbose-only description says
where the focused row goes. `View receipt` opens the receipt this operation recorded
(`_KEEPS_FOCUS`). Done and Esc both leave for Marketplace. Undo is explained, never offered: either
the recorded reason it is unavailable, or that no reviewed undo is offered here. Receipt Details
no longer says "Undo: available".

Evidence:

- New `installation_success_actions_test.py` (12 tests):
  - rows versus status, with no bracketed prose in the frame;
  - every row's Enter destination, emitting only `LOAD_SCREEN`;
  - Done leaves the wizard's history;
  - with an older receipt present, `View receipt` opens this operation's exact receipt;
  - View installed and Done carry no subject;
  - the Enter label per row;
  - Verbose describes each row differently, and Fast hides the description;
  - Esc goes to Marketplace;
  - a Hypothesis property: no key sequence on Success emits `PREPARE_ACTION`/`EXECUTE_ACTION` or
    re-enters a wizard screen;
  - unavailable Undo states its reason, a reversible transaction still offers no Undo, and Receipt
    Details does not promise one.
- Real application E2E, `consumer_application_e2e_test.py`: after a real install through the
  terminal, `View receipt`, `View installed`, `Done` and Esc each reach their screen. The machine
  still holds exactly one receipt, and View receipt shows its `recorded_at`.
- `consumer_install_flow_shell_test.py`: Enter on Done finishes the wizard at Marketplace.
- Focused runs: 13 install/Success/transaction/legend/back-stack/activity/setup modules (**131
  OK**); the CLI modules sharing `render_transaction_success` (`marketplace_lifecycle_e2e`,
  `consumer_command_seam_e2e`, `merged_installation_e2e`) (**46 OK**).
  `make typecheck format-check lint`: OK.
- Targeted mutations, all killed:
  - `_back` walking into the wizard (**3 red**, including the property and the E2E);
  - dropping `(SUCCESS, RECEIPT_DETAILS)` from `_KEEPS_FOCUS` (**2 red**);
  - restoring `Enter → Done` as a screen binding (**4 red**);
  - restoring the button line (**1 red**);
  - replacing the explanation with `[ Undo ]` (**1 red**);
  - `detail` ignoring the cursor (**7 red**).
- Walkthrough section 11 checks the rows, the exact receipt and Esc. Scoped `make mutants` and the
  full suite are left to task 15. No human terminal retest is claimed.

### Task 07 — The focused Marketplace offer is described (2026-09-14)

Done. D-257 records the choice.

Characterized first: `description()` had no Marketplace branch, so screen 02 described nothing in
either profile. The only words about an offer were the `key  summary` row, which a narrow terminal
clips. Approved metadata carries exactly one description field, the manifest `summary`, which is
already on `MarketplaceArtifactRow` and `Collection`.

After: `marketplace_offer_description` renders the focused artifact (Artifact/Kind/Version/Source/
Description) or Collection (Collection/Version/Source/Includes/Description) as a field block.
`CanonicalScreenSource.description` answers from the same search filter as the rows. There is a
fallback for an offer without usable words, and there are no reads at render time.

Evidence:

- New `marketplace_cursor_description_test.py` (14 tests):
  - Verbose draws the block directly below the list's rule, and Fast draws none;
  - `v` round-trips the same offer and emits only `PERSIST_SETTINGS`;
  - each row is described with its own summary, and ticked rows do not move the description;
  - a long summary is described in full within the measure;
  - a blank summary gets the fallback and borrows no other summary;
  - Collection rows are described with their own member count, and the Collection Preview they
    open carries no Marketplace description;
  - search narrows, empties, or leaves a stale cursor undescribed;
  - a Hypothesis property over cursor and search: a description exists exactly when the cursor is
    on a listed offer, and names that offer;
  - describing and drawing every row with `open`, `subprocess`, `socket.create_connection` and
    `urlopen` patched to fail.
- Focused runs: 20 Marketplace/shell/legend/skeleton modules (**196 OK**); 54 modules exercising
  `description`/`frame`/Verbose plus the application and flow E2Es (**723 OK**).
  `make typecheck format-check lint`: OK.
- Targeted mutations, all killed:
  - ignoring the search (**2 red**, including the property);
  - a fallback that borrows a summary (**1 red**);
  - truncating the summary (**1 red**);
  - a fixed Collection count (**1 red**);
  - Collections undescribed (**4 red**);
  - describing the first row instead of the cursor (**5 red**).
- Walkthrough section 11 checks the description. Scoped `make mutants` and the full suite are left
  to task 15. No human terminal retest is claimed.

### Task 08 — Remediation states the changes AART proposes (2026-09-14)

Done. D-258 records the choice.

Characterized first: `render_remediation` printed `N thing(s) need preparing first`, rows as
`configure credential: macos-keychain (credential mutation)`, the unestablished `Nothing outside
this installation will be modified.` and `[ Continue ]` as prose. Screen 08 had no rows, so the
legend said `Enter Open`. Every plan with any remediation stopped there, including plans that
only configure a harness. The TUI accepts the whole remediation offer, so there was never a picker.

After:

- The status is the outcome list, then its material impacts; effect terms and owners are Verbose.
- Continue is the row, with the `Enter Continue` legend and a Verbose description.
- `remediation_needs_decision` is the single rule; configure-harness is routine.
- Ready discloses every remediation in the same wording.

Evidence:

- New `remediation_changes_test.py` (13 tests):
  - the heading, singular and plural, with no "need preparing";
  - an outcome naming its subject for each of the seven kinds;
  - harness rows told apart;
  - Fast impact against Verbose effect terms and owners;
  - no isolation guarantee in either profile;
  - Continue is the only row and absent from the status;
  - the legend;
  - Continue lands on Ready with no action and only `LOAD_SCREEN`;
  - the Verbose description;
  - harness-only routes from Required Inputs and Review Selection go to Ready;
  - Ready discloses them;
  - every non-routine kind stops;
  - a Hypothesis property: `install_flow_screens` and the screen route agree on one rule.
- Reworked:
  - `remediation_row_subject_test.py` holds QA-080 in the new wording and adds an unknown kind;
  - `consumer_properties_test.py`: the Ready property checks each remediation's outcome sentence;
  - real-install key sequences in `consumer_application_e2e_test.py`,
    `configured_setup_gap_test.py` and `configured_setup_report_test.py` lose the Remediation
    Enter, because their plans are harness-only.
- Focused runs: 90 modules touching remediation, Ready, install key sequences or the fake terminal
  (**1,012 run**; the one failure was the Ready property, reworked above); after rework, 12 core
  modules (**126 OK**). `make typecheck format-check lint`: OK.
- Targeted mutations, all killed:
  - no kind routine (**2 red**);
  - never stopping (**3 red**);
  - the Required Inputs route diverging (**1 red**);
  - `[ Continue ]` restored (**1 red**);
  - Ready reduced to a count (**2 red**, including the property);
  - impact Verbose-only (**1 red**);
  - effect terms in Fast (**1 red**);
  - an unnamed harness (**5 red**);
  - the legend back to Open (**1 red**);
  - the isolation claim restored (**1 red**).
- Walkthrough section 11 checks the wording, Continue and the skipped stop. Scoped `make mutants`
  and the full suite are left to task 15. No human terminal retest is claimed.

### Task 09 — A promoted Candidate is no longer offered again (2026-09-14)

Done. D-259 records the choice.

Characterized first, with a temporary probe over the real composed walk from
`maintainer_composition_e2e_test`. After the local commit, the composed Candidate was still
`ready`. Both promotion reviews had no refusals, and the Registry diff still carried plan digests.
Root cause: Candidate state moves to `promoted` only when Source Sync reconciles against the
synchronized approved Registry. The checkout's version and audit evidence fed only screen 48's
lifecycle.

After:

- `candidate_promotion_record` derives `not-promoted` / `promoted-locally` / `promoted` from the
  synchronized versions and the attributable checkout on every composition.
- Candidates show `Promoted locally` (or `Promoted`) in the row, the cursor detail and the Candidate
  heading.
- Review, diff and bulk refuse with the way on.
- The transaction refuses a recorded Candidate by name before the baseline comparison.
- No history is rewritten; restart reads the same trees.

Evidence:

- New `candidate_promoted_locally_test.py` (20 tests):
  - the record for local-only, synchronized (with and without a checkout) and unreadable trees;
  - a genuinely new version and a same-version content change are not covered;
  - a repeat Source Sync keeps the Candidate promoted locally;
  - Source Sync after Registry Sync stores `promoted` and keeps its history;
  - a Hypothesis property over two Candidates and every local/synchronized subset;
  - the row and detail read `Promoted locally`, never New/Ready/Published;
  - a synchronized record reads `Promoted`;
  - the other Candidate keeps its state, and the projection is unchanged without evidence;
  - review and diff refuse in both modes and name Registry Sync, or Source Sync;
  - an unrecorded Candidate is still offered;
  - bulk excludes only the recorded Candidate;
  - the transaction refuses a synchronized record, an unpublished local commit and a mixed
    selection, and a failed promotion (nothing written) stays promotable.
- `maintainer_composition_e2e_test` (the real walk) now also asserts:
  - no record before the walk;
  - on the immediate return and after a restart composed from disk, `Promoted locally`, refused
    reviews and diffs, and no bulk offer;
  - the restart's Candidates and reviews equal the return's.
- Focused runs: 76 maintainer/candidate/registry modules (**746 OK**) plus three other modules
  touching the changed projections (**76 OK**). `make typecheck format-check lint`: OK.
- Targeted mutations, all killed:
  - no tree records anything (**9 red**);
  - the checkout outranks the synchronized Registry (**3 red**);
  - the choke point open (**3 red**);
  - review open (**3 red**), diff open (**2 red**), bulk open (**2 red**);
  - composition drops the records from Candidates (**1 red**);
  - composition never reads the checkout (**1 red**);
  - status from stored state only (**3 red**);
  - the refusal without its way on (**1 red**).
- Walkthrough sections 7 and 8 check the return, a restart and the refusals. Scoped `make mutants`
  and the full suite are left to task 15. No human terminal retest is claimed.

### Task 10 — Explicit installation harness choice (DONE 2026-09-14)

Implemented and focused-verification complete. The application model in
`application/consumer_views.py` contains:

- `HarnessTargetView(harness, artifacts)`;
- `target_row`/`target_from_row` (the row key is `target:<harness>`);
- `target_choice_problems(view, chosen)`, which covers the empty choice, stale/ineligible names and
  artifacts no chosen harness covers;
- `targets_confirmed(view, chosen)`;
- `ConsumerPlanView.targets`/`chosen_targets` (both default `()`, so update flows and existing
  fixtures are unchanged).

Why a picker is needed: the TUI host (`tui.py` `_canonical_installation_host`) passes every measured
harness with `profiles_requested=False`. `placement_for` then installs into every measured harness the
artifact declares, so today the user never chooses. D-241's "no picker needed" is what task 10
supersedes; its rule that setup follows recorded delivery stays.

Implemented design (D-260):

1. **Reducer (`application/consumer_ui.py`).**
   - Add `ConsumerUiState.targets` and `ConsumerUiCommand.targets` (validated like rows).
   - Add screen 05 to `_SELECTABLE`.
   - In `_toggle_selection` on 05, toggle a `target:` row in `state.targets` (never in
     `selection`). When `state.action is INSTALL`, emit `PREPARE_ACTION(INSTALL,
     selection=state.selection, focus=<the original request focus>, targets=...)`.
   - Careful: `_request_action` sends `focus=""` from Marketplace, while `state.focus` on 05 is
     whatever `_navigate` set. Re-send the request's subject, not `state.focus`.
   - `_request_action` passes `state.targets` for INSTALL.
   - `_action_recorded` clears `targets`.
   - Back and `v` keep them (Hypothesis property).
   - The Enter label on 05 is `Continue`.
2. **Screen 05 (`tui_consumer.py`).**
   - Rows are `target:` rows for `plan.targets`, plus stale chosen names, with nothing preselected.
   - `_body` draws `[x]/[ ] harness`.
   - `_view_status` holds `render_review_selection`, then the problems or `Installing into: ...`.
   - `detail` is `None` unless `targets_confirmed(plan, state.targets)`.
   - The Verbose description says which artifacts that harness hosts.
   - `render_ready` must stop saying "every harness this machine measured..." and name the chosen
     harnesses.
3. **I/O (`io/consumer_actions.py` `_offer_installation`, INSTALL only).**
   - Prepare as today. Eligibility per harness comes from `draft.placements`: `targets`,
     `deliveries` and `merges` harness → `str(artifact.version.coordinate)`, in measured order.
     Eligibility is available even when the draft is not ready.
   - If `command.targets` has no `target_choice_problems`, prepare again with
     `replace(host, profiles=chosen)`, keeping `profiles_requested=False`.
   - Set `plan = replace(plan, targets=..., chosen_targets=chosen or ())`, and set `_pending_host`
     to the narrowed host.
   - `_execute_installation` must refuse when targets exist but none are chosen: no mutation with
     an empty set.
4. **Existing E2E install key sequences** (e.g. `tests/consumer_application_e2e_test.py`
   `_INSTALL = (SPACE, "i", ENTER, ENTER)`) need a Space on 05 before Enter.
5. **Owner request (2026-09-14):**
   - The manual lab's test MCP and Skill must be installable into opencode and Tabnine as well as
     Claude, so harness choice and the opencode installer can be tested.
   - In `scripts/manual_test.py` the `manual-check` Skill and `dummy-mcp` manifests declare
     `compatibility.harnesses: ["claude"]`. Widen both to `["claude", "opencode", "tabnine"]` and
     update `tests/manual_test_lab_test.py`.
   - Tabnine MCP (`.tabnine/agent/settings.json`) and Tabnine Skill delivery
     (`.tabnine/agent/skills/<name>`, project scope only) must be covered by a real isolated
     filesystem E2E through the chosen-target path.
6. **Tests required by the slice:**
   - one, many and zero eligible harnesses;
   - multi-artifact compatibility;
   - cancel/Back;
   - policy restriction;
   - a stale choice refused visibly;
   - real delivery only to the chosen harnesses, with receipt profiles equal to the choice;
   - no mutation with an empty choice;
   - Hypothesis subset/persistence properties.
7. **Then:**
   - D-260 (and a BACKLOG note that updates keep their installed harnesses);
   - TODO 10, NEXT, MIGRATION_STATUS, walkthrough section 11;
   - focused gates only (`make typecheck format-check lint docs-check` plus the touched test
     modules, per owner instruction) and targeted mutations;
   - `handoff-plan done CP-23.10`, then commit.

Evidence:

- Characterization/model tests cover target row round trips, zero/one/many eligible harnesses,
  stale and incomplete multi-artifact choices, exact confirmation, validation and machine
  projection.
- Reducer/screen tests prove harness state is separate from artifact selection, re-preparation
  keeps the original request focus, Back and `v` preserve target intent as a Hypothesis property,
  stale rows remain visible, Continue is gated, and Verbose names the artifacts hosted by the
  focused harness. A second Hypothesis property covers every nonempty eligible subset.
- Real isolated filesystem E2Es install both a Skill and an MCP through the chosen-target path into
  OpenCode and Tabnine. They assert `opencode.json`, `.opencode/skills/<name>`,
  `.tabnine/agent/settings.json` and `.tabnine/agent/skills/<name>`, prove unchosen harness paths
  are absent, and read receipt profiles back from disk. A two-target Skill test records and
  delivers to exactly OpenCode plus Tabnine.
- The execution boundary test bypasses the UI with an empty target choice and proves refusal,
  absent harness files and absent receipts. Policy refusal exposes no target plan and mutates no
  harness. The manual lab test proves both fixtures declare Claude, OpenCode and Tabnine.
- Focused run: 147 relevant reducer/view/shell/navigation/setup/E2E tests pass; the manual lab
  module separately passes 11 tests using its temporary macOS Keychains. `make typecheck
  format-check lint docs-check`: OK.
- Five deliberate semantic mutations were killed: removing the exact-choice Continue gate (1
  red), preparing against the full rather than chosen host (2 red), opening the empty-choice
  execution boundary (1 red), and sending the old rather than toggled targets for re-preparation
  (1 red), and reusing Marketplace's cursor focus instead of its original whole-selection subject
  (1 red).
- D-260 records the target-intent boundary. B-119 records the noncritical future explicit harness
  migration question for updates. Scoped `make mutants`, the full suite and human acceptance stay
  with task 15; no human terminal retest is claimed here.

### Task 11 — Artifact Details controls and one eligibility rule (DONE 2026-09-14)

Codex started this task before its limit (controls, eligible/detected wording, and the
`compatible` → any-eligible change). This segment verified it against the production composition,
found that Details still disagreed with task 10, and fixed the rule (D-261).

Before (production composition, E2E Skill declaring `harnesses: ["claude"]` and no platforms):

```text
- company/skill/code-review@1.2.0
  Approved
  Code review
  What it needs
    - platform 'darwin' is not supported; supported platforms: none
    - profile 'codex' is not supported; supported profiles: claude
    - profile 'opencode' is not supported; supported profiles: claude
    - profile 'tabnine' is not supported; supported profiles: claude
  Actions: select, install, verbose.

[i] Install   [v] Fast / Verbose
```

After:

```text
- company/skill/code-review@1.2.0
  Approved
  Code review
  Eligible installation harnesses
    - claude
  Detected but not eligible
    - codex
    - opencode
    - tabnine
  What it needs
    - Nothing else before choosing an eligible harness

- Not selected for installation.

[i] Install   [Space] Select   [v] Fast / Verbose
```

A probe also showed that a Skill declaring only `windows` installed on darwin through the TUI
while Details called it unavailable. It is now refused by placement, naming both platforms.

- `tests/artifact_details_controls_test.py` (14 tests) covers:
  - one eligible harness keeps the artifact available, and detected-unsupported harnesses are not
    requirements;
  - no eligible harness is a visible blocker with per-harness reasons;
  - Verbose calls each detected harness eligible or detected-unavailable;
  - Space selects and deselects the focused artifact with a Select/Deselect label and status;
  - the selection survives Back and keeps the Marketplace cursor identity;
  - the frame advertises the working controls and no decorative prose;
  - install from Details needs no Marketplace tick (real E2E);
  - an unavailable install declines back on Details;
  - a Hypothesis property over declared/detected harness subsets and empty/this/other platform
    declarations;
  - an undeclared platform is not reported as unsupported;
  - placement refuses an excluded platform whether profiles were requested or measured, and still
    places when this platform is declared;
  - production-composition E2Es: Details' eligible harnesses equal screen 05's target rows (Claude
    only; Claude/OpenCode/Tabnine; undeclared), and an excluded platform is unavailable on both
    screens and delivers nothing.
- `tests/install_review_names_harnesses_test.py` still asserted D-241's "not a choice" wording,
  which task 10 superseded without running this module. It now holds D-260: Ready names the chosen
  set as chosen.
- Focused runs: every test module mentioning compatibility, platforms, placement, harnesses or the
  E2E environment (196 modules, 2,299 tests). The only failures were:
  - the stale Ready wording test above, now fixed;
  - `tests.aggregate_gate_test`, which fails to import when loaded directly, and fails the same way
    without this change (checked with the change stashed).

  `make typecheck format-check lint docs-check`: OK.
- Targeted mutations, all killed:
  - empty harness declaration strict again (**2 red**);
  - empty platform declaration strict (**3 red**);
  - placement ignores platforms (**2 red**);
  - Details needs every harness compatible (**2 red**);
  - Space uses the cursor row instead of the focused artifact (**1 red**);
  - selection status inverted (**1 red**);
  - eligible harnesses not listed (**1 red**).
- Walkthrough section 11 adds the Details checks. Scoped `make mutants` and the full suite are left
  to task 15. No human terminal retest is claimed.

### Task 12 — Credential Action rows wired to the credential lifecycle (DONE 2026-09-14)

Before (screen 24, Fast and Verbose identical; no rows, and no key did anything):

```text
- github-token: choose an action
    [ Verify ]
    [ Replace ]
  Replacing affects
    • public/mcp/github
  It cannot be removed while these use it.
  Replacement stores a new value and verifies what uses it; no old value is kept.

[v] Fast / Verbose
[↑/↓] Move   [Esc] Back   [?] Help   [q] Quit
```

After (production adapter over an isolated environment and a recording fake provider):

```text
> Verify
  Replace

- github-token in macos-keychain  ✓ Ready
  Used by
    • public/mcp/github@1.6.0
  It cannot be removed while these use it.
  AART never reads or shows its current value.

[Enter] Verify   [v] Fast / Verbose
```

On Replace, Verbose describes the row (`Opens a review first. macos-keychain then asks for the new
value itself; …`), and Enter reads `Review replacement` and opens 24a:

```text
AART / Credentials / Credential Details / Credential Action / Review Credential Action

- Replace github-token in macos-keychain.
  macos-keychain asks for the new value in this terminal.
  AART never reads or shows the current one.

- These use it and will use the new value:
    • public/mcp/github@1.6.0
  No copy of the current value is kept, so this cannot be undone.

[Enter] Confirm   [v] Fast / Verbose
```

Confirming lends the terminal to the provider, re-inspects, and lands on Credential Details with
`- Replaced github-token in macos-keychain.` Verify answers on 24a (`Checked just now; nothing was
changed.`, `[Enter] Credential details`).

Design and scope (D-262):

- New screen 24a, action kinds `credential-verify|replace|delete`, and a `_ROW_ACTIONS` table:
  Enter and the legend read the same row.
- The adapter plans with `plan_credential_mutation` over a live read and executes through
  `CredentialEffectInterpreter`.
- `credential_lifecycle` named effects by input only, so the interpreter could not act on them. It
  now uses the whole reference, as `installed_state` does.
- `credential_lifecycle` left the deliberate non-runtime list, and B-074 is resolved.
- Backing out of 24/24a now keeps the credential as the subject. Before, Esc from 24 showed
  `No credential is known here.` on 23.
- Receipts for credential actions, 23's `Actions:` sentence and 24a's title are B-120 or task 14.
- Unused Delete is held at the projection, reducer and planner. A real Credentials list only holds
  referenced credentials, so it has no unused row yet.

Evidence:

- `tests/credential_action_rows_test.py` (26 tests) covers:
  - rows from the permitted actions, Delete only when unused;
  - no bracketed labels, and consequences in status only;
  - the Enter label follows the cursor;
  - Verbose-only row descriptions;
  - a Hypothesis property: after any moves, Enter requests the row's action on the same reference;
  - replace/delete review wording, Esc cancel keeping the reference, and confirm executing the
    reviewed digest on that reference;
  - landing on 23 or 22, and Verify finishing in place.
- Adapter tests with a recording fake provider:
  - Verify inspects only and re-reads health;
  - preparing Replace touches nothing, and confirming releases the terminal, prompts with no value
    (`store` receives no value and `replace=True`), restores it and re-inspects;
  - a mismatched digest runs nothing;
  - a replacement not reported present fails;
  - in-use Delete is refused, naming the installation;
  - an unavailable provider refuses before any prompt, and an unknown reference is refused;
  - the digest is stable per plan and differs per intent.
- Shell E2Es run keys, reducer, adapter and frames together: replace reviewed and confirmed, Esc
  leaves the credential untouched, and Verify reports in place. No frame holds a value shape.
- `tests/credential_terminal_handover_test.py`'s composition test was already failing at HEAD: its
  fixture predated D-260's `targets`. Its namespace now carries the fields D-260 reads.
- Focused runs:
  - 51 consumer/frame/screen/credential/reachability modules. The only failure was the
    reachability exception list, now updated.
  - `make typecheck format-check lint docs-check`: OK.
- Targeted mutations, all killed:
  - deletion acknowledges dependants (**1 red**);
  - no terminal loan (**2**);
  - an unverified replacement counts as success (**1**);
  - Verify left pending (**2**);
  - Enter requests the first row (**6**);
  - the review forgets the reference (**9**);
  - Esc forgets the reference (**2**);
  - Delete lands on Details (**1**);
  - effects named by input only (**3**);
  - in-use restriction not stated (**1**);
  - no rows (**13**). On the first run this mutant hung: `_moved` looped forever looking for a row
    that no longer existed. The helper is now bounded by the rows, so it fails instead of hanging.
- Walkthrough section 12 adds the credential action checks. Scoped `make mutants` and the full suite
  are left to task 15. No human terminal retest is claimed.

### Task 13 — Credential guidance from Source to the point of entry (DONE 2026-09-14)

Link check against the real pipeline (compile → scan → assess → promote → publish → vendored
Registry → shell install, recording fake provider):

- The author's `help` already survived compilation and promotion into installation.
- Three display links were incomplete, plus a safety gap in guidance text (below).

Before, screen 07 for an MCP whose `help` declares a label, description, format and link:

```text
- A few things are needed before installation
  GitHub token
    Enter securely during installation
    Format: ghp_...
    GitHub token settings → https://github.com/settings/tokens
```

At the prompt, the journal read `released → prompted → restored` and nothing was written. The
operator's `password data for new item:` stood alone. The CLI printed:

```text
error: required installation inputs are unanswered
  - github-token (credential)
```

After, from the same pipeline (Fast):

```text
AART / Marketplace / Review Selection / Required Inputs
- A few things are needed before installation
  GitHub token — needed by company/mcp/github@1.5.0
    Lets the server read the repositories you choose.
    Get it: Create a token in GitHub settings → https://github.com/settings/tokens
    Format: fine-grained personal access token
    Grant read-only access to Contents and Metadata.
    Enter securely during installation
```

On the lent terminal, immediately before the provider's prompt:

```text
AART needs a credential to continue.
GitHub token — needed by company/mcp/github@1.5.0
  Lets the server read the repositories you choose.
  Get it: Create a token in GitHub settings → https://github.com/settings/tokens
  Format: fine-grained personal access token
  Grant read-only access to Contents and Metadata.
macos-keychain asks for it next. Type it there; AART never sees or keeps it.
```

The CLI's refusal now carries the same lines under `- github-token (credential)`, and its JSON
carries `inputs[].guidance`.

Design (D-263):

- `application/credential_guidance.py` makes the words for all three places. It groups by what
  owners say, so identical help is shared, differing help is kept per owner, and no owner is lost.
- Missing guidance says `Where to get it is not stated; ask the maintainer of <owner>.`
- `help.obtain_from.url` is optional, for manual issuance. The domain refuses Cc/Cf/Cs characters
  in guidance.
- Composition no longer treats a help difference as a declaration conflict.
- The author warning names the fix.
- The lab's `dummy-mcp` declares complete guidance with a disposable manual instruction.
- An older test held that Fast leaves a secret's description out. It now holds the owner's newer
  requirement that Fast says what the credential is for.

Found and deferred:

- B-121: two artifacts sharing a credential in one transaction fail the second's pre-check. It
  reproduces on the unchanged code.
- Screen 07's `[Enter] Open` legend and Ready's duplicated `credential(s) stored securely` line are
  left for task 14's audit.

Evidence:

- `tests/credential_guidance_test.py` (30 tests) covers:
  - exact Fast lines; manual issuance with no link; the honest fallback with no invented URL;
  - shared and conflicting owners, with a Hypothesis property that no owner is lost or repeated;
  - the stored and replacing briefing; screen 07 Fast vs Verbose; a projection without owners;
  - a Hypothesis property that Cc/Cf characters are refused in every guidance field; unsafe links
    (`javascript:`, `file:`, userinfo, embedded OSC, `ftp:`) refused; parser refusal before
    compilation; the optional link but required instruction;
  - the actionable author warning, and that a manual instruction clears it;
  - the interpreter briefing before the prompt, as a replacement, for an undescribed reference,
    and never for Verify/Delete;
  - the curses loan writing after `endwin` and before the prompt; narrow-terminal wrapping that
    never breaks a link longer than the width; an unbound loan still briefing;
  - composition keeping help per owner while a binding difference still conflicts.
- Real-pipeline E2Es:
  - guided help on 07 and in the briefing before `prompted`;
  - an unguided artifact's fallback on both;
  - a stored credential is neither prompted nor briefed;
  - two artifacts sharing a credential: one prompt, both owners' instructions;
  - no frame or briefing holds a credential shape;
  - the CLI text and JSON guidance, with the provider never prompted.
- Updated tests:
  - `consumer_views_test` now holds the new Fast rule;
  - the handover fakes accept the briefing;
  - `manual_test_lab_test` asserts the lab's complete manual guidance.
- Focused runs:
  - 118 related modules (1,344 tests) plus the lab module: OK. A second run failed only because I
    passed the new module twice, which trips Hypothesis's `differing_executors` check.
  - `make typecheck format-check lint docs-check`: OK.
- Targeted mutations, all killed:
  - purpose dropped (**2 red**);
  - prompt not briefed (**6**);
  - installation guidance dropped (**3**);
  - owners dropped from 07 (**3**);
  - CLI guidance dropped (**1**);
  - control characters allowed (**2**);
  - link required again (**3**);
  - authoring drops `obtain_from` (**4**);
  - help counted as a conflict (**2**);
  - loan says nothing (**2**);
  - fallback silent (**3**);
  - owners merged across differing help (**9**);
  - warning not actionable (**1**);
  - links broken when wrapped (**1**). This one first survived: at 40 columns the link fit
    anyway. The test now uses 30 columns, and the mutant is killed.
- Scoped mutmut and the full suite belong to task 15. No human terminal retest is claimed.

### Task 16 — User variables and credentials (DONE 2026-09-14)

Increments 16.1 and 16.2 are done (D-264–D-265). Increments 16.3–16.5 are not started.

#### 16.1 — Configuration lives per harness beside the installed artifact (DONE)

- `domain/configuration_files.py` is new. It covers:
  - the path `<artifact root>/config/<harness>.conf`;
  - one plain `input-id=value` format;
  - `configuration_value_problem`, which refuses empty, control/format characters, surrounding
    space and credential shapes;
  - a strict `parse_configuration_file`;
  - `ConfigurationFileRecord`, which holds a harness, path and digest and never a value.
- Planning (`artifact_installation.py`, `installation_proposal.py`):
  - A configured artifact gets one `ConfigurationProjection` per chosen harness.
  - Each harness registration passes its own harness as the single launcher argument.
  - `PlannedInstallation` refuses a plan whose files and registrations disagree, or whose file
    content is not the reviewed values.
- The launcher (`application/runtime_projection.py`) holds no configuration value. When the
  artifact has configuration, it reads `config/$1.conf` with `read -r`, so nothing is evaluated.
  It exits 76 with a message pointing at "User variables and credentials" when:
  - the harness argument is missing or invalid;
  - the file is missing;
  - a value is empty or repeated.
- Receipts record `configuration_files` (path and digest) only when configured, so older receipts
  are unchanged.
- Desired state has one `configuration:<harness>` WriteFile component per file. Observation hashes
  each file:
  - as written → MATCHED;
  - edited → DIVERGENT;
  - missing → ABSENT;
  - unreadable → UNKNOWN.
- `io/installation_execution.py` offers the file content to the file interpreter.
- Evidence:
  - `tests/configuration_files_test.py` (Hypothesis round-trip and credential-shape refusal);
  - `tests/harness_configuration_planning_test.py` (Hypothesis over harness subsets);
  - `tests/runtime_projection_test.py` `LauncherReadsHarnessConfigurationTest` (real sh, a
    Hypothesis property that a hostile value reaches the process as exact text and runs nothing);
  - `tests/configured_installation_action_e2e_test.py`
    `test_configuration_lands_per_harness_beside_the_artifact_and_nowhere_in_aart_state` (claude
    and tabnine files, mode 0600, `args` per harness, value absent from data root, launcher and
    settings).
  - The wide affected set (922 tests) passed, and typecheck, format-check, lint and docs-check are
    OK.
- **Not yet done for 16.1:** targeted mutations are not recorded. Candidates:
  - drop registration args;
  - skip the credential-shape check;
  - drop offering the config content;
  - DIVERGENT→MATCHED;
  - drop the launcher's duplicate check;
  - drop the receipt record.

#### 16.2 — Install-time configuration form (DONE)

- D-265 makes screen 07 a pre-review form when preparation finds unanswered ConfigInputs. Its
  rows are input ids plus Continue; defaults are prefilled but remain unaccepted until Enter.
  Printable input and whole-paste follow the existing forms, Backspace trims, and editing an
  accepted value makes it require Enter again.
- Inline refusal uses both the declared `validate_config_value` rule and
  `configuration_value_problem`. Credential-shaped accidental input is not drawn back into the
  frame.
- Secret inputs are auto-bound to an available provider even while config inputs are unanswered.
  They are shown under a distinct Credentials section and no credential value crosses the form.
- Continue re-issues INSTALL preparation with `PromptedConfigValue` answers before screen 05.
  Harness toggles carry the answers into each narrowed plan, after which the existing screen-07
  summary and Ready/remediation flow use the value-bound review digest.
- `tests/install_time_config_form_test.py` covers the pure draft/reducer, form rendering, inline
  validation, paste/backspace, reference separation, the real configured preparation and a shell
  E2E. The E2E selects OpenCode and Tabnine and proves only their real per-harness files contain the
  value while AART's isolated data root contains none.
- Focused evidence: 110 tests pass across the new module, installation-input/draft/action suites,
  action shell, task-10 harness choice, UI state, form lifecycle, frame structure and key legends.
  `make typecheck format-check lint docs-check` passes.
- Targeted mutations killed for 16.2:
  - treating a visible default as accepted was killed by
    `test_default_is_prefilled_but_continue_submits_nothing_until_enter_accepts_it`;
  - dropping `config_answers` from the continuation command was killed by the same reducer test;
  - bypassing declared validation was killed by
    `test_invalid_and_credential_shaped_values_stay_on_the_field`;
  - drawing a credential-shaped refused paste was killed by
    `test_problem_is_inline_and_a_credential_shaped_value_is_not_drawn`;
  - waiting to bind credentials until *all* unanswered fields were secrets was killed by
    `test_answer_reissues_the_real_preparation_as_a_prompted_source`.

The six previously owed 16.1 targeted mutations were also run and killed:

- dropping the harness registration argument;
- skipping credential-shape refusal;
- not offering configuration content to the file interpreter;
- reporting an edited file as MATCHED;
- dropping the launcher's duplicate-value refusal;
- omitting configuration-file records from the receipt.

#### 16.3 — Grouped user-input area (DONE)

- D-266 renames screen 22 to **User variables and credentials** and makes installed artifact
  coordinates its rows. Screen 22a is the group detail: Configuration lists each ordinary input's
  value and observed state per harness; Credentials lists provider-owned inputs and routes to the
  accepted Details and Action screens rather than duplicating them (INV-067).
- Composition reads real paths from `InstallationReceipt.configuration_files`, strictly parses the
  supported format, and compares bytes with the receipt digest. The four projections are matched,
  changed outside AART, missing and unreadable. Invalid/unreadable content contributes neither a
  guessed value nor raw content to application state.
- Credential health remains derived from provider references and observations. Fast shows no
  provider reference; Verbose may show the reference but never material.
- `tests/user_inputs_area_test.py` covers real matching, edited and missing files, invalid-content
  redaction, separate sections and an artifact having only a credential dependency. Existing
  credential action and shell tests now traverse the artifact group.
- Focused evidence: 137 tests pass across the new area, credential actions, navigation, session and
  machine composition, shell flows, frame structure and consumer properties.
- Targeted mutations killed for 16.3:
  - reversing the receipt-digest comparison;
  - reporting a missing file as matched;
  - projecting invalid file text as an ordinary value;
  - replacing the Credentials section heading with Configuration;
  - dropping credential-only artifacts from the grouped rows.

#### 16.4 — Reviewed per-harness configuration edit (DONE)

- D-267 adds screens 22b (choose harnesses; all installed harnesses for that input start ticked),
  22c (the value form) and 22d (review) under 22a's Configuration rows.
- The pure planner `application/configuration_edit.py` replaces one declared input in exactly the
  chosen files. It returns CONFIGURATION-only replacements and a digest-updated receipt, and it
  refuses:
  - an empty, duplicate or stale choice;
  - a credential-shaped value;
  - a value that breaks declared validation;
  - a changed or unparseable baseline;
  - an unchanged value.

  Diagnostics never echo the value.
- `io/configured_configuration_action.py` refuses when the installation has any existing drift and
  checks the plan's steps equal the chosen components (INV-179).
  - Completion checks the review digest, offers the rendered bytes, takes the lease and compares
    each chosen file's digest on every inspection (compare-and-swap).
  - It records the updated receipt (`Reconfigured` in Activity) and re-reads the machine.
- The handler reads the declared validation from the installed artifact's immutable object.
- Evidence:
  - `tests/configuration_edit_test.py` holds Hypothesis properties: touched components equal the
    chosen harnesses, and credential shapes are refused without being echoed. It also covers the
    reducer, form and masking.
  - `tests/configured_configuration_action_e2e_test.py` makes a real isolated install into Claude,
    OpenCode and Tabnine, then edits one, a chosen set and all harnesses. It checks:
    - only those files change in the project;
    - the receipt digests change only for them;
    - each harness's recorded command starts the server with its own value;
    - the value is absent from Activity, receipts and the whole state root.

    It also covers:
    - empty and stale choices;
    - a file changed after Review;
    - unrelated drift refused;
    - the real handler applying declared validation without keeping the value;
    - a shell run through 22a → 22b → 22c → 22d that writes only Claude's file.
- Targeted mutations killed:
  - Codex killed three:
    - editing only the first chosen harness (`harnesses[:1]`);
    - skipping credential-shape refusal;
    - not offering the rendered content (the edit E2Es failed).
  - This session killed four more:
    - skipping the compare-and-swap;
    - recording the old receipt;
    - allowing unrelated drift (it survived until
      `test_unrelated_drift_is_refused_so_an_edit_cannot_carry_a_repair` was added);
    - ignoring declared validation.

#### 16.5 — Credentials established from the area (DONE)

- Credential Action offers **Set** for an absent credential (`CredentialIntent.STORE`, the
  provider's `store` receives no value and `replace` is false). It offers only Verify for an
  unknown credential. A present one keeps Verify/Replace, plus Delete when unused.
- Set and Replace hand the terminal to the provider with task 13's briefing, gathered from every
  installed artifact declaring the input, then verify. A store the provider does not report as
  present is a failure, not a success.
- Evidence: `tests/credential_action_rows_test.py` covers:
  - the adapter setting and verifying;
  - an unconfirmed set that fails;
  - a shell E2E from the grouped area with the briefed handover.

  `tests/configured_configuration_action_e2e_test.py` checks that Set uses the installed authored
  briefing and verifies. `tests/consumer_flow_e2e_test.py` now expects `("verify", "set")` for a
  credential the provider lost.
- Targeted mutations killed:
  - offering Replace for an absent credential;
  - Set overwriting (`REPLACE` intent);
  - dropping the briefing.

#### Close-out

- The manual lab's `dummy-mcp` declares an ordinary `dummy-user` input (default `lab-user`,
  `AART_DUMMY_USER`), and its server reports the value. `tests/manual_test_lab_test.py` holds it,
  and the real authoring parser accepts the manifest. `docs/testing/TUI_MANUAL_WALKTHROUGH.md`
  gains the install-form, grouped-area, per-harness edit and Set steps.
- The secret-shape gate was failing on literals introduced during CP-23. They were fixed through
  `tests/credential_fixtures.py`, a parenthesized remediation string and slice wording:
  - `credential_guidance_test`;
  - `install_time_config_form_test`;
  - `configuration_edit_test`;
  - `tui_consumer.py`;
  - this slice.
- For task 14's audit, observed in the captured 22a–22d frames:
  - 22c opens with an empty field rather than the value the chosen harnesses currently hold;
  - 22d's Fast review is the generic lifecycle text (`Review configure …`, `Review identity:
    sha256:…`) rather than naming the input, the harnesses and the old → new change;
  - the breadcrumb for 22d runs to five segments.
- Candidate Product Specification revision (for the owner; not edited unilaterally):
  - §96 and §97 should say configuration lives per harness beside the installed artifact;
  - AART state keeps only its path and digest;
  - the launcher reads it rather than embedding it;
  - changes are CONFIGURE lifecycles over those files (D-264, D-267).
- Focused evidence:
  - 1199 affected tests across every module importing the consumer UI, views, actions, session,
    repair or configuration code, with one expectation then updated;
  - the touched modules re-run (88 tests);
  - `make secret-shape-check typecheck format-check lint docs-check` passes.

  The full suite and scoped mutmut remain task 15's.

### Task 14 — Frame and Verbose contract on every view (DONE, D-268–D-274)

#### 14.1 — The shared order is §167's (DONE, D-268)

- `Frame` now declares view status before notices, with help after them, next to the legend.
- `tests/screen_skeleton_test.py` holds the declaration to §167's order.
- `tests/screen_block_structure_test.py` holds it on a rendered Registry frame carrying a notice.
- Targeted mutation: restoring the old order failed both tests.
- 1041 tests pass across every module that draws a frame (85 modules).

#### Audit method (applies to the remaining increments)

- Every frame drawn by the 85 frame-drawing test modules was captured by wrapping `frame`, together
  with a synthesized Verbose variant of each Fast state.
- Each captured frame was checked for:
  - prose in the actions block;
  - the number of cursor markers;
  - a description with no row;
  - the header repeated in the body;
  - bracketed control text in the body;
  - that `v` changes only the profile;
  - that every advertised key dispatches.
- All 74 catalog screens (39 Consumer, 35 Maintainer) are drawn somewhere in the suite.
- Findings outside forms are listed under the increments that fix them.

#### 14.2 — Form keys follow the cursor row (DONE, D-269)

- Findings fixed:
  - forms 07, 21a, 22c, 31a, 46a and 46c advertised `v`/`?`/`q` on text fields, where those letters
    are typed;
  - the same forms left those letters dead on toggles and Continue;
  - Backspace and Space were offered on rows that do not take them;
  - a paste into Add Source raised.
- `tests/form_row_keys_test.py` covers every row of all six forms, both configuration forms included.
  Its key laws live in `tests/frame_contract.py`.
- Targeted mutations, all killed:
  - advertising `v` on a field;
  - leaving the letters dead off a field;
  - refusing a paste on Add Source;
  - offering Space on every row.
- 1110 tests pass across the 93 modules that import the TUI or its reducer.
- `make typecheck lint format-check docs-check secret-shape-check` passes.

#### 14.3 — Consumer list screens draw rows, the cursor and Verbose descriptions (DONE)

- The checker gained the frame laws, stated once in `tests/frame_contract.py`:
  - the actions block holds rows, what a row says under itself, and headings that group rows;
  - it draws exactly the state's rows, with the cursor on the state's row;
  - the description appears only in Verbose, and only on a screen with rows;
  - the body never repeats the screen name or talks about keys;
  - `v` changes only the presentation: the rows stay the same, and pressing it twice returns to the
    start. A row that shows the stored preference itself, such as the Settings detail level, may
    change.
- `tui_consumer.compose_frame` returns the `Frame`, so the checker reads blocks instead of lines.
- Findings fixed:
  - **21 Registries.** `[ Add Registry ]` is a plain row. A registry's sync explanation and snapshot
    details are its Verbose description (`registry_purpose`), not more lines at row level.
  - **22 User variables and credentials.** It no longer repeats its own name under the trail.
  - **22a.** The artifact and the provider promise moved to the view status. File paths and
    provider references describe the cursor row in Verbose.
  - **25 Activity.** Entries are cursor rows under their day, and the review identity is the
    cursor row's description. `render_activity` stays the command line's timeline.
  - **29 Doctor.** The repairable issues `r` acts on are cursor rows. Healthy artifacts and counts
    are the view status. `render_doctor` still prints the whole report for the command line.
- `tests/list_screen_rows_test.py` covers 22, 22a and 25 on every row in both profiles. The block
  tests for 21 and 29 were updated to the new rows.
- Targeted mutations, all killed:
  - a cursorless Activity or Doctor;
  - 22 naming itself;
  - file paths among 22a's rows;
  - the bracketed Add Registry button.
- 1115 tests pass across the 94 modules that import the TUI or its reducer. The static gates pass.
- Remaining audit findings for the next increments:
  - 04/04a Collection: prose among rows, and rows redrawn by `v`;
  - 07 and 22c forms: prose at row level;
  - 05: Enter offered before a harness is chosen;
  - 35 Candidates: table gutter;
  - 38 Validation;
  - 46 Registry Maintainer: rows redrawn by `v`, and a description with no rows;
  - 46d, 46f and 47: prose and the cursor;
  - 51: rows redrawn by `v`;
  - 53: prose, and Space/Enter on an empty facet list.

  The 21 toggle report came from a fixture whose session and stored profiles disagree; it will be
  confirmed before the matrix lands.

#### 14.4 — Collection, the configuration forms and screen 05 (DONE, D-270)

- **Findings fixed:**
  - **04 Collection.** It follows §161.4 and has no rows. Its view status is the summary: Includes
    and counts, what you will need, `N / M selected` and the custom warning. Verbose adds the
    contents and the selection identity. It no longer states `N selected` a second time.
  - **04a Contents.** The members are `[x]`/`[ ]` cursor rows. Verbose describes the member under
    the cursor rather than listing them all again.
  - **07 Required Inputs form.** The rows are `Configuration`, the fields and Continue. The
    introduction and the credentials, guidance included, are the view status. A field's binding is
    its Verbose description.
  - **22c.** The artifact, harnesses and explanation are the view status.
  - **05.** `[Enter] Continue` is offered only once the re-prepared plan matches the choice.
- **Checker corrections, found while confirming findings:**
  - The `v` law's comparison state could not exist, because the state keeps the stored and session
    profiles in step. So every Settings frame was reported, although 14.3 already said a row
    showing the preference may change. The allowance is now stated on drawn lines: a row may change
    only by naming the new detail level.
  - The 21 Registries report came from the shell's final `exited` state, which takes no keys. The
    `v` law now skips exited states; it was not a product finding.
- **Tests:**
  - `tests/list_screen_rows_test.py` covers Settings, 04 and 04a.
  - `tests/form_row_keys_test.py` holds every row of all six forms to the frame and `v` laws in
    both profiles, with a credential beside the install form's field.
  - `tests/install_time_config_form_test.py` pins the credentials out of the rows.
  - `tests/installation_harness_choice_test.py` holds screen 05's Enter to the key law.
- **Targeted mutations, all killed:**
  - the preview dumping members as rows;
  - member rows on the preview;
  - the selection count stated twice;
  - Verbose contents on 04a;
  - cursorless member rows;
  - `Harnesses:` among 22c's rows;
  - a `Credentials` heading among 07's rows;
  - Enter always offered on 05;
  - removing the checker's detail-level allowance.
- 1151 tests pass across the UI modules. The static gates pass.
- Audit re-run: every Consumer screen is clean. The remaining findings are all on Maintainer
  screens: 35, 38, 46, 46d, 46f, 47, 51 and 53.

#### 14.5 — Maintainer lists (DONE, D-271)

- **Findings fixed:**
  - **35 Candidates.** The `> ` gutter is inside the first cell and the heading is flush left, so
    rows and heading share the grid (`tests/tabular_list_columns_test.py` offsets by the gutter).
  - **38 Validation.** The checks are cursor rows under `Checks`. The verdict is the view status,
    and a check's detail is its Verbose description.
  - **46 Registry Maintainer.** Each subscribed registry is one cursor row with short digests
    indented under it, the same in both profiles. Verbose describes the registry under the cursor
    with the digests in full. With no row, the QA-095 explanation is Verbose view status rather
    than a description of nothing.
  - **46d Scan Result.** Only adoptable artifacts are rows. The rest, with reasons, and "Nothing in
    this repository can be adopted." are the view status. The `Space selects…` prose is gone.
  - **46f Adopted Artifacts.** Rows with URL, ref and short commit under them. The full commit,
    manifest and recorded input are the Verbose description, and the `Enter checks…` prose is gone.
  - **47 Bulk Promotion.** Candidates are cursor rows under their registry. Refusals and
    `Not promotable` are the view status, with no second `N selected`.
  - **51 Collection Candidates.** Rows only. Source, manifest, candidate and members are the
    Verbose description.
  - **53 Candidate Filters.** Values are rows and `Search / Filtered / Showing N of M` is the
    status. A value's match count is its description. `Space/Enter` is offered only with rows.
- **Tests:** `tests/maintainer_screen_rows_test.py` holds the frame, `v` and key laws on every
  cursor of each screen in both profiles. It covers the empty filters, bulk promotion with and
  without a selection, and Registry Maintainer with no row. It checks full digests only in the
  description, and `Not promotable` and the refused scan artifact in the status.
- **Targeted mutations, all killed:**
  - the cursor outside the Candidates cell;
  - a full digest in a registry row;
  - a cursorless registry row;
  - the registry detail dropped;
  - the no-rows descriptor dropped;
  - a description with no rows;
  - non-adoptable artifacts as rows;
  - key prose back on 46d and 46f;
  - cursorless bulk rows;
  - `Not promotable` dropped;
  - `Space/Enter` on empty filters.
- 1162 tests pass across the UI modules. The static gates pass.
- Audit re-run over 1172 recorded frames: no violation on any screen.
- **Still open for task 14** (the first three were fixed in 14.6):
  - Ready's duplicate credential line;
  - 23's `Actions:` line;
  - 24a's title;
  - 22c not prefilling the current value;
  - 22d's generic review text;
  - long breadcrumbs;
  - the recorded matrix: catalog coverage of all screens, laws over recorded states, `v`
    properties, text/curses equivalence.

#### 14.6 — Ready's count, `Actions:` sentences, 24a's title and long trails (DONE, D-272)

- **Findings fixed:**
  - **09 Ready** counts stored credentials from the plan's effects only. It said it twice, and said
    it where the plan stores none.
  - **23 Credential Details, Installed Artifact Details and Installed Collection Details** no
    longer print `Actions: …`; the legend offers the keys.
  - **24a** is titled `Review Replacement`, `Review Deletion`, `Review Setup`, or `Verification`
    for Verify's answer.
  - **Trails** past `CONTENT_MEASURE` elide their middle places as `…`, keeping the area and the
    place Esc returns to. 24a's went from 142 characters to 83.
- **Tests:** `tests/frame_wording_test.py` covers:
  - Ready with and without a store effect;
  - the three details renderers in both profiles;
  - 24a's three titles under the frame laws;
  - a deep trail and a trail that fits.
  `credential_action_rows_test` and `consumer_install_flow_shell_test` now expect the new titles
  and the legend instead of the sentence.
- **Targeted mutations, all killed:**
  - the inputs line back on Ready;
  - `Actions:` back on 23;
  - the generic 24a title;
  - an unfitted trail;
  - eliding the area first.
- The UI modules pass. The only errors are Hypothesis's differing-executors check from listing two
  modules twice in one run, which also fails at HEAD. The static gates pass.
- **Still open for task 14:**
  - 22c not prefilling the current value (fixed in 14.7);
  - 22d's generic review text (fixed in 14.7);
  - the recorded matrix.

#### 14.7 — 22c opens on the value held; 22d names the change (DONE, D-273)

- **Findings fixed:**
  - **22c** opens holding the value the chosen harnesses share, unaccepted. Differing values open it
    empty, and the status lists each harness's value.
  - **22d** Fast shows `Change <input> for <artifact>`, `harness: old → new` for each of the plan's
    configuration components, and the risks. The review identity is Verbose.
- **Mechanism:** `ConsumerScreenSource.drafted`, seeded once by `_reload(entering=True)` through
  `EDIT_CONFIGURATION`. `ConsumerScreens.held_configuration` reads the per-harness values.
- **Tests:**
  - `tests/configuration_edit_test.py` covers:
    - the shared value prefilled and unaccepted;
    - differing values opening empty and listed;
    - a reload keeping what was typed;
    - 22d's Fast and Verbose status under the frame laws.
  - The existing interaction tests clear the field before typing.
  - `configured_configuration_action_e2e_test` drives the real handler through the prefilled field
    and the `old → new` review.
- **Targeted mutations, all killed:**
  - no prefill;
  - prefill when values differ;
  - prefill on every reload (hangs `_cleared`, stopped by a timeout);
  - the differing values not stated;
  - the generic review back;
  - the 22b ticks instead of the planned components;
  - the review identity in Fast.
- 1187 tests pass across the UI modules and the configuration E2E. The static gates pass.
- **Still open for task 14:** the recorded matrix, with catalog coverage of every screen, laws over
  recorded states, `v` properties and text/curses equivalence.


#### 14.8 — the recorded matrix (DONE, D-274)

- **Recorded cases:** `tests/screen_cases.py` names all 74 catalog screens explicitly; it does not
  derive the expected inventory from the enums. Consumer installation, Marketplace, Registry,
  configuration and Activity states use their existing sources. Maintainer source sync,
  validation, promotion, Registry, lifecycle/provenance, immutable-version-conflict and Collection
  states use the real typed projections from their focused fixtures. Eight additional cases record
  searching, a filtered list, Help, quit confirmation, both active configuration forms, a refused
  review and a failed action.
- **Matrix laws:** `tests/frame_matrix_test.py` checks every recorded cursor in Fast and Verbose
  with `frame_violations`, `key_violations`, `literal_violations` and `toggle_violations`; checks
  that every offered row has a local or Enter action; and runs Hypothesis over interleaved move/`v`
  sequences. `_TextTerminal` receives the exact composed frame, a tall fake curses terminal draws
  its anchored equivalent, and a clipped one retains the complete footer and rule.
- **Findings:** the two walk-probe candidates were not product defects. Populated 22b has its
  harness rows when Space is offered, and entered 21d has the reviewed registry focus. The matrix
  design itself did have a coverage hole when the prospective expected set was enum-derived; the
  explicit `RECORDED_SCREENS` inventory closes it, so a new enum member fails before it can acquire
  a fallback case. No production change or screen-specific exception was needed in 14.8.
- **Focused evidence:** 242 task-14 tests pass, including the six matrix/property/terminal tests.
  `make typecheck format-check lint secret-shape-check` passes; `docs-check` is recorded after this
  close-out. Four targeted semantic mutations were killed:
  - removing Doctor from the recorded catalog failed exact coverage;
  - making `v` change focus as well as presentation failed 302 matrix states;
  - stealing literal `v` from configuration text entry failed eight form states;
  - dropping the curses footer failed all 74 clipped projections.
- The full suite, scoped `mutmut` and the owner's manual acceptance remain task 15, as requested.

#### 15 — closing evidence (IMPLEMENTED; awaiting the owner's manual acceptance)

Task 15 was started by Codex, which ran the full gates and the three scoped `mutmut` runs before
reaching its usage limit. Claude finished it from the recorded outputs. Nothing below was re-run to
get a better result.

- **`make quality`, one run at `085d5df`:** green.
  - format-check, lint and typecheck (260 source files);
  - unit: 4,273 tests, 1 skipped, 0 failures;
  - validate;
  - coverage: a second run of the same 4,273 tests, 85.94% branch coverage;
  - packaging-check, docs-check and secret-shape-check.
  - The built-in integration step was skipped as redundant: its 393 tests are among the unit run's.
  - Two `ResourceWarning`s for unclosed file reads in `maintainer_registry_rebuild_test.py` are not
    failures (B-123).
- **`make integration`, one run:** 393 tests, **1 error**, which is B-108 recurring.
  - `mcp_stdio_e2e_test.InstalledMcpServerTest.test_the_real_keychain_delivers_the_secret_to_the_launched_server`
    failed when `/usr/bin/security create-keychain` returned status 206 for its unique temporary
    Keychain.
  - No real login Keychain and no credential value were involved.
  - It was not retried, skipped or weakened. The separate integration gate is therefore **not
    green**, and B-108 records the recurrence.
- **Scoped advisory `mutmut`** (D-134; the working copies are kept under `/private/tmp/cp23-task15-*`
  because of B-110).
  - Property-test files had to be left out of `TESTS` (B-111). That exclusion alone made several
    task-14 claims look unheld, so every survivor inside a CP-23 function was re-run against the
    full focused modules through mutmut's own `MUTANT_UNDER_TEST` switch, with plain `unittest`.

  | module | mutants | killed | survived | no test | timeout |
  |---|---:|---:|---:|---:|---:|
  | `tui_consumer.py` | 3,957 | 1,912 | 1,892 | 151 | 2 |
  | `tui_maintainer.py` | 1,501 | 624 | 782 | 95 | 0 |
  | `application/consumer_ui.py` | 2,292 | 1,111 | 1,166 | 15 | 0 |

  - A first `consumer_ui.py` attempt aborted in its clean-test phase on B-111, so it is not a result.
  - **In-slice survivors turned into tests:**
    - **`_fitted` (D-272):**
      - a trail exactly `CONTENT_MEASURE` long;
      - a lone overlong place;
      - area kept, then area dropped;
      - the last place kept when even it does not fit;
      - the failure suffix counting towards the measure.
    - **`_screen_title`:** Verify named `Verification` while the provider is still being asked.
    - **`_heading`:** the failed trail ends with ` - did not run`.
    - **`configuration_value_status` and `configuration_review_status` (D-273):** both line for
      line, including `not set`, several risks, and `read only` when there are none.
    - **Maintainer (D-271):**
      - `maintainer_registry_detail`: observed and unobserved;
      - `maintainer_registry_rows`: registries separated, and no working tree without a workspace;
      - `maintainer_bulk_promotion_status`: nothing composed, nothing promotable, refused, and
        silent when there are offers.
    - Tests were added to `frame_wording_test`, `configuration_edit_test`,
      `maintainer_screen_rows_test` and `failed_action_terminal_state_test`.
    - Re-run against those modules, 46 of 49 consumer survivors and 17 of 30 maintainer survivors
      are now killed.
  - **Left standing, with reasons:**
    - `_fitted` 4, 10 and 11 are equivalent. `(1, 1)` falls back to the same `["…", last]`, and
      `>=`/`head - 1` only admit shapes longer than a whole trail that already failed to fit.
    - The maintainer ones are the wording of internal type-guard `ValueError`s, one guard's
      `or`→`and`, and a default cursor no alias can equal.
    - The bulk of the survivors are outside CP-23's claims:
      - `tui_consumer`: `CanonicalScreenSource._body` (418), `description` (130) and the older
        renderers;
      - `consumer_ui`: `key_event` (454), `reduce_consumer_ui` (269) and `key_bindings` (148),
        whose exact-key properties live in the excluded Hypothesis files.
    - They are recorded as B-122 rather than inflating this slice.
  - **`consumer_ui.py` action transitions.** The 72 survivors in `_action_prepared`,
    `_action_recorded`, `_action_failed` and `_declined_preparation` were re-run against 18
    non-E2E action, form, credential, configuration and matrix modules; 27 were killed.
    - The CP-23-owned remainder was screen 07's config-draft branch (16.2): entering Required
      Inputs cleared no earlier review identities and loaded no named screen. It is now held by
      `install_time_config_form_test`'s
      `test_a_preparation_that_needs_answers_opens_07_without_the_previous_review`, which kills
      mutants 14, 15, 16, 30 and 32.
    - Still standing:
      - `quit_pending=False` removals, which are equivalent unless a result arrives while a quit is
        pending;
      - the pre-CP-23 Registry Commit landing (`registry_commit_applied`, from CP-19/21);
      - Help/search reset on a declined preparation.
    - These go to B-122.
- **The complete screen/state matrix** is task 14's `tests/frame_matrix_test.py` (D-274). It covers
  74 screens plus 8 conditional states, every cursor in Fast and Verbose, text, tall-curses and
  clipped-curses projections, and Hypothesis over move/`v` sequences.
- **Before/after through the production composition.** "Before" was captured by the task 14 audit
  at `4394645` with `tui_consumer.frame`. "After" was rendered from `tests/screen_cases.py` at this
  close-out.

  | screen | before | after |
  |---|---|---|
  | 09 Ready | `1 credential(s) stored securely` twice, once from effects and once from inputs | the one effect line |
  | 23 Credential Details | ends `Actions: verify, replace.` above `[Enter] Open` | facts only; the legend offers the keys |
  | 24a (Replace) | `… / Credential Details / Credential Action / Review Credential Action`, 142 characters | `AART / Credential Details / Credential Action / Review Replacement` |
  | 22c | `> github-org` empty although every harness held a value | `> github-org [old-team]`, unaccepted |
  | 22d | `Review configure for …`, `Components changing: configuration:claude.`, `Review identity: sha256:…` | `Change github-org for public/mcp/github@1.6.0`, `claude: old-team → new-team`, `tabnine: other-team → new-team`, `Risks: local mutation.`; the identity is Verbose only |

- **Manual acceptance: not run.** The Git-backed walk is the owner's, in the marker-owned manual
  lab and the owner's own terminal: Source → Candidate → local commit → manual publication →
  Registry Sync → Marketplace → selected-harness install → guided credential entry →
  Success/receipt → credential lifecycle. It needs the lab state and a provider prompt that agents
  must not touch. `docs/testing/TUI_MANUAL_WALKTHROUGH.md` now ends with a CP-23 acceptance
  checklist naming what each step must show.
- **Lab reset fix before the walk (2026-09-15).** The owner's `make manual-test-setup-empty` failed
  in `reset_lab`: the lab Registry's vendored payload directory is `r-x`, and removing an entry
  needs write permission on its parent. The error handler only made the entry itself writable, so
  the retry failed again. It now also makes the parent writable and searchable.
  `manual_test_lab_test.test_reset_clears_a_payload_delivered_into_a_read_only_directory` reproduced
  the same `PermissionError` before the fix and passes after it. All 12 lab tests pass, as do
  format-check, lint and typecheck.
- **Candidate Product Specification revision:** the §96/§97 note stands as recorded under task 16.
- **Status:** CLOSED on the owner's instruction, 2026-09-16, without the walk being recorded here.
  What is claimed is what was measured: the gates above. No manual acceptance result is claimed,
  and B-108 was never recorded green in a standalone `make integration`. The walk in
  `docs/testing/TUI_MANUAL_WALKTHROUGH.md` remains worth running; it is no longer a blocker.
