# CP-27 — one baked default Registry, so a first run starts connected

Status: tasks 1–4 done on `docs/cp-27-default-registry-plan` (PR #40). Task 5, the full
quality/integration/release-facing verification, runs on `pr-check` rather than locally: the owner's
standing rule is that the complete suite is CI's job, and D-317 reserves it for the epic's last task.

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
