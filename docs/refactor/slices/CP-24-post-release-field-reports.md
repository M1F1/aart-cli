# CP-24 — Field reports from the first released version

Status: NOT STARTED

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

### 05 — Effect counts must be reconcilable with what was asked for

Reported in issue #7: installing one MCP server reported `2 launcher(s) written`.

- `_OUTCOMES` (`agent_artifacts/tui_consumer.py:287`) maps one effect kind to one phrase and the
  view counts effects. Two written files are two launchers to the counter and one installation to
  the reader.
- After this task: establish what the two files are. If both are launchers the reader would
  recognize, say what each is for; if one is not a launcher, count it as what it is. A count the
  reader cannot reconcile with their own request is the defect, not the number.
- Cover a single-harness install, a multi-harness install and an artifact with no launcher.

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

### 07 — Gates, targeted mutations and the release

- Full `make quality`, plus a standalone `make integration`.
- Scoped `make mutants` over each module this slice changed, with survivors classified.
- Every task's targeted mutation recorded in this document.
- Then cut the release: merge to `main` with a Conventional Commits title per change, approve the
  workflows on the Release Please pull request, and merge it. Confirm the run attaches
  `aart_cli-<version>-py3-none-any.whl` to the new tag. Tasks 01–03 are `fix:`, so the version is a
  patch unless a task lands a feature.

## Evidence log

Empty. Each task appends its characterization, targeted mutation, gates and before/after here.

## Handoff

`plan.json` holds CP-24 with these seven steps. Start at task 01: it is the one that takes the
application down, and task 02 is the same defect from the writing end.
