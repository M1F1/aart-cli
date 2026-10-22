# CP-35 — Headless installation inputs, optional inputs, locked uv projects and a fast CI

Status: **in progress** on `feat/cp-35-headless-inputs-and-fast-ci`, at the owner's request
(2026-10-22). The first three product steps come from an Enterprise agent's report on installing
an MCP server from an upstream fork with no terminal: required inputs could not be answered on the
command line, skipped optional inputs reached the server as `AART_NOT_SET`, and a `uv.lock`
project was refused. The owner added CI speed to the same epic. Authority so far: Product
Specification §169.4, §185-188, INV-286-289, D-466-470.

## Steps

See `docs/refactor/plan.json`, epic CP-35.

1. CI runs the suite once, in parallel processes, and measures coverage once. Done.
2. The generated Registry CI refuses versions promoted from a local checkout; the plain audit
   warns (§185, INV-286, D-467). Done.
3. `consume install` answers inputs on the command line (`--input`, `--secret-env`,
   `--set-later`; §186, INV-287, D-468). Done.
4. Optional inputs are asked, never become `AART_NOT_SET`, and reach the server only when
   answered (§187, INV-288, D-469). Done.
5. The Registry CI takes only versions adopted from an upstream's default branch (§188, INV-289,
   D-470). Added by the owner during the epic. Done.
6. A uv-locked project installs exactly its lock. Todo.
7. Focused verification and the PR. Todo.

## Step 1 — the suite runs once per interpreter, in parallel (D-466)

**Evidence of the bottleneck.** Successful full PR runs took 37–40 minutes. In each of the three
interpreter jobs, setup took about a minute and the non-test gates under a minute. `unit` ran 4,996
tests in one process (10.5–17 minutes), and `coverage` ran the same tests again (13–21 minutes),
with identical coverage on every interpreter (85.4%).

**Change.**
- `scripts/parallel_tests.py` runs unittest discovery split across processes. Modules are imported
  by their top-level name with `tests/` on `sys.path`, as `unittest discover -s tests` imports
  them. It makes about four chunks per worker, heaviest first, and a pool takes them as each
  finishes.
- `--coverage DATAFILE` runs every worker under `coverage run --branch --parallel-mode` and
  combines the data.
- `AART_CLI_TEST_WORKERS` sets the number of processes. It is also a repository variable in
  `pr-check.yml` and in the Enterprise rollout table.
- Each worker turns off Hypothesis's 200 ms per-example deadline. Ten workers under coverage pushed
  `frame_matrix_test` and `registry_collection_promotion_test` properties to 300 ms. A test that
  sets its own deadline keeps it.
- `scripts/quality.py` runs `unit`, `integration` and `coverage` through the runner.
  `redundant_gates` skips `unit` when `coverage` is selected; the skip is checked against the
  patterns. `integration` was already skipped under `unit`, and is now also skipped under
  `coverage`.
- Nothing is added to any dependency group. The runner is standard library plus `coverage` and
  `hypothesis`, both already dev dependencies, so the Enterprise image needs nothing new.

**Local measurement.**
- The whole suite under coverage on 10 processes: 5,041 tests in 210 s wall time, 85.68% coverage.
- The only failures were the two B-217 properties, the two Hypothesis deadlines (fixed above), and
  the two new `quality_gates_test` tests (that run started before their implementation).

**Tests.**
- `tests/parallel_tests_test.py`:
  - Hypothesis: every module lands in exactly one chunk, heaviest first.
  - The discovery pattern matches unittest's.
  - The worker count comes from the variable or the CPUs.
  - A passing temporary suite runs every test once and says OK.
  - A failing one fails and shows the failure.
  - A slow Hypothesis example is not a failure.
- `tests/quality_gates_test.py`:
  - `unit` is skipped under `coverage`.
  - The test gates run the runner over the same patterns.

**Targeted mutations.**
- Disabling the `unit`-under-`coverage` skip turned
  `test_the_unit_gate_is_skipped_when_coverage_runs_the_same_tests` red, and only it.
- Removing the `_without_deadline()` call turned
  `test_a_slow_example_is_not_a_failure_under_load` red, and only it.

## Step 2 — CI refuses versions from a local checkout (§185, INV-286, D-467)

**Why.** In Enterprise the owner promoted trial artifacts from checkouts on their machine into a
Registry that was then pushed. The owner asked that such content be impossible to merge into the
default branch, not merely discouraged.

**Change.**
- `audit_registry_workspace(for_default_branch=...)` reports each approved version whose
  `provenance.json` origin kind is `local`, or whose `references/KIND/NAME/VERSION.json` revision
  is a `local:` pin. Each finding names the coordinate and the recorded location and says to adopt
  from the upstream's Git URL.
- The finding is a warning by default, which is what `publish` runs, so trial Registries still
  commit. It is an error under `registry audit --for-default-branch`.
- `REGISTRY_PUBLICATION_GATES`' audit command, and therefore the generated workflow, passes
  `--for-default-branch`.
- The generated README and `docs/tutorials/company-registry-tabnine-v1.md` say so and say to make
  `registry-quality` required on the default branch.
- `docs/ci/github-enterprise-rollout.md` adds that the pull request bringing the new workflow must
  already hold no local version, because the audit reads the whole Registry.
- B-221 is resolved.

**Tests.** `tests/registry_remote_origins_test.py`:
- `approved_registry_snapshot` gains `local=` and `mode=`. It still promotes through the real
  promotion, so both content modes are covered.
- With the flag, the audit refuses. Without it, the audit warns and passes.
- Remote origins produce no finding either way.
- The generated workflow runs the strict command, and the parser accepts it.

**Targeted mutations.**
- Forcing `refused=False` on the provenance path turned only the self-contained subtest of
  `test_ci_refuses_every_version_promoted_from_a_local_checkout` red.
- Testing pinned references for `git` instead of `local` turned every pinned-reference subtest
  red.

## Step 3 — `consume install` answers inputs on the command line (§186, INV-287, D-468)

**Why.** An agent with no terminal could not install an MCP server with a required input: the
command prepared with no answers and refused.

**Change.**
- New `application/command_line_inputs.py`, pure:
  - `parse_command_line_input` splits `ALIAS/KIND/NAME:INPUT=VALUE` on the first `=`, then the
    target's last `:`. A refusal shows the target, never the value.
  - `resolve_command_line_inputs` checks every flag against `draft.inputs.fields` and refuses, all
    at once: an artifact the operation does not install, an undeclared input, a credential given
    to `--input` or a configuration value given to `--secret-env`, and an input answered twice.
  - `declared_defaults` gives each ordinary input no flag answered its declared default, as 07's
    pre-filled field does (§172.4).
  - `secret_references` points each installation's credential at its own provider item
    (`credential_address` with the whole owner), for credentials named by `--secret-env` and,
    under `--set-later`, for every unanswered one.
  - `secret_variables` maps each bound reference to the variable that holds it.
  - `missing_input_flags` gives the flag that answers each missing binding.
- `domain/inputs.py` exports `is_input_id`.
- `cli_parser.py` adds `--input`, `--secret-env` and `--set-later` to `consume install` and
  `consume update`; `Request` and `cli.py` carry them.
- `commands/marketplace.py`:
  - `_credential_providers()` is the one place that builds the provider tuple, so tests replace it
    with a fake and never touch the Keychain.
  - `_command_line_sources` runs when flags are given or the first preparation is not ready. It
    refuses an unset or empty variable by name and a credential when no store is available, then
    `_configured_lifecycle` prepares again with the sources.
  - The environment variable is read only after the review is confirmed, into a `TransientSecret`
    passed as `credential_secrets`. `--set-later` passes `skipped_secrets_as_placeholders`.
  - The refusal for unanswered inputs lists each flag, in text and as `flag` per input in JSON, and
    mentions `--set-later`.
- `docs/using/consumer-lifecycle-v1.md` documents the flags.
- A Linux credential store is missing, so `--secret-env` refuses there (B-222).

**Tests.**
- `tests/command_line_inputs_test.py`: the Hypothesis round-trip of the flag shape, refusals that
  never echo a value, one answer per artifact across harnesses, defaults, one reference per
  installation, and the flag lines.
- `tests/command_line_inputs_e2e_test.py` drives `cli.main` against a published Registry with a
  recording fake store:
  - the refusal names the token's flag only, because the organisation has a default;
  - `--input` and `--secret-env` install, write the answer into the installation's configuration
    file, store the generated token, and leave it in no file;
  - `--set-later` stores `AART_NOT_SET` and keeps the default;
  - an empty variable, an unknown artifact, a credential given to `--input` and a missing store are
    refused with nothing written.

**Targeted mutations.**
- Dropping `declared_defaults` from `_command_line_sources` turned the refusal and `--set-later`
  tests red.
- Checking only that the variable exists, not that it is non-empty, turned the empty-variable
  subtest red, and only it.

## Step 4 — optional inputs are asked and never become the placeholder (§187, INV-288, D-469)

**Why.** For mcp-atlassian, an input skipped with Set later reached the server as the text
`AART_NOT_SET`. 07 never asked optional inputs at all. A required input that is set later still
gets the placeholder (§172.3); an optional one must not.

**Change.**
- `copy_artifact_answers(skip_unanswered=True)` gives `AART_NOT_SET` only to required inputs. This
  is the CLI's `--set-later` path.
- `InstallationConfigField` gains `required` and `unset`, meaning optional and empty.
  - `ready` accepts an unset field.
  - `answers` leaves it out.
  - `set_later()` empties an optional field without a valid value instead of filling it.
- `consumer_actions.py` adds each optional ordinary input of an artifact that 07 asks about, after
  the required ones and pre-filled with its default.
- `tui_consumer.py` marks the field `(id, optional)`. The Verbose text for Set later says optional
  values stay unset.
- 07b's optional credentials are B-223.

**Tests.** `tests/optional_inputs_test.py`:
- Hypothesis over the form draft: after Set later the draft is ready, every required row has an
  answer, and no optional row holds the placeholder or an empty answer.
- Hypothesis over `copy_artifact_answers`: the placeholder goes only to required inputs nobody
  answered.
- The form marks an optional field.
- The production action prepares 07 with the optional `github-host` after `github-org`, and binds
  it only once it is answered.
- `consume install --set-later` writes no `github-host` line and no placeholder. With `--input` it
  writes the value.

**Targeted mutations.**
- Dropping `field.input.required` from `copy_artifact_answers` turned the copy property and the CLI
  `--set-later` test red.
- Making `ready` ignore `unset` turned the two form-draft tests red.

## Step 5 — the Registry CI takes only an upstream's default branch (§188, INV-289, D-470)

**Why.** The owner pointed out that step 2 still let a version adopted from an upstream's feature
branch reach the Registry's default branch. Adoption from any branch must stay possible for trials.

**Change.**
- `io/git_acquisition.py` adds `commit_on_default_branch(request, commit)`. It runs
  `git merge-base COMMIT refs/remotes/origin/HEAD` in the mirror the acquisition already fetched,
  where `HEAD` is the upstream's own default branch. The result is None when that cannot be
  answered.
- `io/curation_runtime.py`: `_candidate` returns the answer beside the candidate.
  `NativeReferenceAcquisition` gains `default_branch`.
- `registry_maintenance/model.py` now holds `REPOSITORY_ADOPTION_RECORD` and
  `adoption_record(ref, default_branch)`, which writes the field only when it is known.
  `io/registry_adoption.py` uses it for adoption and for the next version `upstream check`
  proposes.
- `registry_commands/planning.py` adds `_off_default_branch`:
  - The plain audit warns about a version recorded as off the default branch.
  - `for_default_branch` refuses that, a version adopted without the record, a version promoted
    from a Git Source, and every remote pinned reference.
- `--require-remote-origins` (step 2, unreleased) is renamed `--for-default-branch` everywhere.
- The generated README, the tutorial and `docs/ci/github-enterprise-rollout.md` say what CI refuses
  and that the upstream's default branch is its Git host's, not always `main`.
- Release branches other than the default are B-224.

**Tests.**
- `tests/registry_default_branch_test.py`:
  - Audit: an adoption recorded on the default branch passes either way. One recorded off it warns,
    naming the ref and the upstream, and is refused under the flag. Promoted, pinned and
    unrecorded remote versions are silent in the plain audit and refused under the flag.
  - Real Git: `main` and a tag on it are on the default branch; a feature branch is not.
- `tests/registry_repository_scan_test.py`: a real adoption writes `default_branch: true`.
- `tests/registry_remote_origins_test.py` follows the rename.

**Targeted mutations.**
- Treating a record with no `default_branch` as on it turned only the `unrecorded` subtest red.
- Comparing the commit with itself instead of `refs/remotes/origin/HEAD` turned the reachability
  test red.
