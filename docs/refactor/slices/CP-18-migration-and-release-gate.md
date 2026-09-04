# CP-18 — Migration completion and release gate
Status: VERIFIED (opened 2026-09-03; closed 2026-09-04)

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
ships to others.

### The remaining rows, audited

Each was read against its own words, then against the flow that would break it. Where a claim was
universal it was closed as a property over every CI source — the three workflows, every composite
action, and the three templates `registry init` emits — rather than sampled a job at a time.

| invariant | what was already held | what was added |
|---|---|---|
| INV-072 | the two container shapes run identical steps | **closed:** the only repository variables appearing in *any* conditional are `AART_IMAGE_USERNAME_SECRET` (which shape) and `AART_PAGES` (whether a dashboard is published). The action that runs the gates reads no variable at all, and its gate step carries no condition. So no settings change can switch a check off. |
| INV-073 | credential halves remasked, no log line carries the assembled URL | **closed:** every `secrets.` reference is `secrets[vars.…]`. The one exception is `GITHUB_TOKEN`, which GitHub mints per run and scopes to the instance, so there is no stored secret for a variable to name. |
| INV-074 | runner/container/index defaults, no credentials block by default | **closed:** every absolute URL in every source is the fallback of a variable, in both the expression and the shell spelling. |
| INV-075 | the variable table is complete in both directions | the registry README now names the requirable check, held to the emitted YAML by a drift test. |
| INV-076 | the shared step is the only copy | **closed:** every step in this repository's three workflows is a checkout or a composite action; exactly one inline script remains, the aggregate's own report, and `aggregate_gate_test` executes it under `bash`. The emitted templates are deliberately exempt — they run where no action of this project's is reachable until AART has been fetched, which is what their inline step does. |
| INV-078 | four fetch arms, `gh` pointed at the instance, Pages switchable | **closed:** the only public host named anywhere is `pypi.org`, always as a variable default. |
| INV-079 | version verified against the pin; both shapes identical | carried by INV-072's closed property: no variable changes the verdict, only where the work runs. |
| INV-080 | a skipped gate is named and never on the OK line; the skip is proven rather than assumed | the aggregate names both arms whatever it decides, and both-skipped fails instead of passing. |

### The finding the mutations produced

M18 put a variable on a gate step of the emitted registry workflow, written `- if:` — the inline
spelling of a step condition. The INV-072 test did **not** catch it. It was caught only by the
documentation test noticing an undeclared variable, which is a different claim that a fork writing
the variable onto the page would satisfy. The harvester read lines beginning `if:` and the inline
form begins `- `. Fixed, with the guard test now asserting both spellings.

That is the mutation doing its actual job: not confirming the code, but finding that the test's
reach was narrower than its name.

M21 produced the other finding. `test_nothing_names_github_com` failed on the *unmutated* tree,
because `cut-release` builds the tagger's email as `…@users.noreply.github.com`. The test as first
written overclaimed: INV-078 is about egress, and a committer email is connected to by nothing. It
is now stated over URLs, with that one occurrence pinned so a real `github.com` URL fails
immediately. **B-069** records the enterprise wart — an instance has its own noreply domain — as a
low-severity item explicitly *not* filed under INV-078.

### Targeted mutations (D-091)

| # | mutation | red |
|---|---|---|
| M17 | `if: vars.AART_SKIP_GATES != 'true'` on the gate run | both INV-072 tests |
| M18 | `- if: vars.AART_AUDIT != 'false'` on an emitted gate step | `test_no_variable_outside_the_two_infrastructure_switches_gates_anything` (after the harvester fix; **survived it before**) |
| M19 | `secrets.ACME_NEXUS_CREDENTIALS` in place of `secrets[vars.…]` | `test_no_workflow_names_a_secret_it_was_not_told_the_name_of` |
| M20 | a hardcoded index host in `pip-index` | `test_every_absolute_url_is_a_variable_default`, `test_the_only_public_host_is_the_package_index` |
| M21 | a `curl https://api.github.com/meta` step | all four URL tests |
| M22 | a third-party action added to a workflow | `test_every_step_is_a_checkout_or_a_composite_action`, `test_the_two_shapes_run_the_same_steps` |

### Status

**Step 2 is VERIFIED.** INV-072 through INV-080 all move PARTIAL → EVIDENCED.

---

## Step 3 — legacy removal (DONE)

Begun by Codex, which removed seven production modules and the five test files that existed only to
drive them — `application/compiler.py`, `compatibility.py`, `fp.py`, `hashing.py`, `io/cache.py`,
`policy.py`, `registry_publication.py`, −2552 lines — and added
`tests/legacy_authority_reachability_test.py` as the evidence.

That test is the right shape for this step. It builds the import graph from `agent_artifacts.cli`
and `agent_artifacts.__main__`, and asserts by `assertEqual` on an exact set that every shipped
module is reachable or named as an exception. Its premise is the one the step needs: a production
module reachable only from tests is not evidence of shipped behaviour, it is parallel authority
whose callers have already disappeared.

### What was left red

Codex hit its weekly limit mid-step and the tree was **not** green when it stopped. Two failures:

- `tests/compiler_boundary_test.py` still named `application/compiler.py` among the three files it
  holds to a no-durable-IO boundary, so the deletion turned it into a `FileNotFoundError`. Narrowed
  to the two `compiler/` files that survive and are really imported by the marketplace, catalog and
  installation paths, with an existence assertion so the same failure cannot recur silently.
- `docs/testing/PLAN-live-acceptance-v1.md` linked to the deleted `io/cache.py` for its claim that
  overriding `HOME` isolates the object cache. The claim is still true and now belongs to
  `configuration/paths.py`, so the link was repointed rather than dropped — and repointing it
  surfaced a real gap in the plan's isolation: `XDG_CACHE_HOME` takes precedence over `HOME` in that
  derivation, so a shell exporting it leaves the cache pointing at the real one while every other
  path moves. That is exactly the shape that makes an offline scenario pass for the wrong reason,
  and the plan now says to unset it along with `XDG_CONFIG_HOME` and `XDG_DATA_HOME`.

### The finding that kept the step open

The exception list holds **six** names while the docstring justified **two**. The other four —
`domain/ports.py`, `domain/outcomes.py`, `domain/collections.py`, `profiles/loader.py` — are
production modules no runtime path reaches, imported only by tests, which is precisely the
definition the docstring opens with. They were listed to keep the set exact, not because a decision
was made about them, and the docstring said "two exceptions remain deliberate" while the code said
six.

The docstring now states a reason per name and says outright that those four are unexamined.
**B-070** carries the decision. Each is one of: legacy to remove, the intended kernel that something
else currently duplicates (in which case the duplicate is the legacy), or a genuine build exception
like `_commit` — and telling them apart needs step 2's audit method, not a guess at the end of a
budget window. `domain/collections.py` is generic immutable helpers, unrelated to B-067's Collection
capability despite the name.

### Targeted mutations (D-091)

| # | mutation | red |
|---|---|---|
| M23 | add a production module nothing imports | `test_only_deliberate_non_runtime_modules_are_shipped` |
| M24 | drop one name from the exception list | the same test, from the other direction |

The `assertEqual` on an exact set is what makes both directions fire: an unreachable module that
appears, and an exception that stops being needed, are both drift.

### B-070 decided: the four verdicts, and what they cost to reach

The audit asked one question of each module — *what shipped thing answers the question this module
claims authority over?* — and got four different answers.

| module | answer | verdict |
|---|---|---|
| `domain/ports.py` | thirty other `Protocol` classes, none the generic pair | **removed** |
| `domain/collections.py` | nothing; the sorted helpers had no caller at all | **removed** |
| `domain/outcomes.py` | `reporting/model.py`, which has a `no-op` state the enum lacks | **kept** |
| `profiles/loader.py` | *nothing does* | **kept** |

The two kept modules are the interesting half, because both were removed first and both removals
were wrong for reasons the reachability graph cannot express.

**`domain/outcomes.py` — authority by path (D-154).** Deleting it turned the unit gate red ten
tests deep inside `shutil.copy2`, with a bare `FileNotFoundError` and no hint that a *release
contract* was what broke. `scripts/release.py:31` declares `SCHEMA_INPUTS`, a hand-maintained tuple
of paths the release contract hashes, and this module is one of them — its sha256 pinned in fifteen
issued `docs/release/schema-freeze-v*.json` documents including the live v18, which
`scripts/release.py:22` declares immutable. Retiring it is a new `RELEASE_CONTRACT_VERSION` with its
own freeze, not a cleanup, so it stays and B-071 carries the retirement.

Two claims now hold that gap in the unit gate, in `tests/release_test.py`: every declared schema
input exists, and the issued freeze covers exactly the declared path list. Paths only, deliberately
— freeze *hashes* are release-time evidence and legitimately drift mid-cycle (three inputs drift
from v18 on this branch right now), which `make release-check` is where to answer.

A third attempt at the same lesson failed instructively: a docstring was added to the top of
`domain/outcomes.py` warning the next reader not to delete it, and that edit changed the file's
sha256 and broke the very freeze it described. A file pinned by content cannot carry the note
saying it is pinned by content. The note lives in D-154 and B-071.

**`profiles/loader.py` — an unwired invariant (D-155).** Every surface signal said legacy: no
runtime importer, three test-only consumers, and the Product Specification never says the words
"profiles.json" — the overlay appears only in `docs/design/DESIGN.md` and `docs/plan/PLAN.md`, which
CLAUDE.md classes as historical evidence rather than authority.

INV-001 reverses it. "Enterprise-specific artifact definitions, policy values, profiles ... live
outside the public tool", and the private layout the specification draws holds a `profiles/`
directory of per-tool files. A profile living outside the public tool needs a mechanism to get in;
`profiles/loader.py` is the only one in the tree, and `profiles/builtin.py` is its opposite. The
finding is therefore not a dead module but a capability gap worth more than the deletion would have
been: **nothing calls it**. `consumer/runtime.py:947` passes `builtin()` straight into the
`ConsumerContext`, so a project's `.agent-artifacts/profiles.json` is parsed by three test files and
ignored by the product. INV-001 is unsatisfied, not merely untested — B-072, and step 5 must not
mark that row covered by the module's mere existence.

### Targeted mutations, second round (D-091)

| # | mutation | red |
|---|---|---|
| M26 | delete a module named in `SCHEMA_INPUTS` | `test_every_declared_schema_input_is_a_file_in_the_tree`, with the message naming the release contract |
| M27 | drop one entry from `SCHEMA_INPUTS` | `test_the_frozen_document_covers_exactly_the_declared_inputs` |

### Status

Step 3 is **DONE**. Seven modules removed by Codex plus two decided here, two kept with recorded
reasons and backlog items, the reachability exception list carrying a justification per name, and
two new claims holding the release contract's declared inputs. Full quality suite (nine gates) and
the integration gate green at `d055796`.

**The rule the step produced, for steps 4–6 and after.** An unreachable module is *replaced*,
*unadopted*, or *unwired* — and only the middle case is safe to delete. Unreachability is a reason
to ask whether a module is legacy, never on its own an answer, because the import graph is silent
about every consumer that addresses a file by path and about every capability an invariant requires
but nothing has yet wired.

Steps 4–6 remain: docs reconciliation, traceability completion for the other 121 PARTIAL rows, and
the closing gates.


## Step 4 — docs reconciled with the Product Specification (DONE)

Steps 1-3 were each decided by mechanical comparison against a shipped artefact — the import graph,
the emitted YAML, the release contract's declared inputs. Step 4 applies the same method to prose: a
document that names a command is making a checkable claim about `cli.build_parser()`.

### Both directions, because they fail differently

A command the README invents wastes a reader's time at the shell. A command the README omits is
capability nobody can find — and it is the one a reading pass never finds, because nothing on the
page is wrong.

The omission was **`aart doctor`**: the whole of CP-16, three verified steps, an entire top-level
command, documented nowhere in the README. It now has a section covering what one read reports, the
three separate offline answers, the review-then-confirm repair boundary, and D-150's rule that what
it cannot repair it still reports.

The first draft of the test was right for the wrong reason: requiring a backticked `` `aart <name> ``
spelling made it report five commands the README documents perfectly well inside fenced shell blocks.
A test that mixes true findings with false ones teaches the next reader to skim it.

### The same comparison, applied to the product's own strings

A diagnostic's remediation is documentation read at the worst possible moment, and it drifts the way
a page does with nobody to notice. Every `aart <group> <subcommand>` in every user-facing string in
the package resolves against the real parser. That was already true; it is now a claim rather than a
coincidence. The check is deliberately scoped to the two-token shape, because bare `aart <word>` also
matches the managed-block marker `# >>> aart setup: ... >>>` and prose like "aart installs".

### What the sweep found beyond the README

| document | finding |
|---|---|
| `docs/tutorials/direct-source-v1.md` | flat 0.1 verbs `aart status`, `aart check`, `aart update`, `aart uninstall`, plus a pinned wheel version in a literal |
| `docs/tutorials/company-registry-v1.md` | a `1.0.0` in the title, a version this repository is not at |
| `docs/installation/canonical-setup-v1.md` | "legacy `aart setup` remains available during the staged 0.1.x migration" — already recorded as replaced in `compatibility-v8.md` |
| `docs/state/installation-state-v2.md` | opens "records the **implemented** STATE01/MIG01 boundary", then describes a migration service that does not exist |

The state document was the largest. It describes `prepare`/`apply`/`rollback`, a
`LegacyMigrationCandidate`, an `aart migrate state` command surface and two `state-migration-*`
diagnostics — none of which are in the package. What ships is the opposite:
`install_state/schema.py` detects the retired envelope and *refuses* it with `install-state-legacy`,
remediation "not converted at runtime". Its schema, path and transaction sections remain accurate, so
it is bannered rather than deleted.

Deliberately **not** reconciled: `CHANGELOG.md` and `docs/release/compatibility-v*.md` name retired
verbs because recording their retirement is their job, and the Product Specification's
`aart registry policy-check`, `refresh-upstreams` and `sync` appear under "Suggested flow" and
"Possible maintainer-side vocabulary" — illustrative, not mandates, and therefore not capability
gaps. Recorded here so the next agent does not re-chase them.

### The three root files, which is what a newcomer opens first

`PLAN.md`, `PROGRESS.md` and `TODO.md` are the completed `M1F1/agent-artifacts` 1.0 program, cited 75
times between them, and `TODO.md` opened by stating its GitHub issues "remain the source of truth for
discussion and status" — pointing at a repository the execution contract names as legacy. CLAUDE.md
classifies them correctly, which does nothing for a reader who never opened CLAUDE.md. They now say
it themselves, and a test holds both halves.

### Targeted mutations (D-091)

| # | mutation | red |
|---|---|---|
| M28 | rename `aart doctor` out of the README | `test_every_shipped_top_level_command_is_named` |
| M29 | write `aart marketplace reinstall` into the README | `test_the_readme_invents_no_command` |
| M30 | strip a root file's historical banner | `test_a_root_document_citing_the_legacy_program_says_it_is_historical` |
| M31 | restore the wrong-source-of-truth sentence | `test_no_root_document_sends_a_reader_to_the_legacy_issue_tracker_for_status` |
| M32 | point a real remediation at `aart marketplace migrate` | `test_no_user_facing_string_names_a_subcommand_that_does_not_exist` |

### Status

Step 4 is **DONE**. Nine quality gates green.

**What this method cannot do, which is step 5's subject.** It compares *names*. A page whose every
command exists can still describe behaviour those commands do not have, and no parser comparison
will say so. The remaining PARTIAL traceability rows are where that gets answered.

---

## Step 5 — traceability complete for all mandatory invariants

The matrix opened this step at 121 PARTIAL. It now stands at **209 EVIDENCED / 8 PARTIAL /
25 CONFLICT**, and the eight remaining PARTIALs are the honest ones: each names a flow that does not
exist yet, with a backlog item, rather than a stage of work somebody has not got to.

### The method, which is the reusable part

Read the invariant's own words. Find the flow that would break it. *Then* look for a test. Not the
reverse. Reading the tests first produces rows that cite whatever is nearby, which is how the ten
TUI rows came to share one copy-pasted verdict between them.

Roughly half of what looked like missing work was stale bookkeeping — the claim was held, by a test
nobody had connected to it — and roughly half was a real gap. Both halves matter. Recording the
first is most of the value; the second is where the tests below came from.

### What the audit was measuring against

Not coverage. A line that ran is not a line whose behaviour anything asserts, and the two gaps that
mattered most this step were both in code that every suite executed on every run:

- `render_ready(view, VERBOSE)` returns `_verbose_plan(view)`, so `install` printing a plan and the
  shell drawing screen 09 are the same bytes. That is INV-061 — "one core, multiple skins" — made
  checkable, and nothing asserted it. Both paths were exercised constantly; nothing compared them.
- `configured_offers.py` declines a referenced version by name and `configured_installation.py`
  refuses to materialise one. Both lines ran. Neither refusal was asserted, so the seam that keeps
  unverifiable content out of the Marketplace could have been deleted in silence (INV-025).

### The four new layer claims

| file | invariant | what it makes impossible |
|---|---|---|
| `tui_boundary_test.py` | INV-062, INV-064, INV-066, INV-068 | a screen module that imports infrastructure, reaches `io/` outside the one declared seam, imports dynamically, branches on the host platform, or needs a terminal to import |
| `presentation_is_not_semantics_test.py` | INV-149, INV-152, INV-158 | any module under `domain/`, `security/`, `configuration/`, `installation/` or `application/` naming a presentation profile at all |
| `consumer_properties_test.py::OneCoreTwoSkinsTest` | INV-061 | screen 09's Verbose half drifting from the reviewed plan |
| `traceability_matrix_test.py` (extended) | the matrix itself | a row citing a test case that is not in the file it names |

The first two are reachability claims rather than behavioural ones, and that is the point. The
behavioural half of INV-158 was already held — switching the profile provably changes nothing — but
two branches that happen to agree pass every property test there is. What was missing was that the
preference is not *there* to be consulted.

### Targeted mutations (D-091)

| # | mutation | red |
|---|---|---|
| M44 | `import subprocess` in `tui_marketplace.py` | `test_no_screen_module_is_an_implementation_of_infrastructure` |
| M45 | an undeclared `io` import inside a screen function | `test_the_effect_boundary_is_crossed_only_where_it_is_declared` |
| M46 | `import curses` in `wizard.py` | the driver claim, and the headless import for `wizard` and `tui_failures` |
| M47 | `__import__("sys").platform` in a screen | `test_no_screen_module_decides_anything_from_the_platform` **and** the dynamic-import claim |
| M48 | `importlib.import_module` in a screen | `test_screens_import_statically_so_the_sweep_above_can_be_complete` |
| M49 | a `"fast"` literal in `domain/policies.py` | `test_no_deciding_module_knows_what_a_presentation_profile_is` |
| M50 | a `profile` parameter on `project_install_plan` | `test_the_plan_is_built_before_the_profile_is_known` |
| M51 | the profile toggle restricted to one screen | `test_the_way_back_to_the_detail_exists_on_every_screen` |
| M52 | the obtain-from route moved behind Verbose | `test_fast_carries_enough_help_to_obtain_or_construct_the_value` |
| M53 | one line appended to screen 09's Verbose half | `test_the_non_interactive_review_and_screen_09_are_the_same_review` |
| M54 | the referenced-mode decline deleted from the offer seam | `test_a_referenced_version_is_declined_because_the_snapshot_holds_no_content` |
| M55 | the unchanged-candidate reuse branch skipped | `test_a_rescan_of_unchanged_rejected_source_leaves_it_rejected` |
| M56 | a cited test method renamed in the matrix | `test_every_cited_test_case_exists_under_the_name_it_is_cited_by` |

M47 is worth keeping. The first draft of the platform check searched the source text for
`sys.platform`, and a screen carrying `__import__("sys").platform` survived it — while
`view.platform`, the platform arriving as data from the core, has to keep passing. The check is read
off the syntax instead: an attribute on `os`/`sys`/`platform`, or on a dynamic import. Text search
found a word; the invariant is about a dependency.

M55's second form is the more interesting failure. Re-deriving a rejected candidate as `CHANGED` is
not merely caught by the test — the domain refuses to construct it, because only a rejected
candidate may carry a rejection reason. A state that cannot be laundered even by code that tries is
a stronger guarantee than a test that notices afterwards.

### The eight rows still PARTIAL, and why each one is

| row | the flow that does not exist |
|---|---|
| INV-001 | **B-072**: nothing calls `load_profiles`, so no externally-defined profile can enter the tool (D-155) |
| INV-057 | **B-074**: dependants are computed and reported, but no public verb deletes, replaces or rebinds a credential |
| INV-067 | **B-075**: `WizardInputKind` is navigation only; no screen collects an input value, so the UI clause has no surface |
| INV-069 | a process rule with no runtime witness — the evidence is CP-13 and CP-14 having replaced screen structure rather than preserving it |
| INV-123 | **B-073**: the fast path exists; no live smoke scenario runs in CI and there is no deep-quality workflow |
| INV-164 | **B-076**: two artifacts declaring one input id project two identical rows, and no input view carries its dependants |
| INV-187 | CP-14: the catalog sweep is over `ConsumerScreen`; the maintainer catalog is still being accepted |
| INV-213 | **B-067**: the identity half is closed, but no Collection can be installed, updated or repaired yet |

None of these is a row somebody forgot. Each is a measurement.

### The release-model block

The 25 CONFLICT rows, INV-081 to INV-105, were one block rather than 25 independent fixes. Release
Please is now the sole version/changelog authority. The retired manual cut workflow and its version,
changelog and preparation scripts are gone; the reviewed squash title is validated as the semantic
input; the generated release PR remains the explicit human-controlled boundary; and release CI
checks the built wheel against the tag instead of reconciling source-tree copies of a version.

Six decisions carry the shape:

- D-160 leaves one version literal and makes every other release mention an engine-written output.
- D-161 keeps issued schema freezes immutable and reads their release identity as recorded data.
- D-162 makes the wheel the subject of release verification: filename, metadata, dependency
  metadata, clean install, `aart --version` and `aart --help` all have to agree with the tag.
- D-163 calls the release workflow directly after Release Please creates a release, because events
  produced with `GITHUB_TOKEN` do not recursively start another workflow.
- D-164 derives the accepted Conventional Commit types from the Release Please configuration.
- D-165 gives mutation testing an explicit, manually scoped deep-quality workflow rather than an
  arbitrary schedule or a mandatory fast-PR cost.

The matrix therefore stands at **234 EVIDENCED / 8 PARTIAL / 0 CONFLICT**. The eight PARTIAL rows
remain the measured absent flows listed above; none is release bookkeeping left unfinished.

### Release-model mutation evidence

Three deliberate mutations held the critical claims independently:

| # | mutation | red |
|---|---|---|
| M57 | remove `fix` from the committed patch-type mapping | `test_the_semver_step_is_the_committed_mapping` |
| M58 | let a wheel carrying `Requires-Dist` pass | `test_a_wheel_that_declares_a_runtime_dependency_is_refused` |
| M59 | replace the artifact verifier in the release action | `test_the_release_run_proves_only_what_has_the_release_as_its_subject` |

A fresh scoped mutmut run over `scripts/release_artifact.py` generated 373 mutants: 174 were killed,
four survived and were inspected as equivalent/cosmetic changes (`utf-8`/`UTF-8`, two renderings of
one diagnostic, and `partition`/`rpartition` on the already selected single-colon header), and 195
belonged to the real-environment/CLI wrapper deliberately outside the focused unit executor. The
actual closing artifact gate executes that wrapper against the built wheel.

That run also found a defect in the mutation runner itself: `ONLY=scripts/...` still copied only
`agent_artifacts`, producing zero mutants and an import failure. `scripts/mutants.py` now derives the
top-level source roots from the requested repository-relative paths, with tests for single-root,
multi-root and unsafe scopes. Fully qualified `scripts.*` imports make the original and mutated
module identities agree.

### Status

Step 5 is **VERIFIED**. INV-081 through INV-105 move CONFLICT → EVIDENCED.

---

## Step 6 — closing gates

The deep-quality workflow made B-068 critical: an unattended job now invokes mutmut, so declaring
it without locking it would make the workflow fail before measuring anything. The Poetry lock was
regenerated rather than edited. mutmut 3.7 and its Textual dependency carry a dev-only
`python >=3.10,<4.0` marker because Textual does not claim Python 4 support while AART's runtime
range intentionally leaves that future major open. Nothing enters the zero-dependency runtime.

Closing evidence on the finished implementation:

- `make quality`: all nine gates green; 3,321 tests, one skipped; 85.35% branch coverage; packaging,
  documentation and secret-shape checks included.
- `make integration`: all 343 public E2E tests green.
- `python scripts/build_wheel.py && python scripts/release_artifact.py --tag v0.0.1`: the built
  `aart_cli-0.0.1-py3-none-any.whl` passed metadata, zero-runtime-dependency and clean-install smoke
  verification against the tag.
- `poetry check --lock`: the regenerated dev-tool lock is internally consistent.

Step 6 and **CP-18 are VERIFIED**. The mandatory execution plan is complete. The eight remaining
PARTIAL traceability rows stay honest, explicitly named capability/process gaps in BACKLOG rather
than hidden release work.
