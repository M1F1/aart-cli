# Development dependencies and what the quality gates run

**The installed runtime has no dependencies.** `dependencies = []` in `pyproject.toml`, standard
library only — that is a design rule, not an accident, and the gates below exist partly to keep it
true. Everything in this section is developer and CI tooling that a user of `aart` never installs.

Install them into a virtual environment, so nothing lands in the system interpreter:

```sh
python3 -m venv .venv
```

```sh
source .venv/bin/activate
```

```sh
poetry install --with dev
```

Or, with pip and no Poetry — which is what CI runs:

```sh
python scripts/dev_tools.py install
```

Both install the same versions: Poetry decides what they are, in `pyproject.toml` and
`poetry.lock`, and `scripts/dev_tools.py` carries the lock's pins to pip. The second route exists
because Poetry cannot be pointed at a per-fork internal index — it takes an install source only
from a block inside `pyproject.toml` — while pip reads `PIP_INDEX_URL` and always could. Behind an
internal index, set `PIP_INDEX_URL` and use the second command.

`.venv/` is already in `.gitignore`. Activate it in every new shell before running the gates or
`scripts/packaging_check.py`; `deactivate` leaves it. If `python3 -m venv` fails with an
`ensurepip` error, that interpreter's venv support is broken — use another one, for example
`python3.11 -m venv .venv`.

Without these tools six of the ten gates cannot run. `scripts/quality.py` says so before it starts,
names the ones that are missing, and prints the install command; the other four — `unit`,
`integration`, `validate`, `docs-check` — need nothing but Python and can be run on their own.

| Package | Constraint | Used for |
|---|---|---|
| `ruff` | `0.16.4` | formatting and linting — the `format-check` and `lint` gates. Pinned exactly: a formatter that changes its mind between two versions fails the gate on a file nobody edited |
| `mypy` | `^1.11` | the `typecheck` gate |
| `coverage` | `^7.6` | the `coverage` gate, branch coverage with `fail_under = 82` |
| `poetry-core` | `2.4.0` | the build backend, at the exact version `[build-system]` pins. Present in the environment so an offline editable install has a backend to build with |

Tests are **stdlib `unittest`** — there is no test-runner dependency. The wheel is built by
Poetry, wrapped by `scripts/build_wheel.py`; see
[docs/release/wheel-reproducibility-v1.md](../release/wheel-reproducibility-v1.md) for what that
wrapper holds and why building now needs Poetry on the machine.

## The ten gates

`python scripts/quality.py` runs all ten, each in a temporary cache directory with
`PYTHONDONTWRITEBYTECODE=1`, stopping at the first failure. `make quality` is a wrapper around
the same script; CI calls the script directly, because a CI image is not obliged to carry GNU Make
and a real one did not. Run a single gate with `make <gate>`.

| Gate | Command | Depends on |
|---|---|---|
| `format-check` | `ruff format --check aart_cli tests scripts` | `ruff` |
| `lint` | `ruff check aart_cli tests scripts` | `ruff` |
| `typecheck` | `mypy` | `mypy` |
| `unit` | `unittest discover -s tests -p "*_test.py"` | stdlib |
| `integration` | `unittest discover -s tests -p "*e2e_test.py"` — drives the real CLI over real trees | stdlib |
| `validate` | `scripts/validate.py` | stdlib |
| `coverage` | `coverage run --branch --source=aart_cli` over the unit suite, then `coverage report` | `coverage` |
| `packaging-check` | `scripts/packaging_check.py` — builds the wheel and inspects it | stdlib |
| `docs-check` | `scripts/docs_check.py` | stdlib |
| `secret-shape-check` | `scripts/secret_shape_check.py` — refuses credential-shaped literals anywhere in the tracked tree, so the repository stays pushable to an instance with push protection on | stdlib |

Four of the ten — `unit`, `integration`, `validate`, `docs-check` — need nothing installed beyond
Python itself.

One more gate exists that the full run does not include:

| Gate | Command | Depends on |
|---|---|---|
| `release-bump` | `unittest` over the release policy, release, packaging and install-command tests | stdlib |

It is selectable by name and deliberately outside `make quality`, because every module it names is
already discovered by `unit` and the full run would prove one thing twice. It exists for the release
pull request, which is gated on what it changes rather than on everything (INV-096); see
[`docs/ci/workflows-v1.md`](../ci/workflows-v1.md).
