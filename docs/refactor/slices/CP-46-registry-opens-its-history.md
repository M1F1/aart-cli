# CP-46 — Only the Registry here opens, and its commands are there

Status: **steps 1–11 done; step 12 (the owner's lab run and the PR) open**, on `feat/cp-46-registry-context`, from `main` at 0.19.0, at the owner's
request (2026-10-27). Authority: Product Specification §202–§210, INV-303–INV-315, D-488–D-498.

## Steps

See `docs/refactor/plan.json`, epic CP-46.

1. Screen 46 keeps each Registry to a few lines and acts on nothing. Only the Registry here,
   marked, opens as screen 46k, with its checkout's promotions and every command acting on it.
   Done.
2. A running action beats, and `consume mcp test` reads generated schemas (§203). Done.
3. Test MCP finds an installation where its key says, and a failed test names the error (§203
   addendum, D-491). Done.
4. A secret may declare its length; a value of another length is not configured, and a value the
   Keychain prompt cut is entered another way (§204, D-492). Done.
5. Focused verification, targeted mutations, documents. Done.
6. `consume mcp test` reads every schema FastMCP generates, checked against mcp-atlassian 0.23.1
   and 0.21.1 (§205, D-493). Done.
7. Every screen taller than the terminal scrolls (§206, D-494). Done.
8. A credential is entered on 07b: Enter opens the store's prompt there, the install is prepared
   again, and what was entered is deleted when the install is abandoned or fails (§207, D-495).
   Done.
9. Uninstall deletes the credentials of exactly the installations it removes (§208, D-496). Done.
10. Scope is chosen before configuration and credentials: 05, 07a, 07, 07b, Ready (§209, D-497).
    Done.
11. Installed shows by default what this context reaches: user installations and this project's;
    `a` shows every project's (§210, D-498). Done.
12. The owner's run in the lab, and the PR.

## Why

The owner: with a large font, one Registry with its promotion history pushed another Registry off
the screen, which was hard to read. The Recent promotions should show once a Registry is entered,
and Candidates, Initialize, Rebuild, Scan repository, Check upstream and Collections should work
there too.

Testing the first version in the lab, the owner asked for every command to be possible only inside
a Registry, and then set the rule (D-489): only the Registry whose checkout aart-cli runs in can be
entered, any other says to run aart-cli there, and the Registry here is marked. The first version
had offered the commands on every subscribed Registry, where they still acted on the checkout.

The owner also asked for a sign that an install is still working, and for the fix to an enterprise
report: `consume mcp test` refused a working fastmcp server with `unsupported JSON Schema keyword
'minimum' at $.limit` (D-490).

Then the owner reported that Test MCP in the TUI did nothing visible, and pasted
`…#opencode#user#/Users/… has no recorded MCP installation to test` (D-491). The same enterprise
report showed `jira-api-token` stored as 128 characters, about 60 short. The owner chose an
optional length check in the manifest and a modular fallback, a macOS dialog then Keychain Access
instructions, testable in CI with fakes (D-492).

Then (2026-10-28) `jira_get_issue` was still refused over `pattern`, and the owner asked for aart-cli
to work with FastMCP and with sooperset's mcp-atlassian exactly (D-493). Testing a collection of
many MCPs, the owner found that the install screens did not scroll, so most configuration and
credential rows, and the end of the summary, could not be seen; every long screen should scroll.

## Change

- `aart_cli/application/maintainer_views.py`:
  - `MaintainerViews.registry_here`, the Registry in the directory aart-cli runs in;
  - the navigation from 46 is Initialize and 46k only. 46k navigates to Candidates, Bulk
    Promotion, Rebuild, Scan Repository, Check upstream, Push and Collections.
- `aart_cli/io/maintainer_views.py`: `_registry_here` reads the checkout as its own approved state,
  so promotions not pushed yet are in its history. Versions approved under another name are given
  the checkout's name.
- `aart_cli/application/consumer_ui.py`:
  - 46 binds only `n` Initialize, offered while no row is the workspace;
  - 46k binds `c`, `b`, `s`, `u`, `p` (when ready) and `o`;
  - the workflow routes for Bulk Promotion, Collections, Rebuild and Scan start at 46k, and Push
    is prepared from 46k;
  - `_back_focus`'s 46k rule and the Collections gate are removed.
- `aart_cli/tui_maintainer.py`:
  - `HERE` (`● you are here`) ends the workspace row;
  - `render_maintainer_registry(..., brief=True)` is a list row, and `named=False` drops the alias
    line where the workspace row already names it;
  - `maintainer_registry_status(..., listed=True)` says to open the Registry here.
- `aart_cli/tui_consumer.py`:
  - Enter opens 46k only on the workspace row. Another row's status says to run aart-cli in its
    checkout, or, for the subscription with the same name, points to the marked row;
  - 46k is the workspace row and the Registry here's full block, titled `This Registry`;
    Collections (51, 52) are the Registry here's;
  - `Heartbeat` and `heartbeat_frame` beat over PREPARE_ACTION and EXECUTE_ACTION, and
    `_progress_redraw` hands the heartbeat each reported frame.
- `aart_cli/tui.py`: `_CursesTerminal` and `_CursesHandover` share a lock. `tick` draws only on a
  non-blocking acquire, so no beat lands on a credential prompt.
- `aart_cli/application/mcp_smoke.py`:
  - applies the bounds, `anyOf`/`oneOf`/`allOf` and a list of types;
  - passes over `format`, `contentEncoding`, `contentMediaType` and `x-` keywords;
  - still refuses `pattern` and `$ref`, inside a branch too.
- `aart_cli/consumer_actions.py`:
  - `_prepare_installed_mcp_test` reads records per scope and root named by each key;
  - `_why` names the error in the three MCP test notices;
  - `_PendingCredentialAction.length` comes from the installed secret inputs.
    `_execute_credential_action` passes it and the fallbacks to the interpreter, and fails by name
    while the value is still the wrong length.
- `aart_cli/domain/credentials.py`: `CredentialLength`, `CredentialCheck`, `checked_observation`.
  `CredentialObservation.length` and `clipped`.
- `aart_cli/domain/inputs.py`: `SecretInput.validation`, written by `input_to_data` only when
  declared. `aart_cli/protocol/authoring.py`: `_parse_credential_length`.
- `aart_cli/domain/receipts.py`: `InstallationReceipt.credential_checks` and `credential_length`.
  `aart_cli/application/installation_proposal.py`: `PlannedInstallation.credential_checks`, written
  by `intended_receipt`.
- `aart_cli/io/credentials.py`: `inspect` sets `length` and `clipped`.
  `aart_cli/io/consumer_machine.py`: each receipt's checks are applied to what the provider reports.
- `aart_cli/io/credential_entry.py` (new): `EntryOutcome`, `CredentialEntryFallback`,
  `MacOsDialogEntry`, `dialog_script`, `KeychainAccessInstructions`, `enter_another_way`,
  `default_entry_fallbacks`.
- `aart_cli/io/execution.py`: `CredentialEffectInterpreter` takes `lengths` and `fallbacks`. After
  storing, within the loan, it runs the chain and inspects again.
- `aart_cli/io/installation_execution.py`, `aart_cli/io/configured_installation_action.py`: carry
  the lengths and the chain. `aart_cli/tui.py`, `aart_cli/commands/marketplace.py`
  (`_credential_entry`) and `aart_cli/cli_inputs.py` compose the real chain.
- `aart_cli/application/credentials_and_variables.py`: `credential_state` says `Not configured: …`.
  `aart_cli/commands/doctor.py` says `… is not configured: …` and reads stores through
  `marketplace._credential_providers`.
- `docs/examples/author-source/example-mcp/aart-cli.yaml` shows a secret's `validation`.
- D-494 (§206): `aart_cli/tui_layout.py` gains `Viewport`, `scroll_window` and `screen_viewport`.
  `aart_cli/tui_marketplace_rows.py` `marketplace_viewport` uses `scroll_window` and returns a
  `Viewport`. `aart_cli/application/consumer_ui.py` replaces `marketplace_scroll` and
  `SCROLL_MARKETPLACE` with `scroll`, `scroll_follows`, `scrollable`, `SCROLL` and
  `_KEEPS_THE_PAGE`; page keys scroll every screen, and the legend offers them only when the screen
  pages. `aart_cli/tui_consumer.py` `viewport()` picks the paging, `frame()` draws it, and the shell
  loop stores the clamp and whether it paged.
- D-495 (§207): `aart_cli/consumer_actions.py` `_ask_secret` runs the install's own
  `CredentialEffectInterpreter`s (from `interpreters_for`) for the row's references, Store or
  Replace, checks each item with `unfit`, and prepares the install again from `_install_command`.
  `_entered` and `_forget_entered` replace `_asked_rows`; `discard_secrets` and a failed install
  delete, success releases. The install no longer lends the terminal. `aart_cli/io/execution.py`
  makes `unfit` public. `aart_cli/application/consumer_ui.py` takes the new review identities from
  `SECRET_ASKED`, labels `Enter value`/`Enter again`, and Set later no longer discards.
  `aart_cli/tui_consumer.py` words 07b's rows and status and Ready's block.
- D-496 (§208): `aart_cli/io/configured_uninstall_action.py` `prepare_configured_uninstall` drops
  `delete_credentials` and plans each record's deletion unless it is retained.
  `aart_cli/commands/marketplace.py` reviews `"credentials": {"deleted": [...]}` and says it in
  text. Docstrings in `removal_proposal.py` and `installed_state.py` no longer call retention the
  rule.
- D-497 (§209): `aart_cli/application/consumer_views.py` reorders `install_flow_screens` and
  `_NAVIGATION`. `aart_cli/tui_consumer.py` adds `ConsumerScreens.install_scope_offers` (07a's
  rows before any plan), `_after_harnesses` replaces `_after_configuration`, and 07 leads to 07b or
  Ready. `aart_cli/consumer_actions.py` returns the form with the pairs' scope rows and their
  `pair_scopes`; `_after_inputs` no longer leads to 07a. `aart_cli/application/consumer_ui.py`
  opens the form from 07a, accepts a form event on 07a keeping typed fields by row, and resets
  `harness_column` when 07a is entered (B-195).
- D-498 (§210): `aart_cli/application/consumer_views.py` `reached_from`. `aart_cli/tui_consumer.py`
  adds `ConsumerScreens.project_root`, `reached`, `collections_reached`, Installed's and Updates'
  rows from them, `_reach_status`, Home's counts recounted in `screens_from`, and the shell re-reads
  rows after `a`. `aart_cli/application/consumer_ui.py` adds `installed_everywhere`,
  `TOGGLE_EVERYWHERE` and the two `a` bindings. `aart_cli/consumer_actions.py` passes
  `host.project_root`.

## Evidence

- `tests/registry_opens_its_history_test.py` (23):
  - the list names no promotion; the Hypothesis length property; list Verbose; the mark once;
  - the list offers and takes no command on any row;
  - another Registry does not open and says where to run, and the same-name subscription points to
    the marked row;
  - Initialize only without a workspace;
  - Enter opens `AART / Registry / This Registry` with the checkout's promotions, also in Verbose;
  - `c`, `b`, `s`, `u` and `o` are offered on 46k, `n` is not, and `p` only when ready;
  - `o` shows the Registry here's Collections, Enter opens Bulk Promotion, Esc returns;
  - read from a real git checkout, `registry_here` carries its transactions.
- `tests/running_heartbeat_test.py` (10):
  - a Hypothesis property on the beaten heading;
  - the mark turns;
  - beats stop when the action returns, follow `show`, and leave a terminal without `tick` alone;
  - the shell beats over the step reached during a slow install;
  - `tick` is skipped while the lock is held, and the handover holds it for the whole loan.
- `tests/mcp_smoke_schema_bounds_test.py` (11): Atlassian's `jira_search` input and fastmcp-wrapped
  output; bounds (with a Hypothesis property on `minimum`); a list of types; branches; any `x-`
  keyword (Hypothesis); `format`; `$ref` refused. `mcp_smoke_evaluation_test.py` now uses `pattern`
  for the unsupported case.
- `tests/installed_mcp_test_e2e_test.py` (+3, D-491): a user installation is reviewed and run
  from a project; a run and a plan that raise name the error in the failure.
- `tests/credential_length_test.py` (31, D-492):
  - `CredentialLength.failure` against both bounds (Hypothesis), the message, refused bounds;
  - `checked_observation`: the wrong length is invalid with why, a fitting one is untouched
    (Hypothesis), the placeholder and an unmeasured value are not judged;
  - authoring accepts `validation` on a secret and refuses every other shape by name;
    `input_to_data` and the receipt keep it, and a secret or receipt without one reads as before;
  - the Keychain inspection measures the length and marks 128 bytes as clipped, reading no value;
  - the interpreter asks another way for a declared misfit or, with no declaration, a clipped
    value, asks only the first way that can, and says why a value is still invalid;
  - the dialog script carries no value, keeps any service name inside a JSON literal (Hypothesis)
    and writes hex to `security -i` on a pipe; osascript's answer and its absence; the
    instructions and how they are left.
- `tests/credential_length_e2e_test.py` (4, D-492): through the CLI with a store whose prompt
  cuts at 128, an install asks the other way and keeps the whole value; a value left cut is not
  configured in doctor (JSON and text) and `consume inputs list`; `set-credential` fails by name
  and then succeeds; a fitting value asks nothing.
- `author_skeleton_test.py`: the generated skeleton's secret carries a length `validation`, since
  the parser now accepts one there. `doctor_configuration_credentials_e2e_test.py` admits
  `length` and `clipped` to the observation, typed as a count and a yes/no.
- `tests/mcp_smoke_fastmcp_compatibility_test.py` (25, D-493), over `tests/fixtures/mcp/`:
  - for every tool of mcp-atlassian 0.23.1 (98) and 0.21.1 (73) and every FastMCP 3.4/2.14 shape,
    a call filling every property is allowed and a fitting answer passes (368 subtests);
  - `jira_get_issue`'s key: valid keys allowed, six wrong ones refused by pattern, and a Hypothesis
    property against the pattern;
  - `pattern` searched, ECMA `$`, only on strings, unreadable ones refused;
    `additionalProperties` as a schema, `propertyNames`, `patternProperties`, `prefixItems`;
  - `$ref` followed, at every depth of a recursive model, and refused when unresolved, circular or
    remote; a tagged union decided by its branches;
  - numbers with a fraction exact, whole ones integers (also beyond 64 bits), non-finite refused,
    a Hypothesis property on `minimum` over written decimals, and the preview showing `0.25`.
- `mcp_smoke_stdio_test.py`: a refusal is said alone, without the server's stderr banner.
  `mcp_smoke_schema_bounds_test.py` and `mcp_smoke_evaluation_test.py` now use `not` for the keyword
  still refused, and a remote `$ref`.
- 19 MCP-related test files: 293 passed, 444 subtests passed.
- Live (local, D-493): aart-cli's `execute_stdio_smoke` against the real mcp-atlassian 0.23.1 and
  0.21.1 with a stand-in Jira Server: `jira_search`, `jira_get_issue`, `jira_get_project_issues`
  PASS; `proj-1` refused by pattern. The FastMCP shapes server PASSes, reading `0.25` exactly.
- Updated to the new screens:
  - legend, form drafts, workflow progress, rebuild, adoption, push, terminal return and failed
    action start at 46k;
  - `collections_registry_choice_test.py`: `o` only inside the Registry here;
  - `registry_workspace_lifecycle_test.py`: the mark, Enter opens 46k, the accepted snapshot on the
    subscription's row;
  - the collection editor and search fixtures set `registry_here`;
  - `maintainer_composition_e2e_test.py`: the project is the subscribed Registry's checkout with
    its marker, published as the baseline, and one more Enter before `o`.
- 103 affected test files, each run on its own: all pass except `screen_skeleton_test`'s two stored
  Hypothesis examples, which fail at `v0.19.0` too (B-226). Together, without it: 1155 passed, 1842 subtests passed.
- With D-491 and D-492, the 104 CP-46 files and the 164 credential and MCP files together (240):
  2592 passed, 2809 subtests passed; the only failures are B-226's two stored examples.

- D-494: `tests/screen_scrolling_test.py` (16): the viewport property (Hypothesis: fits, keeps
  trail and footer, pages cover the body in order), follow, clamp, the reducer's half-terminal step,
  following again on a move, the top of another screen, page keys on every screen but search, the
  legend only when paged, and an end-to-end run at 20 rows that pages screen 07's fifteen settings
  to the last, and one that pages screen 22a (User Variables and Credentials, the owner's report) to
  the fifteenth setting after a real install. The Marketplace paging tests moved to the new
  signature.
- D-495: `tests/install_credentials_test.py` (17): `EnteredOn07bE2ETest` on both backends: Enter
  asks the store once per installation on 07b, before Ready, and the install asks nothing; Enter
  again replaces; an item stored before the review is neither asked nor deleted; Set later stores
  the placeholder, and after entering keeps what was entered; Esc from 07b, `q` on Ready and a
  failed install delete what was entered; a cancelled prompt and a value still cut are deleted
  with their reason shown. The reducer tests cover the labels, the refusal, and the review prepared
  again. `tests/credential_terminal_handover_test.py`: the install lends the terminal to nobody,
  and a failed install deletes what 07b entered. 47 credential, install and consumer files: 599
  passed.
- D-496: `tests/install_credentials_test.py` `UninstallDeletesTheInstallationsCredentialsE2ETest`
  (both backends): uninstalling opencode's installation names `credential:github-token` in the
  review, deletes its item and keeps tabnine's; uninstalling both deletes the placeholders.
  `tests/credential_contract_migration_e2e_test.py` `RemovalDeletesCredentialsTest` (replaces
  `RemovalRetainsCredentialsTest`): the review's JSON and text, `consume uninstall --yes` over a
  stand-in store empties it, a credential already gone is not listed, every receipt reference is
  planned, a narrowed record plans none. 72 uninstall-related files: 872 passed.
- D-497: `tests/install_credentials_test.py` `ScopeComesBeforeConfigurationE2ETest` (both
  backends): screens come as 05, 07a, 07, 07b, with opencode's row marked `(*)` on 07a before any
  plan; a user scope chosen before the form is where 07b's prompts address the items; 07 goes on
  to 07b without asking the scope again; what was typed survives going back to 07a.
  `tests/scope_matrix_test.py`: Enter on 07a goes on only once the plan is the one prepared for
  these scopes, to 07 while unanswered; 05 goes to 07 when no scope is to choose and past it once
  answered. Every install key sequence in the TUI e2e files follows the new order. 123 TUI test
  files: 1472 passed, and only B-226's two known `screen_skeleton_test` examples failed.
- D-498: `tests/installed_reach_test.py` (10; 124 TUI files: 1482 passed, only B-226's two failed): Hypothesis over scope, root and project for
  `reached_from`; Installed and Updates rows, status and legend before and after `a`; Updates
  counts only the updates it leaves out; a Collection whose members are all elsewhere is hidden; a
  session with no project hides nothing. E2E: a real install puts opencode with the user and
  tabnine in the project; from another project Installed lists opencode only, `a` lists both, and
  Home counts one.

- Ready's `Left as AART_NOT_SET, to set later in Credentials and variables:` is followed by a blank
  line before its list, at the owner's request. `tests/placeholder_warnings_test.py` was red before
  the line was added. 42 files that draw Ready: 537 passed.

- CI on PR #106 failed two tests that the local runs missed. `installation_changed_where_made_lab_e2e_test`
  updated another project's row, which Installed and Updates now hide until `a` (§210), so that walk
  presses `a`. `install_credentials_test`'s 07-to-07b drive relied on the macOS Keychain; it now
  uses a stand-in store, as its neighbours do, because Linux CI has none. Each fix, undone, turns
  its test red again.

## Targeted mutations

Run with `PYTHONDONTWRITEBYTECODE=1 python -B`, and each restored file is touched.

| Mutation | Red |
|---|---|
| 46 binds `c` again | no command on any row of the list (subtests) |
| The Initialize gate always true | no command on any row of the list (subtests) |
| Enter on any row opens 46k | another Registry does not open; the same-name subscription; Initialize only without a workspace |
| `registry_here` never read | the checkout's transactions |
| `● you are here` dropped | the mark once; Enter opens the Registry here; three workspace-row tests |
| The heartbeat never entered | the shell beats during a slow install |
| `tick` ignores the lock | a beat is skipped while the screen is held |
| `x-` no longer an annotation | the fastmcp-wrapped answer passes and is checked; any `x-` keyword |
| `minimum` inverted | `jira_search` allowed; the wrapped answer; the `minimum` property |
| A branch's unsupported keyword read as a failed branch | an unimplemented keyword in a branch is refused |
| D-491: a target's scope taken from the host, not its key | a user installation is reviewed and run from a project |
| D-491: `_why` says nothing | a run and a plan that raise name the error |
| `failure`: `<` becomes `<=` at `min_length` | the bounds property; a fitting length is left as it was |
| The placeholder judged as a value | what cannot be judged is not judged (subtest) |
| `input_to_data` writes `validation` for every secret | a secret without a length keeps the data it had |
| The receipt always writes `credential_checks` | a receipt declaring nothing reads as before |
| The machine skips the receipts' checks | a value left cut is not configured wherever it is read |
| The Keychain never marks 128 bytes clipped | a value as long as the prompt keeps is marked clipped |
| `_unfit` ignores a clipped value | without a declaration, a value on the ceiling is offered another way |
| The other way is never asked | three interpreter tests; the install keeps the whole value; set-credential |
| `enter_another_way` stops on UNAVAILABLE | the first way that can ask is the only one asked |
| `hiddenAnswer: false` | the script carries no value and writes hex on a pipe |
| An invalid credential's state worded as `Invalid` | not configured wherever it is read; `credentials_and_variables_test` |
| doctor says `is invalid` | not configured wherever it is read |
| `intended_receipt` drops the checks | not configured wherever it is read; the install keeps the whole value |
| `set-credential` accepts a value still cut | set-credential fails by name while the value is still cut |
| D-493: a pattern never fails | the issue-key property; ECMA `$`; searched, not anchored; six wrong keys |
| D-493: `$` left to Python | a pattern ends where JavaScript's does |
| D-493: `re.ASCII` dropped | an Arabic-Indic digit in an issue key (subtest) |
| D-493: `additionalProperties` schema ignored | additional properties as a schema |
| D-493: `prefixItems` ignored | prefix items check each position and items the rest |
| D-493: `Fraction(value)` for `Fraction(repr(value))` | a fraction kept exactly; `multipleOf` a fraction |
| D-493: a whole number never an `int` | a recursive model; fractions and integers; 11 more |
| D-493: a refusal annotated with stderr | a refusal is said alone |
| D-493: `integer` only for an `int` | a whole number beyond the protocol's integers |
| D-493: `discriminator` refused | every generated schema (subtests); a recursive model |
| D-493: `propertyNames` ignored | property names and pattern properties |
| D-493: `$ref` never followed | a reference is followed; a recursive model; every generated schema |
| D-494: no room for the above/below lines | a tall frame keeps its trail and keys; the viewport property; the 20-row run |
| D-494: no clamp at the last page | the clamp; the viewport property; the 20-row run; short curses Marketplace |
| D-494: never follow the cursor | following; the viewport property; a turned Marketplace page |
| D-494: what is above never said | paging down says what is above; the 20-row run |
| D-494: a fitting frame paged anyway | a frame that fits is drawn whole |
| D-494: PgDn moves one line | half a terminal; the 20-row run |
| D-494: PgDn keeps following | half a terminal; the 20-row run; short curses Marketplace |
| D-494: another screen keeps the page | another screen starts at its top |
| D-494: a move never follows again | moving follows again and keeps the page |
| D-494: the legend always offers scrolling | the legend only when paged |
| D-494: page keys only on Marketplace | page keys on every screen; the 20-row run |
| D-494: the shell never marks a frame scrollable | the 20-row run; short curses Marketplace |
| D-494: the shell does not store the clamp | short curses Marketplace |
| D-494: the legend measured only without its scroll key | short curses Marketplace |
| D-494: Marketplace follows with a margin | a turned Marketplace page |
| D-494: a negative page allowed | the state refuses a negative page |
| D-494: every screen but Marketplace drawn unpaged | both 20-row runs (07 and 22a) |
| D-495: leaving the review deletes nothing | leaving 07b; quitting from Ready |
| D-495: an item stored before the review asked again | an item stored before this review is left alone |
| D-495: Enter again stores instead of replacing | Enter again asks the store again |
| D-495: a row cut by the prompt left in place | a value still cut is deleted and the reason said |
| D-495: an entered row counted as configured | Enter on 07b asks there and the install asks nothing |
| D-495: a failed install keeps what was entered | a failed install deletes what 07b entered (both files); the install lends the terminal to nobody |
| D-495: success leaves `_entered` held | Enter on 07b asks there and the install asks nothing |
| D-495: the install not prepared again | four e2e runs (Ready's preflight refuses the stale review) |
| D-495: the reducer ignores the new review | the same four, and the reducer's review prepared again |
| D-495: no placeholder for what was not entered | Set later stores the placeholder; a cancelled prompt; the install lends the terminal to nobody |
| D-495: a stored row drawn `not set` | Enter on 07b asks there and the install asks nothing |
| D-496: no record's credentials deleted | both TUI uninstall runs; every receipt reference planned; a narrowed record (its pair); `consume uninstall --yes` |
| D-496: the review lists every receipt reference | a credential already gone is not said to be deleted |
| D-496: the text says nothing when none go | the human rendering says it too |
| D-497: typed fields replaced by the form asked again | what was typed survives going back to 07a |
| D-497: `harness_column` carried into 07a | a scope chosen before the form is where 07b asks |
| D-497: 05 never leads to 07a without a plan | the 05, 07a, 07, 07b order |
| D-497: the form event drops `pair_scopes` | 07a marks each pair's starting scope before any plan |
| D-497: 07 not opened as a form from 07a | the order; a scope chosen before the form |
| D-497: a submitted form asks the scope again | 07 goes on to 07b without asking the scope again; Enter on 07a once answered |
| D-497: `_after_inputs` leads to 07a again | 07 goes on to 07b without asking the scope again |
| D-497: 07a skips an unanswered form | Enter on 07a goes to 07 while it is unanswered |
| D-497: 05 skips 07 when no scope is to choose | 05 goes to 07 when no scope is to choose |
| D-498: every installation reached | the `reached_from` property; the default rows; Updates; the e2e |
| D-498: no project root still hides elsewhere | the property; a session with no project |
| D-498: the shell does not re-read rows after `a` | the e2e |
| D-498: both `a` bindings on | `a` shows every project and again this one; `a` toggles only that |
| D-498: a Collection elsewhere listed | the default rows |
| D-498: Updates not narrowed | Updates follows the same toggle |
| D-498: Home counts the whole machine | the e2e |
| D-498: `project_root` not passed | the e2e |
| D-498: Updates counts every installation left out | Updates counts only the updates it leaves out |
| D-496: a narrowed record asked to delete too | equivalent: it converges on its installed state, so no deletion reaches an effect; `not retained` states the intent |

## Left for later

- B-239: the opencode ENOENT on a generated launcher, seen in the same enterprise report.
- B-241: a credential stored as one character, also from that report.
- B-243: Doctor and Credentials and variables still read every project.
