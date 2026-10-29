# CP-48 — Activity in SQLite, and which artifacts are used, per harness

Status: **done** (the owner ran the lab in opencode and Claude Code; one PR with CP-47 and CP-49), on
`feat/cp-47-aart-cli-update` with CP-47, in one PR at the owner's request (2026-10-28).
Authority: Product Specification §212, INV-318–INV-321, D-500, D-502.

## Steps

See `docs/refactor/plan.json`, epic CP-48.

1. A use from a hook payload, names only, and the ranking against what is installed, pure. Done.
2. One SQLite database for actions and uses; the receipt store's actions move into it. Done.
3. The hook script, and putting it in Claude Code's settings and opencode's plugins. Done.
4. Settings rows per harness, Activity's ranking, `consume usage`, the default harness at start. Done.
5. Robust under many concurrent writers (agents and subagents). Done.
6. The owner's run, and the PR. Done.

## Why

The owner asked for Activity to say which skills and MCPs are actually used, per harness, with a
ranking, beside install, update and uninstall, kept in SQLite rather than one JSON file per action,
in preparation for a telemetry server. They chose consent per harness with user-level hooks, every
event its own row, a hook tied to the Settings toggle and not to the Marketplace, recorded data that
can be deleted, and recording on by default only in opencode. Before the PR they moved that
default into a release variable, `AART_CLI_DEFAULT_USAGE_HARNESSES`, unset or `none` recording
nowhere without asking (D-502). Later: "w przypadku wielu agentów i
subagentów to musi być robust rozwiązanie".

## What changed

- `aart_cli/domain/artifact_usage.py` (new, pure): `USAGE_HARNESSES`, `parse_usage_harnesses`,
  `ArtifactUse`, `use_from_hook`, `installed_names`, `rank_usage`.
- `aart_cli/io/activity_store.py` (new): `ActivityDatabase` (`record_action`, `actions`,
  `record_use`, `usage_counts`, `forget_uses`); created 0600; schema under `BEGIN IMMEDIATE`; WAL
  switched on only when nobody holds the file (`_write_ahead`).
- `aart_cli/io/usage_hook.py` (new): the script a harness runs, `python -I … <harness> <home>`.
- `aart_cli/application/usage_recording.py` (new): `UsageHook`, Claude settings merge and removal,
  the opencode plugin, `ArtifactUsageView`, the disclosure and ranking lines.
- `aart_cli/io/usage_hooks.py` (new): `harness_file`, `running_usage_hook`, `set_usage_hook`,
  `reconcile_usage_hooks`, `read_artifact_usage`.
- `aart_cli/_default_usage.py` (new, empty in the source), `scripts/inject_default_usage.py`
  (new), the release action's step, both release jobs' `AART_CLI_DEFAULT_USAGE_HARNESSES`, the
  receipt's `default_usage_harnesses`, `configuration.seed.baked_usage_harnesses` (D-502).
- `aart_cli/commands/usage.py` (new): `consume usage show [--json] | enable | disable [--forget] |
  forget`; `cli.py`, `cli_parser.py`, `model.py` route it.
- `aart_cli/io/receipt_store.py`: actions through `ActivityDatabase`; the `activity/` directory is
  gone. `consumer_machine.py`: `ACTIVITY_WINDOW = 500`.
- `consumer_views.py` (`ConsumerSettings.artifact_usage`, the rows), `consumer_ui.py`,
  `tui_consumer.py` (rows, disclosure, `most used:`), `consumer_actions.py` (hooks applied on save
  and reverted on failure, `record_usage_by_default`), `tui.py` (the default at start).

## Evidence

- `tests/artifact_usage_test.py`: Hypothesis — no part of what a tool was called with reaches a
  use, over generated payloads; the ranking keeps every use and never rises. Claude and opencode
  payloads, the longest installed server prefix, one artifact in two harnesses.
- `tests/activity_store_test.py`: newest first and a limit; 0600; another schema version reported
  and left byte for byte; forget per harness; 4 rounds × 4 spawned writers on new databases; a
  writer creating the database waits for one that holds it (deterministic); the journal is WAL.
- `tests/usage_hooks_e2e_test.py`: the hook run as a harness runs it, from a project whose
  `aart_cli`, `json` and `sqlite3` would shadow them; 32 hooks at once on a new home; garbage and an
  unwritable home exit 0; Claude settings merge, replace and removal keep foreign entries;
  non-JSON settings left byte for byte; a foreign opencode plugin kept; only a present opencode is
  hooked by default and no `.config` is created.
- `tests/artifact_usage_screens_test.py`: the setting's default and round trip; Settings rows and
  disclosure; Activity's ranking; the production composition hooks opencode and not Claude; a hook
  that cannot be written leaves the row off; `consume usage enable/show/disable --forget`; tabnine
  refused.
- Stress (not committed, scratchpad): 64 processes × 100 writes on a new database each round, and
  3 × 100 concurrent real hook processes on a new home: nothing lost, slowest write 0.25 s.
- Installed wheel (lab, not committed): the branch's wheel installed with pipx into a lab
  `PIPX_HOME`, with `HOME` and `AART_CLI_HOME` in the lab. `consume usage enable` for both
  harnesses wrote the pipx environment's Python with `-I` and its `site-packages` script, after the
  person's own Claude hook. Run as Claude runs it (`sh -c` with the settings' command) and as the
  plugin runs it, from a project whose `aart_cli`, `json` and `sqlite3` would shadow them and with
  `PYTHONPATH` on it: both exited 0 with no output and recorded; 20 at once recorded all 20; the
  database was 0600 with no argument in it or its journal; `show --json` ranked them;
  `disable --forget` restored the settings exactly and deleted Claude's uses only; opencode's plugin
  was removed. Running aart-cli's own entry point with that `PYTHONPATH` loads the project's
  `aart_cli`, as any Python program would; only the hook is started with `-I`.
- Live, in an isolated project with a project-level hook and plugin and a temporary home:
  opencode 1.18.29 recorded `opencode|skill|hello-usage` and `opencode|mcp|usagedemo_word`;
  Claude Code 2.1.312 (`claude -p … --mcp-config .mcp.json --strict-mcp-config`) recorded
  `claude|skill|hello-usage` and `claude|mcp|usagedemo`. The real `~/.claude/settings.json` was
  unchanged (sha checked before and after) and `~/.config/opencode/plugins` was never created.

## Targeted mutations

| # | Mutation | Killed by |
|---|---|---|
| M1 | Claude's MCP name is the whole tool name, not the server | `artifact_usage_test` (server's name) |
| M2 | opencode's own tools are counted | `artifact_usage_test` (own tools are no use) |
| M3 | Claude added to the default harnesses (the constant D-502 removed) | `artifact_usage_test` (the default harness) |
| M4 | Shortest installed prefix instead of the longest | `artifact_usage_test` (longest server) |
| M5 | Merging tools of one server drops uses | `artifact_usage_test` (property and one line) |
| M6 | Oldest first | `activity_store_test` (newest first) |
| M7 | Database created 0644 | `activity_store_test` (owner's alone) |
| M8 | Another schema version accepted | `activity_store_test` (reported and left alone) |
| M9 | `PRAGMA journal_mode=WAL` before the lock again (the defect found in step 5) | `activity_store_test` (writer waits, 3/3; the spawned race 4/5) |
| M10 | WAL never switched on | `activity_store_test` (journal is WAL) |
| M11 | The hook exits 1 when anything inside fails | `usage_hooks_e2e_test` (fails inside, exits 0) |
| M12 | Removing the Claude hook removes every entry | `usage_hooks_e2e_test` (takes only aart-cli's) |
| M13 | A hook that cannot be written still turns the row on | `artifact_usage_screens_test` |
| N1 | `none` refused | `release_default_usage_injection_test` (unset and none) |
| N2 | a name that cannot record accepted | the value, the build, the runtime reader |
| N3 | a repeated name accepted | the value test |
| N4 | a baked value aart-cli cannot read records in opencode | the runtime reader records nowhere |
| N5 | settings ignore the baked list | `artifact_usage_screens_test` (5 tests) |
| N6 | the injector drops the value | a list is baked and read back |
| N7 | the receipt records `none` as a value | the receipt test |

M7 and M8 also turned the spawned-writer test red in a batch run: the spawned children import the
mutated module. Run alone, each was killed only by the test named.

## Not done here

B-246 (Tabnine's modelled hook), B-247 (typed `/skill`), B-248 (the TUI's reason for a failed hook),
B-249 (the CLI's default), B-250 (a stale hook path), B-251 (telemetry), B-252 (opencode custom
tools with `_`).
