# CP-30 — per-artifact installation flow

Status: **in flight**. Steps 1–2 are done on `feat/cp-30-install-flow-per-artifact`.

Date opened: 2026-10-16. Authority: the product owner (D-413, Product Specification §172). Their
requests, in order:
- harnesses chosen per selected artifact, on one screen;
- configuration entered once per artifact for all its harnesses;
- the scope chosen per artifact and harness pair, starting on the Settings default;
- credentials settled before installation, so a missing credential cannot break the install.

Every screen handles one or many artifacts. They then asked for entering inputs during installation
to be optional: skipped values become placeholders, set later one by one in Credentials and
variables.

## Design

- **The pair is the unit.** UI state and commands carry `artifact\tharness` pairs and
  `artifact\tharness\tscope` choices instead of one global harness set and one scope.
- **One draft, one transaction.**
  - The draft places each artifact per scope group, with that scope's root.
  - `McpTarget.scope` already exists, so a registry that routes each target to its scope root lets
    one transaction write both scopes.
  - A composite lock takes both scope leases in sorted order.
- **Answers per artifact.**
  - Config answer rows are `artifact\tinput_id`.
  - `consumer_actions` fans each one out to every owner of that artifact as an
    `OwnedInputSource`, so each installation still stores its own copy.
- **Placeholders.** A skipped input is stored as the literal `AART_NOT_SET`, for ordinary values and
  secrets alike. Nothing blocks on it: the install completes and the launcher starts. Doctor,
  Installed and Credentials and variables warn about it. A secret is matched through
  `find -w | grep -cx AART_NOT_SET` in child processes, so this process never reads it.
- **Secrets.**
  - A hidden prompt under terminal handover captures a `TransientSecret` per artifact secret,
    held by `LocalConsumerActions`.
  - The credential interpreter stores it, or the placeholder, per owner through `security -i` on
    stdin with `-X <hex>`, which keeps it off argv. Verified against a temporary keychain.
  - The transaction never prompts.

## Steps

See `plan.json` CP-30. Step 1 (spec and D-413) is done.

**2. One transaction over pairs.**
- `InstallationAssignment(artifact, harness, scope)` is what the draft is given. Each artifact
  is placed per scope group against that scope's root. A pair naming an artifact outside the
  selection, or an artifact with no pair, is refused by name.
- `ScopedHarnessRegistry` resolves each `McpTarget` against its own scope's root, and refuses a
  scope it has no root for. Prepare, complete and the whole-machine read use it. That read used
  to measure every installation against one root, so user-scope installations read as drifted.
- `CompositeMutationLock` takes every scope root's lease in sorted order, gives back what it held
  on refusal, and releases in reverse. `complete_configured_installation` uses it when the
  action's owners span both scopes.
- Remediation capabilities come from the paired harnesses.
- Evidence:
  - `tests/install_assignments_e2e_test.py` installs claude/project and opencode/user in one
    transaction. Both are `ready` with no drift, and nothing crosses roots.
  - `tests/scoped_installation_targets_test.py` covers routing, the refusal, and lock ordering as
    a Hypothesis property, plus the refusal rollback.
  - Mutations: a single-root machine read turns the e2e test red (`attention`/drift), and so
    does a single-root execution registry.
  - Focused: 838 tests in the install, harness, machine, consumer and credential modules.

## Step 3: the AART_NOT_SET placeholder (done)

- `domain/inputs.py` adds `SKIPPED_INPUT = "AART_NOT_SET"` and `is_skipped_value`. `validate_config_value`
  does not judge the placeholder, so a skip never fails a url, identifier or pattern rule.
- `CredentialObservation.placeholder` is a bool that is valid only on a PRESENT item.
- `MacOsKeychainProvider.holds_placeholder` prints the item into `grep -c -x -F AART_NOT_SET` in a child
  pipeline, and only the count returns. `inspect` reports a stored placeholder as PRESENT with
  `placeholder=True` and a "set it in Credentials and variables" detail. Nothing refuses it.
- Evidence:
  - `tests/skipped_input_placeholder_test.py` runs against a real temporary keychain: `AART_NOT_SET`
    reads as the placeholder; a token and `AART_NOT_SET_LATER` do not.
  - A Hypothesis property: only the exact `AART_NOT_SET` counts as skipped.
  - The structural no-material test now admits the `placeholder` field and pins it to `bool`.
  - Mutation: dropping `-x` from the comparison turns the `AART_NOT_SET_LATER` case red.
  - Focused: 418 tests in the credential, inputs, doctor, installed and runtime modules.

## Step 4: secrets written by the transaction, never asked for (done)

- `MacOsKeychainProvider.store` with a `TransientSecret` runs `security -i`. It writes one
  `add-generic-password … -X <hex>` command on stdin, with the account, service and keychain
  double-quoted and their `\` and `"` escaped. No value is on argv, so `store_exposure` is
  PRIVATE on both paths.
- `security -i` answered 0 for a failed command (a missing keychain), so a carried write counts
  only when `inspect` finds the item afterwards: "the Keychain write did not take". A refusal's
  stderr has the hex redacted.
- `CredentialEffectInterpreter(secrets=…, skipped_as_placeholder=…)`:
  - a Store or Replace with a carrier writes it without a prompt or the terminal;
  - a Store with nothing entered writes `AART_NOT_SET`;
  - a Replace with nothing entered leaves the item as it is and the run continues.
- Plumbed through `interpreters_for` and `complete_configured_installation`
  (`credential_secrets`, `skipped_secrets_as_placeholders`). `LocalConsumerActions` no longer
  runs the interactive prompt on install. It passes `_entered_secrets`, which step 8 fills from
  07b and which is cleared after each run, and it turns placeholders on.
- Evidence:
  - `tests/secrets_before_ready_test.py`: the value is not on argv and is hex on stdin; a write
    that did not take is a failure; a refusal does not echo the hex; the interpreter writes
    carried values, placeholders and keeps-on-replace with no handover. Against a real keychain,
    quotes, backslashes, spaces and non-ASCII survive in the value and the address, and a
    replacement through stdin holds `AART_NOT_SET`.
  - The `credential_lifecycle_integration_test` fake learned `security -i`, and its non-interactive
    test now pins the value off argv.
  - Mutations, each turning only its own test red: dropping the placeholder carrier, and dropping
    the quoting.
  - D-414 moves four tests from the install-time prompt to the new contract.
    `credential_guidance_test` keeps the guidance on screen 07 and now asserts no terminal loan
    and one `AART_NOT_SET` per installation. `credential_terminal_handover_test` asserts the install gets
    the carriers and not the loan, and that the carriers are not kept for the next install.
    `install_time_config_form_test`'s fake still refuses any material except the placeholder.

## Step 5: the 05 harness matrix (done)

- Screen 05 is a matrix: one row per artifact, one column per harness, and a cell is `[x]`, `[ ]`,
  or `–` where that artifact cannot go into that harness. With more than one artifact an
  "All artifacts" row comes first. Its cell ticks the column over the artifacts that can host it,
  clears the column when all of them are ticked, and draws `[~]` when only some are (D-416).
- ↑/↓ move between rows and ←/→ between harnesses; the cell Space acts on is marked `>`. The row
  string carries what each artifact can go into (`pairs:<coordinate>\t<harness,…>`), so the
  reducer stays pure and needs nothing from the plan.
- `ConsumerUiState.pairs` holds the choice as `<coordinate>\t<harness>` keys, and
  `ConsumerUiCommand.pairs` carries it to the install. `LocalConsumerActions` turns each pair into an
  `InstallationAssignment` at the plan's scope; step 7 replaces that single scope with one per pair.
  The plan records `chosen_pairs`, and execution refuses a plan prepared for a different set.
- `pair_choice_problems` keeps nothing silent: no tick at all; an artifact with no harness, naming
  the harnesses it can go into; a pair no longer offered.
- Found on the way: `key_event` raised on `left`/`right`, because `_SPECIAL_KEYS` did not list them.
  In the real TUI, an arrow key anywhere would have crashed the shell. They are listed now, and
  they mean nothing outside the matrix.
- Evidence:
  - `tests/harness_matrix_test.py`, 14 tests: the matrix rows, cell and All-row ticking, a
    Hypothesis property that every ticked pair is one the matrix offers and none repeats, the
    problems, the arrows on and off the matrix, and an e2e test. In the e2e test the MCP goes
    into claude and the Skill into opencode, and the receipts are exactly those two pairs.
  - `installation_harness_choice_test`, `install_time_config_form_test`,
    `python_installer_choice_test` and `post_install_mcp_test_test` now drive the matrix, choosing
    a harness with → where they used ↓. `tests/frame_contract.py` knows the `←/→` legend key.
  - Mutations: `_assignments` returning nothing turns only the two-artifact e2e test red. Dropping
    the arrows from `_SPECIAL_KEYS` turns the arrow test and the e2e test red.
  - 1823 related tests pass, along with ruff, ruff format and mypy.
- §172.2's default: an artifact only one harness can host has it ticked already
  (`default_pairs`).
  - `LocalConsumerActions` uses those pairs while 05 has none, and sends them back on
    `ACTION_PREPARED` (`ConsumerUiEvent.pairs`). The reducer adopts them, so the matrix and the
    plan agree and Continue works without a keypress.
  - Evidence: a scenario plus a Hypothesis property over random hosting, and an e2e test in which
    a claude-only Skill goes from `i` to Success with two Enters.
  - Mutation: dropping the adoption turns that e2e test red.
- Fixed on the way: the narrowed plan, the one prepared for the ticked pairs, dropped
  `scope_choice` and `installer_choice`, so no scope radio was drawn as chosen afterwards. This
  predates the matrix (checked on the stashed tree).
  - Now that the scope offer survives, `install_time_config_form_test`'s form goes back to 05 for
    the scope, as D-380 specifies, and needs one more Enter.
  - Evidence: `test_a_complete_choice_keeps_the_scope_it_offers`. Mutation: dropping
    `scope_choice=` turns it red.
  - 1827 related tests pass.

## Step 6: 07 asks once per artifact, with Set later (done)

- `application/installation_inputs.py` adds `ArtifactAnswer(source, artifact, input, value)` and
  `copy_artifact_answers(fields, answers, skip_unanswered=…)`. Each artifact's answer is copied
  into every new installation of that artifact and no other; a local and a remote alias are two
  artifacts. Set later fills unanswered ordinary fields with `AART_NOT_SET`. Secret fields are left to 07b,
  and answering one artifact twice is refused.
- Evidence: `tests/artifact_answers_copy_test.py` has scenarios plus a Hypothesis property: every
  installation gets its own artifact's answer, the placeholder, or nothing. Mutation: keying
  without the Registry alias turns the alias scenario and the property red. 93 tests in modules
  using `installation_inputs` pass.
- The 07 screen (D-417):
  - One field per artifact and input. The row is `<alias>/<kind>/<name>\t<input>`
    (`artifact_answer_key`), and `_offer_installation` turns each answer into an `ArtifactAnswer`
    for `copy_artifact_answers`. With more than one artifact, each group is headed by its artifact.
  - Set later is the first row, but the form opens on the first field. Enter on Set later keeps
    every value that is there and valid, a declared default included, and writes `AART_NOT_SET`
    into every other field. It then submits, so the placeholder travels as an ordinary answer and
    needs no flag on any command.
  - Secret rows stay per installation until 07b (step 8). Step 7 moved the scope to 07a (D-418).
- Evidence:
  - `install_time_config_form_test`, 18 tests:
    - one row for an artifact going into two harnesses, whose answer reaches both owners;
    - a group per artifact, with no heading for a single artifact;
    - the form opening on its field;
    - Set later keeping a default and skipping an empty and an invalid value;
    - an e2e test in which a cleared field plus Set later writes `github-org=AART_NOT_SET` into
      both installations' configuration files and completes.
  - `inputs_go_forward_test` now holds what D-380 promises: the harness matrix is never drawn
    again after the form. It had asserted that 05 never comes back, which held only while the
    scope offer was lost (fixed in step 5). Step 7 tightens it again.
  - `form_row_keys_test` walks the form's real rows.
  - Mutations:
    - Set later leaving blanks empty turns the two Set later tests red.
    - Keying fields by installation instead of artifact turns the two e2e tests and the
      re-preparation test red.
  - 2342 related tests pass, with ruff, ruff format, mypy and tach.

## Step 7: 07a, one scope per pair (done)

- The design is in D-418. The helpers in `consumer_views` are `scope_matrix_rows`,
  `scope_matrix_from_row`, `scope_matrix_columns`, `choose_pair_scope`, `default_pair_scopes`,
  `scope_choice_offered` and `pair_scope_key`/`pair_scope_from_key`.
- `ConsumerPlanView` carries `scope_offers` and `chosen_pair_scopes`. The state, the command and
  the event carry `pair_scopes`.
- In the adapter, `_pair_scope_offers` builds the per-pair offers. `_assignments` puts each pair
  at its own scope, and `_PendingInstall.chosen_pair_scopes` is compared at execution.
- `_after_inputs` routes 05 for a backend choice, then 07a, then Ready. The TUI does the same
  through `_after_configuration`.
- `configured_setup` reads each receipt's owner scope, so a mixed-scope install reports its setup
  instead of failing.
- Evidence:
  - `scope_matrix_test`, 11 tests:
    - rows and the All row;
    - the starting scope, kept and dropped;
    - the radio, with a Hypothesis property that every pair always holds exactly one offered scope;
    - Enter gated on the re-prepared plan.
  - `harness_matrix_test.test_each_pair_goes_to_the_scope_chosen_for_it_on_07a` is an e2e test.
    The MCP goes into the user home and the Skill into the project in one run, and the setup
    report raises no warning.
  - `install_scope_choice_test`:
    - the UI tests are rewritten for 07a;
    - 05 no longer draws a scope;
    - a scope chosen on 07a is where the files land;
    - a confirmation naming other pair scopes than the review is refused and writes nothing.
  - `inputs_go_forward_test` now also requires that the scope is asked on 07a and never as
    "Install into".
  - The frame matrix records 07a with two pairs: `screen_cases`, "07a:two-pairs".
  - `artifact_details_controls_test` read 05's harness rows as target rows. That has been broken
    since step 5, and the earlier filter missed it. It now reads the matrix columns.
  - Every install e2e test gains one Enter for 07a.
  - Mutations, each caught by the named test:
    - `_assignments` ignoring the chosen scope: the mixed-scope e2e and the files-land test.
    - `_receipt_scope` returning the session's scope: the mixed-scope e2e, through the setup
      warning it now checks. Before that assertion was added, this mutant survived.
    - The reducer not adopting `event.pair_scopes`: five tests.
    - Dropping the execution-time pair-scope comparison: the refusal test.
    - Dropping the 07a Enter gate: the gate test. The synchronous shell cannot observe this gate,
      so only the unit test holds it.
  - 2334 related tests pass (modules touching the consumer UI, views, actions or setup), with
    ruff, ruff format, mypy and tach. `make mutants` was not run over `consumer_views.py`: the
    module is large, and the targeted mutations above cover the slice's claims.

## Step 8: 07b, credentials before Ready (done)

- The design is in D-419. `consumer_views` adds `InstallSecretView`, `ConsumerPlanView.secrets`
  and `secrets_to_ask`, and puts 07b in the install flow when something is left to ask.
- `consumer_ui` adds the `ENTER_SECRET` and `DISCARD_SECRETS` commands, the `REQUEST_SECRET` and
  `SECRET_ENTERED` events, and `ConsumerUiState.entered_secrets`. `reduce_consumer_ui` emits the
  discard whenever a state with entries leaves 07b, Ready or Installing.
- In the adapter, `_install_secrets` builds the rows from the reviewed draft's bound inputs, one
  per artifact×input, with every installation's credential reference and its guidance.
  `_enter_secret` reads through the handover and keeps one carrier per reference;
  `discard_secrets` forgets them. `_after_inputs` and the TUI's `_after_scope` route to 07b.
- The TUI draws the rows with `render_install_credentials` and the status with
  `install_credentials_status`. `run_consumer_shell` dispatches the two new commands, and
  `ConsumerActionUpdate` accepts `SECRET_ENTERED`.
- Evidence:
  - `install_credentials_test`, 8 tests:
    - e2e: an entered value reaches the provider once for each of two installations, and appears
      in no frame and no file under the project or the AART home; the terminal is lent with a
      briefing and taken back;
    - e2e: Set later prompts nothing and stores the placeholder twice;
    - e2e: an empty answer is not an entry;
    - e2e: leaving 07b forgets the entry and nothing is stored;
    - unit: Enter on a secret row asks for that row only; Set later, Continue, an unknown row and
      another screen ask nothing; the answer marks and unmarks the row; Back discards and Ready
      keeps.
  - `credential_guidance_test`: a credential every installation holds does not draw 07b.
  - The frame matrix records 07b with two artifacts, one configured secret and one entry:
    `screen_cases`, "07b:two-artifacts".
  - Every secret-bearing install e2e test passes 07b with Set later.
  - Mutations, each caught by the named test:
    - A carrier for the first reference only: the two-installation e2e.
    - `discard_secrets` doing nothing: the leaving e2e.
    - `_after_scope` always going to Ready: all four e2e tests.
    - Every secret reported as not configured: the configured-credential test. Before its frame
      assertion was added, this mutant survived.
  - 1540 related tests pass (modules touching the consumer UI, views, actions, guidance or the
    shell drive), with ruff, ruff format, mypy and tach.

## Superseded work

- `stash@{0}`, "scope rows before the form (D-412 draft)", was the narrow fix for the missing scope
  rows. It is reference only; 07a replaces it.
- D-412 is used by the profile rename (PR #68), not by that draft.
