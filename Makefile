# aart-cli — build & validation tasks (WP-21).
#
# Zero runtime deps. Poetry builds the wheel and installs the developer tooling; nothing it
# installs reaches the runtime, which stays standard-library only. The wheel produced by
# `make wheel` still installs with no index at all:
#     pip install --no-index dist/aart_cli-<v>-py3-none-any.whl

PYTHON ?= python
REGISTRY ?=
QUALITY = $(PYTHON) scripts/quality.py

.PHONY: check test unit integration system-matrix release-freeze release-check wheel validate clean lint format format-check typecheck coverage packaging-check docs-check secret-shape-check quality mutants manual-test-setup manual-test-setup-empty manual-test-reset manual-test-maintainer manual-test-consumer manual-test-shell-maintainer manual-test-shell-consumer live-harness

# Aggregate. The Python discovery is the broad unit/regression gate; integration is end to end.
test: unit integration

unit:
	$(QUALITY) unit

integration:
	$(QUALITY) integration

system-matrix:
	$(PYTHON) scripts/system_matrix.py

release-freeze:
	$(PYTHON) scripts/release.py freeze --write

release-check:
	@test -n "$(REGISTRY)" || (echo "REGISTRY=/path/to/aart-cli-registry is required" >&2; exit 2)
	$(PYTHON) scripts/release.py check --registry "$(REGISTRY)"

# Stamp the git commit, then build the wheel into dist/ with Poetry.
wheel:
	$(PYTHON) scripts/inject_commit.py
	$(PYTHON) scripts/build_wheel.py

validate:
	$(QUALITY) validate

# --------------------------------------------------------------------------- #
# Optional developer tooling. Requires Poetry's dev group:  poetry install --with dev
# These are developer/CI dependencies only; the installed runtime stays stdlib-only.
# --------------------------------------------------------------------------- #
lint:
	$(QUALITY) lint

format:
	$(PYTHON) -m ruff format aart_cli tests scripts

format-check:
	$(QUALITY) format-check

typecheck:
	$(QUALITY) typecheck

coverage:
	$(QUALITY) coverage

packaging-check:
	$(QUALITY) packaging-check

docs-check:
	$(QUALITY) docs-check

secret-shape-check:
	$(QUALITY) secret-shape-check

quality:
	$(QUALITY)

# Mutation adequacy, advisory and always scoped (D-134). A suite that passes proves the code does
# what the tests say; a killed mutant proves the test would have noticed if it did not.
#
#   make mutants ONLY=aart_cli/setup_render.py TESTS="tests/setup_render_test.py"
#
# Survivors are findings to read, not a number to drive to zero. Never weaken a test to move it.
ONLY ?=
TESTS ?=
mutants:
	@test -n "$(ONLY)" || { echo 'usage: make mutants ONLY=<path.py> [TESTS="<test files>"]'; exit 2; }
	$(PYTHON) scripts/mutants.py --only $(ONLY) $(if $(TESTS),--tests $(TESTS),)

# The developer loop: every cheap gate in full, and only the tests the current change could have
# reached. Falls back to the whole suite whenever it cannot prove what is safe to skip, and is
# never the release gate -- run `make quality` before calling work verified.
#   make check              changes against HEAD, plus untracked files
#   make check SINCE=main   the whole branch's diff as well
check:
	$(QUALITY) --changed $(if $(SINCE),--since=$(SINCE),)

# Fresh, marker-bounded manual acceptance. These targets inject HOME/XDG only into the launched
# process; they never ask the operator to export session-global variables.
manual-test-setup:
	$(PYTHON) scripts/manual_test.py setup

# The maintainer-first route: the Registry does not exist yet, so the TUI creates it.
manual-test-setup-empty:
	$(PYTHON) scripts/manual_test.py setup --empty-registry

manual-test-reset:
	$(PYTHON) scripts/manual_test.py reset

# The CLI route: an interactive shell already inside the lab's isolated HOME/XDG.
manual-test-shell-maintainer:
	$(PYTHON) scripts/manual_test.py shell maintainer

manual-test-shell-consumer:
	$(PYTHON) scripts/manual_test.py shell consumer

manual-test-maintainer:
	$(PYTHON) scripts/manual_test.py open maintainer

manual-test-consumer:
	$(PYTHON) scripts/manual_test.py open consumer

# Live harness evidence for installed-MCP smoke verification. Opt-in and local only: it spends a
# real model call and needs a provider that answers, which CI has neither of. Name the harnesses
# whose providers work on this machine, e.g. `make live-harness HARNESS=claude`.
live-harness:
	AART_CLI_LIVE_HARNESS=$(or $(HARNESS),claude) $(PYTHON) -m unittest tests.live_harness_smoke_test -v

# Remove build leftovers (safe: only the dist/ wheels and build/ tree).
clean:
	rm -f dist/*.whl
	rm -rf build
