# CP-42 — One installation is one row, measured and changed where it was made

Status: **done**, on `fix/cp-42-installation-identity`, after the owner's reports and the
Enterprise agent's diagnosis (2026-10-23). Authority: Product Specification §195, §169.3, INV-296,
D-479.

## Steps

See `docs/refactor/plan.json`, epic CP-42.

1. The installation key carries scope and root; one entry per installation, named for people. Done.
2. Each installation is measured under its own root. Done.
3. Actions on another project's installation are refused. Done.
4. Focused verification and the PR. Done: one PR.

## Why

One MCP installed in opencode for the user and in two projects had three keys
`company-mcp-local/mcp/airflow@1.0.0#opencode`. This caused four failures:
- entering Installed or Doctor raised `ValueError` in `ConsumerUiEvent` (rows must be unique);
- User Variables And Credentials merged the three installations into one entry;
- Doctor read every project installation's opencode entry from the directory the TUI was opened
  in, so it reported `harness:opencode: missing`;
- a repair planned from that reading would have written the entry into this project.

## Change

- `domain/installation_owner.py`: `compose_installation_key` (`coordinate#label#scope#root`),
  `installation_key` through it, and `describe_installation`.
- `consumer_views.py`: `InstalledArtifactView.row` composes the same key from harness, scope and
  root.
- `tui_consumer.py`: every place that names an installation describes it:
  - screen 22 entries and the 22a header;
  - 22c's "Change … for …";
  - credential dependants;
  - Doctor's Collection members;
  - the MCP test, and its "is not an MCP" refusal;
  - Doctor's repairable-issue rows.
  The Installed list's Artifact cell reads `artifact · harness`, because Scope and Project have
  their own columns.
- `commands/doctor.py`: the text output's "needed by" describes installations; JSON keeps keys.
- `io/consumer_machine.py`: each owned installation is observed under
  `ScopedHarnessRegistry({owner.scope: owner.root})`.
- `consumer_actions.py`: `_inspections`, which repair, update, uninstall and configure go through,
  refuses an owner root that is not this session's root for its scope. The code is
  `consumer-action-elsewhere`, and the message names the directory to open.

## Tests

- `tests/installation_identity_rows_test.py` covers the owner's machine (user, `alpha` and `beta`
  projects):
  - three distinct keys, and the Installed row equals the record's key;
  - descriptions, and a key splits back into its parts whatever the root holds (Hypothesis);
  - Installed opens with three rows;
  - screen 22 has three entries, each named and each holding only its own credential;
  - 22a names its installation.
- `tests/installation_owner_test.py`: the D-361 property is replaced. Keys are equal exactly when
  label, scope and root are (Hypothesis), and the example keys are updated.
- `tests/installation_measured_where_made_test.py`:
  - a real MCP installation in project B, read from project A, has the same drift as read from B,
    and no harness drift;
  - the real handler in project A refuses repair, update, uninstall and configure on it, names B,
    and writes nothing;
  - from B, the repair is prepared.

- Tests that spelled keys as `coordinate#harness` now compose them, or assert the described name:
  `consumer_application_e2e_test.py`, `installed_artifact_paths_test.py`,
  `installed_mcp_test_e2e_test.py`, `collection_installed_e2e_test.py`,
  `doctor_installation_rows_test.py`, `post_install_mcp_test_test.py` and
  `tui_updates_lab_e2e_test.py`.
- Focused run over the TUI, consumer, installation, credential, Doctor and MCP test files: see the
  PR. The two `screen_skeleton_test.py` properties fail on `main` too (B-226).

## Targeted mutations

| Mutation | Red |
|---|---|
| Key without root | 11 key, row and screen tests |
| `InstalledArtifactView.row` back to `coordinate#harness` | row equals key; Installed opens with three rows |
| Screen 22 heading prints the raw key | only the screen-22 naming test |
| Observation back to the session's registry | both measured-where-made tests |
| `_inspections` refusal disabled | the four refusal subtests |
