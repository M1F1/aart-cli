# OPENCODE-2-USAGE — one opencode usage plugin both opencode runtimes load

**Status:** done, awaiting the PR. §212 amended; D-520; B-272 opened.

## Why

A build of opencode on the OpenCode 2 runtime refused aart-cli's usage plugin at start:
"Plugin must export a default definition with an id and an effect or setup function". The plugin
`~/.config/opencode/plugins/aart-cli-usage.js` had only a named, OpenCode 1.x-style export, so on
OpenCode 2 no skill or MCP use was recorded. Most people run opencode 1.19.4, where the plugin
worked; the fix must not change anything there.

## What was done

- `opencode_plugin()` (`aart_cli/application/usage_recording.py`) writes one module whose only
  export is `export default { id: "aart-cli-usage", server, setup }`:
  - `server({ directory })` returns `tool.execute.before` for OpenCode 1.x (from 1.18.29);
  - `setup(ctx)` registers `ctx.tool.hook("execute.before", event)` for OpenCode 2, with the
    directory from `ctx.location.directory`; it registers nothing without `ctx.tool.hook`, returns
    nothing (a return value is taken as cleanup), and the hook never throws (it would fail the call);
  - a skill's name is `input.id` on OpenCode 2 and `args.name` on 1.x.
- `use_from_hook` (`aart_cli/domain/artifact_usage.py`) records none of OpenCode 2's own
  `opencode_<tool>` tools, which reached the hook beside MCP calls.
- §212's hook bullet and §171.3's OpenCode 2 sentence say what was measured.

## Evidence

Live, each build in its own temporary home (1.x and 2 cannot share `opencode.db`), the real
usage hook writing a temporary Activity database, a project skill and a one-tool MCP stdio server:

| | opencode 1.19.4 | opencode2 2.1.3 |
|---|---|---|
| plugin of 0.30.0 | skill and `probe_ping` recorded | "failed to load plugin"; nothing recorded |
| this plugin | skill and `probe_ping` recorded, once each | skill and `probe_ping` recorded, with the session pseudonym |

Before the `opencode_` rule, 2.1.3 also recorded `opencode_list_mcp_resources` as an MCP use.
The event's shape (`tool`, `sessionID`, `input`), the skill tool's `id` input, MCP naming
(`<server>_<tool>`, CodeMode's inner calls included) and the `opencode_` namespace come from the
types and source of `@opencode/plugin` and `@opencode/core` 2.2.5.

Tests:
- `tests/opencode_plugin_runtimes_test.py` (new): imports the written plugin into node and drives
  it as each runtime does, with a stand-in hook keeping what it is handed: one default export with
  `id`, `server` and `setup`; one `execute.before` registration and no cleanup; no hook throws; both
  runtimes hand over the skill and MCP calls by name only, never the arguments. Skipped without node.
- `tests/artifact_usage_test.py`: OpenCode 2's own namespaced tools are no use; `opencodex_search`
  still is.
- `tests/usage_hooks_e2e_test.py`: the written text holds both hooks and serializes no arguments.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| skill name from `args?.name` only | `test_each_runtime_hands_over_its_skill_and_mcp_calls_by_name_only` |
| drop the `ctx.tool.hook` guard in `setup` | `test_opencode_2_gets_one_tool_hook_...`, and three more |
| add the named export back beside the default | `test_its_one_export_is_a_definition_both_runtimes_load` |
| read `event.tool` without `?.` | `test_a_hook_never_throws_into_opencode_2_s_tool_call`, and three more |
| drop `not tool.startswith(_OPENCODE_OWN)` | `test_opencode_2_s_own_namespaced_tools_are_no_use` |

## Found and left

B-272: OpenCode 2 skips a plugin installed for opencode, because §171.3's entry is a module path
and OpenCode 2 loads only directory entries.
