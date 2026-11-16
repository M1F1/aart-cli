# RUNTIME-DEPENDENCIES-VERIFIED — an MCP's Python packages are checked, not assumed

**Status:** implemented; the PR is open. §217 added; D-529; INV-342. Closes B-029.

## Why

Reported after D-528: an install stopped at pip, was run again, and the MCP servers still could not
start because `mcp` was missing; doctor said nothing, and the reporter warned that a repair could
leave them broken the same way. `runtime-dependencies` counted as installed whenever the
environment existed, and doctor's desired state did not include dependencies at all.

## What was done

- `aart_cli/domain/receipts.py`: `InstallationReceipt.dependencies` (descriptor inside the root,
  kind, installer), written as `dependencies` only when present and read back strictly.
- `aart_cli/application/installation_proposal.py`: `intended_receipt` records the plan's
  dependencies, so a planned install observes them too.
- `aart_cli/io/consumer_machine.py`: doctor, Installed and repair want the recorded dependencies.
- `aart_cli/domain/python_runtime.py`: `requirements_distributions`, `requirement_distribution`,
  `normalize_distribution`, `missing_distributions` (pure).
- `aart_cli/application/installation_verification.py`: `InstallationObservation.missing_distributions`
  (`None` not checked, `()` all present).
- `aart_cli/io/runtime_projection.py`: `observe_installation` reads the descriptor and the
  environment's `site-packages` metadata (`importlib.metadata`, no subprocess); `pyproject.toml`
  through `tomllib`.
- `aart_cli/application/installed_state.py`: missing → `ABSENT` naming them; unchecked → matched,
  detail "packages not checked".
- `docs/using/consumer-lifecycle-v1.md`: running the install again, and doctor's check and repair.

## Evidence

Reproduced red first, through the public commands, with a real venv and real pip installing an
offline hand-built wheel (`tests/runtime_dependencies_verified_e2e_test.py`):
- `test_installing_again_after_pip_failed_runs_pip_again` — was "the second install ran pip: 0 != 1".
- `test_doctor_sees_a_missing_package_and_its_repair_puts_it_back` — doctor said `ok: true` with the
  package deleted.
- `test_a_repair_that_rebuilds_the_environment_installs_the_packages_too` — the rebuilt
  environment was empty.

`tests/runtime_dependencies_test.py`: Hypothesis properties (every plainly named requirement is
found; a file with `-r`/`-e`/URL/path is never complete; any text gives sorted normalized names or
`None` and never raises; missing is declared minus held), pip's option/marker/hash/reference forms,
receipt round-trip and refusal of a descriptor outside the root, and the four judgements.
`tests/runtime_dependencies_test.py` also observes a real directory laid out as an environment:
requirements and `pyproject.toml` against `site-packages` metadata, `-r` and dynamic dependencies
not checked, no recorded descriptor not checked.

Broad regression (every test file touching receipts, installed state, doctor, repair or install):
4547 passed, 1 skipped.

## Targeted mutations (each restored after)

| Mutation | Killed by |
|---|---|
| `installed_state`: a missing package judged matched | the judging unit test; the install-again and doctor e2e tests |
| `intended_receipt` records no dependencies | all three e2e tests' install/repair paths |
| `consumer_machine` ignores the recorded dependencies | doctor-sees-missing and rebuilt-environment e2e tests |
| `normalize_distribution` returns the name unchanged | site-packages comparison; pip-forms example |
| `-r` read past as a source option | the "never reported as complete" property; observation not checked |
| marker-guarded requirement required | pip-forms example |
| receipt accepts a descriptor outside its root | descriptor-outside-the-installation subtest (`/etc/...`) |
| `site-packages` not read (nothing missing) | site-packages and pyproject observation; install-again and doctor e2e tests |
