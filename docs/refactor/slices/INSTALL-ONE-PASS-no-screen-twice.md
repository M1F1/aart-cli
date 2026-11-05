# INSTALL-ONE-PASS — no install screen is drawn twice

**Status:** done (released with the PR that carries it). §172 bullet "After 07, 07a is not asked again" amended; D-526.

## Why

The owner reported that during an MCP install "one window repeats and then switches
automatically". The screen sequence of a single MCP install showed two causes, both after 07:
- **05 flashed while the plan was prepared again.** Submitting 07 rewinds the session to 05
  (D-380), and the preparing heartbeat drew the current state, so 05 was drawn between 07 and
  07b/Ready, then replaced by itself.
- **05 came back to ask pip or uv.** On a machine with both backends the plan left an installer
  choice open, and `_after_inputs` returned 05 to ask it: the same screen a second time.

Asked how pip or uv should be chosen, the owner chose "Use Settings, no question".

## What was done

- `aart_cli/tui_consumer.py`:
  - `_preparing_frame` draws the state before the key when that key left 07, so 07 stays until
    the next screen is ready.
  - 05 draws no installer rows; the row helpers are gone.
- `aart_cli/consumer_actions.py`: `_after_inputs` returns 07b or Ready, never 05.
- `aart_cli/application/consumer_ui.py`:
  - the installer toggle on 05 is gone;
  - moving past the form clears 07's rows, so 07b opens on the credential, not on the Continue
    row both screens share.
- `aart_cli/application/installation_planning.py`, `artifact_installation.py`,
  `installation_proposal.py`: `allowed_remediations`, `prepare_install_plan` and
  `installation_remediations` take `preferred_installer`, read off the planned dependency effect
  by `planned_installer`. Before, the listed change said "with pip" while the effect ran uv.

## Evidence

- `tests/collection_inputs_tui_e2e_test.py::test_after_07_the_screen_stays_on_07_until_the_next_one_is_ready`:
  no Review Selection frame after Required Inputs, and the beaten frames exist.
- `tests/python_installer_choice_test.py`:
  - `TheReviewScreenAsksNoBackendTest.test_no_offer_is_a_row_or_drawn`;
  - `test_the_review_asks_no_backend_when_the_machine_has_both`;
  - `test_the_stored_preference_is_the_backend_the_reviewed_plan_names`: for pip and for uv,
    Ready's More info says `install its Python dependencies with <preference>` and the Verbose
    plan's effect says `installer=<preference>`.
- `tests/inputs_go_forward_test.py::test_after_the_form_no_screen_asks_for_the_harness_again`.
- `tests/install_credentials_test.py`: the 07b e2e tests open on the credential (Set later is
  `UP` from there).

The screen sequence of a single MCP install is now Marketplace, Install Path, Review Selection,
Scope, Required Inputs, Credentials, Ready, each once.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| `_preparing_frame` draws the current state | `test_after_07_the_screen_stays_on_07_until_the_next_one_is_ready` |
| `planned_installer` returns None | `test_the_stored_preference_is_the_backend_the_reviewed_plan_names` (uv) |
| 07's rows kept past the form | 17 tests, 07b opening on Continue |
| `_after_inputs` returns 05 for an open installer choice | 17 tests |

Focused: 1800 TUI, consumer, install, credential, remediation, placeholder and Collection tests
pass; ruff, ruff format, mypy, tach and docs-check pass.
