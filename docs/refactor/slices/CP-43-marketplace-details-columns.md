# CP-43 — Marketplace leads with Artifact and Type; `d` shows the other columns

Status: **in progress**, on `feat/cp-43-marketplace-columns`, after a colleague's report
passed on by the owner (2026-10-23). Authority: Product Specification §196, INV-297, D-480.

## Steps

See `docs/refactor/plan.json`, epic CP-43.

1. Artifact is `name@version` and Type is a column; `d` toggles the details for the session. Done.
2. Existing column tests read the details; user documents and the manual walkthrough say so. Done.
3. Focused verification, targeted mutations and the PR. Verification and mutations done; the PR
   waits for the owner.

## Why

Marketplace drew seven columns for every offer: Artifact (`kind/name@version`), Registry, Upstream,
Status, Scope, Harnesses, Configuration. A colleague found it overwhelming to read and to move
through. The owner asked for the name and version, a Type column, and the rest behind a key of its
own, separate from Verbose, and hidden by default.

## Change

- `aart_cli/application/consumer_views.py`:
  - `OFFER_TYPES` names each kind, plus `Collection`;
  - `offer_cells(key)` gives the Artifact, Type and Registry cells;
  - `marketplace_cells` leads with them.
- `aart_cli/tui_marketplace_rows.py`:
  - `_HEADINGS` gains Type after Artifact;
  - `render_marketplace_rows(..., details=)` draws the first two columns or all of them;
  - after the owner saw a lab row wrap (`team-glossary@1.0.` / `0`), every offer is one line and
    the stacked form is gone:
    - `_fit` and `_sizes` narrow the detail columns widest-first down to their headings;
    - a column with no room is left off whole, from the right;
    - Type is left off before Artifact narrows;
    - `_cell` cuts a value with `…`;
    - the list ends with "Widen the window to see: …" naming the columns left off;
    - headings and rule are drawn even with no offers.
- `aart_cli/application/consumer_ui.py`:
  - `ConsumerUiState.marketplace_details` (default off);
  - `TOGGLE_MARKETPLACE_DETAILS`;
  - `d` on Marketplace as `Details` / `Hide details`, of which only the one that changes something
    is enabled;
  - the toggle resets Marketplace paging, as `v` does.
- `aart_cli/tui_consumer.py`: Marketplace passes the state's choice to the renderer. Collection rows
  use `offer_cells`.
- `docs/using/consumer-lifecycle-v1.md` and `docs/testing/TUI_MANUAL_WALKTHROUGH.md` describe `d`.

## Tests

- `tests/marketplace_details_columns_test.py`:
  - each kind's Artifact and Type cells, and the heading order;
  - without details, a grid draws exactly Artifact and Type in each row (Hypothesis);
  - with details, every column follows in order (Hypothesis);
  - the stacked form labels only Artifact and Type;
  - the footer offers `Details`, then `Hide details`;
  - any number of `d` presses toggles and leaves rows, cursor, selection and search alone
    (Hypothesis);
  - `d` while searching is a letter;
  - the choice survives leaving Marketplace and coming back;
  - `d` means nothing on Installed;
  - the production application opens Marketplace with two columns and `d` adds the details.
- `tests/marketplace_one_line_test.py` holds these over generated rows, at every width from 14 to
  260 columns, with and without details (Hypothesis):
  - an offer is one line and no line passes the window;
  - drawn headings are whole, and each cell is whole or a cut beginning marked `…`;
  - Artifact is whole while any other column is drawn;
  - a wider window never shows fewer columns;
  - the list names exactly the columns left off;
  - a window as wide as every value cuts nothing.
  The owner's rows, at 60, 80, 100 and 130 columns, keep `team-glossary@1.0.0` whole on one line.
  A value cut just after a space (`claude, opencode` → `claude,…`) still fills its column, so the
  next column stays under its heading. The lab showed that misalignment before it was fixed.
- Updated to read the details or the new cells:
  - `marketplace_readable_rows_test.py` (wrapping and stacking replaced by cutting and leaving
    off), `marketplace_upstream_columns_test.py`,
    `marketplace_configuration_column_test.py`, `marketplace_columns_e2e_test.py`;
  - `marketplace_list_window_test.py` and `marketplace_heading_rule_test.py`, whose properties now
    hold for both forms;
  - `marketplace_cursor_description_test.py`, `consumer_application_e2e_test.py`,
    `consumer_text_terminal_test.py` and `consumer_marketplace_shell_test.py`, whose drawn rows
    are now `name@version  Type`.
- Focused run over every test file that names Marketplace or key bindings (90 files): all pass but
  the two `screen_skeleton_test.py` properties that fail on `main` too (B-226).
- Lab check: in `lab42`, the real application drew Marketplace with Artifact and Type. `d` added
  the six columns and `d` again removed them.

## Targeted mutations

| Mutation | Red |
|---|---|
| Marketplace draws with `details=True` whatever the state | the application test, three shell tests |
| Both `d` bindings enabled | footer test, toggle property |
| Type cell is the raw kind | each kind's cells, the application test, three shell tests |
| Three columns without details | both brief-form tests, the rule property, the application test, three shell tests |
| `d` always hides | toggle property, the application test |
| A value is never cut | cells whole or marked cut; the narrow-window example |
| Artifact narrows with the details | Artifact whole while another column is drawn, and three narrow-window examples |
| No line under the list for columns left off | names the columns left off, and four examples |
| A cut cell is not padded to its column | the cut-at-a-space example |
| A column that does not fit is narrowed below its heading rather than left off | headings whole, the hint, the rule property, and five examples |
