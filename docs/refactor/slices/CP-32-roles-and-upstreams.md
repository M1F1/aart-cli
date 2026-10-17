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
15. Correct unset-input smoke outcomes (§170, D-447); owner-reported false PASS.
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


## Step 15 — unset MCP inputs cannot pass smoke

Done (D-447), promoted onto the critical path by the owner's observed false PASS. The installation
configuration check ignored the provider's placeholder flag and ordinary `AART_NOT_SET` values.
They now yield `NOT CONFIGURED`, with a Credentials and variables recovery, and protocol
`NOT RUN`. An absent credential does likewise. Unsupported/unavailable providers and invalid or
unknown credential observations stay BLOCKED. Typed `SmokeStageResult` failures carry their own
outcomes; no diagnostic wording decides the classification. No secret value is read.

Red first: the new real-file receipt/launcher/configuration tests reported `report.ok == True`
for both secret and ordinary placeholders before the fix. `installed_mcp_configuration_test`
covers those cases, a missing credential, configured references, unavailable/invalid providers,
a generated ordinary-answer property, and the public CLI handler's JSON / nonzero result.
The ordinary placeholder test has a second configured input, so one missing input is enough.

Evidence: the two directly affected modules pass all 20 tests. The MCP-focused selection,
stdio, evaluation, CLI, Installed and post-installation E2E modules also pass. Ruff, mypy and
tach pass; docs-check passes. The separate Author Mode broad run is still an open step, not
claimed as this step's verification.

Targeted mutations, running all eight new tests:
- Ignoring `observed.value.placeholder` turns exactly the secret-placeholder service test and
  its CLI JSON/nonzero test red (the CLI incorrectly returns 0).
- `any` → `all` over ordinary placeholder values turns exactly the ordinary-placeholder test red.

Scoped advisory: `make mutants ONLY=aart_cli/io/installed_smoke.py
TESTS="tests/installed_mcp_configuration_test.py tests/mcp_smoke_cli_test.py"`: 402 mutants,
175 killed, 156 survived, 71 without tests. Initial clean-run collection exposed Hypothesis's
`differing_executors` health check under mutmut's repeated unittest execution. The generated
property now runs in a fresh nested function on each test invocation, retaining the same
examples and assertions without suppressing a health check. The successful scoped run's
out-of-slice integrity/response/plan findings are B-208; the new outcome/no-start claims are
additionally held by the direct targeted mutations above.


## Step 12 — Author Mode

Done (D-448). The Settings opt-in is independent of Registry Maintainer Mode and survives a
restart. Author opens Workspace, Check and New artifact; Workspace remembers a normalized
absolute directory outside the application home. New artifact offers the skeleton generator's
kinds and creates the CLI's template in the workspace or a contained subdirectory. Check uses
the CLI's Git-visible reader and checker, lists every manifest, opens complete diagnostics and
reruns on `r`. No upstream is connected and no Registry operation is invoked.

Red first: the new author-area contract was absent. Negative tests additionally exposed an old
passing report surviving a failed rerun, and a template written before a check refusal being
reported as an operation that never ran; both were red before their fixes.

Evidence: `tests/author_mode_test.py` covers persisted/independent mode gates and generated
workspace round trips; generated malformed stored paths; the real shell's Workspace and
New artifact → Check flow; multiple manifests with the new one focused; CLI/TUI check equality;
full error/recovery projection; one-key reruns; no drawing IO; no overwrite; containment including
symlink escape and the application home; read/template failures; and honest post-write check
failure. All five screens have populated/fallback cases in `tests/screen_cases.py`.
The related run passes **1379 tests in 139 modules plus the frame contracts**, with the two
pre-existing B-194 properties excluded and the remaining frame contracts included. New projection
properties also pass through the scoped mutation runner. Ruff, mypy, tach and docs-check pass.

Targeted mutations:
- Removing workspace containment makes the escaping-path test red.
- Returning an unrelated newly-created manifest path makes only the composed New artifact
  test red: it focuses `00-existing/aart-cli.yaml` rather than the new `aart-cli.yaml`.
- Earlier unset-input mutations are recorded under step 15. Restoring same-size source changes
  can leave a same-second Python bytecode cache; affected generated bytecode was removed before
  the final green run, so mutation state cannot masquerade as the restored source.

Scoped advisory: `io/author_operations.py` with the author-area tests killed 65/83; the 18
reviewed survivors preserve error meaning/casing or are equivalent strict-resolution choices
where the directory check still refuses a missing workspace. `application/author_views.py`
initially appeared untested due to cached scope statistics (B-209); after collecting fresh
statistics it killed 44/47. Generated uppercase paths and preserved command-free recovery
then killed **47/47**. No quality gate or Hypothesis health check was suppressed.


## Step 13 — complete artifact disclosure stays in Marketplace

Done (D-449). The old Artifact Details screen and route are removed. More info carries its full
provenance, security, compatibility, installation and digest fields, plus declared input guidance.
It shows no installation answers or credential provider references/state. Enter on an artifact
keeps Marketplace unchanged; toggling More info preserves search, cursor and selection. Install
uses marked offers or the focused offer when none is marked; an empty list does nothing.
Collection preview and Installed details remain independently navigable.

Red/green: new tests characterize the former complete view and independently assert all four
full digests, origin and revision. Controls, single/bulk install, empty-list refusal, collections,
trail and shell expectations were updated to the accepted route. The targeted mutation deleting
the evidence block makes precisely the two full-evidence/new-view tests fail in the five-test
module. Restored source and cleared bytecode pass. The direct affected selection passes 82 tests.

Scoped advisory mutation of `tui_marketplace_detail.py` initially killed 48/113; added independent
input type/required/guidance assertions raised this to 77/113. Remaining field-label findings
were strengthened with label/value pairs, with cosmetic indentation, equivalent falsy identity
options and duplicate identity rendering reviewed as outside information-preservation claims.
B-210 records the unused former wrapper; no fallback view remains. Fresh mutation statistics after the label/value assertions kill 108/113; five remaining mutants
retain information through indentation, redundant identity or equivalent falsy options, or add
punctuation to the no-description fallback. The related cross-screen run passes 1479 tests
in 149 modules plus the frame contracts. Ruff, mypy, tach and docs-check pass.


## Step 14 — named, complete Marketplace cells at every width

Done (D-450). Marketplace has Artifact, Status, Scope, Harnesses and Unset headings on the same
grid as its cells. Values wrap without ellipsizing. Below 67 usable columns, rows stack those
same labeled fields. A logical row retains its key, cursor and tick regardless of physical height.
The shell samples terminal dimensions outside projections; resize does not change browsing state.
PgUp/PgDn scroll actions and More info one physical line at a time, retaining headings and the
shared footer. The initial viewport follows focus; explicit offsets clamp at both ends.

Red first: the new layout contract failed because no complete row renderer existed. Updated
receipt-derived E2E assertions reconstruct wrapped cells rather than treating one physical line
as one row. The first related run found two identity-contract failures: resetting a default scroll
position needlessly replaced an unchanged state. The fix preserves the original object on refused
navigation and only resets scroll when a real event changes state.

Evidence: twelve focused tests include generated widths 1–140 and long coordinates, labeled
narrow rows, column alignment, absent Collection facts, empty catalogs, generated viewport sizes
with every detail line reachable, a real curses adapter's focus/end-clamping/PageUp behavior,
resize preservation, and a last-character regression. `wrap_lines` already reserves curses's last
column, so no terminal clipping change was needed. The targeted truncation mutation (`value[:width]`
before wrapping) makes exactly the grid, narrow-layout and generated-width tests fail; restored
source passes. The refused-navigation and focused view selection also pass after the identity fix.

Scoped advisory: `make mutants ONLY=aart_cli/tui_marketplace_rows.py
TESTS="tests/marketplace_readable_rows_test.py"` initially killed 173/233. Independent header,
missing-cell, paging, empty-state and explicit-offset claims raised this to 190/233. Reviewed
survivors preserve information through different hanging indentation or wrapping boundaries,
redundant strict zip options over fixed tuples, equivalent default wrap arguments, bounded
viewport overlap, or diagnostic/fallback wording. No test or gate was weakened.

Final related verification: 1510 tests in 152 modules plus frame contracts pass, with the two
pre-existing B-194 properties excluded. Ruff, mypy, tach and docs-check pass. Full suite stays in CI.
