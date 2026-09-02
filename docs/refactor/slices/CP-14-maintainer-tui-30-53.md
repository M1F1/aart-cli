# CP-14 — Maintainer TUI 30–53
Status: IN PROGRESS (opened 2026-09-01)

## Goal

Implement accepted Maintainer Mode screens 30–53 as projections over the canonical Source,
Candidate, Registry and Promotion models CP-05 established, inside the same persistent stdlib/curses
shell CP-13 reuses. Maintainer Mode is opt-in and hides its whole surface when off.

## Product Specification sections/invariants

Sections 164.1–164.10 (screens 30–53, all ACCEPTED) and 161.10 (Maintainer Mode is the boundary that
hides Sources, Candidates, Promotion, Registry Diff, Validation and Publish). INV-019–INV-027 for
what a Source is and is not, and 165.1–165.28 for the lifecycle edge cases these screens surface.

Load-bearing statements:

- "A Source is an authoring/discovery location. It is not itself an approved registry." (164.2)
- "Source Sync performs fetch/discovery/diff and creates or updates candidates. It never performs
  promotion." (164.2)
- "Maintainer review is **semantic diff first, file diff second**." (164.5)
- "Warnings and errors are distinct. Policy determines whether warnings block promotion.
  Policy-required manual approval is an explicit candidate state and cannot be hidden as an ordinary
  warning." (164.6)
- "Promotion creates canonical registry state and provenance but does not automatically push Git
  changes." / "Commit is explicit. AART may create the local registry commit but does not push it."
  (164.7)
- "Bulk promotion produces one coherent registry diff/validation/commit boundary." (164.9)
- "Published `coordinate@version` is immutable. A candidate with the same coordinate/version but a
  different digest is blocked and must receive a new version." (164.10)
- "Collections are candidates too. Collection validation resolves membership against registry state
  and verifies that members are approved and compatible." (164.10)

## Legacy/current paths

`tui.py` holds a mature maintainer-oriented Sources UI and registry command surface, characterized
but wizard-shaped. `commands/registry.py` and `registry_commands/`, `registry_maintenance/` own the
public non-interactive maintainer commands. `agent_artifacts/consumer/*`, `installation/*`,
`lifecycle/*` and `setup_engine/*` still carry consumer authority for Collections and direct/local
sources; CP-13's remaining legacy removal is sequenced behind this slice (D-091).

## Target paths/owners

- `application/maintainer_views.py`: immutable screen/view models projected only from canonical
  Candidate, Source scan, validation, promotion and registry values. No IO, no clock.
- `tui_maintainer.py`: pure Fast/Verbose renderers for screens 30–53.
- `application/consumer_ui.py`: the maintainer screens join the one keymap and the one reducer;
  `key_event` stays the only place a key's meaning is decided (D-041).
- `io/`: readers that assemble a maintainer machine the way `io/consumer_machine.py` assembles a
  consumer one.

## Dependencies

CP-05 (Source/Candidate/Registry/Promotion lifecycle) and CP-13 are verified. Maintainer Mode is a
durable preference as of D-090, without which the opt-in boundary could not hold across sessions.

## Screen coverage at slice start

| Accepted screen(s) | Existing evidence | Gap to canonical acceptance |
|---|---|---|
| 30 Maintainer Dashboard | none | Counts for sources, candidates, validation failures and ready-for-promotion, plus recent maintainer activity |
| 31–34 Sources | mature wizard Sources UI | Canonical list/detail over `source_status` and the scan; sync creates candidates and never promotes |
| 35 Candidates | `CandidateState` covers all accepted states | Status/artifact/version/source list with filters |
| 36 Candidate Details | `Candidate` carries identity, digest, findings | Full authoring detail, including example guidance for config and secret inputs |
| 37 Candidate Diff | none | Semantic diff first; raw file diff on demand |
| 38–40 Validation and Policy Review | `assess_candidate` produces findings | Pipeline of named checks; warnings distinct from errors; approval-required is its own state |
| 41–45 Promotion and Registry Commit | `plan_bulk_promotion`, `project_promotion` | Promotion review, vendor/reference mode, semantic registry diff, explicit commit that never pushes |
| 46 Registry Maintainer View | `load_registry_versions`, snapshot digests | Validity, counts by kind, snapshot, working tree, recent promotions |
| 47 Bulk Promotion | `plan_bulk_promotion` is already bulk | Multi-select over Ready candidates producing one transaction boundary |
| 48–53 Lifecycle, provenance, conflicts, collections, filters | promotion audit records exist | Lifecycle view, provenance detail, conflict surfacing, Collection candidates (B-031), candidate filters |

## Implementation steps

1. **DONE:** Maintainer screen catalog, navigation and the Maintainer Mode boundary in the one
   reducer (D-092).
2. **DONE:** Screen 30 and screens 31–34 over the canonical source scan.
3. **DONE:** Screens 35–37: Candidate list, detail and semantic-first diff (D-098).
4. Screens 38–40: validation pipeline and policy review. **DONE** (D-099, D-100).
5. **DONE:** Screens 41–47: promotion review, registry diff, explicit commit, registry view, bulk
   promotion and truthful Git/local Source provenance (D-101–D-107; closes B-041).
6. **IN PROGRESS:** Screens 48–53: lifecycle, provenance and conflicts are done (D-108–D-110);
   Collection candidates (closes B-031) and filters remain.
7. Retire the legacy consumer/maintainer authority CP-13 left standing, each removal preceded by a
   public-flow test (closes B-031, B-038, B-039).

## Blockers

None at slice start.

## Completed increments

### Step 1 — typed catalog and opt-in navigation boundary

- `application/maintainer_views.py` names screens 30–53 separately from the accepted consumer
  catalog. `ApplicationScreen` lets the existing session, events and commands carry either enum;
  no second state machine or key interpreter was introduced.
- `navigation_targets(..., maintainer_mode=...)` removes every Maintainer route while disabled.
  The reducer refuses a forged navigation event and `ConsumerUiState` refuses a Maintainer screen
  seeded under disabled settings.
- The Dashboard's rows and Enter target derive from that same graph. Consumer navigation is now
  physically reachable in the persistent shell, and the Maintainer root appears there only after
  the durable screen-28 toggle is enabled.
- Every accepted Maintainer screen is reachable from screen 30 when enabled; none is reachable from
  the Dashboard when disabled. Grouped specification screens received stable internal identities
  without claiming their bodies are implemented.

Evidence: `tests/maintainer_navigation_test.py`. Full repository result on 2026-09-01: 2,963 unit
tests and 204 E2E tests green, 83.45% branch coverage, format, lint, typecheck, validation,
packaging, docs and secret-shape gates green.

### Step 2a — pure screen 30–32 projections and renderers

- `MaintainerSourceView` binds a configured authoring Source, its durable health and one Source Scan
  only when aliases and pinned revisions agree. Manifest/Candidate counts, validation failures,
  Ready counts and target registries are projected from active canonical Candidates (D-093).
- `MaintainerDashboardView` aggregates those immutable Source views plus supplied recent activity;
  no projection reads a filesystem, source, clock or registry.
- `tui_maintainer.py` owns pure Fast/Verbose renderers. Fast abbreviates the pinned revision and
  emphasizes status/counts; Verbose reveals the full revision, target registries, Candidate state
  breakdown, sync epoch and redacted diagnostics.
- `ConsumerScreens` accepts an optional composed `MaintainerViews`; the existing
  `CanonicalScreenSource` now gives screen 30, Source list and Source detail real rows, Enter targets
  and bodies. No production composition claims them yet because CP-05 did not persist Source Scan /
  Candidate history.

Evidence: RED-first `tests/maintainer_views_test.py`; affected gate 1,255 tests green plus format,
lint, typecheck, validation, packaging, docs and secret-shape gates.

### Step 2b — durable Candidate lifecycle history

- `application/candidate_history.py` serializes one non-mutating pinned `SourceScan` as strict
  canonical lifecycle metadata referencing canonical compiled artifact object envelopes. It
  reconstructs the typed package, compiled artifact and Candidate graph and rechecks coordinate,
  provenance, payload/input/canonical/object digests, active/history identity and canonical order.
- `io/candidate_store.py` keeps that index and the retained immutable objects beneath one configured
  Source instance (D-094). Objects publish first; `current.json` is a private atomic replace. A
  missing index means no scan, while malformed, missing-object, corrupt-object and symlinked state
  refuse rather than becoming an empty Candidate list.
- An interrupted index replace preserves the last complete scan. Existing content-addressed bytes
  are verified and never overwritten, and superseded/rejected compiled evidence remains available
  after later scans (INV-229/239).

Evidence: RED-first `tests/candidate_history_test.py` and `tests/candidate_store_test.py`. Full
repository result on 2026-09-01: 2,982 unit tests and 204 E2E tests green, 83.37% branch coverage,
and all ten quality gates green.

### Step 2c — production screen 30–32 composition

- `io/maintainer_views.py` reads configured authoring Source health and matching persisted Candidate
  history once, then projects D-093's immutable views. Registry Sources never enter screens 31–34;
  missing history is distinct from corrupt or previous-revision history, which refuse.
- `ConsumerActionContext` carries the composed `MaintainerViews`, and `screens_from` retains them
  through redraws and consumer actions. `_canonical_consumer_actions` now assembles them beside the
  machine, Marketplace and durable settings; no renderer reads a filesystem or clock (D-095).
- The real production composition, configured Source store, Candidate store and shared shell are
  exercised together from the ordinary Dashboard through screen 30 and Source list to screen 32.

Evidence: RED-first `tests/maintainer_composition_test.py` and
`tests/maintainer_composition_e2e_test.py`; 36 focused composition/application tests plus full
format, lint and typecheck gates green.

### Step 2d — reviewed Source Sync and persisted result, screens 33–34

- `SOURCE_SYNC` is a typed action in the existing reducer/keymap/shell. `s` works only on a focused
  Source row/detail; Enter executes only the prepared review digest and keeps the Source focus into
  screen 34. Preparation creates no Source-store path and changes no registry observation.
- `PreparedSourceSync` binds the configured Source, current pointer, strict Candidate-history digest,
  default target registry snapshot, acquisition constraints and runtime semantics. Execution checks
  the registry before mutation and the Source/history baseline under the correct instance lease.
- The existing `SourceSyncPorts` still own acquire/validate/publish. The wider transaction then uses
  exact `compile_author_snapshot` discovery, `reconcile_source_scan`, atomic Candidate-history write
  and strict readback before releasing that lease. `registry_mutations` remains empty and screen 34
  states that fact in both profiles (D-097, INV-200/201).
- Local Sources retain their existing immutable pointer identity, `local:<snapshot-sha256>`, through
  native/domain provenance, Source Scan and Candidate history instead of being presented as Git
  commits (D-096). A temporary production installation proves the whole local path and proves the
  approved registry `CurrentSource` is unchanged.

Evidence: RED-first `tests/consumer_ui_actions_test.py`,
`tests/maintainer_source_sync_application_test.py`, `tests/authoring_compiler_test.py` and
`tests/maintainer_composition_e2e_test.py`. Full E2E gate: 207 tests green in 119s with real
environment permissions. Focused unit tests, format, lint and typecheck green; broad unit discovery
accounted for all tests, with its six sandbox-only keychain/uv failures rerun green with the required
permissions.

## Handoff

- Current working state: step 1 is committed at `a48b0b0`; pure screen 30–32 views/renderers at
  `791d530`; durable history at `a7db021`; production composition is implemented as D-095.
- Exact next action: implement screens 35–37 from the durable scans screens 33–34 now establish.
  Add immutable Candidate list/detail/diff views, production composition over active plus retained
  history, status filters and typed row/detail navigation. Candidate review is semantic diff first;
  raw file diff is explicit on demand. Preserve Source revision/input/payload/canonical digest
  evidence and do not infer Candidate state in a renderer.
- Later CP-14 promotion work must widen the currently Git-only registry-index provenance projection
  deliberately for D-096 local origins before claiming local Candidate promotion; it may not rewrite
  a local snapshot identity as Git provenance.

## Step 3 evidence — screens 35–37 (2026-09-01)

Screens 35, 36 and 37 are live in the production shared shell.

- Screen 35 lists the active Candidates every composed authoring Source's exact durable
  `SourceScan` produced, keyed by stable Candidate ID so two Sources publishing the same artifact
  name cannot collide. Retained lifecycle history stays out of the active list and remains
  available as the baseline the diff is taken against (INV-229).
- What the list is narrowed to is `MaintainerCandidateFilter`: typed application state on
  `ConsumerUiState`, applied by `filter_maintainer_candidates`. `_candidate_filter` is the single
  point where the shared search box meets it, so rows and body cannot disagree. Screen 53 will edit
  this value rather than introduce a second filter model.
- Screen 36 renders identity, kind/version, Source alias and revision, manifest path, the input,
  payload and canonical digests, runtime, transport, dependency descriptor, declared inputs with
  their acquisition guidance, and validation findings. Secret inputs carry no value and no example.
- Screen 37 is semantic diff first: the semantic change list is the body, the raw canonical file
  diff is a bounded, redacted secondary view behind the `f` toggle, off on entry and cleared by any
  navigation (INV-202, 164.5). `d` opens the diff from screen 36; both keys stay inside `key_event`.
- Production composition carries the scans `read_maintainer_views` already read once. Drawing the
  three screens opens no file, rescans nothing and infers no Candidate state; corrupt history still
  refuses the whole observation rather than presenting an empty Candidate list.

Evidence: `tests/maintainer_candidate_shell_test.py` (typed filter, ID-keyed rows and navigation,
duplicate artifact names across Sources, the `d`/`f` keymap, the secondary-diff boundary, and a
no-IO assertion over drawing all three screens) and
`tests/maintainer_composition_e2e_test.py::...::test_candidate_list_detail_and_diff_draw_the_scan_composition_already_read`,
which walks a real temporary installation from the consumer dashboard to screen 37.

Codex's step-3 checkpoint left `format-check`, `lint` and `typecheck` red; all three were repaired
in this segment (a `tuple[()]`-inferred diff accumulator, a loop name reused across two change view
types, and import ordering) rather than by relaxing any gate.

Gates on 2026-09-01 after step 3: `make quality` green end to end (format-check, lint, typecheck,
unit, validate, coverage, packaging-check, docs-check, secret-shape-check) and `make integration`
green. 3,017 unit tests and 208 E2E tests pass; branch coverage is 83.31%.

## Step 4 progress — the validation engine (2026-09-01)

`agent_artifacts/application/candidate_validation.py` implements 164.6's pipeline as a value, ahead
of the screens that show it, so screens 38–40 project a validation run rather than compute one while
drawing.

What it establishes:

- Validation is an *ordered pipeline of named checks*, not a flat findings list.
  `VALIDATION_PIPELINE` fixes the order and `CandidateValidation` refuses to exist unless it carries
  a result for every check in that order — a screen cannot silently omit a stage.
- Warnings and errors stay distinct end to end, and a fourth outcome, `not-run`, is deliberately not
  a pass: a check that produced no evidence has not agreed that anything is fine. Live acceptance is
  `not-run` here because a real installation on a real machine is CP-17's evidence, and ticking it
  would claim evidence nothing produced.
- A warning or error with no actionable detail is refused at construction, so "something is wrong"
  can never reach a Maintainer without a path, a declared value or an expectation attached.
- Policy decides what blocks, through the `EffectivePolicy.required_checks` field that already
  existed and had no reader. A required check that did not pass makes the Candidate
  `APPROVAL_REQUIRED`, which is 164.6's "policy-required manual approval is an explicit state"
  rather than a warning a renderer treats specially (D-099).

What the checks are actually worth was established empirically against `compile_author_snapshot`
before writing them, because a check that cannot fail is decoration. The compiler already refuses a
missing runtime, an unpinned runtime version and a dependency descriptor absent from the payload, so
those checks are re-verifications: their value is catching a Candidate history corrupted or tampered
with after the fact, and they are tested against deliberately doctored canonical trees rather than
against inputs the compiler would have rejected. Two checks bite on artifacts that compile cleanly:
a secret bound to a command-line argument is an **error**, because argv is readable from the process
table, and an executable payload file is a warning the Security check names by path.

Evidence: `tests/candidate_validation_test.py`, 17 tests across pipeline shape, per-check content and
the outcome-to-`CandidateState` mapping, with `make lint` and `make typecheck` green.

### Step 4 evidence — screens 38–40 (2026-09-02)

The screens are live in the production shared shell. `read_maintainer_views` takes the
`EffectivePolicy` as a parameter and composes one validation run per active Candidate, alongside the
Source and Candidate projections it already built.

- Screen 38 lists every named check with its own outcome and marks what policy requires; errors and
  warnings are counted separately rather than totalled, because an error refuses promotion outright
  while a warning is something policy may or may not treat as blocking.
- Enter opens screen 39 for one check, with each finding's path, declared value and expected value.
- `p` opens screen 40, which separates what policy *allows* from what it *requires*. An allowlist
  that is `None` reads "unconstrained" and an empty one "none permitted": a policy that does not
  constrain runtimes permits every runtime and one that constrains them to nothing permits none.
- Enter on screen 37 now moves forward into screen 38: having read the diff, the next question is
  whether it passed.

The row identity is the `"<candidate-id>:<check>"` pair, parsed back through `parse_validation_row`,
which returns nothing rather than raising for anything that is not a row. This is not decoration:
the E2E walk enters screen 40 from a *check row* rather than from a bare Candidate ID, because `p`
navigates with the cursor's row as the focus, and screen 40 resolves both shapes to the same
Candidate. The policy judgement is composed into the run rather than derived again while drawing, so
screen 38 and screen 40 cannot report different verdicts on one Candidate in one session; a test
monkeypatches `builtins.open` across all three screens and asserts drawing opens no file.

Gates on 2026-09-02 after step 4: `make quality` green end to end and `make integration` green.
3,052 unit tests and 209 E2E tests pass; branch coverage is 83.35%.


### Step 5 progress — screen 41, the promotion review (2026-09-02)

Promotion is the first Maintainer action that writes approved registry state, so this increment
deliberately writes nothing: it establishes what a Maintainer confirms, and what confirming is
bound to.

`application/maintainer_promotion.py` binds one Candidate, the run that judged it, the policy behind
that run and the approved registry baseline into one `PreparedCandidatePromotion`. Its
`PromotionEvidence` digests the validation report and the effective policy, which is what lets an
audit record answer "who approved this, against which rules" rather than only "this was promoted" --
two policies a digest could not tell apart could not prove which one approved. The policy digest
distinguishes an unset allowlist from an empty one, because those are different policies.

The run decides whether a promotion may proceed, not the state the scan recorded: policy may have
changed since the scan, and the run is what screens 38-40 actually showed. `INVALID` and
`APPROVAL_REQUIRED` are refused, each with the reason and the screen that explains it.

Screen 41 projects a refusal rather than raising it, and renders the reasons *in place of* the
review digest -- a digest on screen is an invitation to confirm, and there is nothing to confirm.
`read_maintainer_views` reads the approved state of every registry its active Candidates target; a
registry with no synchronized snapshot becomes a stated refusal rather than an error that hides the
rest of the composition. The E2E walk now runs dashboard -> Candidate -> diff -> validation -> policy
review -> promotion review against a real temporary installation and reaches a *confirmable* review,
asserted as such rather than as text that a refusal would also satisfy.

Two fixture findings worth keeping: a secret bound to a CLI argument does compile, so the pipeline's
process-table error is reachable on a real artifact and does block promotion (an earlier note to the
contrary came from a malformed `help` field, not from the binding); and the `.replace`-based edits
used here failed silently twice against text the formatter had reflowed, which is why the
composition patch is now asserted before it is written.

Gates on 2026-09-02 after this increment: `make quality` and `make integration` both green; the full
suite is 3,126 tests with 1,298 subtests.


### Step 5 progress — screen 42, choosing the promotion (2026-09-02)

The mode is inside the review digest, so changing it has to produce a different review to confirm
rather than a relabelled one. That left two options, and composing both modes up front beat
recomposing on a keypress: recomposition would put projection work inside drawing, which is the one
boundary CP-14 has held everywhere. There are exactly two modes, so the cost is bounded (D-102).

`MaintainerViews.promotions` is now keyed by Candidate *and* mode, `promotion(candidate_id, mode)`
selects one, and `ConsumerUiState.promotion_mode` is the typed choice `m` toggles — on screen 42
only, since the mode belongs to the promotion under review rather than to the session. The E2E walk
now runs through to screen 42, toggles the mode, and asserts the review digest on screen actually
changes, so two projections cannot quietly be the same transaction under two names.

Gates: `make quality` and `make integration` both green; full suite 3,131 tests.


### Step 5 progress — screen 43, the registry transaction (2026-09-02)

`plan_candidate_promotion` drives the existing `plan_bulk_promotion` with the evidence the review
bound, so the audit records that reach the registry name the run that approved the promotion rather
than a fresh one taken at write time. Screen 43 projects that plan: the paths it would write with
their change kinds, the registry snapshot before and after, and the transaction digest. The path
list is bounded at 200 rows while `changed_paths` counts the whole transaction, so a truncated list
never understates what would be written.

Planning needs the registry *workspace*, not only its approved projection -- what a transaction
writes is decided against the tree it writes into -- so `read_maintainer_views` now reads both.

This is also where the D-096 trap `NEXT.md` had flagged as "most likely to be got wrong quietly"
actually bit. A promotion audit records a 40-hex Git revision; a local Source carries
`local:<snapshot-sha256>`. The planner **raised** on one rather than returning an error,
`read_maintainer_views` caught the `ValueError` as a composition failure, and the Source Sync walk
stalled at screen 33 with no message at all. It was found by regression -- the E2E that syncs a real
local Source -- not by review. A local-origin Candidate is now refused by name in
`plan_candidate_promotion`, and the projection also survives a raising planner rather than taking the
rest of the composition down with it. B-041 tracks giving the audit record a place for local
provenance so the refusal can be replaced by support.

Two unit tests pinning that refusal directly were dropped when the budget window closed: the fixture
for a local authoring Source needs a filesystem `source` rather than a Git URL. The behaviour is
covered by the local-sync E2E; B-041 records restoring them.

Gates: `make quality` and `make integration` both green.


### Step 5 progress — screens 44–45, validation and explicit local commit (2026-09-02)

`execute_candidate_promotion` is the single application execution boundary for the transaction
screen 43 showed. It first checks the confirmed transaction digest without reading, then re-observes
the exact durable Candidate and synchronized approved baseline. It rereads the writable checkout,
revalidates under the reviewed policy, drives the existing bulk planner again and refuses unless the
result is byte-for-byte the prepared transaction. The projected registry is validated before the
first write; `finalize_promotion` performs the locked atomic compare-and-apply; the persisted tree,
version records and promotion audit are reread and validated before a commit is attempted.

Screen 44 renders that pre-write validation, including the registry snapshot and the Candidate
validation/policy evidence carried by the promotion audit. Screen 45 renders the exact before/after
snapshot, changed-path count and deterministic commit subject. Drawing either screen opens no file.
Enter on screen 43 is the one typed `CANDIDATE_PROMOTION` prepare action; Enter on screen 45 confirms
the digest through the existing reducer and action shell. No second key interpreter, reducer,
planner or shell was added.

The concrete adapter treats the normalized installation project root as the explicit writable
registry checkout and requires its entire tree to match the synchronized approved-registry
observation before preparing the validation view (D-103). It stages only the reviewed paths into an
empty Git index, refuses unrelated staged work, creates one local commit with hooks disabled and has
no push capability. A failure after the validated atomic filesystem write explicitly reports that
the changes remain for recovery rather than pretending the transaction was rolled back.

Evidence includes pure stale-Candidate/stale-baseline/stale-checkout/digest/commit-failure tests; a
real Git-index ownership test; reducer and draw-without-IO tests; and a production-composition E2E
that walks screens 30, 35–45 against a real temporary installation, writes the promoted registry,
validates its readback, creates a clean local commit and proves the checkout has no remote. The
focused promotion/composition suite is 51 tests and the adjacent reducer/action boundary suite is
36 tests, all green.

Checkpoint gates on 2026-09-02: `make quality` is green with 3,098 tests and 83.28% branch coverage;
format-check, lint, typecheck, repository validation, packaging, docs and secret-shape checks all
pass. `make integration` is separately green with 210 E2E tests.

At this checkpoint B-041 remained intentionally open: the increment proved remote-Git Candidate
promotion and did not pass a `local:<snapshot-sha256>` origin off as a commit. Screen 46, screen 47
and the compliant local provenance representation were the remaining work in step 5.

## Step 5c — screen 46, the Registry Maintainer View

Screen 46 answers the four questions a Maintainer asks about a registry at once, all from durable
evidence the registry itself wrote. Validity is a named check rather than a flag: every approved
version must carry a promotion approval record, because a published version nobody approved is
exactly the failure registry validity exists to catch, and `load_registry_promotions` is the only
supported way to read approval back.

Recency needed no clock. Every `PromotionAudit` names the registry snapshot its own transaction
started from and produced, so audits sharing an after-snapshot are one transaction and the
transactions chain. Screen 46 walks that chain backwards from the approved snapshot, bounded at 50
transactions and stopping on any cycle or gap. Stamping a read-time clock instead would have made
the order a property of when somebody looked rather than of what happened (D-104).

Working-tree state is a separate observation on purpose. Synchronized source-store content is an
immutable record of what the registry published, so answering "does my checkout still match" from it
would answer a different question; the checkout is the D-103 project root, digested through the
now-public `registry_state_digest` over `artifacts/` and `references/` only. A multi-registry
installation cannot say which registry the project root is, so the checkout is observed only when
exactly one registry is configured and reported unobserved otherwise (B-042).

Screen 45 keeps its receipt on screen after the commit, so Enter there had no forward route at all.
It now means "confirm" only while an action is pending and "go on to the registry" once the write
happened, which is how the E2E walk reaches screen 46 — where the checkout is legitimately ahead of
the synchronized approved snapshot, because a local commit is deliberately not a sync.

Evidence is `tests/maintainer_registry_view_test.py`: the projection, both working-tree outcomes and
the unobserved case, the missing-approval-record invalidity, chain ordering across two transactions,
a bulk transaction listing every Candidate it promoted, the shell body and its refusal, and a
`builtins.open` monkeypatch proving drawing screen 46 opens no file. The E2E walk in
`tests/maintainer_composition_e2e_test.py` now runs through to screen 46 and asserts the divergence.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green; full suite
3,167 tests.

At this checkpoint step 5 still required screen 47 bulk promotion and B-041's compliant local
provenance representation.

## Step 5d — screen 47's selection surface

Bulk promotion is one transaction, so its plan depends on which subset a session selected. That
cannot be precomposed without enumerating subsets, and composing it while drawing would break the
boundary every other CP-14 screen holds. Screen 47 is therefore split: the projection says what is
selectable, and the transaction is prepared at action time (D-105).

What is selectable is bounded by the registry. A transaction has exactly one target, so Candidates
scanned for another registry are not offered here at all rather than refused after selection.
Promotability is read off the validation run screens 38–40 showed rather than re-derived, so a
Candidate cannot be offered for bulk promotion on a judgement no screen ever displayed. A Candidate
the run refused is listed by name with its reason, because "not in the list" and "does not exist"
look identical on screen.

Selection reuses the reducer's existing typed `selection` with `Space`, the accepted Maintainer
shortcut; `MaintainerScreen.BULK_PROMOTION` simply joins `_SELECTABLE`. No second selection model
was introduced.

Evidence is `tests/maintainer_bulk_promotion_test.py`: the per-registry offer, exclusion by name and
reason, the no-approved-state refusal, cross-registry isolation, the shell's rows, `Space` through
`key_event`, the drawn selection mark and count, an excluded Candidate named on screen, and a
`builtins.open` monkeypatch proving drawing screen 47 opens no file.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

## Step 7f — B-044's fixture and characterization (2026-09-02)

No harness in the repository could produce a setup-declaring artifact, which is why the gap was
invisible: the authoring format has no setup section — `setup` appears zero times in
`protocol/authoring.py` — and every consumer E2E publishes through `compile_author_snapshot`. A
declaration therefore enters at packaging, not at authoring, and the fixture models it where it
happens. `AuthoredSetup` and `_with_setup` in `tests/configured_installation_draft_e2e_test.py`
write `artifact.json`'s `setup` reference, `setup/installer.json` and `SETUP.md` into the compiled
package and recompile it with `compile_native_package`, so the recipe goes through the same strict
parse a vendored one does and every digest is derived rather than asserted; the payload is untouched,
so the payload digest still describes it. The result then goes through the whole real promotion
transaction — `reconcile_source_scan` → `assess_candidate` → `plan_bulk_promotion` →
`publish_registry_version` → `plan_registry_lifecycle` — and the published snapshot carries
`artifacts/skill/code-review/1.2.0/setup/installer.json`. `_promote_one`, `_published_registries`,
`_published_registry` and `_environment(authored=..., setup=...)` all thread it through with every
existing caller unchanged.

Two constraints `compile_native_package` enforces bound any such fixture: a setup declaration's
platforms must be a subset of the artifact's, and `setup.py:562` requires the recipe's own
`platforms` to be exactly `['darwin']`. An artifact whose `aart.json` declares no
`compatibility.platforms` cannot declare setup at all, which is why the fixture Skill names its
platforms where `AUTHORED_SKILL` does not.

`tests/configured_setup_gap_test.py` is the characterization, four tests. The first guards the
other three by asserting the approved registry really does carry the declaration and its recipe —
it was verified red by removing the injection, so a fixture that stopped declaring setup cannot
leave the defect tests quietly passing. The other three assert the absence of the one file the
recipe writes, on both front ends.

**They correct D-118's last sentence.** `aart marketplace install` does not carry setup for an
approved registry coordinate either: it reaches `_configured_lifecycle`, which calls
`complete_configured_installation` — the same seam `_execute_installation` uses — and reports
`session_status: succeeded` with no `setup` key and no diagnostic. Setup runs only on the legacy
path, which `_configured_registry_selection` selects by returning `None` for a direct or local
source. `aart marketplace setup` does not recover it: it resolves through the legacy catalogue and
refuses with `registry company has invalid root manifests`, since a promoted registry snapshot
carries none. So B-044 is one fix at one shared seam (D-120).

The working route now has its evidence too (D-121).
`marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest` runs a declared setup end to end from the
CLI over the legacy native-local-source route — the shared native-source fixture copied writable and
taught to declare setup — and asserts each of its four gates: `install` names the setup it did not
run, an unreviewed source refuses without `--authorize-untrusted-source`, an authorized plan applies
nothing until its effects are separately approved, and both together write the delimited managed
block. `skipUnless(darwin)`, because `setup.py:562` accepts only `['darwin']` recipes. Applying the
preserved draft's hardcoded `TrustClass.COMPANY_REVIEWED` fails two of the four.

What remained before the green was the installed-record question, settled in step 7g below.

## Step 7g — the receipt names the object it was installed from (2026-09-02)

`_prepare_setup_object` resolves what to configure from the install-state manifest, which
`io/consumer_machine.py` treats as the *legacy* store — a record found there with no canonical
receipt becomes an `UnadoptedInstallation` (D-069) — while the configured seam writes receipts. The
choice between widening the engine to read receipts and having the seam also write install state
looked like a taste question and turned out to be a measurement: **the canonical receipt could not
name the object that was installed.** After `aart marketplace install` of the fixture Skill,
`<data_root>/state/installations/*.json` held the coordinate, `payload_digest`, `root` and the
deliveries, and no object digest; `install_state`'s `ArtifactEvidence` carries one. Setup is
declared on the *package manifest*, and `_prepare_setup_object` finds it by loading the object by
digest, so pointing the engine at the receipt store was never a matter of reading the same facts
from a different file — the facts were not there. The other option was rejected on its own terms: it
writes new records into exactly the store the strangler is retiring. (It would not have made
canonical installs surface as unadopted, because `read_consumer_machine` drops a manifest record a
receipt already answers for, `io/consumer_machine.py:362`.)

So the receipt now records it (D-122). `object_digest` on `PlacedArtifactReceipt` and
`InstallationReceipt`, populated by `intended_placement_receipt` and `intended_receipt` from
`planned.artifact.version.object_digest` — the `RegistryArtifactVersion` the Selection already
resolved, so this writes down what the installation knew rather than deriving anything. This is not
only setup's problem: reconciling a repair against the payload digest alone cannot tell one package
apart from another that happens to deliver identical bytes.

It is a schema addition to a durable store, so the field is optional and absence reads as *unknown*
rather than being refused or defaulted — an installation whose object nobody wrote down is honestly
unknown, and a default would put a dangling identity on a real installation.
`tests/installed_object_identity_test.py` was written red (`AttributeError: 'PlacedArtifactReceipt'
object has no attribute 'object_digest'`) and asserts more than presence: the recorded digest must
resolve to an object that is actually in the store and whose `artifact.json` is the installed
package's, declaring the setup the fixture Skill needs. Each receipt shape additionally carries a
round-trip, an older-document read and a malformed-digest refusal.

Two things this deliberately did not do, and step (3) of B-044 must answer. The engine takes a
legacy `MarketplaceCatalog` (`resolve_artifact` plus `_marketplace_evidence`) which cannot read a
promoted registry snapshot, and `RegistryArtifactVersion` carries `object_digest` and
`payload_digest` but no `manifest_digest`, so canonical evidence is not a field-for-field
substitution for `ArtifactEvidence`. And `persist_setup` (`setup_engine/io.py:89`) records that
setup ran by replacing `setup_state_ref` inside the install-state record under its lock, which
`setup_receipt.locate_setup_record` reads for `aart marketplace receipt show|verify|undo` — the
canonical route has no such pointer and needs its own durable setup record. Every trust, evidence
and policy check stays inside the engine either way.

## Step 5e — one transaction carrying a set of promotions

A loop over single promotions is exactly what bulk promotion is not: each iteration would take its
own registry snapshot, write its own commit and be able to half-succeed, leaving the registry in a
state no review ever described. So rather than adding a second prepared type beside the
single-Candidate one, the existing one was generalized: `PreparedCandidatePromotionTransaction`
carries `promotions: tuple[...]`, `plan_promotion_transaction` plans the whole set through the
already-tested `plan_bulk_promotion`, and `prepare_candidate_promotion_transaction` is the
one-element case of `prepare_promotion_transaction`. One review path, one chance for it to be right
(D-106).

Confirmation reads the approved baseline once, before any Candidate, and then rechecks every member
against that one baseline — reading it per Candidate would let a single transaction assemble members
against two different registries. The port-order tests state that ordering explicitly rather than
leaving it to be re-derived. A transaction whose plan carries a Candidate the review never saw is
rejected in `__post_init__`, by construction rather than by check.

Screens 44 and 45 now carry a tuple of Candidates, each with the validation-report and
effective-policy digests that authorized it: evidence stays per Candidate because each is approved
by its own run and policy result, and one summarized pair could not be traced back through the
transaction. Screen 45's commit subject names the artifact for one Candidate and the count for
several.

Screen 47's one forward route is screen 44, not screen 43 — a bulk selection has no
single-Candidate diff to open — and the configured handler re-checks at action time that the
confirmed selection is still a subset of what screen 47 composed, declining rather than promoting
something nobody ticked. A promotion now recomposes the Maintainer views the way a Source Sync
already did, because the commit it just made moved the checkout that screen 46 reports on.

Two defects were caught by writing the E2E rather than by reasoning about the code:

- screen 46 compared the working tree in the audits' published-content digest space, so a correct
  checkout always read as diverged. The working-tree question is the one D-103 asks — does this
  checkout match the approved baseline it would promote from — so it is answered with
  `source_snapshot_digest`, and the audit chain head is read separately with `registry_state_digest`.
- a promotion left screen 46 drawing a pre-commit observation, because only Source Sync recomposed
  the views afterwards.

Evidence is `tests/maintainer_bulk_transaction_test.py` and the walk in
`tests/maintainer_composition_e2e_test.py`, which ticks two Candidates on screen 47 and asserts what
only one transaction can produce: exactly one new commit, one registry snapshot across every
persisted version, and a clean working tree.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

## Step 5f — local Source provenance through promotion

Step 5 is complete. Promotion audit provenance is now a typed discriminated value rather than a
Git-only text field: `git-revision` carries exactly one 40-hex revision, while `local-snapshot`
carries exactly one canonical SHA-256 snapshot digest. Their JSON fields are separate, and a local
pin placed in the legacy `source_revision` field is explicitly refused. Canonical legacy Git audit
records remain readable so durable audit history is not invalidated by the schema evolution
(D-107, closes B-041).

The by-name local refusal is removed from both `plan_candidate_promotion` and
`plan_promotion_transaction`; both still drive the same `plan_bulk_promotion`, and a mixed Git/local
selection is proven to retain per-Candidate provenance while producing one registry snapshot. No
rebind or immutable-package logic changed, and the local E2E promotes into a registry that already
contains an approved version, then validates both together (D-089/B-037, INV-203/229/239).

The two direct cases that were missing now use a local revision with a filesystem source location:
one proves the plan's audit contains `local-snapshot` plus the exact digest and no Git field; the
other proves screen 43 is a reviewable transaction rather than a refusal. Lower-level round-trip,
legacy-compatibility, invalid-legacy-field and mixed bulk tests cover the protocol boundary. The
production composition E2E now continues its real local Source Sync through screens 35–45, creates
one local commit, reloads and validates the registry, and matches the persisted audit digest to the
exact durable Candidate-history `local:<sha256>` pin.

Focused evidence before the full checkpoint: 87 promotion, transaction, registry and composition
tests green; format-check, lint and typecheck green. Full checkpoint results follow after the slice
gates run.

## Step 6a — screens 48–50: lifecycle, provenance and immutable conflicts

Screen 48 walks the exact retained predecessor chain, so a Source change does not overwrite the
promotion that preceded it. Promotion is never inferred from Candidate state: a registry version
and audit must agree on Candidate identity, coordinate, content digests, typed Source provenance and
mode. The local checkout supplies this evidence in the one-registry D-103 topology, which means the
locally committed promotion is visible before a later Source Sync or publication (D-108).

Screen 49 exposes the compiler's Source URL, typed immutable pin, manifest, input digest, importer
identity/version, complete canonical payload path set and warnings. Native and domain provenance are
cross-checked before the view exists, including the Git/local discriminator (D-109).

Screen 50 is present only for an immutable coordinate/version collision. With approved evidence it
shows published and Candidate digests side by side; without that read it retains the durable
Candidate refusal and says evidence is unavailable. It always requires a new version and offers no
path that could mutate the published version (D-110, INV-203/239).

Evidence: `tests/maintainer_candidate_lifecycle_test.py`, `tests/maintainer_provenance_test.py`,
`tests/maintainer_version_conflict_test.py`, and the refreshed production path in
`tests/maintainer_composition_e2e_test.py`. Focused lifecycle/provenance/conflict/composition gates
are green; lint and typecheck are green. Screens 51–53 remain before the step checkpoint.

## Step 6b — screen 53, the filter that could not be edited

`MaintainerCandidateFilter` was typed state screen 35 already obeyed and nobody could change, so
the narrowing was always empty. Two of the four facets the Product Specification names had nowhere
to live at all: the filter carried `states`, `sources` and a free-text `query`, but not kind and not
target registry.

D-098 ruled out a second filter model, so the two missing facets went on the value that already
exists. Which facets are typed follows from what each one is: `states` and `kinds` are closed sets
and stay typed (`CandidateState`, `ArtifactKind`), while `sources` and `registries` are open sets of
aliases and stay strings. A renderer string in a closed-set facet is refused.

The rows are `"<facet>:<value>"` pairs read back by `parse_candidate_filter_row`, for the same
reason screen 38's rows are `"<candidate-id>:<check>"` (D-100): a row is an address the reducer
resolves, never a string a renderer takes apart. A row naming a facet or a closed-set value that
does not exist parses to `None` and changes nothing. The reducer toggles through one
`toggled(facet, value)` entry point rather than four call sites that could drift.

Two choices are worth stating because the obvious alternative is wrong:

- the offered values come from every composed Candidate, not from the already narrowed list. Drawing
  the narrowed list would make a row vanish the moment it was ticked, and it could never be
  unticked.
- each option states what choosing it *would leave*, measured by applying that one value to the rest
  of the current filter — not how many Candidates carry it. That is what makes a narrowing which
  selects nothing legible on screen 53 rather than discovered as a blank screen 35.

Ticking a filter row puts nothing in `selection`. `selection` is what every action reads, and a
filter value is not a chosen artifact.

`f` opens screen 53 from screen 35, which the Product Specification's keyboard table asks for.
Screen 37 already claimed `f` for the raw file diff and keeps it: one key means what the screen it
was pressed on is about. The characterization test that pinned `f` as inert on screen 35 stated a
truth that no longer holds, so it was corrected to state the new behaviour — not relaxed.

Evidence is `tests/maintainer_candidate_filters_test.py`: the two new facets and their
intersection, closed-set typing, `toggled` routing all four facets, the projection's offered values
and per-option counts, active marking, row round-tripping including three rows that must not parse,
the `f` route in and its absence where there is nothing to filter, `Space` toggling without touching
`selection`, toggling twice returning to the unnarrowed list, screen 35 narrowing to what 53 chose,
the drawn body, and a `builtins.open` monkeypatch proving drawing screen 53 opens no file.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

Step 6 remainder: end-to-end evidence for screens 51–52 in a real installation, which is what
closing B-031 requires before legacy Collection authority can be retired in step 7.

## Step 6c — the way into screens 51 and 52

Screens 51 and 52 had projections, a renderer, validation against approved registry state and
durable composition from the Source Scan. What they did not have was a route: every test entered by
constructing a session already sitting on screen 51, which is the same gap screens 35–37 had in
step 3 and screen 53 had in step 6b. A screen only a test can reach is not live.

The navigation graph already accepted screen 35 → screen 51, so the missing piece was a key. `c` on
the Candidate list is it. The Product Specification says "Collections are candidates too", which
puts them on the Candidate surface rather than in a branch of their own — and the accepted screen 30
panel lists Overview, Sources, Candidates and Registry with no Collections entry, so putting them
there would have invented a surface the specification does not describe. The accepted contextual
shortcut table names no Collections key, but it names none for screens 46, 47 or 50 either, which
are reached by navigation; it constrains what the keys it lists mean, not what may exist (D-112).

One thing the E2E forced into the open: the fixture first compiled through `compile_author_snapshot`
and got no Collections at all, because that boundary returns artifacts only. Production Source Sync
compiles through `compile_author_source`, which carries both kinds, and `reconcile_source_scan`
takes the Collections as their own argument rather than mixed in with the artifacts. A fixture built
on the artifacts-only boundary would have passed its own assertions while proving nothing about
Collections.

Evidence is `tests/maintainer_collection_candidate_test.py`'s route tests — `c` opening screen 51,
`c` meaning nothing where nothing is listed, the whole route driven through the reducer rather than
by constructing sessions, and Esc returning to the list it was opened from — and a walk in
`tests/maintainer_composition_e2e_test.py` over one real installation: a Collection authored beside
an artifact in one tree, compiled once, persisted once, reached with `c` and resolved on screen 52
to the exact version the registry approved.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

CP-14 step 6 is complete. What remains is step 7: retiring the legacy consumer/maintainer authority
CP-13 left standing, one route at a time and only behind the public-flow evidence D-091 requires.

## Step 7a — the legacy curses wizard shell is removed

The first removal of step 7, taken under B-039's rule: nothing goes before a public-flow test proves
the canonical path already carries it. Both halves of that evidence pre-existed, so no new test was
needed and none was written.

`run()` has composed `_canonical_consumer_actions` and called `run_consumer` before any wizard
composition since B-025/D-087, so no terminal reached `_run_curses`. ERR05 — the single condition
under which falling back to text is legitimate, namely that the terminal cannot host curses,
detected before interaction — is pinned on the canonical `run()` by
`tests/tui_fallback_boundary_test.py`: text starts exactly once when curses is unavailable, an
internal defect never restarts the application at onboarding, and an unexpected terminal-probe error
is not silently downgraded to text. Three duplicates of those were written against
`tests/tui_consumer_entry_test.py` and then reverted rather than left as a second copy of one
behaviour in a second file.

Removed: `_run_curses` (754 lines) from `agent_artifacts/tui.py`; `_legacy_setup_stage_failure` and
`_run_post_install_setup`, which it was the sole caller of; and the seven tests that existed only to
drive it — three in `tests/tui_fallback_boundary_test.py`, two in `tests/tui_curation_test.py`, two
in `tests/tui_wizard_curses_test.py` — plus the now-dangling `_run_curses` patch in the entry test.

Kept: `run()`, `_run_text` and the whole text route, because no-TTY is a supported environment
rather than a broken one; and the wizard's curses *primitives* (`_curses_onboarding`,
`_curses_singleselect`, `_curses_multiselect`, `_curses_install_scope_event`,
`_curses_install_mode`, `_curses_review`), which the surviving wizard stages still compose and the
36 remaining tests in `tests/tui_wizard_curses_test.py` still cover. `_dispatch_result` also stays:
it lost its last production caller here, but `tests/tui_consumer_text_test.py` still patches it to
prove the canonical text route does not dispatch legacy commands, so it retires with the command
dispatch path rather than with the wizard shell.

One thing the removal exposed: `tests/tui_consumer_text_test.py` reached the legacy `model.Err`
through `tui.Err`, an alias that existed only because `tui` happened to import it. The test now
imports it from `agent_artifacts.model` directly, which is where it lives; the assertion is
unchanged.

Recorded as D-113; B-039 is now partly closed — the shell is gone, the semantic paths behind it
(`consumer/application.py`, `lifecycle/application.py`, `installation/*`, `setup_engine/*`) are not.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

## Step 7b — screen 21 lists the configured sources, and says why a native one offers nothing

B-038's remaining CP-14 dependency was one sentence of wording: screen 21 should say why a listed
native Source offers nothing. Writing the test for that sentence exposed that screen 21 had nothing
to say it about. Nothing on the composition path ever projected the configured sources, so
`machine.registries` stayed the empty default `assemble_consumer_machine` assembles it with, and a
machine with a configured registry on disk opened on an empty screen 21 and a dashboard reading
"0 registries" — the same gap screens 02–04a had before the Marketplace was composed, on the screen
next to it.

So the increment is both halves. `read_consumer_offers` already reads the configured catalog once;
it now also projects it through `project_registries` and carries the rows on `ConsumerOffers`.
`screens_from` takes them and `LocalConsumerActions.source()` passes them, which keeps the read at
composition where an effect belongs. Which sources are configured is configuration rather than
durable machine evidence, which is why it comes through the offers seam instead of being read a
second time by the machine; `machine.registries` stays as the fallback, so nothing that composed
screens without registries changes.

The B-038 half is INV-026. A Marketplace projects configured registries, so an enabled `SOURCE_GIT`
or `SOURCE_LOCAL` contributes its health and offers nothing — and drawing that as a bare "0
artifacts" describes a correct state as a fault, while advertising a sync that "refreshes
Marketplace availability" names an effect that source cannot have. `RegistryView` gains a typed
`is_registry` decided in the projection rather than by a renderer splitting `kind`, for the reason
D-100 and D-111 give. A non-registry row now reads "An authoring Source, not a registry." and "Its
content is offered here once a maintainer promotes it into a registry.", with `actions` of
`("details",)`. The dashboard counts the registries among the configured sources, because "2
registries" over one registry and one authoring Source is a false count (D-114).

Evidence is `tests/consumer_registries_screen_test.py`: the projection deciding which rows are
registries for both native kinds, what each kind of row says and offers, screen 21 listing both
sources in the composed shell, the dashboard counting one, a `builtins.open` monkeypatch proving the
draw opens no file, and — the one that matters for the gap — the production composition
(`tui._canonical_consumer_actions` over a real temporary installation) putting the configured
registry on screen 21 rather than a `screens_from` call a test made. The characterization test that
pinned `("details", "sync")` on every row was corrected to state what each kind of row now offers
rather than relaxed.

B-038 is partly closed: what remains is removing the legacy route's ability to install directly from
a native Source, behind its own public-flow evidence.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

## Step 7c — the text route becomes the canonical application

Surveying what step 7 could remove next turned up the reason it could not remove anything. Every
remaining target — `consumer/application.py`, `lifecycle/*`, `setup_engine/*`, and B-038's legacy
direct-install from a native Source — is reachable only through `_run_text`, which is built on
`ConsumerApplicationService` and through it on that entire stack. The blocker was never evidence; it
was a missing replacement. A no-TTY environment (CI, a pipe, a dumb terminal, SSH without a pty) was
being handed a different product from the one a terminal gets.

ERR05 permits a text fallback for exactly one condition: the terminal cannot host curses. It says
nothing about the application changing. And the shell already takes its terminal as a port of two
methods — `draw(lines)` and `key() -> int` — so text is an adapter, not a second frontend.

`_TextTerminal` draws with `write` and reads with `read`. A line editor has no arrow keys and no
bare Escape, so it names them: `up`, `down`, `enter`, `esc`/`escape`, `back`/`backspace`, `space`. A
single-character line is that character, a blank line is Return, and an unknown word means nothing
at all — taking the "d" out of "delete" would act on a key nobody pressed. `EOFError` answers `q`
once and `y` thereafter, because a pipe that ends mid-selection would otherwise redraw the discard
prompt forever.

`run()` now composes the application once for whichever terminal answers and hands the same
composition to `run_consumer` or `run_consumer_text`. Its whole legacy tail is gone: no
`_runtime_source_stage_context`, no `ConsumerServiceFactory`, no `_run_text` call (D-115).

Evidence is `tests/consumer_text_terminal_test.py`: every key form and the ones that must mean
nothing, case and surrounding space, EOF quitting and confirming, drawing every line of a frame,
`run_consumer_text` running the shell with the composition's own source, handler and settings
writer, and two walks over a real temporary installation — reaching the dashboard through a pipe
(including the "1 registries" that step 7b composed) and opening the Marketplace the configured
registry approved. The ERR05 tests in `tests/tui_fallback_boundary_test.py` were retargeted at
`run_consumer_text` rather than duplicated in the new file; the assertions that had become vacuous —
patching a `_run_text` nothing calls and asserting it was not called — were restated instead of left
standing.

`_run_text` and the stack below it now have no production caller: the same position `_run_curses`
was in before D-113. Removing them is the next increment, under the same discipline.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.

## Step 7d — the legacy text wizard shell, and everything only it reached

D-115 left `_run_text` where `_run_curses` was before D-113: defined, exercised by tests, reachable
from nothing. This removes it and the tail behind it — `_runtime_source_stage_context`,
`_dispatch_result`, and the 26 further private definitions in `tui.py` that became unreferenced once
it was gone. 1,546 lines out of `tui.py`, and about 2,200 with the tests that existed only to drive
it.

The sweep was mechanical rather than hand-picked, and repeated to a fixpoint: removing one orphan
orphans its callees, so a list written by eye would have left a tail behind. Each pass removed only
definitions with no reference anywhere in `tui.py`, in any other production module, or in any test.

What each removed test pinned was checked against a public flow before it went, rather than
assumed:

- scaffolding → `aart registry scaffold` (`registry_init_scaffold_test.py`,
  `registry_cli_integration_test.py`);
- source add / remove / sync / resubscribe → the `aart source` command surface
  (`source_cli_command_test.py`, 23 tests pinning the same review-then-finalize semantics);
- vendoring → the flags half of the parity `tui_vendoring_test.py` was testing; with one front end
  left there is nothing to compare, and the assessment rendering it checked is pinned by
  `registry_vendor_assessment_test.py`;
- the ERR04 legacy install state → `install-state-legacy`, asserted in four other modules;
- ERR06 refusals and the setup queue → the canonical shell's drawn notice
  (`consumer_application_e2e_test.py`).

Two entry tests that asserted "the canonical application and *not the legacy wizard*" were restated
as "and nothing else": a comparison to something that no longer exists pins nothing. The module
docstring, which still opened "Two front-ends, one body", was rewritten to describe what `tui.py`
now is (D-116).

`tui.py` is 4,262 lines, down from 5,705. `lifecycle/*` and `setup_engine/*` are now reachable only
through `consumer/*`; `curation/*` only through `cli.py` and `commands/registry.py`, which are the
public flag-mode commands. `ConsumerApplicationService` survives because the curses wizard *stages*
still compose it and 36 tests still cover them — those stages, and then `consumer/application.py`
with `lifecycle/*` and `setup_engine/*` behind it, are what step 7 removes next.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green, 3,173 tests.

## Step 7e — the wizard front-end, and the stack under it that is not legacy

The last of the wizard front-end is gone: `_run_user_curses_wizard`, `_run_user_text_wizard`,
`_prompt_curation_request`, the `_curses_source_*` maintenance screens with `_selected_source_row`,
`_offer_usage_report`, `_run_canonical_setup_queue`, `_is_canonical_maintainer_workspace`,
`_type_rank`, and the 22 further definitions the fixpoint sweep found once they were gone — 1,515
lines. `tui.py` is **2,747 lines**, down from 5,705 when step 7 began. `tests/tui_curation_test.py`
and `tests/reporting_tui_test.py` are deleted; `SourceLifecycleCursesTests` and
`CursesWizardFlowTests` go with them.

**Step 7 does not end where this slice file said it would.** The plan recorded above — "then
`consumer/application.py` with `lifecycle/*` and `setup_engine/*` behind it" — is wrong, and the
correction matters more than the removal. `agent_artifacts/commands/marketplace.py`, the public
`aart marketplace install|update|uninstall|setup` command, composes `ConsumerApplicationService`
directly and runs the setup queue through it; `tui_marketplace.py`, which the canonical shell
imports, takes `LifecycleItem` and `InstallMode` out of `lifecycle/model.py` and
`installation/model.py`. That stack is load-bearing for a public flow. It is not legacy authority
awaiting a strangler, and nothing further is removed for it (D-117).

Two of the removed tests held an assertion nothing else did, so the assertion moved to the surface
that is actually reachable rather than going with the test:

- **LAF-90**, `registry init`'s default compatibility window. `RS-02`'s loop covers every registry
  action *except* `init`, because `init` is the one action that owns `--minimum-version` and
  `--maximum-version` — so what an operator who supplies neither gets is the parser's defaults, and
  the wizard test was the only thing checking they admit the running executable. Restated against
  the CLI in `tests/registry_cli_test.py` and verified red against a dead `1.0.0..2.0.0` window.
- **The usage-report offer.** `_render_cli_reporting` in `commands/marketplace.py` had no test at
  all, and `tests/reporting_tui_test.py` was the only thing pinning that consent defaults to no,
  that the exact payload is readable before anything opens, and that a reporting failure leaves the
  marketplace outcome unchanged. Those are privacy boundaries, so they are now
  `tests/reporting_cli_offer_test.py` (7 tests), verified red against a consent default of yes. Two
  properties the CLI has and the wizard did not are pinned there too: the second prompt can still
  stop a report the first accepted, and a non-interactive stdin is a refusal rather than an
  unanswered prompt.

The rest went against evidence that already existed: workspace classification against the canonical
planner's refusal of a snapshot with no `aart-registry.json`
(`registry_maintenance_edges_test.py`); the "AART never commits or pushes" menu label against
`maintainer_composition_e2e_test.py::test_validated_promotion_is_committed_locally_and_never_pushed`,
which shows the label was stale rather than carried; source maintenance against the `aart source`
surface; ERR06 refusal-as-a-record and quit-confirms-a-basket against
`consumer_application_e2e_test.py::ConsumerApplicationRefusalTest` and the canonical shell's own
discard prompt.

**What the removal exposed, and what was deliberately not removed.** `io/consumer_actions.py`
performs no setup and no reporting, so since D-115 an artifact installed from the TUI that declares
setup requirements lands unconfigured and no usage report is offered. `_canonical_setup_run` and
`_complete_canonical_consumer_action` are the only implementation of that capability, so they are
kept — production-orphaned and test-pinned — as the material to wire it back. Recorded as D-118 and
promoted to the critical path as **B-044**. ~~the public `aart marketplace install` is
unaffected.~~ — that half is false and is corrected below.

One live output was falsified by the removal and is fixed here: `InternalFailureContext.stage` was
typed `WizardStage` and set only by the wizard, so every canonical crash would have reported
`stage: onboarding`, naming a screen that no longer exists. It now takes a `CanonicalBoundary`
(`compose` / `curses` / `text`) and `run()` sets it; an untyped defect from the composition, which
reads local state and so carries paths in its message, is now redacted through
`internal_failure_lines` instead of propagating (D-119).

571 lines of `tui.py` remain production-orphaned, held only by the widget tests — `_curses_multiselect`
and its 29 tests, the receipt screens, `_load_user_wizard_read_model`, `_curses_install_mode` — and
are the next sweep, minus the two helpers B-044 holds.

Checkpoint gates on 2026-09-02: `make quality` and `make integration` are both green.
