# CP-27 — one baked default Registry, so a first run starts connected

Status: tasks 1–4 done on `docs/cp-27-default-registry-plan` (PR #40). Task 5, the full
quality/integration/release-facing verification, runs on `pr-check` rather than locally: the owner's
standing rule is that the complete suite is CI's job, and D-317 reserves it for the epic's last task.
Its first run was red on all three interpreters, for one interpreter-dependent seed case; that is
recorded below under *What the matrix found*, and D-374 settles it.

Date: 2026-09-21. Authority: the product owner, asking for issue #39 to be designed rather than
implemented as written — *"niech informacja o urlu do default registry bedzie w github settings ktore
sa parametryzowane w forku i wrzucane do wheela in fly w trakcie releasea?"* — and, on the README,
*"zmiana readme powinna byc po implementacji core feature, testow ze wszystko dziala nie?"*, which is
the sequencing this slice follows. Decision: D-373.

## Goal and scope

A first run has nothing configured. In an Enterprise fork the Registry address it is about to ask for
is the same for everybody and was already known at release time. So a release may carry it: one
Registry, supplied per fork by the repository variable `AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL`
holding `<alias>=<url>`, connected only when nothing is configured.

Out of scope, deliberately: any validation or allowlist of permitted Registry addresses, and the
registry-maintainer contact that shared issue #39's original title. The first was rejected on the
merits (see below); the second is a fact a Registry publishes about itself, not one a wheel carries.

## Why this was five tasks and not fifteen

Neither half of the mechanism was new, and both were read before anything was written.

`aart_cli/_commit.py` is already a generated module: it holds a neutral default in the checkout and
`scripts/inject_commit.py` overwrites it in a *copy* of the tree immediately before Poetry builds
(`scripts/release.py`). `AART_CLI_REFERENCE_REGISTRY_URL` is already a per-fork repository variable
whose own comment explains why it deliberately has no default (D-309). CP-27 adds a second client of
the first and a second instance of the second.

## The four rules, and where each is held

**A default, not a restriction.** The alternative considered and rejected was baking an allowlist.
A wheel is a file on the user's own machine, which they may edit or replace, so an allowlist baked
into it restricts nobody and only resembles security. Authority stays in the machine policy file an
administrator owns. Held by `aart_cli/_default_registry.py`'s docstring and by there being no code
that consults the baked value for permission.

**First run only.** `plan_first_run_seed` refuses unless this is a first run *and* the configuration
names no source. The second check is not implied by the first: a caller holding a
`LoadedConfiguration` assembled another way must not be able to seed over somebody's sources. A
local Registry counts as configured — connecting one is a choice too.

**Failure is not fatal.** An unusable baked value, a refusal from the add transaction, and an
unexpected defect during startup all leave the terminal opening on the same first-run screen it
would have reached with no baked Registry at all.

**It says where it came from.** The person did not choose this Registry, so `tui.run` prints the
alias and URL before the terminal takes the screen, and prints the reason when nothing was connected.

## Evidence

Sixteen targeted mutations, each red then restored, listed with the test each one turned red:

| # | Mutation | Test that failed |
|---|---|---|
| 1 | an alias baked into the checkout | `CommittedSourceBakesNothing` (3 failures) |
| 2 | `and` → `or` on the empty pair | `HalfASeedIsRefused` (2 failures) |
| 3 | `fullmatch` → `match` in the alias grammar | `MalformedValuesAreRefused` |
| 4 | a malformed release value stops failing the build | `MalformedValueFailsTheBuild` |
| 5 | `write` touches the file before rendering | `test_a_refused_value_writes_no_module` |
| 6 | the digest build narrows back to the commit stamp | `test_the_digest_build_applies_every_injector` |
| 7 | the release action drops the new injector | `test_the_release_action_runs_every_injector` |
| 8 | seeding over an existing configuration | `test_a_configuration_that_already_names_a_source_is_never_seeded` |
| 9 | an unusable value becomes an error | `test_it_is_a_warning_rather_than_an_error` |
| 10 | the seeded ref changes | `test_it_is_tracked_at_the_ref_configuration_already_defaults_to` |
| 11 | the caller's home is dropped | `test_it_carries_the_caller_s_home_rather_than_resolving_its_own` |
| 12 | an unexpected defect escapes startup | `test_a_defect_in_seeding_never_stops_the_terminal_starting` |
| 13 | the page paraphrases `SETUP REQUIRED`, or one frame line drifts | `readme_tui_screen_test` (both) |

Mutation 3 **survived its first run**, and the finding was real rather than a gap in the harness:
`_SLUG_RE` is already anchored `^...$`, so the only behaviour `match` adds is accepting a trailing
newline — which is precisely what a release variable set from `echo` arrives with. Pinned
explicitly, then red.

Scoped `make mutants` over `aart_cli/configuration/seed.py`: **37 of 37 killed, no survivors**. The
same run over `scripts/inject_default_registry.py` could not collect — the isolated workspace has no
`.github/`, which the injector-parity test reads. That is B-166 a second time and is recorded there;
no adequacy claim is made for that script.

The strongest single test is not a mutation. `ARegistryThatCannotBeReachedLeavesNothingBehind`
drives the real transaction against a real temporary home and a real `git clone` to a loopback port
that refuses. It costs 0.04 seconds, and afterwards there is no `config.json` — which is the whole
of "leaves no partial configuration when it cannot be used", proven rather than asserted.

`enterprise_ci_template_test` caught the omission that mattered on its own: a variable a workflow
reads must appear on the Enterprise rollout page, and it did not.

## What the matrix found, and no local run could

Task 5's first `pr-check` (run `35566617453`) failed `unit` on Python 3.10, 3.11 and 3.14 with a
single test — `MalformedValuesAreRefused.test_a_location_git_cannot_clone_is_refused`, on the case
`" https://example.invalid/team/registry.git"`. The seed reader returned `Ok`, where the local run
of the same commit returned `Err`.

Nothing in the slice was wrong about the padded value being invalid. What was wrong was **who
decided it**. `urllib.parse` began stripping leading C0 control characters and spaces from a URL in
3.10.12, 3.11.4 and 3.12 — a security fix, and so a *patch-level* property of the machine. On the
maintainer's 3.11.0 the leading space makes the location a relative path and it is refused; on CI's
3.11.x it is stripped and the location is a clean URL. Tab and newline have been removed for longer
still, which is how one interpreter can disagree with itself about which whitespace counts.

So the decision moved to where the product makes it. `git_location_parts` now refuses any location
that is not exactly its own `strip()`, before `urlsplit` sees it — refusing rather than trimming,
because these locations are identity-bearing (INV-253 stamps an alias into installed paths, and
`git_origin_key` keys the source store by origin) and quietly repairing an identity is how two
things that differ come to look the same. D-374 records the choice.

Evidence: `tests/configuration_model_test.py::test_surrounding_whitespace_is_refused_on_every_interpreter`
pins all five paddings and the clean control. The targeted mutation is deleting the guard: on the
maintainer's 3.11.0 it turns that test red on the tab and newline cases (the space cases stay green
there, which is exactly the disagreement being removed), and it is what CI was already failing on.
Scoped re-run of the nine modules that reach `git_location_parts` — configuration model, schema,
policy, seed and source-input, the Git source adapter, install-state schema, marketplace boundary
and maintainer source addition — 79 tests OK. `lint`, `format-check` and `typecheck` clean.

Checked at the release boundary too, since that is where a baked value is born. `render_from`
still trims the variable's own surrounding whitespace -- the shell's, from `echo` -- so
`"  company=https://host/team/registry.git\n"` bakes exactly as before. Padding *inside* the value
now fails the build: `"company= https://host/team/registry.git"` exits with `baked default registry
URL is invalid` on every interpreter, rather than baking a leading space into the wheel wherever
`urlsplit` forgave it. The guard makes the release gate stricter, not the product narrower.
`release_default_registry_injection_test::test_padding_inside_the_value_fails_the_build` pins both
spellings, and the same mutation turns it red on the tab case here.

The general lesson is the one the matrix exists for: a test that pins *invalid* must pin it for a
reason the product holds, not for a reason the interpreter happens to supply.

## The release-facing half, checked without a release

Task 5's release-facing third does not need a tag, and doing it without one is what makes it
repeatable. `scripts/release.py wheel-digest` builds the wheel in a throwaway copy of the tree and
applies *every* injector there from the real environment, so it is the release build minus the
publishing:

```sh
AART_CLI_DEFAULT_REGISTRY_ALIAS_AND_URL="acme=https://github.com/M1F1/aart-registry-demo.git" \
  python scripts/release.py wheel-digest --output /tmp/whl
```

The wheel it produced carries `ALIAS = "acme"` and the URL in `aart_cli/_default_registry.py`, and
the checkout is still clean afterwards -- the tracked module is untouched and still empty, which is
the property D-309 asks for and the one a maintainer testing this by hand is most likely to break
(running `inject_default_registry.py` directly overwrites the tracked file in place).

The receipt agrees: `release.py check --without-registry` reports `default_registry: null` with the
variable unset, and the trimmed `<alias>=<url>` with it set. Its two failing checks on this branch
are `repository-dirty` and `source-not-merged-into-main`, which are properties of a feature branch
rather than of CP-27.

Gates run here, all clean: `packaging-check` (built `aart_cli-0.4.1-py3-none-any.whl`),
`secret-shape-check`, `validate`, `lint`, `format-check`, `typecheck`, `docs-check`. The full
`unit`/`integration` suites stay on `pr-check`, for the reason at the top of this document -- and
this slice is the case for it: the one failure the matrix found was invisible to every local run.

## What this slice deliberately did not do

- **B-168** — only the terminal route seeds. `load_runtime_configuration` promises to make no
  implicit source or configuration mutation, and it is the path every command shares, so the
  flag-form CLI still answers `no-source-configured` on a first run.
- **B-169** — the announcement is printed before the terminal starts. That survives in the
  line-oriented terminal and is cleared by `curses.wrapper` in the other; `ConsumerUiState` has no
  notice field to carry it onto the dashboard.
- **B-170** — the dashboard reads `1 registries`. CP-27.4 is what put that frame on the repository
  front page and so is what exposed it, but fixing it is a product change and this slice is the page.

## Reproducibility

The wheel stops being reproducible from its tag alone and becomes reproducible from its tag plus the
repository variables in effect. That is already true of `_commit.py`, and it is the same question
issue #24 must settle for the distribution name.

So the release checklist's receipt now carries `default_registry`: the effective value, trimmed
exactly as the injector trims it, or `null` when the build baked none. Read from the environment
for the same reason `approved_registry_origin` is -- a constant would be contradicted by the
variable the build actually used. Three more targeted mutations hold it: recording an empty string
instead of nothing, dropping the field, and recording an untrimmed value. That closes the last of
issue #39's acceptance notes.
