# CP-35 — Headless installation inputs, optional inputs, locked uv projects and a fast CI

Status: **in progress** on `feat/cp-35-headless-inputs-and-fast-ci`, at the owner's request
(2026-10-22). The first three product steps come from an Enterprise agent's report on installing
an MCP server from an upstream fork with no terminal: required inputs could not be answered on the
command line, skipped optional inputs reached the server as `AART_NOT_SET`, and a `uv.lock`
project was refused. The owner added CI speed to the same epic. Authority so far: Product
Specification §169.4, §185, INV-286, D-466, D-467.

## Steps

See `docs/refactor/plan.json`, epic CP-35.

1. CI runs the suite once, in parallel processes, and measures coverage once. Done.
2. The generated Registry CI refuses versions promoted from a local checkout; the plain audit
   warns (§185, INV-286, D-467). Done.
3. `consume install` answers inputs on the command line (`--input`, `--secret-env`,
   `--set-later`; §169.4). Todo.
4. Optional inputs are asked, never become `AART_NOT_SET`, and reach the server only when
   answered. Todo.
5. A uv-locked project installs exactly its lock. Todo.
6. Focused verification and the PR. Todo.

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
- `audit_registry_workspace(require_remote_origins=...)` reports each approved version whose
  `provenance.json` origin kind is `local`, or whose `references/KIND/NAME/VERSION.json` revision
  is a `local:` pin. Each finding names the coordinate and the recorded location and says to adopt
  from the upstream's Git URL.
- The finding is a warning by default, which is what `publish` runs, so trial Registries still
  commit. It is an error under `registry audit --require-remote-origins`.
- `REGISTRY_PUBLICATION_GATES`' audit command, and therefore the generated workflow, passes
  `--require-remote-origins`.
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

## Step 3 — design (not started)

§169.4 requires every non-interactive binding to name its installation target, never a generic
input id. §172.4 lets one operation copy an answer into every installation of one artifact (D-413).
The flags therefore always name the full artifact key `ALIAS/KIND/NAME` (`artifact_answer_key`),
with no shorthand.

- `--input ALIAS/KIND/NAME:ID=VALUE`, repeatable. Split on the first `=`, then `rpartition(":")`.
  An unknown artifact, an input the artifact does not declare, a credential given to `--input`, or
  a duplicate is refused before anything is prepared. A refusal never echoes the value.
- `--secret-env ALIAS/KIND/NAME:ID=ENVVAR` reads the credential from that variable into a
  `TransientSecret` keyed by `str(reference)`. A missing or empty variable is refused by name. Only
  `SecretInput`s are accepted.
- `--set-later`: required ordinary inputs left unanswered get the placeholder (`copy_artifact_answers(...,
  skip_unanswered=True)`, fixed in step 4 to touch required fields only), and secrets are stored as
  placeholders (`skipped_secrets_as_placeholders=True`).
- Flow in `commands/marketplace.py` `_configured_lifecycle`:
  1. Prepare with `sources=()`.
  2. Resolve the flags against `draft.inputs.fields` (pure, in a new
     `application/command_line_inputs.py`, since `TransientSecret` is `io` and stays in the
     command).
  3. Copy the answers. Add a `SecretProviderReference(credential_address(owner, id,
     provider=...))` for each secret field named by `--secret-env`, or for each unanswered one
     under `--set-later`, as `consumer_actions.py` does for the TUI. With no available provider,
     refuse by name.
  4. Re-prepare.
  5. On `--yes`, pass `credential_secrets` and `skipped_secrets_as_placeholders`.
- The refusal for unanswered inputs prints the exact flag line for each missing binding.
- The flags are added to `install` and `update`.
- Linux has no provider yet (`MacOsKeychainProvider` only), so `--secret-env` refuses there. That
  is a backlog gap, not this step.
