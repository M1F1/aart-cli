# OPENCODE-HARNESS-VERSION — OpenCode 2's uses carry the version it reported (D-536, B-279)

Status: implemented on `feat/opencode-harness-version` (2026-11-28), with the server's revision 8
on its `feat/harness-version`. D-536, §212, §213, INV-318, INV-340.

## Why

OpenCode 1.x and 2 both send `opencode_plugin`/`opencode`, so neither Activity nor the dashboard
could say which OpenCode delivered a use. A brief from the enterprise deployment asked for the
version, read safely and failing softly; B-279's `opencode2` label is no longer needed.

## What was done

- The plugin's OpenCode 2 `setup` reads `ctx.app.version` once, in a `try`, and hands it over as
  `harness_version` only when it is a string of at most 64 characters matching
  `HARNESS_VERSION_PATTERN`; OpenCode 1.x's path hands none. It calls nothing and reads no
  environment, executable path or `--version`.
- The hook checks it again (`harness_version_from_hook`) and keeps it on `ArtifactUse`; the
  Activity database gains the nullable column on open and records and reads without it when it
  cannot.
- `EventContext.harness_version` is sent only to a server naming revision 8 or later
  (`_FIELD_REVISION`); the outbox keeps it either way.
- The contract (`docs/telemetry-api-v1.md`, examples) gains the field, its rule, one valid and
  three invalid examples, and revision 8; the digests are pinned again. The server repository
  holds byte-identical copies.

## Evidence

- `artifact_usage_test.py::HarnessVersionTest`: the pattern equals the brief's, kept and refused
  values, `ArtifactUse` refuses a bad one, a Hypothesis property over generated strings.
- `opencode_plugin_runtimes_test.py::OpenCodeSVersionTest`: the real plugin under Node with 13
  `ctx.app` shapes (plain, beta, none, null, number, function, empty, `latest`, `v`-prefixed, a
  path, an appended `; x`, too long, a throwing getter) and OpenCode 1.x; only plain and beta are
  handed over, and every call is still recorded.
- `usage_hooks_e2e_test.py`: a real hook keeps a version and drops a false one;
  `AnOlderActivityDatabaseTest` (an old database gains the column; a failing `ALTER` still records
  the use, without a version); the plugin holds no `process.execPath`, `process.version`,
  `--version` or a call of `ctx.app.version`.
- `telemetry_context_test.py::TheHarnessVersionTest` and
  `telemetry_sync_test.py::test_opencode_s_version_reaches_a_server_holding_revision_8_and_no_older_one`
  (revisions 7, 8, 9).
- Server: `test_context.py` (held only in uses, seven refused shapes, breakdown with the uses that
  said none apart), `test_repository_contract.py` (memory and SQL held equal over generated
  histories with the field; a revision-7 SQLite database gains the column, keeps its rows and
  remakes `event_wide`), `test_api.py` (`/api/v1/contract` says 8).
- Targeted mutations, each turning its named test red: client -- the version read from
  `process.version`, the pattern check dropped in the plugin, the hook keeping any string, the
  `_FIELD_REVISION` gate removed, the ALTER failure not caught; server -- the column not added, the
  view not remade, the pattern dropped, the suffix widened to 64, the field held in lifecycle
  events, the SQL row not read back, the dimension dropped.
