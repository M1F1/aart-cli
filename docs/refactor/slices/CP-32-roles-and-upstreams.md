# CP-32 — Three roles, three command families: consume, maintain, author

Status: **in progress** on `fix/source-local-git-visible-files` (PR #78), at the owner's request. Authority: the product owner (2026-10-17), Product
Specification §175, D-439.

## Why

`aart-cli source` configures Registries and author repositories alike, and `source list` shows
them together. A consumer can add an author repository although the Marketplace offers nothing from
it (`aart_cli/io/configured_offers.py` skips every non-Registry). The word "source" names both, so
neither role can tell from a command what it is about.

## Target

See §175.2 for the full command tree. In short: `consume` (Registries and installation), `maintain`
(`upstream`, `candidate`, `registry`), `author`; `doctor`, `upgrade`, `reset` and `security` stay
at the top level. Configuration keeps `registries` and `upstreams` apart; the TUI names its areas
the same way.

## Steps

See `docs/refactor/plan.json`, epic CP-32.

1. Specification (§175, INV-269–INV-272, D-439–D-441). Done.
2. Configuration split.
3. `consume`.
4. `maintain upstream`.
5. `maintain candidate`.
6. `maintain registry`.
7. Remove `source`, `marketplace`, top-level `registry` and the four kinds.
8. TUI names and hints.
12. TUI Author Mode (§175.5, D-441).
13. Marketplace details under More info; remove its standalone Artifact Details view (§175.6).
14. Named Marketplace columns with complete values at narrow widths (§175.6).
9. Documentation.
11. `reset` backs up and restores (§175.4, D-440); runs before the PR.
10. Full verification and the PR.

## Notes for the implementer

- No aliases, fallback readers or migrators (§169); a changed `config.json` shape is a clean break.
- Steps 3–6 can each land with focused tests (D-334): the argparse tree, one CLI e2e per family,
  and INV-269 as a test that no consumer path accepts an upstream.
- Policy fields `allow_direct_sources`, `recommended_sources` and `required_sources` follow the
  split: the direct switch goes; the other two name Registries.

## Step 2 — configuration split

Done (D-442). `config.json` keeps `registries` and `upstreams` with `kind: git|local`; the policy
names `recommended_registries`, `required_registries` and `company_reviewed_registries`, and
`allow_direct_sources` is gone from the model, the parser, first-run options and the TUI Sources
stage.

Evidence:
- `tests/configuration_schema_test.py` `test_registries_and_upstreams_are_separate_lists`: written
  files carry both lists and no combined kind; `sources`, combined kinds, a branchless local
  Registry, a local upstream with a ref, `url` on a local entry, one alias in both lists and an
  upstream as default Registry are each refused. The round trip covers all four combinations.
- `tests/configuration_policy_test.py`: an upstream with the required alias does not satisfy
  `required_registries`.
- 54 configuration-related modules, 652 tests, green; ruff, mypy and tach clean.

Targeted mutations:
- Required-registry check without `is_registry`: only the new upstream subtest turned red.
- `upstreams.git` mapped to `REGISTRY_GIT`: the round trip and the upstream-as-default refusal
  turned red.

## Steps 3, 4 and 6 — consume, maintain upstream, maintain registry

Done (D-443). The parser has only the role families; `source`, `marketplace`, `mcp` and the
top-level `registry` are gone with no aliases, and `--kind` takes `git|local`. Each connection
family lists, syncs, checks and removes only its own aliases and names the owning command for the
other's. `consume registry sync` ends with the `consume update` hint (B-201 for naming the
artifacts). The TUI and first run pass the family explicitly. Every hint in the package and the docs
names the new commands, through `SourceKind.command` where the connection is known.

Evidence:
- `tests/source_cli_command_test.py`
  `test_each_family_lists_and_removes_only_its_own_connections`: with a Registry and an upstream
  configured, each family lists its own under its own key, and `consume registry remove` of the
  upstream is refused, naming `maintain upstream`.
- `tests/registry_cli_test.py` `test_all_registry_actions_map_to_one_command_boundary`: the
  `maintain registry|candidate|upstream` action sets and the routing to the Registry handler.
- `tests/source_remediation_test.py`
  `test_every_hint_built_on_a_connection_family_is_a_command`, with the package-wide scan.
- `tests/adoption_first_contact_test.py`: the README route and the documented surface parse
  against the new tree. `tests/local_registry_promotion_e2e_test.py`: the TUI removes an upstream
  and adds it back.
- 197 related modules, 2,166 tests: green except `tests/screen_skeleton_test.py` (two Hypothesis
  properties that fail the same way on the base commit, unrelated). ruff, mypy, tach and docs-check
  are clean.

Targeted mutation: `_in_family` returning True turned only the family test red among
`source_cli_command_test`, `local_registry_promotion_e2e_test` and `source_remediation_test`.

Open in later steps: the consumer catalog still reads upstream
snapshots, so INV-269's "nothing a consumer installs comes from one" is step 7 with the e2e
fixtures that install from the shared `reference` upstream.

## Step 7 — a consumer reads only Registries

Done (D-444). The parser families went in steps 3, 4 and 6. The four `SourceKind` names stay
internal (D-443). This step removes what was left of the other half of INV-269.

- The `consume` lifecycle runs only the Registry seam, and every way it declines has its own code
  and remediation.
- Installing never fetches, and a Registry that was never synchronized is named as such
  (`registry-not-synchronized`).
- An unqualified name is resolved across Registries.
- `--mode` and `--memory-mode` are gone.
- The consumer runtime projects nothing from an Upstream repository, and its native
  materialization helpers are deleted.
- Two product fixes the conversion found: a `registry-local` installation's setup evidence is its
  checkout path, and a refused Registry revision names the snapshot that stays in use.

The e2e fixtures connect `tests/reference_registry.py`: the former reference content, promoted
through the real pipeline into a Git-backed `registry-local`, and republished by commit. The
modules converted:
- lifecycle, memory, setup, interrupted and verification;
- sync, upstream movement, offline and resolution vocabulary;
- project isolation, scope teardown, identity agreement, identity change and withdrawal;
- Tabnine MCP, OpenCode and the promotion boundary;
- consumer runtime, source CLI and remediation.

Tests whose subject exists only on the retired path are deleted (D-444 lists them). The gaps they
exposed are B-203 (runtime requirements), B-204 (files left after the last uninstall), B-205
(status compares nothing against the Registry) and B-206 (the unreachable native pipeline).

Evidence:
- `tests/resolution_vocabulary_test.py`: no Registry alias, an Upstream alias, an unsynchronized
  Registry and a missing name give four codes.
- `tests/offline_capability_test.py`: with or without `--offline`, one refusal; after a sync, the
  offline install succeeds.
- `tests/source_upstream_movement_e2e_test.py`: a sync rewrites no record and offers 1.1.0;
  `update` applies it; a rolled-back Registry is a refused downgrade.
- `tests/local_registry_checkout_e2e_test.py`: an unqualified name both Registries offer is
  ambiguous and names both.
- `tests/install_state_schema_test.py`: local Registry evidence round-trips and malformed origins
  are refused.
- Two sweeps of the related modules (84 modules, 759 tests; then 941 tests with every module that
  installs) are green. `docs/release/schema-freeze.json` is refreshed for the install-state change.
  ruff, mypy, tach and docs-check are clean.

Targeted mutations:
- Skipping the Upstream branch in `_outside_registries`: only the two resolution-vocabulary tests
  naming an Upstream alias turned red.
- Skipping the `registry-not-synchronized` return: the unsynchronized-Registry tests in
  `resolution_vocabulary_test` and `offline_capability_test` (both subtests) turned red.

## Step 5 — maintain candidate list|promote

Done. `maintain candidate list [--source DIR] [--json]` (`commands/candidate.py`) prints the active
Candidates `read_maintainer_views` projects — what Registry Maintainer Mode's Candidates screen reads
— with ID, state, coordinate and version, Upstream repository, revision, manifest, target Registry
and promotion record, and writes nothing. `promote` stays with the Registry handler. Only the TUI's
Source Sync records Candidate history today (B-202), so the empty state says that.

Evidence: `tests/authoring_source_admission_e2e_test.py`
`test_candidate_list_shows_what_the_sync_recorded_and_changes_nothing`: empty before the Source
Sync; afterwards exactly the synchronized Candidate, at the author's HEAD, `not-promoted`, with the
data root byte-for-byte as before the list. `tests/registry_cli_test.py`: `list` routes to its own
handler. Related modules green; ruff, mypy, tach and docs-check clean.

Targeted mutation: listing no Candidates turned only that e2e test red.

## Step 11 — reset with backup

Done (D-440), ahead of steps 3–8 at the owner's priority. `aart-cli reset` renames every planned
target into `<home>-backups/<UTC timestamp>/` (a `-2`, `-3` suffix when a second reset lands in the
same second) after one `RESET AART` or `--yes`, and prints the directory and the restore command.
`reset --restore DIR` refuses a directory inside the home, a symlink, or one holding anything a reset
could not have put there; it backs the current state up first, moves the entries back and removes
the emptied backup. A move across filesystems is refused rather than copied. The TUI's "local AART
state could not be loaded" ends with the reset hint.

Evidence: `tests/factory_reset_test.py` -- one confirmation moves each target with its content into
the named backup; `--yes` prompts nothing; two resets keep two backups; `AART_CLI_HOME` is backed up
beside itself; cancel and EOF change nothing and create no backup; symlinked targets and homes are
refused before anything moves; restore round-trips and keeps the newer state; a foreign directory is
refused; the startup failure names `aart-cli reset`. The plan-level Hypothesis properties are
unchanged. 52 tests with `packaging_test` and `tui_stage_failure_test`, green; ruff and mypy clean.

Targeted mutations:
- Restore without the foreign-entry check: only the foreign-directory test turned red.
- Deleting instead of moving: the five tests reading the backup and `--yes` turned red.


## Step 8 — TUI role names and connection hints

Done (D-445). Maintainer navigation reads Upstream repositories, Candidates, Registry. Upstream
add/remove/details/sync, Candidate provenance and table headings use upstream vocabulary;
Marketplace descriptions identify a Registry. Screen 31 carries the specification's explanation
in both profiles. Connection kinds are shown as git/local. The consumer wizard and empty states
name Registries; shared connection reviews name the reviewed connection's own family.

Red first: the updated dashboard, nested-trail and consumer empty-state tests failed in six
places before production changes. The composed upstream onboarding, sync and removal walks now
assert the new names without changing their navigation or effects. The existing
`consumer_registries_screen_test` still proves that neither local nor Git upstreams appear on
screen 21, including production composition and upstream-first ordering.

Evidence: 124 related modules, **1229 tests**, green. This includes TUI, consumer, maintainer,
source, wizard, frame/trail and Marketplace cursor-description tests. The two pre-existing
`screen_skeleton_test` Hypothesis findings (B-194) remain outside this focused run. Ruff, mypy
and tach pass; docs-check passes. No full local suite was run.

Targeted mutations:
- Restoring screen 31's title to `Sources` turned only
  `MaintainerRenderingTest.test_screen_30_and_sources_are_reachable_bodies_in_the_shared_source`
  red in the targeted run. Its dashboard assertion holds all three area names, and its screen-31
  assertion holds the subtitle and Add upstream action.
- Restoring the onboarding's `from a source repository` sentence turned only
  `WizardOnboardingTests.test_onboarding_keeps_what_the_bar_cannot_say` red in the targeted run.

Scoped advisory mutation: `make mutants ONLY=aart_cli/wizard.py
TESTS="tests/wizard_render_test.py tests/wizard_state_test.py"` initially found 476 killed and
160 surviving of 636 mutants. The changed onboarding sentence needed an exact-line assertion;
explicit reruns of its three mutants timed out (476 killed, 157 survived, 3 timeouts), so its
claim was additionally checked by the direct targeted mutation above. Other wizard survivors
are outside this naming slice and recorded in B-207.


## Owner addition — Marketplace details and complete labeled columns

Accepted during step 12 (2026-10-17, D-446). §175.6 and INV-273/274 are added, with steps
13 and 14 after Author Mode and before documentation/final verification. No implementation is
claimed yet. Step 13 must characterize every detail the old Marketplace Artifact Details view
shows before removing that route; More info retains the focused offer and browsing state. Step
14 needs generated-width layout properties that preserve complete headings and values, alongside
focused real-shell cases for readable rows and cursor behavior. Existing column truncation may
remain on other screens; this acceptance change is specifically Marketplace.
