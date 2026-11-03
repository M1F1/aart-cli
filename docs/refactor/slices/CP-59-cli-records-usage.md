# CP-59 — A `consume` command puts the usage hook in place too

Status: **done** on its branch; merged with its PR.
Authority: Product Specification §212 (amended), D-516. Resolves B-249.

## Why

A build that records opencode without asking (D-502) put the hook in place only at the TUI's start.
Someone who installed a plugin with `consume install` and never opened the TUI recorded nothing,
so the server saw no use of its skills.

## What changed

- `commands/usage.record_usage_for_this_build(request)`: reads the person's settings in the
  application home the run uses, and runs `reconcile_usage_hooks` with their harnesses, else the
  build's. It says each newly hooked harness on stderr and never raises.
- `cli._records_usage`: any `consume` command but `consume usage`. `cli._dispatch` calls the
  above after the command.
- `tests/conftest.py`: under pytest, a module hooks only with `RECORDS_USAGE = True`.
- Spec §212, the user guide's usage section, D-516, B-249 resolved; D-500's line marked superseded.

## Evidence

`tests/cli_install_usage_hook_test.py`, on real commands in a temporary HOME and AART_CLI_HOME:

- a real install (review, then `--expect … --yes`) in a build baking `opencode` hooks opencode, and
  says so exactly once;
- `consume status` hooks it too and says so once; a second command says nothing;
- a build baking nothing hooks nothing;
- a person who turned recording off is not overruled;
- the choice is read from `AART_CLI_HOME` when it is set elsewhere;
- with no `~/.config/opencode`, no file and no directory is created;
- a hook that cannot be written never fails the command;
- `_records_usage`: `consume list/install/update/telemetry` yes; `consume usage show/disable` and
  `maintain` no.

Targeted mutations, each killed:

- U1 never hooking;
- U2 `consume usage` hooking too;
- U3 every command family hooking;
- U4 the person's choice ignored;
- U5 said on stdout;
- U6 a failure escaping;
- U7 nothing said;
- U8 `AART_CLI_HOME` ignored.
