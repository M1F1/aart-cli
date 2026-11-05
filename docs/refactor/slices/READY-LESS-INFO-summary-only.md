# READY-LESS-INFO — Ready's Less info is the summary; the changes and placeholders are More info's

**Status:** done (released with the PR that carries it). §161.5 (08, 09) and §172.3 amended; D-525.

## Why

For a Collection, Ready in Less info listed a screen of text under its counts:
- every material change once per artifact, so "Install its Python dependencies with uv" appeared
  seven times;
- "Store the credential it needs securely in macOS Keychain" once per credential;
- the whole list of inputs left as `AART_NOT_SET`.

The owner asked for the credential line to go and for everything else to go to verbose.

## What was done

`render_ready` (`aart_cli/tui_consumer.py`):
- **Less info** keeps the counts and the harnesses. It also keeps the INV-151 sentence for a
  material risk no count names, plus `Press [v] for more info: the changes it makes, what is set
  later, the plan.`
- **More info** opens with `_changes_block`: the material changes, each once, with `(×n)` when the
  plan needs one more than once. After it come what 07b stored, what is left as `AART_NOT_SET`, and
  the Verbose plan as before.
- **`configure-credential`** (`_UNLISTED_CHANGES`) is not listed in either mode. The count
  `credential(s) stored securely` says it, and the Verbose plan's Remediations and Effects still
  carry it (INV-152).

## Evidence

Unit tests, `tests/remediation_changes_test.py`, rewritten for D-525:
- Less info lists no change.
- More info names each change once, with `(×2)` for two artifacts.
- No mode says "store the credential".
- Less info still says network access in plain words.
- A Hypothesis property: Less info lists nothing, and More info lists exactly the material changes.

TUI flow tests:
- `tests/consumer_install_flow_shell_test.py`: storing a credential is the count only.
- These e2e tests press `[v]` on Ready, then find the lists in More info and not in Less info:
  - `tests/placeholder_warnings_test.py`, for `AART_NOT_SET`;
  - `tests/collection_inputs_tui_e2e_test.py`, for a Collection's members;
  - `tests/install_credentials_test.py`, for what 07b stored.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| The placeholder and 07b lists back in Less info | 2 e2e tests |
| `configure-credential` listed again | 3 tests |
| No `(×n)` count | `test_a_change_many_artifacts_need_is_said_once_with_how_many` |
| No change list in More info | 6 tests |
| The network risk sentence suppressed | 2 tests |

Focused: 1006 TUI, consumer, install, remediation, placeholder and Collection tests pass; ruff, ruff format,
mypy, tach, docs-check and secret-shape-check pass.
