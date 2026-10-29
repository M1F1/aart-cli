# CP-47 — A newer aart-cli that a Registry runs is announced, with how to install it

Status: **done** (the owner's lab run; one PR with CP-48 and CP-49), on
`feat/cp-47-aart-cli-update`, from `main` at 0.20.0, at the owner's request (2026-10-28).
Authority: Product Specification §211, INV-316, INV-317, D-499.

## Steps

See `docs/refactor/plan.json`, epic CP-47.

1. The governing pin and the `.aart-cli-source` routes, pure. Done.
2. Pins and source read from the current snapshots; the running aart-cli and its installer. Done.
3. `consume` commands say it on stderr; `aart-cli upgrade --how` prints the commands. Done.
4. TUI: Home's line, the entry's badge, the footer, and screen 30 AART CLI Update. Done.
5. The Registry and Enterprise rollout documents name `.aart-cli-source`. Done.
6. The owner's run, and the PR. Done.

## Why

The owner asked for the person to be told when the Registry runs a newer aart-cli, and how to
upgrade. The commands must follow how the default Registry's organisation supplies aart-cli: a
Nexus index gives pip, pipx or uv, a clone gives an editable checkout. `gh release download` does
not work in every Enterprise. The owner chose a file committed in the Registry, in the names of the
CI variables, and kept `.aart-cli-version` and the CI unchanged.

## What changed

- `aart_cli/application/aart_cli_update.py` (new, pure): `governing_pin`,
  `parse_aart_cli_source`, `detect_installer`, `aart_cli_update` (routes per installer),
  `upgrade_headline`, `upgrade_steps`, `upgrade_guidance`.
- `aart_cli/io/aart_cli_pins.py` (new): `read_registry_pins` reads `.aart-cli-version` and
  `.aart-cli-source` from each enabled Registry's current snapshot through its pointer;
  `running_aart_cli`; `read_aart_cli_update`, which never raises.
- `aart_cli/commands/upgrade.py`: `--how` and `announce_newer_aart_cli`; `aart_cli/cli.py` says it
  after every `consume` command, on stderr; `cli_parser.py` and `model.py` carry `upgrade_how`.
- `aart_cli/application/consumer_views.py`: `ConsumerScreen.AART_CLI_UPDATE`, Home's last entry,
  and `DashboardView.aart_cli_available`/`aart_cli_registry`.
- `aart_cli/tui_consumer.py`: `ConsumerOffers.aart_cli_update` (read with the offers),
  `ConsumerScreens.aart_cli_update`, `screens_from`, `_badge`, `render_dashboard`, the footer,
  the screen's title, description and status. `consumer_actions.py` passes it through.
- Docs: `docs/ci/github-enterprise-rollout.md` (Part 4) and
  `docs/registry/maintaining-a-registry-v1.md`.

## Evidence

- `tests/aart_cli_update_test.py`: Hypothesis for the governing pin against an oracle written
  apart from the code; build metadata is not newer; a pin is read as `tr -d` reads it; every
  accepted file reads back; one bad line anywhere (unknown or repeated name, `export`, no `=`,
  quotes, a user name in `https`, a password in any scheme, a control character) refuses the whole
  file; each route per installer; every command is bare words with the pin in place.
- `tests/aart_cli_pins_e2e_test.py`: a Registry published into the real source store with the two
  files; `consume list --json` keeps stdout JSON and says it on stderr; `upgrade --how` runs no
  subprocess.
- `tests/aart_cli_pins_e2e_test.py` also opens the production terminal composition over that
  machine: Home and the screen carry the pin.
- `tests/aart_cli_update_screen_test.py`: Home's line and badge, the footer, the screen's guidance
  and its words when nothing is newer, the entry last on Home.
- `tests/screen_cases.py` records screen 30 in the frame matrix, plus `30:newer-aart-cli` with
  commands, so every shared frame, key and literal law holds on it.
- Updated for the new last Home entry: `consumer_navigation_test.py`, `maintainer_navigation_test.py`
  (Maintainer is second to last), `screen_block_structure_test.py`, and the README frame.
- Focused regression: every test file naming the consumer screens, the TUI, the CLI or `upgrade`
  (2374 passed). The 2 `screen_skeleton_test` Hypothesis failures are B-226's, unchanged.

## Lab check (2026-10-28)

A fresh lab Registry (`scripts/manual_test.py setup`) was given `.aart-cli-version` 0.21.0 and a
`.aart-cli-source` naming a Nexus-shaped index, committed and pushed as a merged change. A consumer
connected it: `registry add` and `consume list --json` said `aart-cli 0.21.0 is available` on
stderr with stdout still JSON, and `upgrade --how` gave the checkout route from the lab (which runs
the checkout through `PYTHONPATH`). The built wheel installed with pipx and with uv into their own
moved homes gave `pipx install --force --index-url …` and `uv tool install --force --default-index
…`. The first pipx run said "Installed with pip.": its environment was at `…/home/venvs/aart-cli`,
so the default-path check missed it. The installer is now read from the file each tool leaves in
the environment first (`RunningAartCliTest`, M15, I4, I5).

## Targeted mutations

Each was made by hand, run against the named tests, and reverted. All 30 turned their tests red.

After CP-48 changed `cli.py`, `tui_consumer.py` and `consumer_actions.py` in the same branch, C1,
C3, T1, T4, T6 and T7 were made again on the changed files: all six still turn their tests red.

| # | Mutation | Red |
|---|---|---|
| M1 | newer is `>=` instead of `>` | build metadata, oracle, nothing newer |
| M2 | the default Registry never governs | oracle (Hypothesis) |
| M3 | ties go to the last alias | oracle (Hypothesis) |
| M4 | a repeated name is accepted | `test_a_repeated_name_is_refused` |
| M5 | `https` with a user name accepted | one bad line refuses the file |
| M6 | a password in any scheme accepted | one bad line refuses the file |
| M7 | the wheel wins over the package | first route in CI order; property |
| M8 | another default index | pypi as in CI; guidance |
| M9 | a checkout is not an editable install | installer detection; editable route |
| M10 | an SCP origin is not turned into `git+ssh://` | SSH Registry |
| M11 | the checkout goes to the bare version, not `v<pin>` | editable route |
| M12 | `AART_CLI_REPOSITORY` wins over `AART_CLI_TOOL_URL` | tool URL wins |
| M13 | a quoted value accepted | one bad line refuses the file |
| M14 | uv given `--index-url` | the package index route per installer |
| I1 | `.aart-cli-source` not read | snapshot read; `upgrade --how` |
| I2 | the pin read beside the snapshots, not in the pointed one | snapshot read; stderr; `--how` |
| I3 | a defect raises | a defect is nothing |
| C1 | announced after `upgrade` instead of `consume` | stderr test |
| C2 | `--how` ignored | both `--how` tests |
| C3 | announced on stdout | stderr test (stdout stays JSON) |
| T1 | footer leaves the newer version out | Home test |
| T2 | Home's line left out | Home test |
| T3 | the entry's badge left out | Home test |
| T4 | `screens_from` drops it from the dashboard | `screens_from` test |
| T5 | the screen's guidance left out | screen test |
| T6 | the actions do not pass the offers' update | production composition |
| T7 | the offers do not read it | production composition |
| M15 | the marker files are ignored | a moved pipx or uv home |
| I4 | the IO passes no marker files | `RunningAartCliTest` |
| I5 | a checkout is not seen | `test_a_checkout_is_an_editable_install` |
