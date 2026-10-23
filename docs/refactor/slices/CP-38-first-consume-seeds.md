# CP-38 — A first `consume` command connects the baked default Registry

Status: **done**, on `feat/cp-38-first-consume-seeds`, at the owner's request (2026-10-23).
Authority: D-373, D-475; closes B-168.

## Steps

See `docs/refactor/plan.json`, epic CP-38.

1. Every `consume` command except `consume registry add` and `--offline` seeds on a first run
   (B-168, D-475). Done.
2. Focused verification and the PR. Done: one PR, released as 0.16.0 on merge.

## Step 1 — The flag form seeds too

**Why.** The owner tried an Enterprise build whose first command was a flag-form one. Only
`tui.run` connected the baked Registry, so the command refused with `no-source-configured` although
the build named one.

**Change.**
- `aart_cli/commands/first_run.py`: `seed_first_run(command, user_home)` wraps
  `connect_baked_default_registry` and never raises; `announce_first_run_seed(report, write)` says
  what was connected, or the warning, through the channel it is given.
- `aart_cli/tui.py`: `_seed_first_run` and `_announce` delegate to both.
- `aart_cli/cli.py`: `_seeds_first_run` is true for `consume` unless the command is
  `consume registry add` or carries `--offline`; `main` then seeds before dispatching and writes the
  report to stderr.
- `docs/ci/github-enterprise-rollout.md`: Part 5 and the variable row say which first run connects
  the baked Registry.

**Tests.** `tests/first_run_connect_test.py::TheFlagFormSeedsAConsumerToo`: a `consume` command
seeds before it dispatches; the report is on stderr and not stdout; `consume registry add`,
`--offline` and `maintain registry validate` seed nothing; a defect in seeding does not stop the
command.

**Targeted mutations.**
- Exempting `remove` instead of `add` turned only
  `test_adding_a_registry_is_a_choice_and_seeds_nothing` red.
- Dropping the `--offline` check turned only `test_offline_forbids_the_fetch_and_seeds_nothing` red.

**Verified.** `tests/first_run_connect_test.py` 22 passed; every test file importing the CLI, 393
passed and 1 skipped; `make lint typecheck` clean.
