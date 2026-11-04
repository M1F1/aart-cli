# CP-62 — The rest of contract revision 7, in one PR

Status: **done**; PR #133, released in 0.30.0. Branch `feat/telemetry-context-rest`, worktree
`/Users/mifi/code/aart-cli-context-rest`, from `main` at 0.29.0 (`0e82a58`).
Authority: Product Specification §213 (amended: "The rest of revision 7"), D-519, INV-340. Resolves B-269; B-270 and B-271 are open.
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

## What was done

- **Lifecycle** (`application/telemetry_events.py`, `receipt_recording.py`,
  `installation_action.py`, `io/configured_installation_action.py`,
  `io/configured_uninstall_action.py`):
  - every receipt field reaches `lifecycle_event`;
  - `_came` decides `via` and the Collection;
  - `_with_installations` (formerly `_with_members`) adds the digest and the input counts per
    installation;
  - `record_installation_transaction` and `complete_installation_action` take `inputs`,
    `interface` and `elapsed`;
  - the io layer starts a `stopwatch()`;
  - the TUI passes `tui` and `commands/marketplace.py` passes `cli`.
- **Domain** (`domain/telemetry.py`): the coordinate's Registry alias always wins over a `registry`
  passed beside it (found by Hypothesis).
- **Uses**:
  - `domain/artifact_usage.py`:
    - `ArtifactUse.tool` and `.session`;
    - `session_from_hook`, `session_pseudonym` and `use_scope`;
    - `InstalledName.scope`/`.root`.
  - `use_event` takes `tool`, `session` and `project`.
  - `io/usage_hook.py` turns the session into the pseudonym.
  - `io/activity_store.py`:
    - `tool`/`session` columns and a `meta` table, added in place;
    - `session_key()`.
  - `io/telemetry_store.py`: a local `project` column, and a use's tool and session in `context`.
  - `telemetry_sync` passes them on.
  - The opencode plugin hands over `input.sessionID`.
- **Disclosures**: `what_is_sent` and `usage_disclosure` name the new fields.
- **Docs**:
  - §213;
  - D-519;
  - plan.json (CP-61 done, CP-62);
  - NEXT, MIGRATION_STATUS;
  - B-269 resolved, B-270 and B-271 opened.

## Evidence

- `tests/telemetry_context_rest_test.py` (23 tests). Hypothesis states the property that an event
  is never lost to what it says, and that every field it says was given, in a field its type holds.
  Other tests cover:
  - via/Collection;
  - the recorded receipt's digest, counts, interface and duration, and their round trip;
  - session pseudonyms (Hypothesis: a UUID, stable, never the id, keyed by harness and key);
  - a use's scope;
  - the hook storing no raw session id anywhere in the state directory;
  - an older Activity database gaining its columns;
  - the outbox keeping a use's tool, session and project.
- `tests/installation_action_test.py`: the counts come from the plan's bound inputs (1/1), with
  the interface and duration.
- `tests/plugin_installation_e2e_test.py`:
  - a `consume install` sends `interface=cli`, `via=direct`, the digest, 0/0 inputs and a
    duration to a revision 7 server, and each skill sends `via=plugin` without the package;
  - an opencode use in the project sends `scope=project` and a UUID session, never the raw id or
    the directory.
- Updated for the new behaviour:
  - `artifact_usage_test` (Claude's MCP use keeps its tool);
  - `usage_hooks_e2e_test` (the plugin hands over the session).
- Focused run: the receipt, installation, uninstall, plugin, telemetry, usage and Activity modules
  (493 tests), plus every boundary and purity test (58), pass. ruff, ruff format, mypy and tach
  pass. CI runs the full suite.

Targeted mutations, each killed by the test named:

| Mutation | Killed by |
|---|---|
| `_came` treats any Collection owner as chosen | `test_an_artifact_picked_by_hand_is_direct_even_when_a_collection_owns_it` |
| `_input_counts` swaps and inflates the counts | `test_the_receipt_counts_the_inputs_the_plan_asked_for_and_says_how_it_ran` |
| the CLI passes `tui` | `test_a_command_line_install_says_so_and_the_plugin_s_skills_say_how_they_came` |
| `_with_installations` drops the configuration count | `test_the_receipt_holds_the_package_counts_interface_and_duration` |
| a member says `via=direct` | `test_a_plugin_s_skill_says_how_and_where_but_not_the_plugin_s_package` |
| a passed `registry` overrides the coordinate's | `test_the_registry_is_always_the_coordinate_s` |
| `_within` accepts any prefix (`/work/app` for `/work/application`) | `test_a_use_in_the_project_an_installation_is_for_says_project` |
| the hook pseudonymizes a constant instead of the session | `test_a_session_is_kept_as_one_pseudonym_and_its_id_is_nowhere` |
| the sync drops the session | `test_an_opencode_use_says_its_session_and_the_scope_of_what_it_reached` |
| Claude's MCP use loses its tool | `test_a_claude_code_use_says_the_tool_its_hook_named` |
| Activity stores no session | `test_a_session_is_kept_as_one_pseudonym_and_its_id_is_nowhere` |
| the plugin stops handing over the session | `test_the_plugin_hands_over_names_only` |

One mutant survived: `if project and any(...)` → `if any(...)` in `use_scope`. It was equivalent,
since an empty directory is within no root, so the redundant condition was removed.

## Rules kept

- No project name, path or directory, nor a hash of one, leaves the machine; the session is a
  keyed pseudonym.
- Tests use a temporary HOME and AART_CLI_HOME.
- No enterprise stack names in the public repository.
