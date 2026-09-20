# CP-21 — Second manual TUI run

Status: OPEN — 7 OF 11 STEPS DONE

## Goal

Close the findings of the operator's second manual TUI run: the run that walked the maintainer
route from an empty Registry through initialization, Sources, Candidates, promotion and publication,
then the consumer route through Marketplace, install and credentials.

Three of them stopped the journey rather than blemishing it, and they set the order of work. Steps
2 and 3 have closed the credential and promotion-path blockers. The next boundary is the absent
screen skeleton: each screen composes its own spacing, sections and footer position, which is why
every second finding in the run is about not being able to read the screen.

## Product Specification authority

- 161.1 and INV-187: navigation and presentation remain understandable and safe.
- 161.5 and INV-197: automatic inspection is work inside the canonical install flow; conditional
  screens appear only when operator input or a decision is required.
- 161.7 and INV-199: approval is separate from publication, and Registry connections are distinct
  from the local Registry workspace. **QA-082 asks to narrow this, not to discard it** — see below.
- 161.8, 161.9 and INV-206/INV-207: credential values stay out of plans, receipts, logs and output.

## The push question (QA-082) — decided

The operator asked that AART, having already made the commit for them, also push it. This slice
originally recorded that as blocked: 164.7 said "AART may create the local registry commit but does
not push it", and the Product Specification is the sole authority.

**The product owner decided it on 2026-09-10, and 164.7 has been amended (`D-228`).** Having to
leave the surface to type `git push` is the defect, not the safeguard — the same bytes were reviewed,
validated and committed here a moment earlier, and moving them by hand is not a decision. The
boundary is now carried by the branch instead: a maintainer configures which remote branch a
registry publishes to and may choose any branch but the registry's default one; a push to, merge
into or fast-forward of the default branch is refused by AART itself, by name, rather than left to
the forge's branch protection to catch. A consumer subscribing to a registry reads its default
branch, so what a consumer can install is still what a person merged.

Step 9 builds it: the configured publication branch, the push effect and its receipt, the refusal
and its test, and the Registry Commit screen's action. It also settles QA-055, which asked the
weaker version of the same question.

## Findings

Fixed already, awaiting the operator's retest:

| Item | Surface |
|---|---|
| QA-058 | A space typed into Initialize Registry made a usable identity unusable |
| QA-059 | The TUI walkthrough went from Add Source straight to Sync, which cannot work |
| QA-061 | The default lab's Registry disagreed with the Sources it claimed to have vendored |
| QA-062 | An author editing an already-published version crashed Source Sync (`D-227`) |
| QA-081 | Credential entry dropped out of the TUI into a raw shell prompt (`D-229`) |
| QA-084 | The manual lab borrowed the real default keychain, so macOS offered to reset it |
| QA-063 | One malformed manifest failed the whole Source, with no path (`D-230`) |
| QA-064 | `[v]` now visibly toggles Fast/Verbose cursor descriptions (`D-233`) |
| QA-065 | Empty screen regions no longer draw duplicate rules (`D-232`) |
| QA-066 | The launch directory no longer runs into the title (`D-235`) |
| QA-067 | Every consumer screen uses one standard skeleton (`D-232`) |
| QA-068 | Screen and universal keys are split in an anchored footer (`D-234`) |
| QA-069 | The working directory is in the footer (`D-235`) |
| QA-070 | Cursor descriptions are one toggleable mode (`D-233`) |
| QA-071 | Nested views name the trail actually walked (`D-236`) |
| QA-072 | Completed sequences leave the Back stack (`D-237`) |
| QA-073 | Back through Validation keeps and restores the Candidate identity (`D-232`) |
| QA-074 | Enter on Validation Details continues to Policy (`D-232`) |
| QA-075 | Empty Registries says no Registry is *subscribed* yet (`D-228`) |
| QA-076 | Registry approval refreshes unchanged Candidates as promoted (`D-239`) |
| QA-077 | A screen identifier can no longer become a Source alias |
| QA-060 | Source Sync names publication, subscription and defaulting in order (`D-238`) |
| QA-083 | Nested Maintainer titles name Maintainer once (`D-236`) |

Open, in the order the steps take them:

| Item | Surface | Severity |
|---|---|---|
| QA-078 | A Skill reports three harnesses unsupported, then installs for all four | high |
| QA-080 | Remediation lists "configure harness" three times, unactionably | high |
| QA-079 | Install never asks which harness | medium |
| QA-082 | Requested: push a reviewed Registry commit to a branch | medium |

The raw transcripts are the operator's own notes in `nowe bledy i znaleziska.txt`, which is
untracked and is the reproduction for every item above.

## Two revisions of earlier decisions

`QA-066` and `QA-069` revise `QA-053`/`D-224`, which put the launch directory directly under the
heading with no blank between them, on the reasoning that the directory is part of naming where the
reader is. The operator, having lived with it, wants the heading separated by a blank line and the
directory moved into the footer above the keys. Both are placement decisions about the same line and
must be settled as one, in step 5, rather than applied one at a time.

`QA-071` and `QA-083` pull in opposite directions — one adds the parent to the breadcrumb, the other
removes a repeated word from it. They produce one scheme or they produce an inconsistent one.

## Verification approach

Every screen-shape finding is a claim about a rendered frame, so each is stated first as a failing
assertion over `frame()` output rather than over an intention. The credential step is the exception:
its claim is that no interactive subprocess shares the terminal, which is a claim about the process
tree and is tested at the effect boundary.

The end of the slice is the operator's third run, not a green suite.

## Step 2 — done (2026-09-10)

The credential step turned out to be two faults with one symptom, and they are separable.

The product one (`QA-081`, `D-229`) is that nothing in the codebase ever released the terminal:
`curses.endwin`, `def_prog_mode` and `reset_shell_mode` appeared nowhere, and the whole session runs
inside one `curses.wrapper` while `security` prompts from far below it. Bringing entry into the TUI
would have fixed the drawing and discarded the invariant that AART never sees the value, so the fix
is a loan instead: `CredentialEffectInterpreter` wraps only `provider.store` in an optional
`terminal_handover`, and `_CursesHandover` gives the terminal up and takes it back around it. The
loan is composed unbound and bound by whichever adapter draws, so the text terminal and the CLI are
untouched.

The lab one (`QA-084`) is that `security` resolves the default keychain from `HOME` — measured, not
assumed — and the lab home had `.config`, `.local/share` and `.cache` and nothing else, so macOS
offered to reset a keychain. The lab now creates, defaults, lists and unlocks its own
`Library/Keychains/aart-manual.keychain-db`. No product change was needed, and a setup provably
leaves the real default keychain unchanged.

Six targeted mutations across the two, all killed. Tests:
`tests/credential_terminal_handover_test.py` and the two keychain tests in
`tests/manual_test_lab_test.py`.

## Step 3 — done (2026-09-10)

`QA-073` was one navigation-state defect with two representations of its subject. Candidate Diff
needs a bare Candidate ID, while entering a Validation check stores `candidate:check` so Validation
Details can identify the selected evidence. The existing workflow preservation kept focus only
across screens present in the progress route; Validation Details, Candidate Lifecycle, Provenance
and Version Conflict are deliberately absent because inspecting them is optional. Back therefore
discarded focus from every one. Even unconditional preservation would still have handed Diff a
composite identity it cannot resolve.

`D-232` keeps those concerns separate. Optional inspection screens stay out of progress chrome, and
a separate finite reverse-edge table preserves their Candidate-review subject: Lifecycle,
Provenance and Version Conflict can return to Details or their nested owner, and Validation Details
can return to Validation. When Back targets a screen that consumes a bare Candidate, the reducer
parses a validation-row identity and keeps only its Candidate part. Unrelated Back navigation still
clears focus. The full Details → Validation → Diff journey now renders `Semantic changes:` for the
same Candidate instead of either unavailable message, and an exhaustive test holds that reduction
for every member of the closed `ValidationCheck` enum.

`QA-074` was the missing forward edge. Validation Details now advertises `[Enter] Policy`, and its
canonical detail destination is Policy Review whenever the composed validation evidence still
exists. No check is rerun and no policy or promotion effect occurs; it is navigation over evidence
already assembled outside the renderer. The direct `p` shortcut remains on Validation, but its
label is now the screen it opens — `Policy`, not `Promote`. The production-composition E2E takes the
operator's route through one check and continues with Enter.

Five deliberate semantic mutations were killed: remove an optional Candidate-inspection edge,
remove the Validation Details edge, retain the composite row on Diff, remove the Details
destination, and replace its Enter binding. The scoped
advisory mutation run killed all mutants in the changed back-navigation helpers and six selected
mutants in the Details/Policy projection. Its remaining whole-file survivors concern code outside
this step's tests and claims.

## Step 10 — done (2026-09-10)

`QA-063` was recorded as unconfirmed, and measurement settled it in both directions. One manifest at
`not-a-version` did abort the whole Source and discard its healthy neighbour — but the diagnostic
already carried `location.path`, so the missing filename was a rendering fault sitting on top of a
compilation fault. Two halves, one symptom, again.

The compile step now answers with both: `compile_author_manifests` judges each manifest alone and
returns `(artifacts, refusals)`, a `ManifestRefusal` holding a path beside its diagnostics. A fault
in the tree itself still refuses whole, because no manifest owns it, and `compile_author_snapshot`
survives as a strict wrapper so adoption and publication keep refusing whole. Only
`compile_author_source` — the watching boundary — tolerates.

A refusal is reported beside the scan, not stored as an `invalid` Candidate (`D-230`). It rides on
`SourceSyncExecutionResult`, projects to `MaintainerSourceSyncResultView` as `(path, reason)`, and
renders under `Could not read N manifests:`. Candidates are persisted and reconciled; a refusal has
no compiled artifact to promote, so a row for one would be a Candidate-history schema bump for a
record that can never advance. `manifest_count` counts refusals beside the candidate states, so the
arithmetic on the screen closes.

Order mattered here: making `compile_author_source` tolerant while nothing downstream could carry a
refusal would have dropped bad manifests silently, which is worse than the loud abort. It was
reverted once for exactly that and re-applied only after the result, the view and the renderer could
report.

Four targeted mutations. Three killed on sight; the fourth — a schema refusal turned into a silent
skip — survived, and
`test_a_manifest_whose_schema_cannot_be_read_is_refused_rather_than_skipped` is what closed it.
Tests: `tests/source_partial_compilation_test.py` and `tests/source_sync_refusal_report_test.py`.

## Step 9 — partial (2026-09-10): the rule and the push exist; the screen action does not

`D-228` made publication AART's work, and this builds it from the bottom. Three layers landed, and
the fourth is deliberately not started because Codex holds the screens it would touch.

`aart_cli/domain/publication.py` decides the rule from two strings and nothing else — what
was asked for, and what a subscriber reads — so the refusal needs no repository and no network.
`refs/heads/main`, `HEAD` and `Main` are the default branch under other spellings rather than three
separate targets, and each is refused as such. `aart_cli/application/registry_publication.py`
binds one reviewed revision to one branch on one remote; `force`, `merge`, `fast_forward` and
`delete` are absent from the command rather than refused by it, and a test asserts that absence.
`aart_cli/io/registry_publication.py` pushes `<revision>:refs/heads/<branch>`, so the reviewed
commit moves rather than whatever `HEAD` has become, and it makes the default-branch refusal a
second time from the remote's own advertised `HEAD` — because a configured ref can disagree with the
remote it names, and the branch that must never move is the one the remote calls default.

Evidence is a real bare remote, not a fake: `tests/registry_publication_io_test.py` pushes, reads
the remote back, and asserts `main` is byte-for-byte where it was. A rewritten history is a failed
push rather than a lost one, because `--force` is never constructed.

Five targeted mutations, all killed by exactly the test that names the claim: the case fold on the
default comparison, the `refs/heads/` strip, `--force` on the push, the remote-`HEAD` check, and the
revision shape in `prepare`. `make mutants` then found four the targeted set had not: the adapter's
three guard-clause branches, and the "does this checkout hold that commit?" check, which existed
only to give a better message than Git's and had no test holding it. All four are closed. The 39
survivors that remain are message prose and equivalent mutants (`decode("UTF-8")`, `revision[:13]`,
a dropped `--`), plus one class that belongs to `Diagnostic` rather than here — `B-109`.

**Still to do:** the Registry Commit screen's action, the publication branch as configuration rather
than an argument, and the receipt's place in the maintainer's frame. All three live in
`tui_maintainer.py` and the maintainer views. Step 3 has landed, so they are step 9's next surface.

## Step 8 — diagnosed, not landed (2026-09-10): use the setup path established by step 3

`QA-078` was measured to the line and the answer is `D-231`. Two screens, two sources: Artifact
Details asks the manifest through `evaluate_compatibility`, the install plan asks the request through
`_deliveries`, and neither is wrong about its own source. Nothing about a Markdown Skill makes three
harnesses unsupported — the author declared one harness and only one screen was listening.

The narrowing was built at the placement boundary and backed out on evidence rather than on doubt.
It worked: the targeted tests passed, the shell reached `SUCCESS`, the Skill was delivered to the one
declared harness. But the receipt then records the narrowed set while the host it is reconciled
against still carries every measured harness, so `configured_consumer_completion` refuses —
`configured-setup-invalid: setup requires one exact configured installation receipt` — and the
`CONFIGURED` marker is never written. That refusal is correct. Narrowing is a change to what is
offered, and the offer is made in the consumer setup and remediation path that step 3 established;
doing it inside the placement that merely serves the offer makes the receipt disagree with the host.

Step 3 has landed, so step 8 can now make that setup-path change; it also settles `QA-080` for free:
a plan for one harness cannot list "configure harness" three times. Two things the next agent should
not re-derive — empty means
unconstrained, because `allow_empty=True` makes an absent block and an explicit `[]` the same `()`;
and `measured_host_profiles_test.py` and `git_backed_runtime_e2e_test.py` assert the defect rather
than tolerate it, so they change with the fix and that is not a regression.

Nothing product-side was left behind. The tree is as it was, and the diagnosis is in `D-231` and in
the `QA-078` entry of `TODO.md`.

## Step 4 — done (2026-09-10)

Five findings, one cause. Every screen composed its own spacing, so the same kind of thing sat at a
different height depending on when that screen was written, and the doubled rule `QA-065` reported
was the most visible thing that fell out of it.

The fix is a decision about what a rule *is* (`D-232`). `section()` treated it as a border and wrapped
each region in one above and one below, which is how two adjacent regions produced two adjacent
rules and an empty region still produced its pair. `screen_frame` treats it as a separator between
two regions that both have something to say, and drops empty regions before placing any rule at all,
so the doubled rule cannot be constructed rather than being avoided by each screen remembering to.
The blank either side of every rule comes from the same place. One `frame` now puts title,
menu/list, cursor description, help, view status and footer through that composition, and
`CanonicalScreenSource` gained `description` and `status` so the skeleton's named slots are answered
by the screen rather than embedded in its body.

The legend is placed rather than drawn (`D-234`). `footer_start` reads back where the footer begins
— the last rule, its own boundary by construction — and `anchor` inserts blank rows above it for a
terminal of a given height, which the curses adapter supplies. The frame never learns the terminal
height, so it stays a value that can be asserted against; the adapter only adds rows, and a body too
tall is clipped with the legend kept whole. Screen keys now sit on the line above the universal ones,
read off the order `key_bindings` already guarantees rather than off a second list that could drift.

`[v]` became the toggle over the cursor descriptions (`D-233`), which settles `QA-064` in the same
move: the key already changed `PresentationProfile` and nothing the operator could see read it, so
it was honest in the state and invisible on the screen. Fast is the default, so the descriptions are
off until asked for — the direction the finding wanted.

Five targeted mutations, each killed by the test that names its claim: the empty-region drop, the
padding side, the last-rule search, the legend split, and the description gate. `make mutants` then
found six the targeted set had not — the `anchor` guard clause, its `height=0` boundary, the blank it
pads with, `footer_start`'s loop bounds and its no-rule fallback, and `screen_frame`'s refusal of a
region that is not lines of text. All six are closed. What survives is the message-prose class and
one genuinely equivalent mutant: at an exact fit, padding by zero rows and not padding produce the
same frame.

Five tests changed with the fix rather than around it. Four read the frame by landmarks the skeleton
moved — `lines.index(SECTION_RULE)` used to find help's boundary and now finds the frame's first
separator — and one held the description as a permanent fixture, which is the claim `QA-070`
deliberately reverses. Tests: `tests/screen_skeleton_test.py`.

**Not settled here:** where the launch directory and the view path live. `QA-066`/`QA-069` revise
`QA-053`/`D-224` and must be decided together with the nested-title scheme, which is step 5. The
skeleton only fixes that the heading and the context line arrive as one region.

## Step 5 — done (2026-09-10)

Two pairs, each settled once rather than one finding at a time, because in both pairs the two halves
pull against each other.

The operator revised themselves mid-run on the launch directory: separate it from the title
(`QA-066`), then move it out of the header entirely (`QA-069`). `QA-069` is the later and more
specific half and it wins (`D-235`, revising `D-224`). The top line carries only the trail, and
`working at <path>` is a region immediately before the key legend — which answers `QA-066` by
removing the second header line rather than by adding the blank it asked for. `D-224`'s reasoning
survives its own reversal: the directory is still chrome every screen carries, and only its place
changed. Beside the keys it also sits with the other thing that is true of the session rather than
of the view, so the skeleton's existing rule was enough and nothing new had to be invented.

The title scheme is the trail the reader actually walked (`D-236`), taken from `ConsumerSession`'s
history rather than from the declared navigation graph. The graph could not answer without guessing:
Review Selection declares four parents, so a breadcrumb that picked one would be wrong for three
journeys out of four. History is the ancestor chain by construction — `advance` pushes, `back` pops.
Two places are named differently in opposite directions for one reason: the home Dashboard
contributes no step, because `AART` already names it, and a dashboard passed *through* drops the
word, because a dashboard inside a trail is the place it is the dashboard of. Together those turn
`AART / Maintainer Dashboard / Sources` into `AART / Maintainer / Sources`, which is `QA-071`
answered and `QA-083` answered by the same rule instead of by two rules that would drift apart.

Four targeted mutations, each killed by the test naming its claim: the home-dashboard step, the
dropped word, the trail's use of history, and the directory's place. `make mutants` left one
survivor in `_step` — `title[:+10]` instead of `title[:-10]`, which for "Maintainer Dashboard"
returns the same ten characters. It is equivalent within the real screen catalog, where that is the
only passed-through dashboard carrying the word, so it was recorded rather than closed with a
synthetic screen that does not exist.

Twenty-two existing assertions changed, all of one kind: `screen_containing("AART / Installing")`
identified a screen by assuming it sits directly under `AART`, which is exactly the flat scheme
`QA-071` replaces. They now look for the screen's own name at the end of the trail, which is the
claim they were always making. `workspace_context_line_test.py` is the exception worth naming: it is
`QA-053`'s own characterization, and `QA-066`/`QA-069` revise `QA-053`, so its docstring records the
revision rather than quietly changing the assertions under it.

Tests: `tests/screen_trail_test.py`. `B-111` records that `make mutants` aborts the whole run when a
Hypothesis property test is in `TESTS`, which cost this step one run to diagnose.

## Step 6 — done (2026-09-10)

`QA-027` fixed the forward exit and left the stack alone, which is why `QA-072` outlived it: the
list a finished journey lands on was already on the stack, arriving there a second time, and Esc
walked back into the wizard that had just run.

The rule is that returning to a place already stood in is a return rather than a step deeper
(`D-237`). `ConsumerSession.navigate` rewinds to that place instead of pushing, dropping exactly the
screens walked since it. What makes this the right shape rather than a special case is that it needs
no list of which journeys count as finished: a sequence that ends by returning somewhere is finished
by the act of returning, and one that ends somewhere new is not, so the same line reads correctly in
both cases and nothing has to be kept in step as journeys are added.

The finding's second sentence is a second rule, because it holds where nothing was completed. A list
is a place reached *from* a dashboard, so leaving it means "done looking at this" however the reader
arrived — Candidates is reachable sideways from the Registry screen and still answers to the
Maintainer Dashboard. Ownership is read from the declared navigation rather than from a new table.
The redirect is guarded on the owner being on the stack: leaving is a return, and `make mutants`
proved that guard was unheld by anything, which is a fair description of the bug it prevents —
without it, Esc from a stranded list invents a forward step into a screen never opened.

Four targeted mutations, all killed. The `make mutants` run over `consumer_views.py` reported no
survivors in the changed code and is worth distrusting: `B-112` records that it mutated no class
method in that module at all, so `navigate` was covered by the targeted mutations and by nothing the
tool did. The `_back` survivors it did report are the pre-existing focus and search resets, held by
other suites — outside this slice's claims, and left as such.

No existing test changed, which is the useful signal here: the stack was never asserted to contain a
completed sequence, so nothing was holding the defect in place. Tests:
`tests/back_stack_after_a_sequence_test.py`. One consequence worth naming — the heading reads the
same stack (`D-236`), so this also removed the trail that could name a place twice.

### Step 7 — Screens tell the truth about state (`QA-060`/`QA-075`/`QA-076`/`QA-077`)

All four landed and await the operator's retest.

**`QA-077` — no internal screen identifier reaches the operator.** Measured before touching code,
because the message (`authoring Source 31-sources is not configured and enabled`) named a thing that
does not exist and could have come from anywhere. The route is short and entirely ordinary: a
dashboard's rows *are* screens, so `current_row` on a dashboard holds `"31-sources"`, and `_navigate`
carried it forward as the next screen's `focus`. It then survived `SET_ROWS` loading the real
aliases — nothing re-checks a focus once set — and arrived at `prepare_configured_source_sync` as a
`SourceAlias` that no configuration could match, which is why both Sources read `Stale` at once.

Fixed where the wrong value is created rather than where it was seen: `is_screen_identifier` in
`consumer_views.py` asks the two screen enums, and `_navigate` drops a focus that is one. That is one
guard on the single carrying-forward point, so it holds for every route rather than for the two the
operator happened to walk — `tests/screen_identifier_leak_test.py` asserts it over all 86 declared
routes as subtests, and separately proves the value used to survive the real rows loading.

**`QA-075`/`QA-060` — one complaint from two screens.** A maintainer who has just initialized a
Registry is told `No Registry is connected.` on one screen and `configure an enabled default
registry` on the next. Both true, both unactionable, for the same reason: neither says that the
Registry they just made is not yet a *subscribed* one, or what turns it into one. Both now say it,
in the same words (`D-228`).

`QA-060` also produced a constraint worth having found: remediation cannot express an order.
`Diagnostic` normalises it with `tuple(sorted(set(...)))`, so several remediation lines are a
deduplicated *set* of independent remedies and alphabetical is the only order they can have — here,
exactly backwards. The steps that must happen in sequence are therefore one remedy on one line, and
`D-238` records why, so the next agent wanting ordered advice does not rediscover it by watching a
test fail on line order. The targeted mutation is the honest one for a claim about order: reversing
the clauses turns the ordering test red and nothing else.

**`QA-076` — registry state is re-derived even when the Source did not move.** The diagnosis was
correct: the unchanged-artifact short circuit returned the prior before consulting `approved`.
`reconcile_source_scan` now passes that unchanged Candidate through the same exact registry match as
a freshly derived one. Collections take the same path because 164.10 makes them Candidates too
(`D-239`). Exact coordinate, Candidate ID and content digests produce `PROMOTED`; different content
at an approved coordinate remains `INVALID` with `registry-version-immutable`; unrelated Registry
entries do nothing.

The refresh is guarded for `PROMOTED`, `SUPERSEDED`, `REJECTED` and `SOURCE_REMOVED`. Those records
carry historical decisions or terminal facts, `assess_candidate` refuses terminal input, and
INV-239 requires an unchanged rejected Candidate to stay rejected. `QA-062`'s promoted/current split
therefore remains intact rather than being worked around.

One existing test changed, and it is the ordinary kind:
`maintainer_registry_view_test.py::test_an_installation_with_no_composed_registry_refuses_instead_of_raising`
asserted the old sentence while claiming to be about refusing rather than raising. It now tracks the
new wording; nothing about what it holds moved. The broad run is what caught it, which is the reason
that run exists.

Tests: `tests/empty_state_truthfulness_test.py`, `tests/screen_identifier_leak_test.py`,
`tests/maintainer_version_conflict_test.py`, and `tests/maintainer_collection_history_test.py`.
Two deliberate QA-076 mutations were killed. The scoped advisory run generated 472 mutants and
killed 353; none survived in the registry matching helpers or the new refresh branches. Broad set:
1767 passed / 799 subtests. Gates: focused suites, `ruff check`, `ruff format --check`,
`make typecheck`, `make docs-check`, and `make secret-shape-check` — all clean.

### Step 8 — harness delivery is one honest answer (`QA-078`/`QA-079`/`QA-080`)

This step began by re-opening a deferral rather than by writing code. `D-231` had measured `QA-078`
completely and then declined to land it, because narrowing inside `placement_for` made
`configured_consumer_completion` refuse: the receipt recorded one harness while the machine carried
four. It expected the narrowing to arrive with the consumer setup path step 3 was rebuilding. Step 3
turned out to be the promotion path, so that host never existed, and re-deferring on a premise that
had expired would have been the easy wrong answer.

Looking again at the refusal turned out to be the whole step. It was not blocking the fix; it was
the second half of the same defect. Setup iterated every harness the build measured and asked the
receipt store for evidence about harnesses the install had never touched — which is also `QA-080`
told from the screen instead of from the code: four `configure harness` rows for an artifact
installed into one, three of them about nothing, and the operator asking *"jak mam skonfigurowac
harness?? nie rozumiem"* with no answer available because three of those rows had no subject.

`D-241` names the rule both findings share: a setup step is owed for a harness the artifact actually
reached. `receipt_profiles` already answered that and answered it the right way — from recorded
effects rather than from the request — so the fix was to ask it rather than to build anything. Once
the two sides stopped being asked the same question, the narrowing landed where `D-231` had said it
belonged: one point in `placement_for`, reusing the `_skippable` asymmetry instead of inventing a
second one, and sharing `supported_label` with `evaluate_compatibility` so the two screens that
disagreed cannot word one fact two ways again.

`QA-079` is closed by explanation, which is the honest half of its own expectation. The harness set
is derived from the machine and the manifest together, so there is nothing left to choose, and a
picker offering one answer would be a different lie. Screen 09 names the set and says where it came
from, read off the plan's effects so it cannot disagree with what runs.

Several fixtures declared one harness while asserting delivery to several — the defect written down
as a test, as `D-231` predicted. Where the file's own subject was the measured-versus-requested
asymmetry the declaration was incidental, so it was removed with a comment saying where the
narrowing is held instead; making those tests depend on two rules at once would have left them
saying which of the two failed for neither.

Four targeted mutations, all killed. Tests: `tests/declared_harness_narrowing_test.py`,
`tests/remediation_row_subject_test.py`, `tests/install_review_names_harnesses_test.py`. **Whole
unit suite: 3915 passed, 1 skipped, 2091 subtests.** Gates all clean.

### Step 11 — targeted mutations, full gates and durable handoff

The operator asked for the full suites to be deferred to the end of the batch rather than run after
every step, so this step is where that debt is paid, and where the advisory mutation run over the
module step 8 changed is finally read rather than skimmed.

**What `make mutants` found.** The scoped run over `aart_cli/io/artifact_placement.py`
generated 390 mutants and left 99 alive. Fifteen of them were inside
`_declared_narrowing`, the function step 8 added, and reading them named three claims the step had
made in prose and held nowhere:

- **`expected_identity=identity` was doing nothing any test could see.** Narrowing reads a package
  out of the object store to find out what the artifact declares. Passing `None` there — mutants 3
  and 5 — still delivered, using whatever manifest the object happened to hold. Every other
  assertion in the file would have passed with somebody else's declaration; the identity check is
  what makes "what the artifact declares" mean *this* artifact, and nothing said so.
- **The refusal the operator reads was unasserted.** `_declared_narrowing`'s docstring promises that
  a typed harness is refused *and* that the message names the set they can choose from — the same
  set Artifact Details showed them. The test asserted only that the refused name appeared. Mutants
  17–22 rewrote the remediation freely.
- **One test did not hold what its name said.**
  `test_a_declaration_that_leaves_nothing_is_refused_rather_than_silently_empty` passed
  `profiles=("codex",)` with the default `profiles_requested=True`, so it took the *typed* refusal
  and never reached the branch it was named after. That branch — the measured set narrowing to
  nothing — had no test at all, which is why mutants 27–35 rewrote its message and remediation
  untouched.

Two more survivors sat in `_deliveries` and `_merges`, in the asymmetry step 8 reused rather than
reinvented, and both are the same shape as `QA-078` one layer down:

- **`continue` → `break` survived** because every existing assertion puts the unusable harness
  *last* in the profile tuple. A loop that steps over it and a loop that stops at it agree on
  `("claude", "codex", "opencode", "tabnine")`. Reversed, they do not: a stop delivers to nothing
  and reports success.
- **`requested=profiles_requested` → `requested=None` survived** because a typed unusable harness
  produces an `Err` either way — once by name, once because nothing was left. Asserting `Err` and
  the refused name cannot tell a refusal from a silent narrowing that then ran out of harnesses.
  What separates them is whether the *usable* half is placed, so that is what is asserted now.

Eight targeted mutations, all killed, each by the test whose name says it: the identity argument
dropped from the narrowing call and from `_declared_narrowing` itself; the two refusal messages and
both remediations rewritten; `continue` turned into `break` in both per-profile loops; and
`requested` forced falsy at all four `_skippable` call sites.

Three tests were added and one corrected. `tests/declared_harness_narrowing_test.py` gains
`test_the_declaration_read_is_the_one_belonging_to_this_coordinate`, holds the supported-set half of
the typed refusal, and its misnamed test now reaches the branch it is named after.
`tests/measured_host_profiles_test.py` gains a pair for deliveries and a pair for merges: a skip is
a skip and not a stop, and the same profiles typed rather than measured are refused instead of
quietly reduced to the part of them that works.

The rest of the survivors are outside CP-21's claims, and `B-113` classifies them rather than
sweeping them up here. About sixty change only the *wording* of refusals that predate this slice,
each reached by a test that asserts `Err` and a code and nothing about the sentence. About ten drop
arguments on the hook `_settings` path or the optional `sources`/`preferred_installer` pass-through,
which no fixture in this scope walks. Three are genuinely behavioural and genuinely unheld: the
argument guard's `or`, the identity given to `ArtifactEnvironment` in both per-profile builders, and
the second half of `_merges`' destination join. Naming them is the honest form of "advisory";
asserting sixty sentences nobody has read at a terminal would work against the manual runs that keep
improving them.

**Gates.** `make integration` passes all 381 end-to-end tests standalone. `make quality` passes all
nine gates it ran, over 3,866 tests with one skipped, at 85.43% branch coverage — it skips
`integration` as redundant, because all 381 of those tests are among the 3,866, which is why the
standalone run is quoted separately. `make mutants` re-run over the same scope after the new tests
kills 22 more, leaves 77, and leaves none at all in `_declared_narrowing`.

CP-21 is implemented. What it is not is verified: every finding from `QA-058` to `QA-084` is closed
in the tree and none of it has been seen at a terminal by a person since the run that produced it.
The operator's retest of `QA-044`…`QA-057` was already outstanding; this batch joins that queue.
