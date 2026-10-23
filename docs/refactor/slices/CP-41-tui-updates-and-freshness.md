# CP-41 — The TUI says what is new, and where to go for it

Status: **done**, on `feat/cp-41-tui-updates-and-freshness`, after the owner's audit (2026-10-23).
Authority: Product Specification §194, INV-295, D-478.

## Steps

See `docs/refactor/plan.json`, epic CP-41.

1. Updates lists installations a connected Registry offers newer versions of, and its rows are
   installations. Done.
2. The TUI checks each Registry under `sync.mode` on launch. Done.
3. A Registry row says when its snapshot is not current. Done.
4. Dashboard and menu marks; Show available updates governs them. Done.
5. Lab publish commands, end-to-end test, manual walkthrough. Done.
6. Focused verification and the PR. Done: one PR.

## Why

The owner's report: a Collection approved in the Registry did not appear in the TUI until `s` was
pressed on Registries. Nothing said a sync was due, and Updates never listed anything. The audit
found four causes:
1. `InstalledInspection.update_available` was never set in production; only tests set it.
2. The TUI read local snapshots only. The CLI observes the origin under `sync.mode`.
3. A Registry row said "connected" whatever its health.
4. Updates rows were keyed by coordinate, but the update action looks installations up by row.

## Change

- `consumer_session.py`:
  - `highest_offered` takes the highest SemVer each artifact is offered at;
  - `with_offered_versions` turns each ready installation offered a higher version into an update.
    It rebuilds the Installed, Collections, Dashboard and Doctor views from that.
  - `InstalledInspection.update_available` is gone.
- `consumer_views.py`:
  - `InstalledArtifactView.available` holds the offered version, and the cell shows
    `ready → 1.0.1`;
  - `DashboardView.registries_to_sync` counts Registries to sync;
  - a Registry whose origin is unreachable but has a snapshot stays connected.
- `configured_offers.py`:
  - `observe_configured_registries` checks each enabled Registry under `sync.mode` and announces it;
  - `read_configured_marketplace(observed=…)` prefers the observed health.
- `tui.py`:
  - `run()` observes before the screen is taken, printing one line per Registry;
  - after a Registry change, only that Registry's observation is dropped.
- `tui_consumer.py`:
  - `screens_from` applies the offered versions and counts Registries to sync;
  - Updates rows are installation rows;
  - `registry_state` adds a line to the Registry row;
  - `_badge` marks the Updates and Registries menu entries, and the Dashboard says where to go;
  - the Updates mark follows Show available updates, but the Registries mark does not.
- `scripts/manual_test.py`: `publish version` and `publish collection` push straight to the lab
  Registry's remote, as a merged promotion would. The Makefile targets are
  `manual-test-publish-version` and `manual-test-publish-collection`.
- `README.md`: the Dashboard frame now shows the Updates mark.

## Tests

- `tests/tui_updates_and_freshness_test.py` (27):
  - update availability, with a Hypothesis property over versions;
  - cells, offered versions, and Updates rows as installation rows;
  - Registry row states, and observed health reaching the row;
  - menu and Dashboard marks, Show available updates off, and number agreement;
  - composition with and without observation, and `run()` passing the observer.
- `tests/tui_updates_lab_e2e_test.py` (2), over the manual lab's real Git remotes:
  - the consumer installs `manual-check` 1.0.0, then the maintainer publishes 1.0.1 and the
    `lab-starter` Collection;
  - the consumer application, composed as on launch, announces the check, lists the update to
    1.0.1, counts it, and shows the new Collection.
- A focused run of 153 TUI, consumer, registry and doctor test files gave 1447 passed. Three
  failed:
  - the README frame, which now carries the mark; it was regenerated;
  - two `screen_skeleton_test.py` properties, which also fail on `main` from examples in the local
    Hypothesis database (B-226).

## Targeted mutations

Each mutation turned red only the tests that claim it:

| Mutation | Red |
|---|---|
| `screens_from` no longer applies `with_offered_versions` | four Updates and mark tests |
| `<` → `<=` in `_with_offer` | the Hypothesis property and "nothing is marked when nothing is newer" |
| `read_configured_marketplace` ignores `observed` | the three observed-health tests |
| Updates rows keyed by coordinate again | only `test_an_updates_row_is_the_installation_the_update_action_addresses` |

## Not in this slice

The owner's Installed crash, where one artifact is installed at both scopes for one harness, is
CP-42 (see `NEXT.md`).
