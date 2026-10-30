# CP-52 — An update keeps the configuration its installation holds

Status: **done in code and evidence**, on `fix/update-keeps-inputs`; the PR is next (2026-10-30).
Authority: Product Specification §38, §161, §169.3, INV-196, D-507.

## Steps

See `docs/refactor/plan.json`, epic CP-52.

1. Characterize: an update of an installation whose configuration file holds every value. Red: the
   CLI refused, `--set-later` wrote the placeholder over the values, the TUI returned to 15. Done.
2. Keep the held values for the same installation only, behind its own validation; precedence flag,
   held, default, placeholder. Done.
3. Screen 16 asks what is new with 07's form. Done.
4. The PR. Next.

## Why

The owner updated an installed MCP and was told its inputs were unanswered, though its
configuration file held them. They asked for the fix and, at once, for the form on 16
("od razu stworz formularz").

## What changed

- `application/installation_inputs.py`: `retained_input_sources(fields, stored)` keeps a stored
  value for a field of the same `InstallationOwner` only, for a config input only, never
  `AART_NOT_SET`, and only if the new version's validation accepts it. `with_retained(given,
  retained)`: what is given now wins.
- `application/command_line_inputs.py`: `command_line_sources` binds flag, then held, then default,
  then (with `--set-later`) the placeholder.
- `io/configured_configuration_action.py`: `installed_configuration_values(inspections)` reads each
  receipt's configuration file for its own harness, only while its digest is the recorded one, and
  never raises.
- `commands/marketplace.py` (`consume update`) and `consumer_actions.py` (the TUI) pass the held
  values; the TUI's draft starts from them.
- `application/consumer_ui.py` and `tui_consumer.py`: `input_form_open(state)` opens the form on 07
  for an install and on 16 for an update; Continue prepares the same update with the answers; a new
  update starts with an empty form.

## Evidence

- `tests/update_retained_inputs_e2e_test.py` (12), real `consume` commands and the TUI's
  composition over a fixture Registry: an update keeps every value and needs no answer; an
  optional value is kept when nothing is asked, and `inputs set` still finds its file; `--set-later`
  never overwrites; a flag replaces; an input the new version adds is the only question; a value the
  new version refuses, and a placeholder, are asked again; another harness never receives a value;
  a file edited outside aart-cli gives nothing; the TUI reviews with the held values, asks a new one
  on 16's form and keeps the rest, and the form starts from what is held.
- `tests/update_inputs_form_test.py` (10): the reducer opens the form on 16, Continue sends
  `PREPARE_ACTION` for UPDATE with the answers, Set later, the review closes the form, typing is kept
  across a second prepare, Escape returns to 15, a new update starts empty, a ready update never
  opens it, and 16 draws it as 07 does.
- `tests/retained_inputs_test.py` (9): same owner only (harness, scope, root, alias each refused);
  placeholder, refused value, credential and undeclared input keep nothing; Hypothesis over every
  mix of flags, held values and Set later: each field bound once, by its strongest source.
- 262 existing tests of install, update, inputs and the consumer TUI pass unchanged.

## Targeted mutations

| # | Mutation | Killed by |
|---|---|---|
| M1 | The placeholder kept as a value | `retained_inputs_test` |
| M2 | No validation of a held value | `retained_inputs_test` |
| M3 | A credential kept | `retained_inputs_test` |
| M4 | A value kept for any owner with the same input id | `retained_inputs_test` (4 failed) |
| M5 | A held value beside a given answer for the same field | `retained_inputs_test` |
| M6 | Held beats a flag | `retained_inputs_test` |
| M7 | Defaults bound over held values too | `retained_inputs_test` |
| M8 | A file edited outside aart-cli read | `update_retained_inputs_e2e_test` |
| M10 | `consume update` passes nothing held | `update_retained_inputs_e2e_test` |
| M11 | Held values do not make the update re-prepare | `update_retained_inputs_e2e_test` (optional kept, `inputs set` afterwards) |
| M12 | `command_line_sources` without the held values | `update_retained_inputs_e2e_test` |
| M13 | The TUI passes nothing held | `update_retained_inputs_e2e_test` |
| M14 | The TUI's sources without the held values | `update_retained_inputs_e2e_test` |
| M15 | 16 not mapped to UPDATE | `update_inputs_form_test` |
| M16 | The form opened only on 07 | `update_inputs_form_test` |
| M17 | A new update keeps the old draft | `update_inputs_form_test` |
| M18 | A second prepare drops what was typed | `update_inputs_form_test` |
| M19 | Continue sends no answers | `update_inputs_form_test` |
| M20 | Continue on 16 requests an install | `update_inputs_form_test` |
| M21 | Set later on 16 requests an install | `update_inputs_form_test` |
| M22 | The TUI's draft starts from defaults only | `update_retained_inputs_e2e_test` (form starts from what is held) |
| M23 | 16 renders no form | `update_inputs_form_test` |
| M24 | 16 lists no form rows | `update_inputs_form_test` |

M9 (reading a receipt's configuration file for another harness) is equivalent: a receipt records
only its own harness's file (§169.3), so the guard can never skip anything today. It is kept as the
statement of the rule.

M11 first survived: with it, an update that asks nothing kept the value in the file but dropped the
file from the receipt. The optional-update test now runs `consume inputs set` afterwards, which
fails on such an orphaned file.

## Not done here

B-263 (sending uses of artifacts aart-cli did not install) needs a §213 amendment first.
