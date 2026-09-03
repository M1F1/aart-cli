# CP-18 — Migration completion and release gate
Status: IN PROGRESS (opened 2026-09-03)

## Goal

`EXECUTION_PLAN.md` names six obligations: remove only legacy code whose authority has been replaced
and verified; reconcile docs with the Product Specification; complete traceability for all mandatory
invariants; run the full quality + packaging + security + mutation/deep acceptance gates; confirm
zero runtime dependencies; and prepare the release workflow according to the accepted release model.

## What is already covered, and what this slice is actually for

The survey matters here for the same reason it mattered in CP-17. Read the traceability table alone
and CP-18 looks like eleven untouched invariants (INV-071 through INV-080 plus the migration rows).
Read the tests and most of that is already built:

- **The CI profile contract exists.** `enterprise_ci_template_test.py` holds forty-odd assertions
  over the emitted workflows: every `pip` install points at the configured index first (INV-078);
  every variable a workflow reads is on the documentation page and the page lists none that nothing
  reads (INV-075); the container switch is exclusive and its default shape carries no credentials
  block (INV-074); both halves of an index credential are remasked and no log line carries the
  assembled URL (INV-073); every fetch arm ends at the same check and the git arm is the `else` so
  it cannot be reordered (INV-080).
- **The release model is asserted.** `release_workflow_test.py` proves the release run proves only
  what has the release as its subject, does not re-prove the same tree twice, follows the tag rather
  than pinning one release, and that publishing to an index is optional, credential-named-by-variable
  and installs no publishing tool.
- **Zero runtime dependencies is asserted twice.** `dev_tools_test.py::test_the_runtime_declares_no_
  dependencies_at_all` reads `[project] dependencies` out of `pyproject.toml`;
  `scripts/packaging_check.py` builds the wheel and refuses any non-extra `Requires-Dist`.

So the eleven PARTIAL rows are, for the most part, **stale bookkeeping rather than missing work** —
the same finding CP-15 opened on. What the slice is actually for is the gap those tests leave, the
legacy whose authority is now genuinely replaced, and the honest reconciliation of the table.

## Steps

1. **INV-071 evidenced by the source tree rather than by its declaration.** (below)
2. Audit the remaining CI/release rows (INV-072–080) against the tests that already hold them; mark
   EVIDENCED where a public flow proves the claim, and open a step for each that is genuinely unheld.
3. Legacy removal audit: only code whose authority has been replaced *and verified*.
4. Docs reconciliation against the Product Specification.
5. Traceability completion for the mandatory invariants.
6. Full quality + packaging + security + deep acceptance gates as the closing evidence.

---

## Step 1 — INV-071 evidenced by the source tree rather than by its declaration

**INV-071:** *Development verification tooling (Hypothesis, pytest, mutmut, ruff, mypy, coverage)
MUST remain outside the production/runtime dependency graph.*

### The gap

Two checks already exist and neither one holds this claim.

`dev_tools_test` reads `[project] dependencies` and asserts it is `[]`. `packaging_check` builds the
wheel and refuses a `Requires-Dist`. Both are true and both are worth keeping — but both are
statements about a **declaration**, and INV-071 is about a **dependency graph**. A declaration is
not a dependency graph. A runtime module that does

```python
def _plan(...):
    import hypothesis  # inside the function body
```

declares nothing, adds no `Requires-Dist`, ships inside the wheel, and violates the invariant on the
first call — while every existing check stays green. That is not a hypothetical: it was measured.

### Evidence that the gap is real

Mutation **M10** inserted exactly that import into `agent_artifacts/application/installed_state.py`,
inside a function body, and ran the checks that are supposed to cover INV-071:

| check | with the leak present |
|---|---|
| `tests/dev_tools_test.py` + `tests/packaging_test.py` | 36 passed, 1 skipped — **green** |
| `scripts/packaging_check.py` (builds and inspects the wheel) | `packaging check OK` — **green** |
| `tests/runtime_purity_test.py::test_no_runtime_module_imports_a_development_tool` | **red** |

The absence assertion is evidence because the alternative was reachable and the incumbent checks
walked past it.

### What the test does

`tests/runtime_purity_test.py` parses every module under `agent_artifacts/` with `ast` and asserts
none of them imports a development tool, or the test suite, or the gate scripts.

Two choices carry the claim:

- **The forbidden set is derived, not hardcoded.** It is read out of Poetry's dev group at test time
  (`ruff`, `mypy`, `coverage`, `hypothesis`, `mutmut`, `poetry-core`), so a tool added to the group
  tomorrow is covered without anyone remembering to extend a literal. `poetry-core` is mapped to its
  import name `poetry`; names are normalised `-` → `_`.
- **`ast`, not import-time introspection.** Walking `sys.modules` after importing the package sees
  only what module-level import statements pulled in. The case that matters most — a tool imported
  inside a function body, which is how such a leak would realistically be written and the only shape
  that defeats both incumbent checks — is invisible to that approach and plain to `ast`.

Three of the five tests are guards on the machinery rather than on the package, because an absence
assertion that reads an empty tree passes for the wrong reason (D-149):
`test_the_dev_group_is_known_and_not_silently_empty` fails if the forbidden set is empty,
`test_the_package_really_is_the_tree_being_read` fails if fewer than 100 sources are found, and
`test_the_shortcut_reads_the_table_it_names_and_stops_at_the_next_one` holds the manifest parser.
Without them, a rename of `agent_artifacts/` would turn this file into green tests that assert
nothing.

### The portability defect the first draft carried

The first draft read the dev group with `tomllib`, and `mypy` refused it:

```text
Cannot find implementation or library stub for module named "tomllib"
```

That is not a stub gap. `requires-python` is `>=3.10` and `[tool.mypy] python_version = "3.10"`,
where `tomllib` does not exist — it arrived in 3.11. `dev_tools_test`'s own module docstring
records the same constraint for `poetry.lock` and answers it with a hand parser, guarding it with
`test_the_hand_parser_agrees_with_tomllib` skipped below 3.11.

An INV-071 test that only runs on some supported interpreters is the wrong shape for this
invariant in particular, so the dev group is now read by `_table`, a flat-table shortcut that takes
each key up to the next `[` header. The shortcut is the one part of the file that could quietly read
the wrong thing, so it is held directly: it must take every key of the table it names, stop at the
next table, and return nothing for a header the manifest does not carry — which the emptiness guard
then catches.

### Targeted mutations (D-091)

**M10** — insert `import hypothesis` into a function body in
`agent_artifacts/application/installed_state.py`.

Result: `test_no_runtime_module_imports_a_development_tool` red —
`AssertionError: Lists differ: [] != ['agent_artifacts/application/installed_state.py imports
hypothesis']`. The other four green.

**M11** — delete the `if stripped.startswith("["): break` line, so the shortcut runs past the table
it was given into the next one.

Result: `test_the_shortcut_reads_the_table_it_names_and_stops_at_the_next_one` red —
`['first', 'second'] != ['first', 'second', 'third']`. The other four green, including the
dev-group guard, because the next table in the real `pyproject.toml` happens to add keys that are
not import names — which is exactly why the parser needed a claim of its own rather than being
covered incidentally.

Both mutations discriminate: each turned red only the test that states the claim it breaks.

### A discrepancy found while sourcing the forbidden set

Deriving the set turned up that `pyproject.toml` declares `mutmut` in the dev group while
`poetry.lock` carries no entry for it, so `scripts/dev_tools.py::requirements("dev")` — the list a
provisioned environment installs from — omits it, and `make mutants` cannot run there at all.
Recorded as **B-068**; not critical, since mutation adequacy is advisory by contract (D-134) and no
gate command names the tool. Not fixed here: regenerating the lock is not this step's subject.

### Status

Step 1: **VERIFIED**. INV-071 moves PARTIAL → EVIDENCED.

---

## Step 2 — the CI/release rows, audited one at a time

**INV-077:** *Branch protection should depend on one stable aggregate gate name rather than
matrix-specific or environment-specific job names. The aggregate gate MUST fail when no valid gate
arm ran or when any selected arm failed.*

The audit found two different situations under this one invariant.

### `pr-check` was right and untested

`.github/workflows/pr-check.yml` already carries the aggregate correctly: one stable name,
`if: always()`, an explicit failure when both arms are `skipped`, and an allowlist rather than a
check for `failure`. Nothing tested it. `quality_gates_test` covers the matrix default and the
delegation to the composite action — the shell that decides the verdict, which is the one thing
branch protection depends on, was covered by nothing.

`tests/aggregate_gate_test.py` extracts that script from the YAML and **executes it under `bash`**
with each combination of `needs.*.result`. That is INV-076 collecting on its own promise that such
logic stays "runnable/testable outside GitHub Actions when practical": a workflow cannot be run
here, but this part of one can, and grepping YAML for the substrings a correct script would contain
is a far weaker claim than watching it exit 1.

| `gates` | `gates-private-image` | verdict |
|---|---|---|
| success | skipped | pass |
| skipped | success | pass |
| skipped | skipped | **fail** — "neither gate job ran" |
| failure / cancelled | either | **fail** |
| success | failure | **fail** |

Both arms are named in the output whatever the verdict, which is INV-080's visible-evidence half.

### The emitted registry CI had no aggregate at all

`aart registry init` writes a workflow with `registry-quality` and
`registry-quality-private-image` — two container shapes of which exactly one ever runs, each a
matrix over `compatibility: [minimum, latest]`. A registry owner protecting `main` therefore had no
name that is the same in every configuration. Naming an arm their deployment skips is worse than
useless: GitHub counts a skipped required check as *satisfied*, so the rule passes precisely when
nothing was proven. INV-077's failure mode, in a shipped scaffold — a real defect, not a
bookkeeping gap.

`_aggregate()` now emits `registry-quality-gate` beside the two arms with the same verdict logic,
no container and no Python, since the job branch protection depends on must not be able to fail for
a reason unrelated to the gates. The registry README gained a "Protecting `main`" section naming
it, because a stable name nobody is told about protects nothing (INV-075), and a drift test reads
the name out of the emitted YAML rather than repeating the literal.

### Targeted mutations (D-091)

| # | mutation | red |
|---|---|---|
| M12 | delete `pr-check`'s both-skipped branch | `test_no_arm_running_at_all_fails_instead_of_looking_like_a_pass` |
| M13 | widen the allowlist to `success\|skipped\|cancelled` | `test_any_arm_failing_fails_the_aggregate`, both cancelled subtests |
| M14 | drop `if: always()` from the emitted gate | `test_the_template_offers_one_requirable_name` |
| M15 | delete the README section, leaving the workflow intact | `test_the_registry_readme_names_the_check_the_workflow_actually_emits` |
| M16 | give the emitted gate a container | `test_the_gate_needs_no_container_because_it_runs_no_python` |

Each turned red only the test stating the claim it breaks; the other eleven stayed green each time.

### Status

Step 2 for INV-077: **VERIFIED**, PARTIAL → EVIDENCED, for both this repository's CI and the CI it
ships to others. The remaining rows (INV-072, 073, 074, 075, 076, 078, 079, 080) are still to be
audited the same way — read the invariant, find the flow, and only then decide whether an existing
test holds it.
