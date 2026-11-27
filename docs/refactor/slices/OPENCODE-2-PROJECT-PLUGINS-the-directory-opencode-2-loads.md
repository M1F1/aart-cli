# OPENCODE-2-PROJECT-PLUGINS — The directory OpenCode 2 loads, for the OpenCode chosen (B-276)

Status: implemented on `feat/opencode-2-project-plugins`, stacked on PR #148 (2026-11-27). D-532,
§171.3.

## Why

OpenCode 2 report, P0-2: a project plugin registered as a relative entry in `opencode.json` is lost
when a launcher starts OpenCode 2 from a subdirectory, and OpenCode 2 loads a plugin listed and in
`.opencode/plugins/` twice. The owner chose: an explicit setting, defaulted by the build
(enterprise `2`, public `1`), and no migration of existing installations.

## What was done

- `aart_cli/domain/opencode_runtime.py`, `_default_opencode.py`, `scripts/inject_default_opencode.py`,
  the release action/workflow and receipt (`default_opencode`): `AART_CLI_DEFAULT_OPENCODE`.
- `ConsumerSettings.opencode_runtime` (absent until chosen), the Settings row *OpenCode: 1 | 2*,
  `aart-cli consume opencode [1|2]` (`commands/opencode.py`).
- `PLUGIN_DIRECTORIES` / `plugin_directory` (harness), `plugin_loader` / `plugin_loader_at` (hooks):
  `index.js` importing the tree's module by a relative path.
- `ArtifactDelivery.loads` (receipts); the delivery executor writes the loader
  (`_write_loader`); `DeliverArtifact.loads_code` raises the plan's risk to `high-risk-execution`.
- `placements_for` reads the setting; for OpenCode 2 at Project scope a plugin is that delivery
  and no settings entry. The status view recognises the directory (`consumer_machine`).

## Evidence

- `tests/opencode_runtime_test.py`: parsing (examples and a property naming the value it refused),
  the baked default, the Settings row and stored values, the loader's exact text, its refusals and
  its absolute-path inputs.
- `tests/opencode2_project_plugin_e2e_test.py`, the public command end to end: install (no
  `opencode.json` write, loader only, receipt `loads`), review says it runs code and writes
  nothing, an edited loader is drift that a reviewed repair restores, uninstall removes loader and
  tree, an OpenCode 1 installation stays and uninstalls after the switch, reinstalling moves it,
  user scope keeps the entry, an unchosen build installs for 1, and `consume opencode` says who
  decided.
- `tests/opencode_default_injection_test.py`: unset renders the committed module byte for byte,
  `2` is stamped, `3` stops the release leaving the file, the release receipt value.
- `tests/opencode2_project_plugin_live_test.py` (local only; `opencode2` from `PATH`, skipped
  otherwise): a real OpenCode 2 beta 19271 imports and starts the plugin once from
  `src/deep`, plainly and with the project's configuration off and its plugins handed over as a
  launcher does.
- Regression: 58 related test modules, 680 passed.

### Targeted mutations

| Mutation | Turns red |
|---|---|
| `loads_code=False` in the desired state | `test_review_says_it_runs_code_and_writes_nothing` |
| OpenCode 2 branch disabled in placement | install, repair, reinstall e2e; the launcher-style live test (the plain live test stays green: without a launcher OpenCode 2 also finds the entry) |
| status view ignores the loader directory | install, repair, reinstall e2e |
| loader imports the absolute module | `test_it_imports_the_module_from_itself_not_from_where_opencode_started` and the e2e |
| `isinstance(bool)` instead of `type is int` for the stored value | `test_a_stored_value_it_cannot_mean_is_refused` (`2.0`) |

### Mutation adequacy (`make mutants`, scoped)

- `aart_cli/domain/opencode_runtime.py` with `opencode_runtime_test`: 16/16 killed (one survivor,
  the diagnostic's text, killed by asserting the code, severity and the refused value).
- `aart_cli/domain/hooks.py` with `opencode_runtime_test`: every mutant of `_loading`,
  `plugin_loader` and `plugin_loader_at` killed except the wording of their two `ValueError`
  messages, which nothing claims. The e2e files are left out: under mutmut each mutant times out
  in them. `plugin_entry_test` fails mutmut's `differing_executors` health check, as the
  usage-plugin properties did; a backlog note, not this slice.

### Findings

- OpenCode 2 (beta 19271) starts only a `{ id, setup | effect }` default export, from the directory
  and from the `plugin` list alike; a 1.x function plugin is imported and refused. Recorded in
  §171.3 as the plugin's to fix.

## Left

- B-279: show which OpenCode was last used, and a Settings choice that differs from it.
- B-278: MCP servers, instruction files and the usage plugin live on OpenCode 2.
