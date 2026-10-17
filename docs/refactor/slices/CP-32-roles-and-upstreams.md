# CP-32 — Three roles, three command families: consume, maintain, author

Status: **in progress** on `fix/source-local-git-visible-files` (PR #78), at the owner's request. Authority: the product owner (2026-10-17), Product
Specification §175, D-439.

## Why

`aart-cli source` configures Registries and author repositories alike, and `source list` shows
them together. A consumer can add an author repository although the Marketplace offers nothing from
it (`aart_cli/io/configured_offers.py` skips every non-Registry). The word "source" names both, so
neither role can tell from a command what it is about.

## Target

See §175.2 for the full command tree. In short: `consume` (Registries and installation), `maintain`
(`upstream`, `candidate`, `registry`), `author`; `doctor`, `upgrade`, `reset` and `security` stay
at the top level. Configuration keeps `registries` and `upstreams` apart; the TUI names its areas
the same way.

## Steps

See `docs/refactor/plan.json`, epic CP-32.

1. Specification (§175, INV-269–INV-272, D-439–D-441). Done.
2. Configuration split.
3. `consume`.
4. `maintain upstream`.
5. `maintain candidate`.
6. `maintain registry`.
7. Remove `source`, `marketplace`, top-level `registry` and the four kinds.
8. TUI names and hints.
12. TUI Author Mode (§175.5, D-441).
9. Documentation.
11. `reset` backs up and restores (§175.4, D-440); runs before the PR.
10. Full verification and the PR.

## Notes for the implementer

- No aliases, fallback readers or migrators (§169); a changed `config.json` shape is a clean break.
- Steps 3–6 can each land with focused tests (D-334): the argparse tree, one CLI e2e per family,
  and INV-269 as a test that no consumer path accepts an upstream.
- Policy fields `allow_direct_sources`, `recommended_sources` and `required_sources` follow the
  split: the direct switch goes; the other two name Registries.

## Step 2 — configuration split

Done (D-442). `config.json` keeps `registries` and `upstreams` with `kind: git|local`; the policy
names `recommended_registries`, `required_registries` and `company_reviewed_registries`, and
`allow_direct_sources` is gone from the model, the parser, first-run options and the TUI Sources
stage.

Evidence:
- `tests/configuration_schema_test.py` `test_registries_and_upstreams_are_separate_lists`: written
  files carry both lists and no combined kind; `sources`, combined kinds, a branchless local
  Registry, a local upstream with a ref, `url` on a local entry, one alias in both lists and an
  upstream as default Registry are each refused. The round trip covers all four combinations.
- `tests/configuration_policy_test.py`: an upstream with the required alias does not satisfy
  `required_registries`.
- 54 configuration-related modules, 652 tests, green; ruff, mypy and tach clean.

Targeted mutations:
- Required-registry check without `is_registry`: only the new upstream subtest turned red.
- `upstreams.git` mapped to `REGISTRY_GIT`: the round trip and the upstream-as-default refusal
  turned red.

## Step 11 — reset with backup

Done (D-440), ahead of steps 3–8 at the owner's priority. `aart-cli reset` renames every planned
target into `<home>-backups/<UTC timestamp>/` (a `-2`, `-3` suffix when a second reset lands in the
same second) after one `RESET AART` or `--yes`, and prints the directory and the restore command.
`reset --restore DIR` refuses a directory inside the home, a symlink, or one holding anything a reset
could not have put there; it backs the current state up first, moves the entries back and removes
the emptied backup. A move across filesystems is refused rather than copied. The TUI's "local AART
state could not be loaded" ends with the reset hint.

Evidence: `tests/factory_reset_test.py` -- one confirmation moves each target with its content into
the named backup; `--yes` prompts nothing; two resets keep two backups; `AART_CLI_HOME` is backed up
beside itself; cancel and EOF change nothing and create no backup; symlinked targets and homes are
refused before anything moves; restore round-trips and keeps the newer state; a foreign directory is
refused; the startup failure names `aart-cli reset`. The plan-level Hypothesis properties are
unchanged. 52 tests with `packaging_test` and `tui_stage_failure_test`, green; ruff and mypy clean.

Targeted mutations:
- Restore without the foreign-entry check: only the foreign-directory test turned red.
- Deleting instead of moving: the five tests reading the backup and `--yes` turned red.
