# CP-24 — Field reports from the first released version

Status: IN PROGRESS — tasks 01–07 done in the repository (D-280 to D-286); the release itself
is the owner's to merge

Date: 2026-09-16. Authority: the product owner's GitHub issues #7 and #8 against the released
`v0.1.1`, and the owner's instruction that the Source Sync failure is the priority because it takes
the whole application down.

## Goal and scope

Repair what the first released version does to somebody using it, in the order of how badly it
hurts:

1. a Source whose stored Candidate history no longer matches its pinned revision makes **the whole
   local state unloadable**, with no way back that does not involve deleting files by hand;
2. an installation review names changes that are not going to happen, and counts effects in ways
   the reader cannot reconcile with what they asked for;
3. an installation reports nothing while it runs.

Out of scope: new TUI areas, new lifecycle capabilities, and any change to the release engine
beyond cutting the release this slice ends with.

## Product contract

Specification references: §§85, 116–123, 145–146, 152, 154–157, 161, 164, 167.
Invariants: INV-007–009, INV-016–023, INV-052–057, INV-061–068, INV-124–138, INV-149–168.

Two claims decide task 01 and are quoted in its tests: a projection reports the state it finds and
a refusal names the remedy the reader can carry out. A local state that cannot be loaded at all,
because one Source of several is inconsistent, is neither.

## Execution rules

Work one task at a time, in order. Characterize the real failure first: every task below names a
reproduction that must be red before the fix. Keep data, pure transitions and IO boundaries
separate. Record the targeted semantic mutation per task. Use Hypothesis where the claim is
universal. Run scoped `make mutants ONLY=<changed module.py> TESTS="<relevant test files>"` and
classify survivors. Do not weaken gates, and do not widen a task to cover something the issue did
not report — that goes to `BACKLOG.md`.

## Ordered tasks and acceptance criteria

### 01 — A stale Candidate scan must not make the whole local state unloadable

Reported in issue #8:

```
The local AART state could not be loaded.
  error [maintainer-composition-invalid]: cannot bind Candidate history for agent-mcp-servers:
  maintainer Source scan does not bind the current pinned Source
```

- `project_maintainer_source` (`agent_artifacts/application/maintainer_views.py`) raises when a
  stored scan's revision is not the pinned revision, and `read_maintainer_views`
  (`agent_artifacts/io/maintainer_views.py`) turns that into a refusal for **every** view. One
  inconsistent Source therefore hides every other Source, every Candidate and every Registry.
- After this task: a scan that does not bind the pinned revision is **not** projected as Candidate
  data, and that Source reads as needing synchronization, with the remedy named. Every other
  Source still loads. A scan that belongs to a different Source, or a view whose health belongs to
  another alias, stays a refusal — those are programming errors, not field states.
- Characterization: a store holding a pinned revision `A` and a Candidate history at revision `B`.
  Red before the fix through the composed `read_maintainer_views`, not through the projection
  alone.
- Property test: for any pinned revision and any stored scan, loading either projects the scan or
  reports that Source as needing synchronization, and never fails the composition.
- Targeted mutation: make the revision comparison always true; the characterization test must go
  red.

**Done (D-280).** `scan_binds_current_pin` in `agent_artifacts/application/maintainer_views.py`
decides once whether a stored Scan is Candidate data for the pin. `project_maintainer_source`
projects only a Scan that binds; an unbound one contributes no manifests, no Candidate states and
no registries, the Source reads `ATTENTION`, and `UNBOUND_SCAN_DIAGNOSTIC` names the remedy.
`read_maintainer_views` applies the same predicate before a Scan reaches the collection and
validation lists. A misfiled alias, health belonging to another alias, and unreadable history all
still refuse — those are not field states.

Evidence:
- `tests/maintainer_composition_test.py` — three characterization tests through the composed
  reader (the Source reads as needing a Sync, its collection Candidates do not leak, and the other
  Sources still load), plus the property
  `test_any_stored_scan_either_binds_the_pin_or_asks_for_a_sync` over pinned/stored revision pairs.
- `tests/maintainer_views_test.py` — the projection-level statement of the same contract, that a
  misfiled alias still raises, and that the remedy is added to the Source's own redacted
  diagnostics rather than replacing them.
- Targeted mutations: making the revision comparison always true, and dropping the predicate from
  the reader, each turn the characterization tests red. Verified.
- Scoped mutants: `agent_artifacts/io/maintainer_views.py` 336 killed, 0 survivors.
  `agent_artifacts/application/maintainer_views.py` leaves survivors only outside this task's
  claims — the exception texts, the pre-existing type-validation guard, the registry union and the
  published-at field. The last two are in `BACKLOG.md` as B-130 and B-131.
- Gates: `make unit`, `lint`, `format-check`, `typecheck`.

### 02 — A Source Sync that fails after pinning must leave a state the tool can still read

- `execute_source_sync` (`agent_artifacts/application/maintainer_sync.py`) advances the pin inside
  `sync_source_while_locked` and only then compiles, reconciles and writes the Candidate history.
  Every failure between those points leaves exactly the state task 01 has to tolerate, so the two
  tasks are one defect seen from both ends.
- After this task: a Sync that fails after the pin advanced leaves a state whose next read is
  loadable and whose remedy is "synchronize this Source again". Decide and record which of these
  the implementation takes: the history is written for the new revision in the same transaction,
  the pin is not published until the history is, or the failure records that the two are known to
  disagree. Record the choice in `DECISIONS.md` with the reason.
- Characterization: a compile refusal after a successful fetch. Assert the store afterwards, then
  assert the next `read_maintainer_views` loads.
- Integration test at the IO boundary, with a real store on disk.

**Done (D-281).** The pin is published last. `agent_artifacts/application/sources.py` splits the
locked synchronization into `resolve_source_while_locked` and `publish_source_while_locked` with
`ResolvedSourceSnapshot` between them; `sync_source_while_locked` composes the two and behaves as
before. `execute_source_sync` compiles and reconciles the resolved candidate first, then publishes
the pointer, then writes the history. A synchronization that already ended in the resolve step
(offline, or a refusal the fallback retained) compiles from the snapshot already pinned and
publishes nothing.

Evidence:
- `tests/maintainer_source_sync_application_test.py` — a compile refusal reaches neither `publish`
  nor `write-history` and leaves no pin; with a Source already established, the pin and its history
  both survive untouched and still bind each other; the event order is asserted end to end.
- `tests/authoring_source_admission_e2e_test.py` — the same over a real Git repository and a real
  store: after the failed Sync the store still pins the previous revision, its history still binds
  it, and `read_maintainer_views` loads with the Candidate still there.
- Targeted mutation: moving the publication back in front of the compile turns all three red.
  Verified.
- Gates: `make unit`, `lint`, `format-check`, `typecheck`, `docs-check`.

The remaining window is the two adjacent writes, publish then write-history. Task 01's tolerance
is what covers it; that is why both tasks exist.

### 03 — A way back from an inconsistent Source without editing files by hand

- `aart source sync` refreshes the managed snapshot and never writes Candidate history, so it
  cannot repair the state in issue #8 — and when the revision has not moved it reports `unchanged`
  and does nothing. The only writer is the Maintainer Sync behind the view that refuses to load.
  The owner was left with `mv …/candidates …/candidates.bak`.
- After this task: one documented command repairs it. Either `aart source sync` rebuilds the
  Candidate history when it does not bind the pin, or `aart doctor` reports the disagreement as a
  finding with a repair it can apply. Prefer `doctor`: it already reports and repairs, and Sync's
  contract is deliberately narrow.
- The repair must be reviewed before it runs, must name what it discards, and must never publish a
  registry mutation.
- Acceptance: from the exact store in task 01's characterization, the documented command returns
  the tool to a working state, proven end to end.

**Done (D-282).** Three things were wrong, and the third was the one that left no way back: the
only writer of Candidate history refused to run over a store it had written. `_bound_history` in
`agent_artifacts/application/maintainer_sync.py` now decides whether stored history describes the
pin; `_baseline` starts from no baseline when it does not, instead of refusing, and Candidate state
carries forward only from history that binds. History carrying another Source's alias still
refuses. `read_unbound_candidate_histories` reads the same disagreement outside the screens, and
`aart doctor` reports it under `candidate_history.unbound` with both revisions and the remedy,
exiting non-zero. No new repair kind was added to `aart doctor --repair`: rebuilding Candidate
history is a Maintainer Source Sync, which is already reviewed, leased and refuses registry
mutations. Doctor names it; Sync performs it.

Evidence:
- `tests/authoring_source_admission_e2e_test.py` — the whole loop over a real Git repository and a
  real store: `aart source sync` moves the pin and writes no history (which is how the reported
  store came about), `aart doctor` exits 1 and names the remedy, Source Sync rebuilds, doctor exits
  0 and the Candidate is back. Nothing under the data root is touched by hand.
- `tests/maintainer_source_sync_application_test.py` — a Sync can be reviewed over history that
  does not bind the pin, and its baseline is empty rather than the stale one.
- `docs/testing/TUI_MANUAL_WALKTHROUGH.md` section 5 records the loop as a check.
- Targeted mutations: treating unbound history as bound turns the review test red; dropping the
  finding from doctor's verdict turns the end-to-end test red. Verified.
- Gates: `lint`, `format-check`, `typecheck`, `docs-check`; `make unit` at the task's close.

### 04 — A review must name the installer that will actually run

Reported in issue #7: one artifact's review listed both

```
Install its Python dependencies with pip
Install its Python dependencies with uv
```

- `remediation_change` (`agent_artifacts/tui_consumer.py:732`) renders one line per remediation,
  and the planner offers one per available installer. Two mutually exclusive offers read as two
  changes AART will make.
- After this task: the review names one installer — the one that will run — or, where the reader
  genuinely chooses, presents them as one choice with one selected, never as two changes.
- Cover: only `pip` available, only `uv`, both, neither, and an artifact with no Python
  dependencies.
- Targeted mutation: collapse the selection so both lines return; the new test must go red.

**Done (D-283).** The planner was offering what the installer never does. `chosen_installer`
(`agent_artifacts/domain/python_runtime.py`) is now the single rule for which backend runs out of
every backend that could: `select_python_installer` ends in it, and `allowed_remediations` reduces
each dependency contract to that one offer (`_one_installer_per_contract`) after the policy filter,
so narrowing policy narrows which backend is named rather than removing the offer. The rendering was
left alone: `remediation_change` renders one line per remediation, and there is now one.

Evidence:
- `tests/environment_planning_test.py` — `PythonInstallerOfferTest`: both backends usable is one
  offer naming the one `select_python_installer` would pick; only `pip` and only `uv` each name
  themselves; a policy narrowed to `uv` names `uv`; a `uv` lock names `uv`; no backend at all is no
  offer; an artifact with no Python dependencies is offered no installer. The order the platform
  reports its backends in does not change the answer.
- Targeted mutation: making the reduction a no-op returns both offers and turns the new tests red
  (3 failures, all in `PythonInstallerOfferTest`). Verified.
- Gates: `lint`, `format-check`, `typecheck`, `docs-check`; `make unit` at the task's close.
- Scoped mutants: `agent_artifacts/domain/python_runtime.py` with `python_runtime_test.py` and
  `environment_planning_test.py` — 94 mutants, 53 killed, 31 survived, 10 unreached. The two
  survivors inside `chosen_installer` drop the sort key, which is equivalent: `PythonInstaller`
  subclasses `str`, so ordering by name is the default ordering. The rest are the serialization
  helpers, outside this task's claims, recorded as B-133. Two Hypothesis properties needed
  `differing_executors` suppressed to run under mutmut at all, for the reason
  `doctor_properties_test` records.
- Backlog: B-132 — choosing the backend in the review, if that demand appears, is one choice with
  one selected. B-133 — the serialized shape of a dependency specification is unheld.

### 05 — Effect counts must be reconcilable with what was asked for

Reported in issue #7: installing one MCP server reported `2 launcher(s) written`.

- `_OUTCOMES` (`agent_artifacts/tui_consumer.py:287`) maps one effect kind to one phrase and the
  view counts effects. Two written files are two launchers to the counter and one installation to
  the reader.
- After this task: establish what the two files are. If both are launchers the reader would
  recognize, say what each is for; if one is not a launcher, count it as what it is. A count the
  reader cannot reconcile with their own request is the defect, not the number.
- Cover a single-harness install, a multi-harness install and an artifact with no launcher.

**Done (D-284).** Both files are `WriteFile` effects and the counter keyed on the effect kind, so it
called the harness's configuration file a launcher. `EffectView` now carries an `outcome` beside its
`kind` -- what the change is to the reader -- and `_outcome`
(`agent_artifacts/application/consumer_views.py`) splits `write-file` on the `executable` flag the
plan already carries: the launcher is the file written executable, the configuration file is not.
`_OUTCOMES` is keyed by outcome and also names the delivery and merge effects a placement plans,
which had been counted as "other change". The canonical plan is untouched, so no review digest moves.

Evidence:
- `tests/install_review_counts_test.py` — one server into one harness reads `1 launcher(s) written`
  and `1 configuration file(s) written`, never `2 launcher(s) written`; into two harnesses, one
  launcher and two configuration files; an artifact that configures nothing reports only its
  launcher; a Skill placement, which has no launcher at all, reads `1 harness file(s) delivered`
  rather than `1 other change`.
- Characterization: before the fix those three read `2 launcher(s) written`, `3 launcher(s)
  written` and `1 other change`.
- Targeted mutation: collapsing `_outcome` back to one phrase for every `write-file` turns the new
  tests red. Verified.
- Gates: `lint`, `format-check`, `typecheck`, `docs-check`; `make unit` at the task's close.

### 06 — Show which step of an installation is running

Requested in issue #7: the Ready screen lists what will happen, and then the installation runs
silently.

- After this task: while installing, the reader sees which step is running and which are done,
  inside the shared frame (CP-22/CP-23 rules — no screen-specific skeleton exception).
- The progress report is a projection of the same effects the review listed, so the two cannot
  disagree. Rendering performs no IO.
- Cover: a fast install, a long step, a failing step (the failed step is named), and a narrow
  terminal. Property test: the steps reported are exactly the effects reviewed, in the order they
  run.

**Done (D-285).** The execution loop is the only place that knows where it has got to, so it is the
place that says so: `execute_repair` takes an optional `observe` and announces each step twice --
once when it starts, once with the outcome it got -- as a `StepProgress` (component, effect, `index`
of `total`, status, detail). What it announces is the plan's own steps in the order they run, so the
report is the review projected rather than a second list. `execute_installation`,
`execute_lifecycle`, `complete_installation_action` and `complete_configured_installation` thread it
through; a lifecycle announces its primary run only, never a restoration.
`project_running_installation` folds the reports into a `RunningInstallationView` and
`render_running` draws it in the finished report's shape with `▸` on the running step. The shell
lends a reporting handler a redraw callback for the duration of one execution and takes it back in a
`finally`, the way the credential terminal handover already works, and recognizes such a handler by
the `ProgressReportingHandler` protocol.

Evidence:
- `tests/installation_progress_test.py` — each step announced at its start and again when done; a
  plan with nothing to do announces nothing; the step that failed is the one named and the rest are
  reported as not attempted, never as started; an announcement says which component and which
  effect. Property (Hypothesis, over which components diverge): what is announced is exactly the
  reviewed plan's steps, in the order they run, numbered 1..n of n.
- `tests/running_installation_screen_test.py` — the steps are drawn while they run (`▸ launcher`,
  then `✓ launcher` beside `▸ harness:tabnine`, then `(2 of 2 done)`), inside the shared frame
  (`AART /` heading, section rule, `[q] Quit`); a failed step is named where it failed; the reporter
  is given back when the execution is over, and the handler is never left reporting into nothing; a
  long step detail keeps the report inside the structured measure, because the running report is the
  finished report's shape rather than a screen-specific skeleton.
- Characterization: before the fix nothing was drawn between the Ready screen and the outcome.
- Targeted mutation: disabling the shell binding (`if False and reporting ...`) so the handler is
  never lent a reporter turns three shell tests red plus one error. Verified.
- Gates: `lint`, `format-check`, `typecheck`, `docs-check`; `make unit` at the task's close.

### 07 — Gates, targeted mutations and the release

- Full `make quality`, plus a standalone `make integration`.
- Scoped `make mutants` over each module this slice changed, with survivors classified.
- Every task's targeted mutation recorded in this document.
- Then cut the release: merge to `main` with a Conventional Commits title per change, approve the
  workflows on the Release Please pull request, and merge it. Confirm the run attaches
  `aart_cli-<version>-py3-none-any.whl` to the new tag. Tasks 01–03 are `fix:`, so the version is a
  patch unless a task lands a feature.

**Done (D-286).** Gates and mutation adequacy for the whole batch.

- Full `make quality`: `format-check`, `lint`, `typecheck`, `unit`, `validate`, `coverage`,
  `packaging-check`, `docs-check`, `secret-shape-check` all green. 4,316 tests, 85.96% branch
  coverage. (`integration` is reported as skipped there: all 395 of its tests are among the 4,316.)
- Standalone `make integration`: 395 tests, OK. B-108, the temporary-Keychain failure that made the
  CP-23 run red, did not reproduce.
- Scoped `make mutants` over the two modules this slice gave new behaviour to, beyond the per-task
  runs already recorded above:
  - `agent_artifacts/application/execution.py` with `execution_test`, `installation_progress_test`,
    `installation_execution_test` and `lifecycle_execution_test`: 539 mutants, 254 killed, 115
    survived, 170 unreached. 18 survivors were inside task 06's claims -- `_member_observer` could
    be replaced by a no-op, `execute_lifecycle` could drop its observer, and the index and effect on
    a finished step could be anything -- so they became tests, not notes. After them: 327 killed and
    only 57 unreached, and every remaining survivor is a diagnostic string or a guard belonging to
    CP-12's transaction preflight, which this slice did not touch.
  - `agent_artifacts/application/consumer_views.py` with `consumer_views_test`,
    `install_review_counts_test`, `installation_progress_test` and `running_installation_screen_test`:
    2,220 mutants, 510 killed, 375 survived, 1,335 unreached -- the module holds every Consumer
    projection and the scoped test set exercises a few. The 16 survivors in
    `project_running_installation` were the slice's own, and they are now held by
    `RunningInstallationProjectionTest`; the rest are the older remainder B-122 already records.
- What the survivors bought, in tests rather than numbers: a finished step is numbered and named as
  its start was, including when the interpreter raised, was interrupted, or was missing; an applied
  step reports what the interpreter said; every member of a transaction says which artifact it is
  about; a lifecycle run announces its steps; the fold holds one line per step at the latest thing
  said about it, counted, named and attributed; and the drawn count moves 0, 1, 1, 2 rather than
  merely ending at the right number.

The owner chose the patch. Task 06 adds behaviour `v0.1.1` did not have, so `feat:` and `0.2.0`
were the alternative; they read it as the repair of a silence they reported, which is what the
issue says. The pull request that lands on `main` therefore carries a `fix:` title and a
`BEGIN_COMMIT_OVERRIDE` block whose entries are the six fixes and the slice's documentation, so the
CHANGELOG still names each area.

Remaining, and the owner's to do: merge #14 into `plan/cp-24`, merge #13 into `main`, approve the
workflows on the Release Please pull request and merge it, then confirm the release run attaches
`aart_cli-0.1.2-py3-none-any.whl` to `v0.1.2`.

## Evidence log

Every task's targeted semantic mutation, collected here so task 07 can check them in one place.
Each was applied to the production code, watched turn the named tests red, and reverted.

| Task | Mutation applied | What turned red |
|---|---|---|
| 01 | `scan_binds_current_pin` always true; and the predicate dropped from `read_maintainer_views` | the composition characterization tests in `maintainer_composition_test.py` and `maintainer_views_test.py` |
| 02 | the publication moved back in front of the compile in `execute_source_sync` | all three ordering tests (`maintainer_source_sync_application_test.py`, `authoring_source_admission_e2e_test.py`) |
| 03 | unbound history treated as bound in the Sync review; and the finding dropped from doctor's verdict | the review test, and the end-to-end doctor loop in `authoring_source_admission_e2e_test.py` |
| 04 | `_one_installer_per_contract` made a no-op, so both backends are offered again | 3 tests in `PythonInstallerOfferTest` (`environment_planning_test.py`) |
| 05 | `_outcome` collapsed back to one phrase for every `write-file` | the counts in `install_review_counts_test.py` |
| 06 | the shell binding disabled (`if False and reporting ...`), so no handler is ever lent a reporter | 3 tests plus 1 error in `running_installation_screen_test.py` |
| 07 | `_member_observer` made a no-op; the not-attempted and raised steps misnumbered; the fold's artifact and detail dropped | the tests written for each, in `installation_progress_test.py` |

Scoped `make mutants` runs and their classified survivors are recorded per task above; the
out-of-scope survivors became `BACKLOG.md` B-130, B-131 and B-133. (B-132 is not a survivor: it
records what task 04 deliberately left undesigned, a way for a reader to choose the other backend.)

## Handoff

`plan.json` holds CP-24 with these seven steps. Start at task 01: it is the one that takes the
application down, and task 02 is the same defect from the writing end.
