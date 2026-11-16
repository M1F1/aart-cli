# PYTHON-INSTALLERS-DOCTOR — doctor shows pip and uv as an install runs them

**Status:** implemented; the PR is open. §216 added; D-528; INV-341. Backlog: B-273, B-274.

## Why

A person's Collection install stopped at pip in one MCP's `runtime-dependencies` step and the other
nine members were `not-attempted`. The ordinary view showed `✗ runtime-dependencies` and no cause;
the cause was only in More info or `--json`, and even there it was pip's last line ("No matching
distribution"), not the certificate or proxy failure above it. The same install worked elsewhere,
so the cause was the machine: most likely an index, proxy or CA bundle set in shell variables,
which an install never passes to pip. The owner chose a diagnostic over changing what installs
pass.

## What was done

- `aart_cli/application/python_installers.py` (pure): `is_installer_setting` and
  `ignored_installer_settings` (by name only), `installer_failure` (the cause line, redacted),
  advice per failure kind, `PythonInstallersReadiness` with `needs_attention`, its JSON and its
  doctor lines.
- `aart_cli/io/python_installers.py`: `read_python_installers` runs every probe through
  `run_python_process`, so it gets exactly an install's environment. It reports the pip new
  environments get (`ensurepip.version()`), pip's configuration (`pip config list`, aart-cli's own
  `:env:` lines left out), uv's version, and the ignored names. `check_index` builds a throwaway
  venv from the same interpreter and runs `pip index versions pip` and `uv pip install --dry-run
  --no-cache packaging` in it.
- `aart_cli/io/python_runtime.py`: `_environment` is now `installer_environment` (public, so doctor
  compares against the real thing) and passes `XDG_CONFIG_HOME`; `_execute` reports
  `installer_failure`'s line instead of the last line.
- `aart_cli/commands/doctor.py`, `cli_parser.py`, `cli.py`, `model.py`: the section, the
  `python_installers` JSON key, `--check-index`, and `ok` false when it needs attention.
- `aart_cli/tui_consumer.py`: a failed `runtime-environment` or `runtime-dependencies` step adds
  `pip or uv failed. To see why, as an install runs them: aart-cli doctor --check-index` under the
  member, in either profile.
- `docs/using/consumer-lifecycle-v1.md`: *When pip or uv fails*.

Measured while building it: pip on macOS reads `~/.config/pip/pip.conf` whatever `XDG_CONFIG_HOME`
says; this machine's base interpreter gives new environments pip 22.3.

## Evidence

`tests/python_installers_test.py` (20) and `tests/doctor_python_installers_e2e_test.py` (2):
- Hypothesis: a reported setting is set, is an installer setting and is not passed, and every such
  setting is reported; the reduced environment never holds `PIP_TARGET`/`PIP_PREFIX`/`PIP_USER`/
  `PIP_SRC` and does hold `XDG_CONFIG_HOME`; the failure line is always a printed line (redacted)
  or `(no output)`; a cause anywhere beats a trailing "No matching distribution".
- Examples: real pip and uv certificate output; a missing package; `1.403.0` is not a 403;
  credentials redacted from a proxy line and from pip's configuration and JSON.
- Recorded probes: no venv and no index call without `--check-index`; with it, the venv comes from
  the given interpreter, pip and uv run against that venv, and the venv is gone afterwards.
- `LocalPythonRuntime.install_dependencies` reports the certificate line.
- The hint appears for a failed `runtime-dependencies` step and not for a failed `configuration`.
- The public command: the section and the JSON key from real probes; with a failing check,
  `read_python_installers(check_index=True)`, `ok` false and a non-zero exit.

Targeted mutations, each killed:

| Mutation | Turned red |
|---|---|
| The cause line is never preferred | 6 tests, including the install's failure reason |
| `XDG_CONFIG_HOME` not passed | the reduced-environment property |
| The hint keyed on `applied` instead of `failed` | the hint test |

`make mutants ONLY=aart_cli/application/python_installers.py TESTS=tests/python_installers_test.py`
reported every mutant as a timeout, trivial ones included, after warning about stale cached
results in this worktree; that is the tool's state, not a finding, and is not counted.

Focused: 1982 doctor, runtime, transaction, TUI, CLI and boundary tests pass; `make typecheck`,
`make lint`, `tach check` and ruff format pass. Manual: `doctor` and `doctor --check-index` on this
machine, with an unreachable index in `~/.config/pip/pip.conf` (credential redacted, cause named,
exit 1) and with `PIP_INDEX_URL`/`HTTPS_PROXY` set (both reported as not passed).
