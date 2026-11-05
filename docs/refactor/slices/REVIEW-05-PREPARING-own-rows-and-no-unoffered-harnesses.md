# REVIEW-05-PREPARING — 05 draws its own rows while preparing, names no harness nobody could choose, and 07b asks for a stored placeholder

**Status:** done, awaiting the PR. §173.5 and §172.6 amended; D-522, D-523.

## Why

Two defects on screen 05 Review Selection, both seen while installing a Collection:
- After Set later on 07, 05 showed one `[ ] None` per form row (around 22 for a Collection of MCP
  servers) for the minutes the Collection took to prepare. The shell beats over a frame drawn
  before it reloads the rows, and 05 drew `state.rows`, which were still 07's.
- Every install listed "claude is not offered for …" and "codex is not offered for …" when the
  Registry's artifacts run only on other harnesses, though neither was ever a choice.

## What was done

- `ConsumerScreenSource._body` and `_matrix_lines` (`aart_cli/tui_consumer.py`) draw 05 from
  `self.rows(state)`, and skip a row that is neither a matrix, installer nor target row.
- `_plan` says `PREPARING_INSTALL` ("Preparing the installation.") on 05 while an install is
  prepared and there is no plan or row yet.
- `_grouped_targets` (`aart_cli/consumer_actions.py`) no longer says which harness cannot host a
  Collection; `install_unhosted` is removed from the screens and its status lines.

## Evidence

- `tests/collection_inputs_tui_e2e_test.py`,
  `test_while_set_later_prepares_the_install_the_screen_names_no_form_row`: the real shell installs
  a Collection of two MCP servers with Set later on 07 and 07b, and keeps every frame the heartbeat
  would beat over. None says `None` or "not offered"; every 05 frame shows the Collection's matrix
  or that it is preparing; none says nothing is planned. Red before the fix, with the frame showing
  four `[ ] None` rows and the codex line.
- `tests/collection_install_tui_e2e_test.py`,
  `test_05_offers_the_collection_as_one_row_and_says_nothing_of_a_harness_it_cannot`.
- Focused: 1784 TUI, consumer, install, Collection, inputs and credential tests pass.

Targeted mutations, all killed by the new test:

| Mutation | Turned red |
|---|---|
| `_body` draws `state.rows` again | `test_while_set_later_prepares_the_install_the_screen_names_no_form_row` |
| `_matrix_lines` reads `state.rows` again | the same (it first survived; the test now claims the matrix is drawn) |
| drop the preparing branch in `_plan` | the same |
| a "not offered" line back in 05's status | the same |

## A stored placeholder is asked for again (D-523)

An MCP installed earlier with Set later held `AART_NOT_SET` in its Keychain item, and 07b counted a
present item as configured, so a later install into the same harness and scope never asked for the
credential. `_install_secrets` and `_ask_secret` (`aart_cli/consumer_actions.py`) now treat a
placeholder as unset: the row is asked, the store replaces the item, and `_forget_entered` stores
the placeholder back into an item that held one when the review is abandoned or the install fails.

Tests (`tests/install_credentials_test.py`, `_Keeping(placeholder=True)`):
- `test_a_placeholder_stored_before_this_review_is_asked_for_again`: both installations prompted,
  the placeholder item replaced and the other added;
- `test_a_row_every_installation_holds_as_a_placeholder_is_still_asked`;
- `test_leaving_07b_puts_back_a_placeholder_it_replaced`.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| `_install_secrets` ignores `placeholder` | `test_a_row_every_installation_holds_as_a_placeholder_is_still_asked` |
| `_ask_secret` skips a placeholder item | the first and the third test above |
| a placeholder item is stored, not replaced | the first and second test |
| `_forget_entered` deletes a replaced placeholder | `test_leaving_07b_puts_back_a_placeholder_it_replaced` |

## Found and left

The first Installing frame, before the first step is reported, says "Nothing has run yet." It lasts
only until the first step is reported, so it is not recorded in the backlog.
