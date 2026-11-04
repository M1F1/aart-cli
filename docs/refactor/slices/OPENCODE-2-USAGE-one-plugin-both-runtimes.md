# OPENCODE-2-USAGE — one opencode usage plugin both opencode runtimes load

**Status:** done, awaiting the PR. §212, §171.3 and §171.5 amended; D-520, D-521; B-272 done.

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

## Installed plugins on both runtimes (B-272, D-521)

OpenCode 2 skipped every plugin aart-cli installed ("must be a directory"), because §171.3's entry
was the module's path. Now:

- the `plugin` entry is the installation's tree, `./.opencode/aart-cli/plugin/<registry>/<name>`,
  and `PluginEntry.module` records the payload module inside it (`aart_cli/domain/hooks.py`);
- the settings-entry interpreter writes the tree's `index.js` before the entry
  (`aart_cli/io/execution.py`), only into the existing, unlinked tree: `export *` from the module,
  and as the default the module's own default, or its first function;
- a missing or edited `index.js` is drift of the settings component, and `doctor --repair` writes it
  again (`aart_cli/io/runtime_projection.py`);
- a receipt without `module` reads as the module-path form it always was.

How each runtime loads an entry, measured with marks written by the plugin's own functions:

| Plugin / entry | 1.19.4 | 2.1.3 |
|---|---|---|
| `{id, server, setup}`, module path entry | `server`, `setup` | skipped, "must be a directory" |
| `{id, server, setup}`, directory with `server.js` | not loaded | `setup` |
| `{id, server, setup}`, directory with `index.js` | `server`, `setup` | `setup`, no warning |
| 1.x-only named export, directory with this `index.js` | loaded once | "failed to load plugin" |

The last row is OpenCode 2's own refusal: there is no 1.x API there to adapt such a plugin to.

### Live end to end, fake model and fake MCP

Each build in its own temporary home, with a real `aart-cli consume install --profile opencode` of
a Registry approving a one-tool MCP stdio server (`ping` returns a secret word and leaves a mark),
a dual plugin that leaves a mark from `server` and from `setup`, and a skill, plus
`consume usage enable --harness opencode`. A local OpenAI-compatible fake model calls the MCP tool,
then the skill, then answers. On 2.1.3 MCP tools are reached only through Code Mode's `execute`
(`tools["<server>"].ping({})`); the fake model retries once 2.1.3 has registered them, which it does
in the background after "mcp connected".

| Scope | Build | plugin | MCP called | answer | Activity |
|---|---|---|---|---|---|
| project | 1.19.4 | `server setup` | yes | kumquat, pineapple | `mcp probe-company-project_ping`, `skill probe-skill-company-project` |
| project | 2.1.3 | `setup` | yes | kumquat, pineapple | the same two, with the session |
| user | 1.19.4 | `server setup` | yes | kumquat, pineapple | `mcp probe-company-user_ping`, `skill probe-skill-company-user` |
| user | 2.1.3 | `setup` | yes | kumquat, pineapple | the same two, with the session |

No plugin warning or error in any run's log. `opencode run` reads stdin when it is not a terminal,
so the runs take `< /dev/null`. These runs stay local, never CI.

Tests:
- `tests/plugin_installation_e2e_test.py`: the tree holds the `index.js` both runtimes load; a
  removed `index.js` is drift that a repair puts back; an edited one is drift.
- `tests/plugin_entry_test.py`: a tree entry's validation, the `index.js` text, a Hypothesis
  property that every module is imported as itself, a receipt round trip with `module`, and an
  older receipt without it.
- `tests/opencode_plugin_index_test.py` (new, node): a dual definition passes through; a 1.x module
  keeps its exports and its first function becomes the default; a default function stays it.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| drop the `_write_index` call | `test_the_tree_holds_the_index_both_opencode_runtimes_load`, and eight more |
| drop the `_indexed` drift check | `test_a_removed_index_is_drift_that_a_repair_puts_back`, `test_an_edited_index_is_drift` |
| `_indexed` accepts any `index.js` content | `test_an_edited_index_is_drift` only |
| drop the `?? first function` default | `test_a_1x_plugin_keeps_its_exports_and_its_first_function_becomes_the_default`, `test_the_index_loads_the_module_and_nothing_else` |
| entry is the module path again | `test_the_tree_holds_the_index_both_opencode_runtimes_load`, and five more |
| receipts drop `module` on read | `test_the_tree_and_its_module_survive_a_round_trip`, and the e2e tests |
