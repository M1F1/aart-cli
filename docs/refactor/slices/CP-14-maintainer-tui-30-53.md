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
3. Screens 35–37: candidate list, detail and semantic diff.
4. Screens 38–40: validation pipeline and policy review.
5. Screens 41–47: promotion review, registry diff, explicit commit, registry view, bulk promotion.
6. Screens 48–53: lifecycle, provenance, conflicts, Collection candidates (closes B-031), filters.
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
