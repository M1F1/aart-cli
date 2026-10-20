# CP-33 — Default says which Settings values do not fit, and points to Custom

Status: **in progress** on `feat/cp-33-default-path-mismatch`, at the owner's request (#82,
2026-10-19), which the owner then extended to every open issue in scope: #46, #47, #80 and #24.
Authority: Product Specification §176, §177, INV-275, INV-276, D-452–D-455.

## Why

Default on 05p (§173.7, D-435) took the harnesses, scope and Python installer from Settings, but
did not say when they did not fit. A Settings harness that could host no selected artifact sent
the person to 05 without a reason. A partial fit installed into the subset that fit. A scope or
installer that was not offered was replaced by another one. In every case the person got
something other than what Settings says, and no explanation.

## Target

Choosing Default prepares from Settings as before, then checks each Settings value against what
that preparation measured. When one does not fit, nothing is installed or narrowed: 05p stays,
lists each mismatch once (artifact or whole selection, value, reason), says Default is not
available with these Settings, and moves the cursor to Custom.

## Steps

See `docs/refactor/plan.json`, epic CP-33.

1. Specification (§176, INV-275, D-452; §173.7 amended). Done.
2. Pure check `default_path_mismatches`, with the INV-275 property. Done.
3. Adapter, reducer and 05p. Done.
4. Docs and traceability. Done.
6. #46: variables that name a secret end in `_SECRET_NAME` (D-453). Done.
7. #47: `aart-cli docs`, read from the parser at run time. Done.
8. #47: `llms.txt`, naming no command but `docs`. Done.
9. #47: DOC003, a fenced command the parser rejects fails `docs-check`. Done.
10. #47: one pruning pass. Done.
11. #80: the Enterprise docs for 0.11. Done.
12. #24: blocked, the issue was deleted on GitHub (B-213). Not implemented.
5. Focused verification and the PR.

## Step 2 — the pure check

`application/consumer_views.py`: `DefaultPathMismatch(artifact, setting, value, reason)`,
`default_path_mismatches(targets, *, detected, harnesses, scope_offers, scope, installer,
python_installer)`, `render_default_path_mismatches` and `install_path_label`.

Evidence (`tests/default_path_mismatch_test.py`, 13 tests):
- Examples for each row of #82's table: a Settings harness that cannot host one artifact, one that
  hosts nothing, one not detected (one line for the selection), no Settings harness (nothing to
  check), a scope not offered (one line per artifact), an installer the selection cannot use, and
  no installer check when nothing needs Python.
- Hypothesis, INV-275: the report is empty exactly when every Settings value applies, nothing is
  listed twice, and every reported mismatch is real.
- Targeted mutation: reporting a harness only when it hosts nothing (the old silent narrowing)
  turned the partial-fit example and the INV-275 property red, and only those; restored.

## Step 3 — Default on 05p

`consumer_actions.py` calls the check on the Default path twice: harness and scope right after the
Settings pairs and their scope offers exist, before anything is asked or narrowed; the Python
installer once the plan is ready, because the installer offer is empty until then. A mismatch
returns `ACTION_PREPARED` carrying `default_path_mismatches` and nothing pending.
`application/consumer_ui.py` keeps 05p, clears the action and every identity, and moves the cursor
to Custom. Install from the Marketplace starts with no mismatches, and choosing Default again
prepares and checks again. `tui_consumer.py` draws the block under "Default uses:" and labels
Default as not available.

Evidence:
- `tests/install_path_default_e2e_test.py`: a Settings harness that cannot host the Skill keeps
  05p with the block, the unavailable label, the cursor on Custom and nothing delivered. A partial
  fit (`opencode`, `codex`) installs nothing, where it used to install into opencode alone. Custom
  after the block opens 05. Default again re-checks and stays. The earlier test that expected a
  silent jump to 05 is replaced, because §176 supersedes that behaviour.
- `tests/consumer_ui_actions_test.py`: the reducer keeps 05p with Custom next, clears the action
  and identities, re-prepares on Default, and Install from the Marketplace starts without the old
  block.
- Targeted mutation: disabling the adapter's early check turned three of the e2e tests red
  (partial fit, block shown, Default again); restored.
- Not covered end to end: the Python installer mismatch. No e2e fixture selects an artifact with
  Python dependencies on a machine where the Settings installer is unusable; the unit examples and
  the property hold it (B-211).

## Checks run (D-334)

`make lint`, `make format-check`, `make typecheck`, `make docs-check`, and the consumer, install,
screen, TUI, Marketplace, Collection and Settings test modules: 1,179 passed. The 2 that failed are
in `screen_skeleton_test.py`, fail on `main` without these changes too, and pass without the local
Hypothesis database; they are B-212, not CP-33. `make mutants` was not run:
`application/consumer_views.py` is over 3,000 lines, so a run scoped to it is far beyond a slice's
budget (D-134). The two targeted mutations above are the recorded evidence.

## Step 6 — `_SECRET_NAME` (#46, D-453)

The five repository variables that hold the *name* of a secret end in `_SECRET_NAME`, in the
repository workflows, the generated Registry CI, the docs and the specification. No reader of the
old names remains (CP-26 break policy). `enterprise_ci_template_test.py` holds that every
backticked `AART_CLI_*` name in the rollout page is read by some workflow.

## Steps 7–9 — the command reference is the parser (#47, §177, INV-276, D-454)

`aart_cli/cli_docs.py` walks `build_parser()`; `aart-cli docs` prints the tree, `docs <path…>`
one command or group (a quoted path is the same path), `--json` every leaf with its arguments.
Every command, group, argument and option now carries text: 19 leaves, one group and six
positionals had none. `llms.txt` points agents at `aart-cli docs --json` and the guides.
`scripts/docs_check.py` DOC003 hands every fenced `aart-cli …` and `python -m aart_cli…` line of
the README and user-facing documents to the parser.

Evidence:
- `tests/cli_docs_test.py` (12): description and help everywhere, JSON in walk order and equal to
  the parser, group and text forms, quoted path, unknown command exits 2; Hypothesis: any leaf
  asked for is exactly that leaf.
- `tests/llms_txt_test.py`: shape, only `docs` named, every relative link resolves.
- `tests/docs_command_parse_test.py` (9): rejected command and option, the common spellings,
  module spelling, continuations, prose and output ignored, exemptions, the repository passes;
  Hypothesis: every shipped leaf with `--help` passes and with `--no-such-flag` fails.
- Targeted mutations, each red then restored: `_find` ignoring the last word (5 tests red);
  `llms.txt` naming a command (1 red); `command_failure` accepting every rejection (5 red); a
  README typo `consume serch` (`make docs-check` fails with DOC003).
- Found by DOC003: `validate --strict --frozen`, never an option, in two tutorials; a CLI
  walkthrough on pre-CP-32 names.

## Step 10 — pruning (#47, D-455)

Deleted or merged: `docs/registry/maintainer-commands-v1.md` and `maintenance-planning-v1.md`
(into `maintaining-a-registry-v1.md`), `docs/ci/running-inside-a-company-v1.md`,
`docs/tutorials/direct-source-v1.md` (into `company-registry-v1.md`). README, install, packaging
and protocol pages point at `aart-cli docs` instead of restating commands.

## Step 11 — Enterprise docs for 0.11 (#80, D-455)

`docs/ci/github-enterprise-rollout.md` is rewritten: one remote convention made by commands
(`origin` the Enterprise copy, `upstream` the public repository), one clone for seeding, syncing
and the smoke run, leftover variables found by pattern, a single smoke procedure, the seven shared
Registry variables, the `.aart-cli-version` pin, and how to take a newer generated workflow. The
D-453 claim that `init` replaces it was wrong: `init` refuses an existing registry. A scratch
`git init` plus `maintain registry init --source <dir> --source-id scratch --display-name Scratch
--yes` was run and writes the workflow; the page copies it from there, and D-453 is corrected.
`docs/release/releasing-v1.md` gains the override-block rules and a fork-safe five-step sequence.
`END_TO_END_ACCEPTANCE.md` uses the CP-32 names; it was not walked in the lab (B-214).

## Step 12 — #24 not implemented

GitHub answers HTTP 410 "This issue was deleted" for #24. Not implemented; B-213.

