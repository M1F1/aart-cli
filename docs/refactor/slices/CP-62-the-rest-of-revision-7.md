# CP-62 — The rest of contract revision 7, in one PR

Status: **in progress**. Branch `feat/telemetry-context-rest`, worktree
`/Users/mifi/code/aart-cli-context-rest`, from `main` at 0.29.0 (`0e82a58`).
Authority: Product Specification §213 (to amend), D-519 (to write), INV-340. Resolves B-269.
The owner asked on 2026-11-03 for all of it in **one PR**, with a strong focus on **opencode**
(the enterprise harness), and anything possible for Tabnine.

## Context

- The server side is done and merged: aart-cli-telemetry-server #18 (read API, `/docs`, `/mcp`) and
  #19 (contract revision 7, `event_context`, view `event_wide`, the Breakdown panel).
- CP-61 (#131, released in 0.29.0) already sends:
  - every event's Registry alias;
  - the harness and scope of an install, update or removal;
  - an opencode MCP use's `tool`;
  - the request's `environment`.

  It sends these only to a server that answers `GET /api/v1/contract` with revision ≥ 7.
- `EventContext` in `aart_cli/domain/telemetry.py` already holds all 14 fields, with their shapes,
  and `CONTEXT_FOR`.

## What this PR sends

### Lifecycle events (every harness: claude, opencode, tabnine, ...)

| Field | Source |
|---|---|
| `interface` | `tui` from `consumer_actions.py` (complete_configured_installation ~3821, complete_configured_uninstall ~4215); `cli` from `commands/marketplace.py` (~1224, ~1634). Pass down through `complete_configured_*` → `complete_installation_action` → `record_installation_transaction` → `ReceiptDetailView.interface`. |
| `duration_ms` | The io layer (`configured_installation_action.py`, `configured_uninstall_action.py`) measures with a monotonic clock and passes `elapsed: Callable[[], int]` into the application. It is called just before `store.record_action`, giving `ReceiptDetailView.duration_ms`. |
| `previous_version` | `item.plan.intent.previous.artifact.version` for UPDATE and DOWNGRADE (`_replaced` in consumer_views, **done**). |
| `via` / `collection` / `collection_version` | From the receipt artifact's `ownership` (OwnershipView kind/owner) and `receipt.selection`:<br>- a collection owner that is among `selection.collections` gives `via=collection`; the owner string `source/collection/name@version` is parsed into the name and version;<br>- otherwise, with a selection, `via=direct`;<br>- a dependency only gives no `via`;<br>- a plugin's member skill gives `via=plugin` (**done** in the domain). |
| `package_digest` | `ArtifactReceipt.object_digest` (str is `sha256:<hex>`), added beside `members` in `receipt_recording._with_members` (to be generalised into `_with_installations`). |
| `configuration_inputs` / `credential_inputs` | From `PlannedInstallation`: `len(bound.config_values)` and `len(credentials)`; `PlannedPlacement` gives 0/0. Passed as a new optional argument to `record_installation_transaction`, keyed by coordinate. Counts only, never names or values. |

A member skill's event keeps `interface`, `duration_ms`, harness, scope, Registry and
`previous_version`. It drops the package, inputs and collection (`_THE_PLUGIN_S` in the domain,
**done**).

### Use events (the opencode focus)

- **`session`**. The opencode plugin (`usage_recording.py` template, `tool.execute.before`) also
  hands over `input.sessionID`, and Claude Code's hook payload has `session_id`. The hook
  (`io/usage_hook.py` → `domain/artifact_usage.use_from_hook`) turns it into a pseudonym: a UUID
  built from HMAC-SHA256 under a random key kept in the Activity database's meta table, so it is
  never the harness's id. Activity gets a nullable `session` column on uses, added in place without
  a schema version bump, as the outbox's `context` was. The use event carries it.
- **`scope` of a use**. opencode hands over `directory`. When the installed artifact answering the
  use has a project-scoped installation for that directory, the scope is `project`, else `user`.
  Check how `resolve_installed`/`InstalledName` is built (does it know each installation's scope
  and project root?). Never send the directory.
- **Claude Code `tool`**. Claude's hook sees `mcp__<server>__<tool>`; send the tool part as `tool`
  when the server resolves to an installed or unmanaged MCP.
- **Tabnine**: aart-cli installs MCPs into Tabnine (user and project). Its lifecycle events get
  everything above. Uses cannot be recorded: Tabnine has no known pre-tool hook, and the contract's
  sources are only `claude_hook` and `opencode_plugin`. That goes to the backlog (a new source on
  both sides if Tabnine CLI ever offers a hook).

## Done so far (uncommitted at the time of writing, then committed as WIP)

- `domain/telemetry.py`:
  - `lifecycle_event(..., member=None, **said)` takes every field;
  - `_held(event_type, context)` drops what the type does not hold and keeps the collection rule;
  - member events say `via=plugin` without the plugin's package or inputs;
  - `_event` falls back to the bare event if a context would make it invalid (INV-340: context
    never costs the event).
- `application/consumer_views.py`:
  - `ReceiptArtifactView` gains `previous_version`, `package_digest`, `configuration_inputs` and
    `credential_inputs`;
  - `ReceiptDetailView` gains `interface` and `duration_ms`;
  - all are persisted as optional keys (`_said`, `_optional`);
  - `_replaced(intent)` fills in `previous_version`.

## Remaining steps

1. `application/telemetry_events.py`: pass every field to `lifecycle_event`, compute `via` and the
   collection.
2. `receipt_recording.record_installation_transaction(..., inputs=, interface=, elapsed=)`:
   generalise `_with_members` to add the digest and counts, and set `interface`/`duration_ms` on the
   detail.
3. `installation_action.complete_installation_action(..., interface=, elapsed=)`, computing the
   input counts from `prepared.installations`.
4. io: `configured_installation_action` and `configured_uninstall_action` take `interface` and
   measure `elapsed`; the TUI passes `tui` and the CLI passes `cli`.
5. Uses:
   - the opencode plugin template sends `session: input.sessionID`;
   - `use_from_hook` reads the session (both harnesses) and the directory;
   - Activity gets a session key and a `session` column;
   - `use_event` gets `session`, `scope` and Claude's `tool`;
   - the template change must reach installed hooks: `reconcile_usage_hooks` rewrites the plugin
     file when its content differs (check this).
6. Tests (TDD, then a targeted mutation per claim, Hypothesis for "context never costs the event"):
   - domain held/collection/member rules;
   - receipt round trip;
   - `telemetry_events` via/collection;
   - the transaction records the digest, counts, interface and duration;
   - an e2e CLI install in a temporary HOME/AART_CLI_HOME whose outbox event says `interface=cli`;
   - the hook records a session pseudonym, never the raw id, and is stable within a session;
   - an opencode project use says `scope=project`.
7. Docs:
   - spec §213 "Where and how" bullet: drop the "left out until aart-cli says them" sentence and
     describe every field;
   - D-519, CP-62 in plan.json, NEXT, MIGRATION_STATUS;
   - BACKLOG: B-269 resolved; a new entry for Tabnine uses; the held-events cursor (from B-269)
     stays open as its own entry;
   - Settings/announcement disclosure text: add "TUI or CLI, how long, the versions, counts of
     inputs, a session pseudonym".
8. Scoped gates: ruff, format, mypy, tach, docs-check, secret-shape-check, the affected tests. CI
   runs the rest. Then one PR whose title is a Conventional Commit, with a COMMIT_OVERRIDE block.

## Rules to keep

- No project name, path or directory, nor a hash of one, ever leaves the machine; the session is a
  keyed pseudonym.
- Tests never touch the real HOME; use a temporary HOME and AART_CLI_HOME.
- Keep enterprise stack names out of the public repository.
