# CP-45 — Credentials and variables from the command line; Installed reads like Marketplace

Status: **steps 1–6 done**, on `feat/cp-45-cli-inputs`, from `main` at 0.18.0, at the owner's
request (2026-10-26). Authority: Product Specification §172.6, §198–§201, INV-299–INV-302,
D-483–D-487.

## Steps

See `docs/refactor/plan.json`, epic CP-45.

1. `consume inputs list|set|set-credential`, through the TUI's own consumer actions, with the
   inputs projection shared in `application/credentials_and_variables.py`. Done.
2. Installed and Updates on Marketplace's grid: four brief columns, `d` for the details, cut rather
   than wrapped, More info for the row under the cursor. Done.
3. The footer names the aart-cli version beside the launch directory. Done.
4. Focused verification, targeted mutations, documents. Done.
5. `consume install` hands the terminal to the credential store, and `--secret-env` is removed
   (B-236, the owner's choice). Done.
6. The TUI's 07b marks which credentials the store asks for while installing, and reads none
   (B-237, D-487, the owner's "wariant 2"). Done.
7. Commit, push, PR and release, at the owner's request.

The owner's run, in a real terminal, of `set-credential --yes`, of `consume install --yes` for an
artifact with a credential, and of 07b's marked install, is still theirs: the macOS `security`
prompt cannot be driven here.

## Why

The owner's requests, in order:

- An agent should configure an installed artifact without the TUI, with code shared with the TUI.
  The owner's rule: an agent may at most run, or give a person, the command that passes a
  credential safely to the store, as the TUI does. The process never reads the value.
  Configuration values may be pasted to an agent, because they are not credentials.
- Installed should read like Marketplace, with More info and less info under the cursor and
  sensible text in the columns.
- Configuration and credentials logic should be one module that the TUI and the CLI both import,
  checked with tach.
- The TUI should show its version near "working at".
- Then, on B-236: "zrobić tak, żeby install też oddawał terminal promptowi Keychaina".
- Then, on B-237: 07b should do the same, with the store's prompt during the transaction
  ("wariant 2").

## Change

- `aart_cli/cli_parser.py`, `aart_cli/model.py`, `aart_cli/cli.py`:
  - `consume inputs list [COORDINATE…]`, `set COORDINATE INPUT=VALUE` and
    `set-credential COORDINATE INPUT`;
  - the flags are `--harness`, `--scope`, `--project`, `--yes`, `--expect` and `--json`;
  - `cli.main` routes `inputs` before `DISPATCH`, because `commands` may not import `tui`
    (`tui_dispatch_test`).
- `aart_cli/cli_inputs.py` (new):
  - The three actions over `LocalConsumerActions.handle` PREPARE/EXECUTE. `set` is CONFIGURE with
    one answer for one harness. `set-credential` is CREDENTIAL_SET or CREDENTIAL_REPLACE on the
    reference.
  - Review prints the review digest. `--yes --expect` executes only that change.
  - Without a TTY, `set-credential` refuses before touching the store.
  - Every refusal is `consumer-inputs-refused` with a remediation, and no refusal repeats a value.
- `aart_cli/tui.py`: `_canonical_consumer_actions(..., credential_providers=, handover=)`. The CLI
  injects the providers tests replace, and a `BriefingHandover` on stderr.
- `aart_cli/application/credentials_and_variables.py` (new, read by the TUI and the CLI):
  - `installation_parts`, `InstallationSelector` and `select_installations` (the whole name);
  - `configuration_identifiers`, `ConfigurationValue`, `InstallationInputs` and
    `installation_inputs`;
  - `credential_state` and `credential_setting`.
- `aart_cli/application/consumer_views.py`:
  - `PLACEHOLDER_STATE`;
  - `installed_row_cells` and `installed_collection_cells`, built from `offer_cells`.
- `aart_cli/application/consumer_ui.py`:
  - `TOGGLE_DETAILS` replaces `TOGGLE_MARKETPLACE_DETAILS`;
  - the new state field `installed_details` and `details_shown(state)`;
  - `d` Details or Hide details on Installed and Updates.
- `aart_cli/tui_marketplace_rows.py`:
  - `ColumnLayout` and `render_columns(layout, rows, ..., indents=)`, with the fitting rules
    parameterized by layout;
  - `render_marketplace_rows` is now that grid with Marketplace's layout.
- `aart_cli/tui_consumer.py`:
  - `_INSTALLED_COLUMNS`, and the Installed and Updates branch now uses `render_columns`;
  - More info is `installed_description` and `installed_collection_description`;
  - the caption is `working at DIR · aart-cli X.Y.Z`;
  - `_installed_name`, `_INSTALLED_HEADINGS` and the local `_configuration_identifiers` are gone.
- Step 5 (§201, D-486):
  - `aart_cli/io/terminal_briefing.py` (new): `BriefingHandover` and `terminal_present`.
    `tui._CursesHandover` subclasses it and adds lending the drawn screen.
  - `application/command_line_inputs.py`: `resolve_command_line_inputs(fields, values)` has no
    secrets argument. A credential named by `--input` is refused with `CREDENTIAL_REMEDIATION`.
    `secret_references(unanswered, provider=)` gives one item per installation, and
    `missing_input_flags` gives no flag for a credential. `secret_variables` is gone.
  - `commands/marketplace.py`:
    - `_unanswered_credentials` and `_asked_by_the_store` (with D-263 guidance);
    - `review.asked_by_credential_store` and its text lines;
    - the no-terminal refusal before execution;
    - `interactive_credentials` and a `BriefingHandover` on stderr when the store will ask;
    - the no-store refusal names the credentials.
  - `--secret-env` is removed from `cli_parser.py`, `model.py` (`install_secret_envs`) and
    `cli.py`.
- `tach.toml`:
  - the new module `aart_cli.cli_inputs`;
  - `aart_cli.cli` depends on it;
  - `aart_cli.tui_consumer` depends on `aart_cli.runtime_contract`.

## Evidence

- `tests/command_line_credentials_and_variables_test.py` (10 tests) covers:
  - `list`, as text and JSON, and narrowed by coordinate and harness;
  - `set`: review, a mismatched `--expect` refused, then applied, with the other harness
    unchanged;
  - the service path recorded at `LocalConsumerActions.handle`;
  - a credential never taken as an argument and never echoed;
  - ambiguous and unknown installations;
  - `set-credential`: the store prompts and no value is carried, refused without a terminal, and an
    ordinary input or an `=` value refused;
  - a Hypothesis property: a selector picks exactly the installations it names.

  Every test patches `marketplace._credential_providers`, so no test touches the real Keychain.
- `tests/installed_column_headings_test.py` (10 tests) covers:
  - the headings sit over their cells, with details and without;
  - members indented under their Collection;
  - one line within a narrow window;
  - `d` on Installed and Updates, separate from Marketplace's choice (Hypothesis);
  - More info: harness, scope, whole root, health with the update, each input's value or state;
  - a Collection's More info;
  - a Hypothesis property: every row one line within the window, members indented, at any width
    and either details choice.
- Updated to the new rows:
  - `collection_installed_e2e_test`, `consumer_application_e2e_test`,
    `consumer_session_e2e_test`, `consumer_shell_test`;
  - `installed_multi_uninstall_e2e_test`, `marketplace_columns_e2e_test`,
    `marketplace_details_columns_test`.
- Updated to the caption: `workspace_context_line_test`, `screen_trail_test` and
  `screen_block_structure_test`.
- Focused run: 1063 passed across the TUI, Installed, Marketplace, Collection, credential and
  screen suites. The two pre-existing `screen_skeleton_test` properties stay deselected (B-226).
  `make typecheck` and `tach check` are green.
- Lab (`lab44docs`, isolated keychain) ran `list`, the `set-credential` review, the refusal without
  a terminal, and `set tracker-user=alice`. That last run changed the lab's `tracker-user` from
  `AART_NOT_SET` to `alice`.

- Step 5:
  - `tests/command_line_inputs_test.py` (8 tests) covers:
    - an answer belonging to its artifact on every harness;
    - each mistake refused by name, never echoing the value;
    - a credential given to `--input` sent to the store, with `set-credential` named;
    - one reference per installation and none for an ordinary input;
    - no flag for a credential.
  - `tests/command_line_inputs_e2e_test.py` (5 tests, over the real install path with a fake store
    that "prompts" by making up its own value) covers:
    - the review naming the credential with its guidance and writing nothing;
    - `--yes` without a terminal refused, with nothing written;
    - `--yes` in a terminal, where the store's prompt stores the value, the briefing reaches stderr
      before it, and the value is in no file;
    - `--set-later` asking nothing;
    - each mistake refused before anything is written, with no value echoed.
  - `credential_guidance_test::CommandLineGuidanceE2ETest` holds the review's guidance to the TUI's
    words (D-263). It now patches `_credential_providers`, so it no longer depends on the platform.
  - `git_backed_runtime_e2e_test`: the refusal without a terminal names the credential, with a fake
    store.
  - The step-2 grid also changed two test files that the step-2 run had missed:
    - `artifact_installation_e2e_test` now looks for `name@version`;
    - `installation_changed_where_made_lab_e2e_test` presses `d` and finds a row by the start of its
      cut Project cell.
  - Focused run: 1651 passed across the TUI-related, install, credential, parser and handover
    suites (168 files), with the 7 failures above then fixed and rerun green.
- `tests/credentials_and_variables_test.py` (7 tests) holds the shared module on its own:
  - a key splits back into its parts whatever the root holds (Hypothesis);
  - a bare coordinate;
  - identifiers a file holds without declaring;
  - each value's file, state and documentation;
  - which file a value is read from;
  - every credential state in words;
  - set, replace, or nothing for an unknown.
- `make mutants ONLY=aart_cli/application/credentials_and_variables.py`, with that file and the two
  above. The first run killed 58 of 80. Its survivors were a bare key, identifiers held but not
  declared, the file, state and documentation fields, the other credential states, and
  `credential_setting` with no action. They became the tests above, and the dead
  `.replace("-", " ")` in `credential_state` was removed: no `CredentialState` value has a hyphen.
  The second run killed 73 of 74. The survivor is `partition("@")` → `rpartition("@")` in
  `select_installations`, which is equivalent because a coordinate has one `@`. The three property
  tests suppress `HealthCheck.differing_executors`, as the repository's others do, so mutmut's
  stats run can call them.

- `make mutants ONLY=aart_cli/application/command_line_inputs.py` with
  `tests/command_line_inputs_test.py` and `tests/command_line_inputs_e2e_test.py` killed 131 of
  150. The step-5 survivors:
  - the credential flag starting `True`, which attached the store remediation to every refusal;
  - `continue` → `break`, which stopped at the first unknown artifact.

  Both became `test_every_mistake_is_said_at_once_and_only_a_credential_sends_you_to_the_store`,
  and both are now red. The flag starting `None`, and the `None` → `""` value in `missing_input_flags`'
  ordered set are equivalent. The parser and `declared_defaults` survivors predate CP-45 (B-238).
  The parser property suppresses `HealthCheck.differing_executors` so mutmut can run it.

## Targeted mutations

Run with `PYTHONDONTWRITEBYTECODE=1 python -B`, and each restored file is touched.

| Mutation | Red |
|---|---|
| `set-credential` skips the terminal check | without a terminal nothing changes |
| `set` accepts a credential input | a credential is never an argument |
| `--expect` ignored | set reviews then changes one value |
| More than one match tolerated | an ambiguous installation is refused |
| A coordinate matches by prefix | the selector property and `list` narrowing |
| A member's indent ignored | headings over cells, the grid property, the Collection end to end |
| Installed follows Marketplace's details choice | `d` toggles Installed and leaves Marketplace alone |
| The Harness cell left empty | headings over cells, the Marketplace and Installed end to end |
| Installed details always drawn | without details a row is what it is |
| The project root dropped from More info | the installation said whole |
| A credential's state dropped from More info | each input named with its value or state (added after this mutation first survived) |
| The version dropped from the caption | the caption tests |
| `install --yes` skips the terminal check | without a terminal nothing is written |
| `interactive_credentials=False` | in a terminal the store asks (the run ends `partial`) |
| A credential accepted from `--input` | the unit refusal and the end-to-end mistakes |
| The review's guidance emptied | the review names the credential, and the CLI guidance test |
| `--set-later` still asks the store | set-later stores the placeholder |
| The no-store refusal names no credential | the end-to-end mistakes |
| 07b's Enter never unmarks | Enter twice leaves the row unmarked |
| The install prompts for nothing | the store asks for the marked token, end to end |
| The interpreter ignores the marks | the transaction asks only for what was marked, and its property |
| Set later keeps the marks | Set later forgets every mark |
| The terminal is not lent for a marked install | an install lends the terminal only for what 07b marked |
| The row state never says asked | 07b's row says asked when installing |
| Ready silent about what the store asks | Ready lists the asked credentials |

Step 6 was verified with 170 related test files, 1672 passed (`screen_skeleton_test` deselected,
B-226). `make mutants` was not run on `io/execution.py`: the module is too large for a scoped run
to finish in a reasonable time, and the seven mutations above cover the change.

## Left for later

- B-235: deleting a retained credential from the CLI needs an address for a reference no
  installation names.
- B-236 is done in step 5.
- B-237 is done in step 6.
