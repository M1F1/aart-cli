# OPENCODE-USER-SETTINGS-FILE — OpenCode's user settings go where every OpenCode reads them

**Status:** implemented; the PR is open. §218 added, §171.3 amended; D-530; INV-343. Backlog
B-275–B-278. Next: P0-2, the `opencode2` harness variant (stacked branch).

## Why

Reported 2026-11-27 (deadline 2026-11-30): an OpenCode 2.3.2 that a launcher starts with
`OPENCODE_CONFIG` reads `~/.config/opencode/opencode.jsonc` when it exists and `opencode.json` only
when it does not, and OpenCode 1.x leaves an empty `opencode.jsonc` behind. aart-cli wrote every
user MCP server and plugin into `opencode.json`, so they were installed and never loaded.

## What was done

- `aart_cli/domain/jsonc.py` (new, pure): a JSON-with-comments parser and in-place rewriter. It
  edits only changed members and items, lays out new ones in the file's indent, annotates inserted
  entries, removes an owned marker with its entry, keeps a one-line container on one line, and
  refuses (`JsoncError`) rather than drop a comment. Every result is reparsed and compared.
- `aart_cli/domain/settings_text.py` (new, pure): reads and writes a settings file in its
  harness's syntax; JSONC for opencode, strict JSON elsewhere.
- `aart_cli/domain/harness.py`: `SETTINGS_FILES`, `chosen_settings_file`, `sibling_settings_paths`,
  `preferred_settings_path`, `SettingsSyntax`, `settings_note`/`is_settings_note`/`annotates`;
  `mcp_target` and `plugin_target` take `exists`; a receipt may name either user file.
- `aart_cli/io/harness.py`: the registry reads and writes JSONC, annotates, removes this
  installation's same server (same command only) from the sibling, and observes an entry also or
  only in the sibling as divergent.
- `aart_cli/io/execution.py`: the settings-entry interpreter does the same for plugin entries; the
  MCP interpreter passes the note and the command.
- `aart_cli/io/runtime_projection.py`: a plugin entry also or only in the sibling is drift.
- `aart_cli/io/artifact_placement.py`: placement chooses the file that exists.
- `aart_cli/application/settings_relocation.py` (new, pure): `relocated_receipt`, `settings_moves`.
- `aart_cli/io/consumer_machine.py`, `aart_cli/application/consumer_session.py`: inspections judge
  the relocated receipt and carry the moves.
- `aart_cli/commands/doctor.py`: *Settings files* section and `settings_files` in JSON, naming the
  file the entry is in, the file opencode reads and the repair command; silent when none.

## Evidence

- `tests/jsonc_test.py`: examples (OpenCode's own file, comments, markers, trailing commas, tabs,
  empty and comment-only text, duplicates, refusal) and Hypothesis properties (rewrite equals the
  document or refuses only where comments are; added members keep every comment; unchanged is
  byte-identical; add then remove is identity).
- `tests/opencode_user_settings_file_test.py`: the choice, the receipt, the registry on real files
  (annotated install and exact restore on uninstall, sibling clean-up, someone else's same-named
  server untouched, also/only divergent, refusal, an unreadable sibling skipped), relocation.
- `tests/opencode_user_settings_file_e2e_test.py`: public commands on an isolated home -- neither
  file creates `opencode.jsonc` with the marker; OpenCode's own file is written; comments survive
  install and uninstall byte for byte; json-only stays strict JSON with no marker; a recorded json
  entry is drift, the review writes nothing and the confirmed repair moves it and records jsonc;
  an entry in both files is drift and the repair keeps one; doctor's section in text and JSON;
  a symlinked `opencode.json` without the entry is left alone; uninstall of a recorded json entry
  cleans both.
- Existing opencode tests updated for the `.jsonc` default (`opencode_harness_test`,
  `plugin_entry_test`, `install_assignments_e2e_test`,
  `installation_changed_where_made_lab_e2e_test`); the opencode set passes (93 tests).

### Targeted mutations

- `chosen_settings_file` returning the last candidate → `test_jsonc_wins_json_is_kept_where_alone_and_jsonc_is_created_where_neither` red.
- Dropping the command match in `LocalHarnessRegistry._remove` → `test_a_same_named_server_somebody_else_wrote_is_not_ours_to_remove` red.
- Skipping `relocated_receipt` in `read_installed_inspections` → `test_an_entry_left_in_opencode_json_is_moved_by_a_reviewed_repair` and `test_doctor_says_which_file_opencode_reads_and_how_to_move_the_entry` red.

### Mutation adequacy (`make mutants ONLY=aart_cli/domain/jsonc.py TESTS="tests/jsonc_test.py"`)

First run: 966 mutants, 219 survived. Survivors read as findings: no test removed an entry with a
comment on its line, added under a comment on the opening line, or wrote text outside ASCII, a
reordered document or a duplicate member. Those are now exact examples
(`test_each_edit_lands_exactly_where_a_person_would_put_it`, `test_text_outside_ascii_is_written_as_itself`,
`test_the_same_members_in_another_order_change_nothing`,
`test_a_member_written_twice_is_left_alone_unless_it_is_the_one_changed`). Clean rerun before the
last three: 1000 mutants, 796 killed, 198 survived. The remainder is equivalent or out of claim:
error-message wording, parser error positions, the self-check after a rewrite (reachable only
through another bug), and layout branches for containers whose entries share lines, which the
rewriter replaces whole instead.

## Not done here

`XDG_CONFIG_HOME` (B-275); project plugin directories for `opencode2` (B-276); usage plugin
fixes (B-277); live tests on a pinned OpenCode 2 (B-278); the `opencode2` harness variant (P0-2).
