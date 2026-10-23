# CP-39 — A fork labels its wheel's version, so it never shares a filename with PyPI

Status: **done**, on `feat/cp-39-local-version-label`, at the owner's request (2026-10-23).
Authority: Product Specification §193, INV-294, D-476.

## Steps

See `docs/refactor/plan.json`, epic CP-39.

1. `AART_CLI_LOCAL_VERSION_LABEL` labels the wheel's version, and the release checks and records
   it (§193, INV-294, D-476). Done.
2. Focused verification and the PR. Done: one PR, which ships as 0.17.0 when it merges.

## Step 1 — The fork's wheel gets a filename of its own

**Why.** The owner holds `aart-cli` on PyPI and will publish the public release there. The
Enterprise fork bakes its default Registry, so its `aart_cli-X.Y.Z` differs from the public file of
the same name. A Nexus group that proxies PyPI would list both. `publish-index` refuses the fork's
upload, and a person installing from the group may receive the public wheel.

**Change.**
- `scripts/inject_local_version.py` (new). It reads `AART_CLI_LOCAL_VERSION_LABEL` and writes
  `X.Y.Z+<label>` into the `[project]` version of `pyproject.toml`. Unset leaves the file byte for
  byte. It is idempotent. A label outside the grammar exits non-zero and writes nothing.
- `.github/actions/release/action.yml`: a step `Inject local version label` runs before the build.
- `.github/workflows/release.yml`: both release jobs pass `AART_CLI_LOCAL_VERSION_LABEL`.
- `scripts/release_artifact.py`:
  - `distributed_version(tag, label)` gives the version the build should carry;
  - `verify_artifact` takes `label`, and `main` reads it from the environment;
  - the smoke test still expects `aart-cli --version` to report the tag.
- `scripts/release.py`:
  - `local_version_label_value()` goes into the receipt as `local_version_label`;
  - `wheel_digest` stamps each injector's target at its path relative to the root.
- `aart_cli/commands/upgrade.py`: `upgrade --wheel` accepts a labelled filename.
- Docs:
  - rollout Part 2 step 4 sets the label before the next tag;
  - step 5 installs from the hosted repository;
  - the variable reference has the new variable;
  - `docs/ci/workflows-v1.md` explains how the public repository publishes to PyPI.

**Tests.**
- `tests/release_local_version_label_test.py`:
  - unset leaves the file, including the committed `pyproject.toml`, byte for byte;
  - only the project version moves;
  - stamping twice is stamping once;
  - Hypothesis: every accepted label is a PEP 440 local version, equal as written, and `==`
    prefers it;
  - Hypothesis: whatever `label_from` accepts is a valid local version;
  - malformed labels fail and write nothing, including `00` and `corp.01`;
  - the release check expects the label, refuses a wheel with the label when none was set, and
    refuses one without it when one was;
  - the receipt records the label;
  - `upgrade` takes a labelled wheel.
- `tests/release_default_registry_injection_test.py`: the injector set includes the new script,
  and a target may be `pyproject.toml`.
- `tests/enterprise_ci_template_test.py` (existing): the rollout page names the new variable.

**Evidence beyond the unit tests.** `release.wheel_digest` with `AART_CLI_LOCAL_VERSION_LABEL=corp`
built `aart_cli-0.15.0+corp-py3-none-any.whl` with poetry-core. `scripts/release_artifact.py --tag
v0.15.0` passed it, including the clean-environment install and `aart-cli --version` = `0.15.0`. The
checkout's `pyproject.toml` stayed unchanged.

**Targeted mutations.**
- `distributed_version` ignoring the label turned the two labelled-release tests red.
- A grammar allowing leading zeros turned the `00` and `corp.01` refusals red.

**Hypothesis finding.** The first grammar allowed `00`, which PEP 440 normalises to `0`. The wheel
would have been named differently from the variable. The grammar now refuses it.
