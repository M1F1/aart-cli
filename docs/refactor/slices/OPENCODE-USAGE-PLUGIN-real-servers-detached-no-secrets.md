# OPENCODE-USAGE-PLUGIN — Real MCP servers, a recorder that outlives opencode, no secrets (B-277)

Status: implemented on `fix/opencode-usage-plugin`, stacked on PR #147 (2026-11-27). D-531, §212.

## Why

The owner asked for opencode telemetry to work properly. A report measured on OpenCode 2.3.2 and
1.19.5 found three faults in `~/.config/opencode/plugins/aart-cli-usage.js`:

- any tool with `_` counted as an MCP use, so `experimental_image_generate` and other plugins'
  `<file>_<export>` tools were sent as unmanaged uses;
- `opencode run` ending right after a tool call killed the recorder, losing the last uses (in
  automation, all of them);
- the recorder inherited opencode's whole environment: its server password, a launcher's tokens, a
  provider's key.

## What was done

- The plugin asks the runtime for its MCP servers (`client.mcp.status()` on 1.x, `ctx.mcp.list()` on
  2) and hands over `server`, the longest whose sanitised name prefixes the tool; nothing else is
  handed over as MCP. `use_from_hook` records an opencode MCP use only with a server the tool fits,
  as the server with the tool beside it.
- The recorder is spawned `detached`, `windowsHide`, `unref()`ed, with `RECORDER_ENVIRONMENT` only
  (`PATH`, `HOME`, `LANG`, `LC_*`, `TMPDIR`, `SYSTEMROOT`, proxies, `SSL_CERT_*`, `CI`,
  `AART_CLI_AUTOMATED`).
- The plugin hands over `runtime: 1|2` by the hook that delivered the call; consumed by B-279.

## Evidence

- `tests/opencode_plugin_runtimes_test.py` (node, both runtimes): servers asked, longest chosen,
  false MCP tools and a client-less 1.x not handed over; the recorder in its own session with no
  `OPENCODE_PASSWORD`/`ANTHROPIC_API_KEY` but the proxy; `OpenCodeExitingTest` kills the driver's
  whole process group 300 ms after the calls and both uses are still recorded by a recorder that
  writes after 500 ms.
- `tests/artifact_usage_test.py`: server and tool, a sanitised server name, tools no server fits,
  a property over generated server and tool names.
- Updated: `usage_hooks_e2e_test`, `telemetry_context_rest_test`.

### Targeted mutations

Each turns its named test red: dropping `detached: true` (`OpenCodeExitingTest`); dropping
`env: environment()` (`test_the_recorder_runs_detached_with_nothing_opencode_holds`); the first
server instead of the longest and handing over without a server
(`test_each_runtime_hands_over_its_skill_and_mcp_calls_by_name_only`); Python taking the server
from the tool (`test_a_tool_no_server_is_named_for_is_no_use_underscore_or_not`); the raw server
name as the prefix (`test_a_server_name_opencode_rewrote_still_names_its_tools`).

### Mutation adequacy (`make mutants ONLY=aart_cli/domain/artifact_usage.py TESTS="tests/artifact_usage_test.py"`)

No survivor in `_opencode`. The 11 survivors are in functions this slice did not change (`_claude`,
`_name`, `_project`, `rank_usage`, `resolve_installed`), and are covered by other test modules
the scoped run does not include. The file's properties now suppress `differing_executors`, as
mutmut runs them from another executor.

## Not done here

The `opencode2` label (B-279, with P0-2 and a telemetry-server change). Live runs on OpenCode 2
(B-278): `ctx.mcp.list()` is taken from the published plugin types, not yet from a live 2.3.2.
