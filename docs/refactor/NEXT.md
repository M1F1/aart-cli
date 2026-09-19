# AART Refactor — Next Work

## Where CP-26 is (2026-09-19)

Steps 1–9 are done on `refactor/cp-26-legacy-removal`, and **B-057 and B-149 are both closed**. The
retired authoring-workspace representation has no schema, no fixtures, no planning half and no
command left; `aart registry vendor` writes the approved representation's versioned package through
`plan_bulk_promotion`; the authoring field surface is read out of the parser rather than
transcribed; AART can write the YAML subset it parses; and `aart author init` writes a full-surface
workspace for `mcp` and for `skill`.
`docs/refactor/slices/cp-26-authoring-and-legacy-removal.md` records these under §"Step 5",
§"B-149" and §"Step 6" to §"Step 9" (D-321 to D-329).

**Steps 10–11 are next** — `aart author check [--source DIR] [--json]`, the higher-value half of the
pair (§1.4). Two claims in order: every discovered `aart.yaml`/`aart.json` goes through the real
`parse_author_manifest`, and the parsed manifest compiles to a canonical package that `registry
scan` would accept. `tests/author_skeleton_test.py::CompilationTest` already runs the second claim
against the generated workspaces through `compile_author_snapshot`, which is the function `check`
should use rather than a reimplementation. Until `check` exists, nothing in the package may name
`aart author check`: `source_remediation_test` and `adoption_first_contact_test` both refuse it.

Two open findings from step 5:

- **B-151** — seven shipped documents still describe `aart.lock.json` and `aart.index.json` as files
  AART writes. Not gated by `make docs-check`, which validates fences and links. Noncritical for
  step 5; a precondition of CP-26.21.
- **B-150** — the owner's installation-identity principle: an installation is
  (artifact, harness, user-or-project scope), and no artifact shares global state with any other.
  Input to CP-26 task 19, and to the Product Specification before it.

## CP-26 scope addition (2026-09-18)

The owner added step 17: remove `M1F1` and `M1F1/aart-cli` from generated Registry content and
operational defaults. The concrete locations and acceptance scope are in the CP-26 slice. This is
independent of the removal work and follows the README work in the numbered plan. The `v0.3.0`
release is complete; step 8 is next.

The owner then added step 18 (D-312): `[p] Push` belongs to the local workspace row on Registry
Maintainer, not to individual wizard success screens. That row distinguishes the accepted snapshot,
the local snapshot/`HEAD` and publication readiness. Readiness is recomputed from a clean committed
tree through the shared full Registry gate contract; every blocker is visible. The current named
branch is the only target when it is neither `main` nor the Registry default; otherwise the
maintainer enters a new review branch. The worktree containing `working_at` must itself be the
canonical Registry — a Source, connected snapshot or unrelated repository is never a target. The
full placement and acceptance contract is in the slice and Product Specification §164.7.

For avoidance of doubt, CP-26 step 3 does not delete any canonical command. `lock`, `build`,
`validate`, `audit`, `format` and `publish` remain; only their older-representation branches are
removed. `publish` remains the canonical build/validate/audit/local-commit aggregate and does not
push. Push remains separate and CP-26.18 restores it in Registry Maintainer. CP-23 task 05/D-255 is
historical implementation evidence and is explicitly superseded by D-312.

D-313 / INV-243 define a general consumer-state boundary, promoted by the owner from B-144 to
CP-26.19. An installed artifact's configuration and credential binding are keyed by Registry alias, artifact
identity, concrete project/user destination, harness/profile and input id, whether the Registry came
from a remote URL or local checkout. On macOS each such key maps to a unique Keychain item.
`company/mcp/foo` and `company-local/mcp/foo` do not share values merely because their manifests
match; neither do installations into two projects and user scope. The current input composer,
one-source-for-all-targets projection and automatic Keychain identity are known collision points.
B-143 is promoted to CP-26.20 and depends on step 19. Step 20 adds `registry-local` as a second
acquisition adapter for the same canonical Registry, snapshot, Marketplace and installation path;
local Sync is network-free and last-known-good. These additions do not change active CP-26 step 2.

D-316 / Product Specification §168 settle steps 13–16: README is for the normal user who wants an
artifact installed quickly. It opens with the complete quick path (install AART → connect/sync a
Registry → choose in Marketplace → install into a harness → verify), gives only then a short “What
AART is”, and follows with categorized links to detailed documentation. Authoring, Registry,
Enterprise, architecture, contributor/testing and release detail moves to those documents rather
than becoming a second README tutorial. The existing MIT License wording and copyright/footer stay
last. The gate executes install forms and checks order, explanation size, links and final License.

## Historical record: CP-26 step 2, on `refactor/cp-26-legacy-removal` (2026-09-18)

**Branch.** Work on `refactor/cp-26-legacy-removal`, rebased onto the released `v0.3.0` main.
PR #21 and its release PR #22 are merged; the release workflow passed and attached the wheel.

**The original red test was based on one false grouping.** D-311 corrects it: only `scaffold` is
withdrawn; canonical `publish` remains the aggregate. The replacement test is
`tests/registry_cli_test.py::RegistryCliTest::test_registry_scaffold_is_withdrawn_but_publish_remains_the_canonical_aggregate`.
Run it with:

```
poetry run python -c "import agent_artifacts.application, unittest; \
  unittest.main(module=None, argv=['x','tests.registry_cli_test'])"
```

The indirection is not decoration: importing `tests.registry_cli_test` directly hits a circular
import through `registry_commands.model`, and importing `agent_artifacts.application` first breaks
the cycle. Use it for every test module under `tests/` that touches registry commands.

### What step 2 deletes

`scaffold` wrote the older registry representation and has no approved-representation behaviour.
`publish` does: build, validate, audit and create the reviewed local commit. It survives and loses
only its legacy branch in step 3. Line numbers are a map, not coordinates.

| File | What goes |
|---|---|
| `agent_artifacts/cli.py` | `p_scaffold` parser and the two `registry_action == "scaffold"` default-injections |
| `agent_artifacts/curation/model.py` | `CurationAction.SCAFFOLD`; `CurationAction.PUBLISH` survives |
| `agent_artifacts/curation/runtime.py` | `_prepare_scaffold`, its imports and dispatch entries; `_prepare_publish` survives |
| `agent_artifacts/commands/registry.py` | scaffold dispatch only; `_run_publish` survives |
| `agent_artifacts/registry_commands/planning.py` | `plan_artifact_scaffold` 705–748 and `_payload` 616–702 — verify `_payload` has no other caller before cutting it |
| `agent_artifacts/registry_commands/model.py` | `RegistryOperation.SCAFFOLD`, `ArtifactScaffoldOptions` and its validator; `PUBLISH` survives |
| `agent_artifacts/registry_commands/__init__.py` | the `plan_artifact_scaffold` import (18) and `__all__` entry (43) |
| `agent_artifacts/application/registry_commands.py` | `prepare_artifact_scaffold` 58–66 and its import at 25 |
| `agent_artifacts/application/__init__.py` | the import (10) and `__all__` entry (56) |
| `agent_artifacts/protocol/native_tree.py` | the remediation at 99 tells the reader to run `registry scaffold --help`; it must name `scan`/`promote` instead |
| `agent_artifacts/registry_commands/templates.py` | the generated tutorial line at 377 runs `registry scaffold` |
| `agent_artifacts/wizard.py` | `"scaffold"` at 175 |

**One trap.** Every publish symbol survives. `agent_artifacts/compiler/model.py` defines
`PUBLISH = "publish"` as a compiler phase, while `CurationAction.PUBLISH` and
`RegistryOperation.PUBLISH` are the retained canonical aggregate. Delete none of them.

**Tests to delete, not repair.** They characterize verbs that no longer exist:

- `tests/registry_cli_test.py` — the `_SCAFFOLD` constant,
  `test_scaffold_install_scope_and_mode_do_not_silently_include_defaults`, and `_SCAFFOLD` from the
  `_rs02` loop. The action set loses only `"scaffold"`.
- `tests/promoted_registry_maintenance_e2e_test.py` — only
  `test_scaffold_refuses_a_registry_that_publishes_approved_versions`. Both publish tests survive;
  they hold D-311's canonical aggregate and D-308's mixed-representation refusal until step 3
  removes the legacy branch. **`is_promoted_registry` itself stays.**
- Read every other scaffold mention before cutting it. A publish mention is not removal work.

**Definition of done for step 2:** the replacement test passes,
`grep -rn "CurationAction.SCAFFOLD\|RegistryOperation.SCAFFOLD\|plan_artifact_scaffold" agent_artifacts/` is empty, one recorded
targeted semantic mutation, `make lint format-check typecheck` plus the affected test modules green,
then `handoff-plan done 2` and a commit.

### House rules that are easy to miss

- **Do not run the full `make quality` before CP-26.21.** Tasks 2–20 run the named red/green tests,
  checks for changed files and measured damage radius, and only affected integration/E2E modules.
  Task 21 owns the full quality and integration/E2E closeout once implementation is complete
  (D-317).
- **One recorded targeted semantic mutation per task** — change the code deliberately, watch the
  named test go red, record it in the slice document. Coverage is not evidence.
- **Nothing private in any commit, file or PR.** The owner's Enterprise host, org and secret names
  must never be written down; use `<instance>`, `<org>`, `<nazwa sekretu>`. Check every staged diff
  before committing.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` only for commits
  Claude authors — put your own attribution on yours.
- Record material choices in `docs/refactor/DECISIONS.md`, non-critical discoveries in
  `docs/refactor/BACKLOG.md`. The repository, not a chat log, has to be enough for the next agent.

## CP-26 — start here (2026-09-18)

**Design and plan:** `docs/refactor/slices/cp-26-authoring-and-legacy-removal.md`. The twenty-one steps
are in `plan.json` as CP-26; step 1 is `done`, the rest `todo`. Take them in numbered order. Steps
1–5 canonicalize Registry maintenance while retaining every canonical command; steps 6–12 build the
author loop; steps 13–17 deliver the consumer-first README, linked detailed documents and executable
documentation contract; step 18 restores separately reviewed Push on Registry Maintainer; step 19
(B-144) precedes step 20 (B-143), so local Registry aliases cannot inherit the existing
configuration/credential collision; and step 21 runs the broad full-slice gates once. The `ast`
collector for step 6 is already written and pasted into the design document; do not re-derive it.
Step 17 reruns step 16's install-line gate if it changes one. Step 5 is next.

**The owner has withdrawn backward compatibility, explicitly and more than once.** No compatibility
window, no migration command, no deprecation period, no consideration for registries already
published in the older shape. Delete directly. Do not reintroduce caution here.

**Why removal comes before the new commands:** D-308 already refuses `scaffold` on a Registry that
publishes approved versions, so deleting it takes away no canonical workflow. `publish` remains as
the canonical aggregate under D-311 and loses only its older representation branch in step 3.

**What landed today, on `fix/registry-provide-aart-posix-sh`:**

- D-304, D-305, D-306 — the generated registry workflow now survives an Enterprise runner: POSIX
  `sh` (no bash on the image), an authenticated git arm for a private AART copy, and
  `safe.directory` for a container whose workspace is root-owned. All three were confirmed against
  the real instance.
- D-307 — a refusal only Git can explain now repeats what Git said, instead of a sentence naming
  neither cause nor fix.
- D-308 — `scaffold` and `publish` refuse a checkout carrying both registry representations. This
  is step 1 of CP-26 and the fix for B-142.
- B-142 records the trap in full, with the verified remedy and the content loss its obvious variant
  causes.

**Outstanding, on the owner's side, not the code's:** their Enterprise registry needed
`git rm aart.lock.json aart.index.json` to go green. Confirmed on a reproduction that all six
generated gates then pass and `registry/index.json` is unchanged. If they report the run, check it
before opening a pull request from this branch.

**Two things learned the hard way today, worth keeping:**

- The generated workflow's steps run under `sh`, not `bash`, whenever the image lacks bash. No
  macOS developer machine can observe this: `/bin/sh` there *is* bash. `dash` is the oracle, and
  `tests/enterprise_ci_template_test.py` now runs the real emitted script under it.
- Do not infer a consumer-side break from reading one `if`. `consumer/runtime.py` looked as though
  it hard-required `aart.index.json`; it dispatches on `registry/` about thirty lines earlier, and
  the e2e proves a promoted registry with no legacy files installs fine. Check by executing.

## Post-review installation documentation (2026-09-17)

README now shows one parameterized, publicly readable Release-wheel download and two alternative
local-wheel installs (`pipx` or `uv tool`). After owner feedback, each installer example is now a
complete shell block: no variable needs to survive from a previous block, and `pipx` explicitly
uses the `python3` on PATH. Both were exercised in isolated tool directories against the public
`v0.1.2` wheel. `curl -fL` is followed by a ZIP archive check before either installer runs, to
catch an HTML sign-in page saved as `.whl`. It is not a checksum or an
authentication mechanism: private Enterprise Releases still need an authenticated download or an
internal index. B-136 holds the optional checksum follow-up; no release pipeline changed (D-303).
PR #18 was green before the documentation-only commits; the final run must be checked after push.

## CP-25.16 — credential-shaped test fixtures done (2026-09-17)

The owner added task 16 to the current stream after the first full `make quality` reached its last
gate and failed: two CP-25 redaction tests wrote token-shaped fake values directly into tracked
source. Both now use `tests.credential_fixtures.access_token()` (D-301). Full `make quality` is
green: 4,441 tests (1 skipped), 86.07% branch coverage, all non-redundant gates passed. The
branch was rebased onto current `origin/main` to avoid a `v0.1.2` version regression. Draft PR
[#18](https://github.com/M1F1/aart-cli/pull/18) is open; its `pr-check` matrix is pending. The
owner chose `0.2.0` (D-302), so its squash title stays `feat:` without `!`.

## CI feedback follow-up — CP-25.15 done (2026-09-17)

The owner requested a fail-fast pull-request title check after an Enterprise fork smoke PR titled
`test` reached `scripts/conventional_title.py` only after the quality gates, then promoted B-135 to
CP-25.15. The existing check now runs first in `.github/actions/quality/action.yml`; a test holds
the ordering (D-300). This does not change release semantics; the remaining external gate is
draft PR #18's `pr-check`.

## Current objective — CP-25 (2026-09-17)

**CP-25 is the active slice.** Tasks 01–03 completed the release-pull-request gate (D-290).
Tasks 04–07 withdraw the unused GitHub-issue usage-reporting and static-dashboard mechanism while
preserving the local Activity log and adding only a neutral Activity telemetry port with a disabled
adapter (D-292). At the owner's instruction, tasks 08–14 now carry every open
product issue in `M1F1/aart-cli`: #9, #10, #11, #12, #16 and #17 (D-291).

The written task scope is in
[`slices/CP-25-release-pull-request-gate.md`](slices/CP-25-release-pull-request-gate.md), and
`plan.json` is the executable status authority. Tasks 04–16 are done (D-292 to D-301). #11 was
split into separate scope and backend choices because they
affect different planning contracts; both halves are done.

**PR #18's checks are green and nothing executable is left.** The matrix ran against exactly the
published head `3668a70`: `gates (Python 3.10)`, `(3.11)` and `(3.14)` all pass, and `pr-check`
passes in 3 s. The private-image job reports `skipping`, which is its designed behaviour where the
registry credentials are not available, not a failure.

**What remains is the owner's and only the owner's:** take PR #18 out of draft, approve it, and
squash-merge it under its existing `feat:` title. Do not mark it ready, approve it or merge it on
the owner's behalf, and do not add a breaking `!` — that would release `1.0.0` instead of the
`0.2.0` the owner chose (D-302).

**Version decision made by the owner:** `0.2.0` (D-302). PR #18 is titled `feat: complete CP-25
consumer fixes and reporting withdrawal`; under squash merge that title is the release-semantic
commit. Do not add a `!`, which would make this `1.0.0` under the current policy.

The earlier planning baseline was intentionally stopped during coverage. It has now been superseded
by the complete green `make quality` recorded above for CP-25.16.

## Releasing 0.1.0 (2026-09-15)

- PR #1 is merged. Release Please opened release PR #2.
- D-277 fixes the two things that stopped #2 from becoming a working release: the tag name and the
  README version rewrites. After that fix is squash-merged, Release Please regenerates #2.
- `v0.1.0` was tagged, but its wheel build failed: the release action installed no Poetry (D-279).
  After the fix merges, merge the `0.1.1` release PR. It needs its workflows approved, then a
  green `pr-check`. Then confirm the wheel is attached to `v0.1.1`.
- #2 was merged, but Release Please skipped it: its component check failed (D-278). After the D-278
  fix merges, the next Release Please run releases #2 as `v0.1.0`, because its label is still
  `autorelease: pending`.
- Earlier step: #2 was merged with **squash** once its `pr-check` was green. Then check that the release run built and
  attached `aart_cli-0.1.0-py3-none-any.whl` to the `v0.1.0` release.
- `pr-check` stays on for release PRs, but since CP-25 it runs the narrow gate set rather than the
  whole suite (INV-096 rewritten, D-290). B-129, a race between the manual lab and git's background
  repack that turned it red at random, is fixed.

## Historical CP-25 mid-slice snapshot (2026-09-17)

**CP-25 is the active slice. CP-25.10 is part-done and is the next thing to finish**: the scope
seam is complete and held (D-295), but no screen or key lets a person make the choice before
Ready/Review, which is the half of issue #11a a user can see. Finishing it means a control on
screen 05 driven by `offer_install_scopes`, setting `ConsumerUiState.install_scope`; everything
downstream of that field already works and is under test. Tasks 01–03 gated the release pull
request (D-290), 04–07 withdrew usage reporting and left an Activity telemetry port in its place
(D-292), 08 fixed the Dashboard's Candidate arithmetic (D-293), and 09 made a Marketplace row lead
with installation state and harnesses (D-294). Tasks 10–14 carry the owner's remaining open
issues: #11 (two tasks), #12, #16 and #17.
`docs/refactor/slices/CP-25-release-pull-request-gate.md` holds the ordered tasks and their
acceptance criteria; `plan.json` holds them as CP-25.1 to CP-25.14.

The then-open version question was resolved by the owner after this snapshot: `0.2.0` (D-302).
The pull request title, not the individual commits, decides it under squash merge.

## Closed — CP-24 (2026-09-16)

**CP-24 is done.** It carried the owner's field reports against the released `v0.1.1`,
as GitHub issues #7 and #8, and ended by releasing the fixes: pull request #14, Release Please's
#15 at 10:48 UTC on 2026-09-17, and `v0.1.2` tagged on `origin`.
`docs/refactor/slices/CP-24-post-release-field-reports.md` holds the ordered tasks;
`plan.json` holds them as CP-24.1 to CP-24.10. Tasks 08-10 were added on 2026-09-17, after the
owner ran the gates in a container on their Enterprise instance and three things broke that have
nothing to do with the product: a permission test run as root, an interpreter whose file name the
requirement model rejects, and `actions/setup-python`, which that instance does not carry.

**Task 01 is done (D-280).** A stored Candidate history that does not bind the pinned revision is
no longer projected as Candidate data and no longer refuses the composition: that Source reads as
needing a Sync and names the remedy, and every other Source loads. Its evidence is in the slice.

**Task 02 is done (D-281).** A Sync now compiles and reconciles before it publishes the pin, so a
refusal leaves the Source exactly as it was. The only window left is the two adjacent writes, which
is what task 01's tolerance covers.

**Task 03 is done (D-282).** `aart doctor` names a Candidate history that does not bind the pin,
with both revisions and the remedy, and exits non-zero; the Maintainer Source Sync performs the
repair, which it previously refused to do over exactly that state.

**Task 04 is done (D-283).** A dependency contract is one offer, naming the backend that will run:
`chosen_installer` is the single rule, used by both `select_python_installer` and
`allowed_remediations`, so the review can no longer name a backend the install would not choose.

**Task 05 is done (D-284).** A review counts what each change is rather than which effect kind
carries it: the launcher and each harness's configuration file are counted separately, and a
placement's deliveries are named instead of being "other change".

**Task 06 is done (D-285).** An installation says which step is running and which are done:
`execute_repair` announces each step to an observer it is given, the shell lends the handler a
redraw for the duration of one execution, and the running report is drawn in the shared frame.

**Task 07 is done in the repository (D-286).** Full `make quality` (4,325 tests, 85.96% branch
coverage) and a standalone `make integration` (395 tests) are both green — B-108 did not reproduce.
The scoped mutation runs over `execution.py` and `consumer_views.py` left 34 survivors inside this
slice's own claims; all of them are now tests, each verified by hand.

**Task 08 is done (D-287).** A test whose subject is a permission stands down where permissions
do not apply. `tests/privileges.py` is the one guard; the sealed-lab test now carries it and the two
files that had their own copy were moved onto it.

**Task 09 is done (D-288).** An executable requirement may name the file it really is:
`executable_name` is the rule (no path separator, no whitespace, no control character, not `.` or
`..`), `RequirementId` stays kebab-case, and `InstallExecutable` moved onto the same rule, because
planning derives one from the requirement's own executable name.

**Task 10 is done (D-289).** No workflow and no composite action names `actions/setup-python`,
and every job takes its interpreter from a container image: unset, `AART_CI_IMAGE` falls back to the
official `python:<version>` image, one per matrix entry, so the public run still exercises 3.10,
3.11 and 3.14. The rollout page's two claims that an image "skips" the action are corrected; the
same trap in the registry template is `BACKLOG.md` B-134.

**One pull request carries the whole stream.** On 2026-09-17 the two open pull requests were
flattened, at the owner's instruction, into **#14** (`fix/cp-24-01-stale-scan` → `main`): it already
held the plan commit, so it took the `fix:` title and the `BEGIN_COMMIT_OVERRIDE` block, and #13 was
closed unmerged. `plan/cp-24` is not to be merged.

**What is left is the owner's:**

1. merge **#14** into `main` — squash. Its title is a `fix:` and it carries a
   `BEGIN_COMMIT_OVERRIDE` block, so Release Please cuts **`0.1.2`**. The owner chose the patch over
   `feat:`/`0.2.0` on 2026-09-17: task 06 is the repair of a silence they reported.
2. approve the workflows on the Release Please pull request and merge it;
3. confirm the release run attaches `aart_cli-0.1.2-py3-none-any.whl` to `v0.1.2`.

Still open, and not agent work: the owner's manual acceptance walk
(`docs/testing/TUI_MANUAL_WALKTHROUGH.md`), which now carries the three CP-24 checks.

Reproduction for tasks 01–03, from the owner's own store: a pinned revision and a Candidate history
recorded at a different one. `read_maintainer_views` then refuses everything with
`maintainer-composition-invalid`, `aart source sync` reports `unchanged` and writes no history, and
the only recovery found was moving `<data root>/sources/<instance-id>/candidates` aside.

**CP-23 is CLOSED** — the owner closed it on 2026-09-16 rather than recording the manual
acceptance walk in the repository. What that leaves open is written below, as facts rather than as
blockers.

## Closed — CP-23 (2026-09-15, closed 2026-09-16)

**CP-22 is CLOSED. CP-23 is CLOSED: tasks 01–16 are done in code and task 15's gates are
recorded.** Two things were never recorded, and the owner closed the slice anyway; neither is agent
work and neither blocks CP-24.

1. **The owner's manual acceptance walk was not recorded here.**
   - `docs/testing/TUI_MANUAL_WALKTHROUGH.md`, Acts I–II, finishing with its "CP-23 acceptance"
     checklist, is still the walk to run, and it is worth running.
2. **A green standalone `make integration` was never recorded.**
   - The one task-15 run failed on the B-108 temporary-Keychain creation, `security` status 206,
     in `mcp_stdio_e2e_test`.
   - `make quality` was green: 4,273 tests, 1 skipped, 85.94% branch coverage.
   - Resolve B-108's isolation, or re-run and record what happens. Do not skip the test.

Task 15 also:
- ran the scoped advisory `mutmut` over `tui_consumer.py`, `tui_maintainer.py` and
  `consumer_ui.py`;
- turned every CP-23-owned survivor into a test or argued it equivalent;
- recorded the older remainder as B-122.

Agents can pick up B-122's per-renderer exact-line tests, B-111 or B-123 without waiting on the
walk.
Task 16.4–16.5 (D-267): from screen 22a an ordinary value is edited for one, a chosen set or all
installed harnesses. The edit is a reviewed CONFIGURATION-only lifecycle over those files: it is
compare-and-swap against the reviewed digests, it is refused when the installation has unrelated
drift, and the receipt it records holds only digests. An absent credential offers Set through the
provider with task 13's briefing and then verifies. The §96/§97 candidate spec revision is noted in
the slice.
Task 16.2 (D-265): screen 07 is now a working pre-review config form. Defaults require Enter,
domain validation and credential-shape refusal are inline, credentials remain provider references
in their own section, and Continue re-prepares the value-bound plan before screen 05. A real shell
E2E writes only the two chosen harness files and finds the value nowhere under AART's data root.
Task 16.3 (D-266): screen 22 is the grouped User variables and credentials area. Its rows are
installed artifacts; screen 22a keeps Configuration and Credentials visibly separate. Real
artifact-owned files are strictly parsed and classified as matched, changed outside AART, missing
or unreadable, while credential health still comes only from provider observations.
Task 13 (D-263): an author's credential help reaches every place the value is asked for, in the
same words from `application/credential_guidance.py`:
- Screen 07 in Fast shows the name, which artifact needs it, what it is for, how to get it, the
  format and the permissions hint.
- On the terminal lent to the provider, the same lines come just before its prompt.
- The CLI's unanswered-credential refusal, text and JSON, carries them too.
- Missing guidance says to ask the named artifact's maintainer. `help.obtain_from.url` is optional
  for manually issued credentials.
- Guidance with control or format characters is refused.
- Differing help on a shared credential is kept per owner instead of refusing the install.
- Two artifacts sharing a credential still fail the second's pre-check (B-121).
Task 12 (D-262): Credential Action's permitted actions (Verify, Replace, and Delete when unused) are
rows. Enter's label follows the row, and Verbose describes the focused row. Replace and Delete open
review 24a, which names what uses the credential and says nothing is kept. Confirming plans through
`plan_credential_mutation`, runs the reviewed digest through `CredentialEffectInterpreter`, and
re-inspects before landing on Details or Credentials. The terminal is lent to the provider, so AART
never reads the value. Verify answers in place. Credential actions write no Activity receipt yet
(B-120).
Task 11 (D-261): Artifact Details and installation read one eligibility rule. An empty harness or
platform declaration is unconstrained, and a declared platform excluding this machine refuses
placement. Details lists eligible and detected-but-not-eligible harnesses separately and drops its
decorative actions line. Space selects the focused artifact, and install works from Details.
Task 10 (D-260) makes installation harnesses explicit user intent: screen 05 always offers the
eligible targets, re-prepares against the chosen subset and refuses empty, stale or incomplete
choices. Real isolated E2Es prove exact OpenCode and Tabnine Skill/MCP delivery and receipt
profiles; the manual fixtures now declare all three supported lab harnesses. Updates retain their
recorded harnesses (B-119).
Task 09 (D-259): whether a Candidate is already promoted is read from the Registry trees on every
composition, so it reads `Promoted locally` after the commit and after a restart, and no screen or
transaction offers it again (B-118 tracks the Source counts).
Task 08 (D-258): Remediation states the changes AART will make as outcomes, with Fast impact and
Verbose effect terms; Continue is its row; harness-only plans go straight to Ready, which discloses them.
Task 07 (D-257) describes the focused Marketplace artifact or Collection from its approved summary
below the list in Verbose (collapsed by `v`), following the rows' search, with a truthful fallback.
Task 06 (D-256) made Success's `View installed`/`View receipt`/`Done` working rows; `View receipt`
opens this operation's exact receipt, Esc leaves for Marketplace instead of the finished wizard, and
Undo is explained rather than offered because no reviewed installation undo exists (B-117).
Task 02 (D-252) made the Candidates table the actions block and the focused Candidate its
Verbose-only cursor description; task 03 (D-253) made Candidate file diffs the Verbose projection
of screen 37 and removed `f`; task 04 (D-254) removed Validation's `p` so Enter is the only route
to Policy; task 05 (D-255) removed TUI push entirely at that historical point, so screen 45 ends at
the local commit and lists push → review/merge → update checkout → Registry Sync. The CLI
`registry push` was kept. Product Specification §164.7/D-312/CP-26.18 later supersede the TUI-wide
removal by restoring explicit Push specifically on Registry Maintainer's local-workspace row.
Evidence is in the slice.
The unfinished Source onboarding changes from the previous run are completed in the working tree.
Add Source names the new Source and explains explicit Candidate discovery, retaining its row for
`[s] Sync`. Returning from Source Details or cancelling its Sync review also preserves that Source.
D-251 records the second focus defect reproduced by the real composed workflow and its repair.

Focused evidence: 83 tests and 193 subtests pass, including the real Add → Details → cancelled
review → Sources → Sync → repeat Sync → new-version discovery path and a Hypothesis cursor
precedence/persistence property. Five targeted semantic mutations were killed. Scoped advisory
mutation analysis is recorded; format, lint, typecheck, unit (3,978 OK) and validate passed.
Per-task work runs only the verifying gates; the full suite is task 15 (owner instruction).
Task 01's detailed evidence is in
[`slices/CP-23-actionable-tui-workflows.md`](slices/CP-23-actionable-tui-workflows.md).

**Next product action: task 15.** Run the complete CP-23 verification batch: full tests and gates,
the scoped advisory mutation analysis, and the recorded manual walkthrough. CP-23 as a whole is not
verified until that work and the owner's manual acceptance are complete. No human acceptance is
claimed by task 14's automated matrix.

The CP-23 owner revisions remain historical evidence under Product Specification §167 and
D-249–D-250: its TUI-push removal was done under D-255 and later superseded by §164.7/D-312/CP-26.18;
offer explicit Skill harness choice in task 10, carry credential guidance
through approved metadata in task 13, and enforce the shared frame without in-TUI exceptions in
task 14. All cursor descriptions are Verbose-only; essential input guidance stays in Fast.
Preserve the exact Registry baseline and the distinction between local promotion and publication.
The previous lab and the operator's untracked notes remain untouched.

CP-22's closure is an owner decision, not fresh gate or manual evidence; its historical gate is
`d60bdd5`. Bootstrap stage history remains backlog, and the unfinished old QA-098 sentence is not
a pending user question (D-248). The historical handoffs below do not override this next action.

## Historical CP-22 handoff (2026-09-11; superseded by closure above)

**At this checkpoint CP-22 was OPEN — step 17 was landed and step 16 awaited a manual run.** The
third manual run's seven findings are all built: `QA-092`…`QA-097` (`8f5605b`) and `QA-098`, which
makes the registry this project publishes a row and its description the lifecycle (`D-247`). Whether
a remote branch exists is still a network answer a frame cannot go and get, so what the screen
reports is the checkout's own knowledge of its remote, refreshed by `[u] Check upstream`, and
`MaintainerPublicationState.UNOBSERVED` keeps *"nobody has looked"* apart from *"there is no such
branch"*. Two things are open and neither blocks: the initialization stage report is in
`BACKLOG.md`, and the operator's `QA-098` message ended mid-sentence — *"chcialbym zeby tez byla"* —
so one addition is to be asked for. Slice document:
[`slices/CP-22-one-screen-structure.md`](slices/CP-22-one-screen-structure.md).

CP-21 gave every screen one skeleton; the operator walked it and found the skeleton real but filled
differently by every screen — *"kazdy widok powinien miec ta strukture … bo teraz co widok jest
inaczej mam wrazenie"*, and *"to powinno byc w kodzie zeby nie bylo zbyt wielu wyjatkow od
reguly"*. The rule they stated by name: **actions and view status never share a block.**

Landed so far:

- The launch directory is the footer's caption, flush on its rule, with the terminal's padding
  above it rather than between it and the keys (`QA-086`; `D-242` revising `D-235`, `f43e9ff`).
- The skeleton is a type: `Frame` names the blocks, its field order *is* the layout, `render`
  derives the arrangement from the declaration, and the claims are Hypothesis properties over
  generated frames rather than examples (`QA-087`, `4869c10`).

- The source answers blocks rather than lines: `ConsumerScreenSource.lines` is `actions`, `status`
  carries what only reads, and `tests/screen_block_structure_test.py` holds it over every screen
  with `MIXED_SCREENS` naming the nine that still mix (`QA-087`; `D-243`).
- Both dashboards: rows alone in the actions block, first-run guidance and counts as one `status`,
  the `Navigation:` labels gone (`QA-087`; `D-243`).

- Screen 21 Registries: the Add row alone, what a registry is and what this machine has both in
  view status, the second only while nothing is connected (`QA-087`; `D-243`).

- Screen 27 Settings: the toggles and their group headings alone, the Maintainer Mode consequence
  as view status (`QA-087`; `D-243`).

- Screen 29 Doctor: `doctor_rows` and `doctor_status`, with `render_doctor` still composing the
  whole report for the command line and the TUI dropping its repeated title (`QA-087`; `D-243`).

- Screen 46 Registry Maintainer: rows only where there are rows, both explanations as view status
  (`QA-087`; `D-243`).

- Screen 22 Add Registry: the five fields alone in the actions block; the introduction, the
  reassurance that nothing connected is changed, and the key prompt all below the rule as view
  status, the prompt still last with a blank above it (`QA-087`, `QA-029`; `D-243`). The operator
  settled the open question on the rendered frame — *"Wszystko pod pola (jak reszta)"* — so a form
  is not an exception and `Frame` gains no block above the rows.

- Screens 31 Add Source, 46a Initialize Registry, 46c Scan Repository and 46h Rebuild Registry:
  the same split, and the rule is now a table — `_FORM_PROSE` maps each form to its introduction
  and its one line addressed to the reader, so a sixth form adds a row rather than a shape
  (`QA-087`, `QA-029`; `D-243`). **`MIXED_SCREENS` is empty**; the assertion on it stays as the
  only thing that would notice a future exception.

- A key is advertised, not described (`QA-088`): the prose that moved below the rule turned out to
  describe four keys two lines above a legend that advertised two of them. All five forms lost the
  sentence; a form's legend now reads `[Type] Edit   [Backspace] Delete   [Space] <what it changes>
  [Enter] Next / continue`, with `_FORM_TOGGLE_LABELS` carrying the word the prose used to.

- A row is the choice, not the choice plus its explanation (`QA-089`): screen 46h's rows are bare
  labels and the stage purpose follows the cursor into the description block, so `[v]` opens and
  closes it like every other cursor description (`QA-070`).

- Review and result screens: a review states its subject from the draft the reader just filled in
  (`QA-090`) — the reviews used to draw one line telling the reader to press a key the legend
  already advertised, and nothing about what was about to happen. And a screen with no rows now
  draws no actions block at all, read off the row model rather than off a set of named screens
  (`QA-091`, `D-244`).

- `QA-085` is closed: a reset empties the root before it removes the marker, so a failed reset
  always leaves a lab that is still resettable, and an already-unmarked lab has a checked recovery
  — the refusal prints `chmod -R u+w <root> && rm -rf <root>` and the acceptance document carries
  it under *If the lab loses its marker*.

**Exact next action: finish step 16** with the operator's third manual run over
`QA-044`…`QA-091`, using the lab procedure in `docs/testing/END_TO_END_ACCEPTANCE.md` and the
screen walk in `docs/testing/TUI_MANUAL_WALKTHROUGH.md`. The full `make quality` half passed on
`d60bdd5`: both discovery runs passed 3,924 tests (one skipped), branch coverage was 85.47%, and
format, lint, type, repository validation, packaging, docs and secret-shape gates were green.
Everything CP-22 changed is in the TUI's composition, so the manual run is the remaining evidence:
the screens are what the findings were about.

One thing to raise on that run rather than decide alone: on three forms the key legend now wraps to
three lines with `[v] Fast / Verbose` alone on the middle one. Moving `v` down to the row with
`[↑/↓] [Esc] [?] [q]` would close it up, and `v` is arguably universal in the same way they are —
but it changes the footer on every screen, so it waits for the operator.

The screen steps move one concrete view at a time and never in the abstract:
*"musimy rozmawiac zawsze o konkretnych widokach"*.

CP-21 remains **IMPLEMENTED — AWAITING MANUAL RETEST**; its retest folds into CP-22 step 16. Its
plan entry is now `done` — all eleven steps were evidenced — so the status line advances to CP-22
rather than sitting on a finished epic.

## CP-21 current objective (2026-09-11)

**CP-21 is IMPLEMENTED — AWAITING MANUAL RETEST.** All eleven steps in `docs/refactor/plan.json`
are done. The operator's second manual TUI run walked the maintainer route from an empty Registry
through initialization, Sources, Candidates, promotion and publication, then the consumer route
through Marketplace, install and credentials; its findings are `QA-058` through `QA-084` in
`TODO.md` (retired; git history keeps it), the slice document is
[`slices/CP-21-second-manual-tui-run.md`](slices/CP-21-second-manual-tui-run.md), and the raw
transcripts are the operator's own `nowe bledy i znaleziska.txt` (untracked).

Every finding that run opened is closed in the tree. What that means and does not mean:

- Credential entry stays inside the TUI — the screen is lent to the provider's prompt and taken
  back — and the lab keeps its own keychain (`QA-081`/`QA-084`; `D-229`).
- The promotion path advances on its own evidence, and back navigation keeps its Candidate
  (`QA-073`/`QA-074`).
- One screen skeleton composes every screen, with an anchored footer, no empty sections and a
  Fast/Verbose toggle that means something (`QA-064`/`QA-065`/`QA-067`/`QA-068`/`QA-070`;
  `D-233`, `D-234`).
- The launch directory sits above the key legend and a nested title is a trail through session
  history (`QA-066`/`QA-069`/`QA-071`/`QA-083`; `D-235`, `D-236`).
- A completed sequence leaves the back stack, and Esc from a list reaches its dashboard
  (`QA-072`; `D-237`).
- Screens tell the truth about state: promoted Candidates, empty connected-Registry blocks, stale
  Sources and no leaked screen identifiers (`QA-060`/`QA-075`/`QA-076`/`QA-077`; `D-238`, `D-239`).
- Harness delivery is one honest answer across Artifact Details, review, Remediation and Success
  (`QA-078`/`QA-079`/`QA-080`; `D-241`).
- A reviewed Registry commit is published from inside AART to a configured branch that is never the
  default (`QA-082`/`QA-055`; `D-228`, `D-240`).
- One malformed manifest is reported beside the scan rather than failing the whole Source
  (`QA-063`; `D-230`).

Closing evidence: `make quality` passes all nine gates it ran, over 3,866 tests with one skipped, at
85.43% branch coverage, and `make integration` passes all 381 end-to-end tests standalone — quality
skips that gate as redundant, because all 381 of its tests are among the 3,866.

Step 11's mutation run found five unheld claims inside step 8's own code and the asymmetry it
reused. All five are held now, eight targeted mutations were killed, and the scoped run went from 99
survivors to 77 with none left in the new function. What remains predates this slice and is
classified in `B-113`, including three behavioural gaps worth a test the next time `placement_for`
or `_merges` is opened.

**What is left is not code.** CP-21 is implemented and not verified: none of it has been seen at a
terminal by a person since the run that produced the findings.

**Exact next action:** run `make manual-test-setup`, follow the generated `START_HERE.md` through
the TUI, and manually retest `QA-044` through `QA-057` (already outstanding from CP-20) together
with `QA-058` through `QA-084`. Check those items only after the operator confirms them, then
commit the retest result. The findings still genuinely open from earlier runs — `QA-025`, `QA-027`,
`QA-028`, `QA-032`, `QA-033`, `QA-056`, `QA-057` — are outside CP-21's scope and remain in `Open`.



## CP-20 current objective (2026-09-09)

CP-20 is **IMPLEMENTED — AWAITING MANUAL RETEST**. All seven steps in
`docs/refactor/plan.json` are done: the Registry/Doctor/install wording and navigation are clear;
Registry disconnection is reviewed and bounded; the disposable MCP exercises a provider-owned
credential prompt; fresh manual labs own isolated HOME/XDG, repositories, bare remotes and unique
branches; and `aart reset` plans only exact AART-owned state behind two confirmations.

Closing evidence is green: six targeted semantic mutations were killed; the focused CP-20 set
passes 177 tests plus eight subtests; `make quality` passes 3,677 tests (one skipped) at 85.36%
branch coverage and every non-test gate; separate `make integration` passes all 381 E2E tests. A
real lab smoke created three repository/remotes pairs on `manual/7fd37689f593` and its marked reset
removed only that lab. B-108 did not reproduce and remains recorded as an intermittent historical
test-isolation finding.

**Exact next action:** run `make manual-test-setup`, follow the generated `START_HERE.md` through
the TUI, and manually retest QA-044 through QA-052. Check those items only after the operator
confirms them, then commit CP-20. CP-19 remains closed at `e9616dd`.

## Current objective

**CP-18 Migration and release gate is VERIFIED. All six steps and the mandatory execution plan are
complete.**
The slice document is `docs/refactor/slices/CP-18-migration-and-release-gate.md`.

Manual first-run acceptance after closure found and completed B-077 (D-168): bare `aart` exposed its
complete key vocabulary only after `?`, while its first frame never advertised `?`. Every canonical
shell frame now ends with a concise navigation legend naming movement, forward navigation,
selection/toggle, back, help and quit. The curses adapter treats that final line as pinned chrome,
so a tall body cannot
clip the instructions away; the text fallback receives the same frame. Both claims were red against
the shipped behavior before implementation, and the 67 nearest shell/entry/text/layout tests pass.
No PyPI publication or release was performed; manual CLI/TUI acceptance remains the next operator
activity before the first GitHub Release. Full verification is green: all nine `make quality` gates
over 3,324 tests at 85.35% branch coverage, followed by all 343 `make integration` tests.

The next manual pass found and completed B-078 through B-082 (D-169–D-171), using focused tests as
the operator requested rather than repeating the full gates. Curses now resolves a lone Esc after
50 ms instead of inheriting its roughly one-second prefix wait. The Dashboard shows a short purpose
statement for the highlighted destination. A machine with no configured sources shows a compact
first-run explanation of AART before the navigation menu and points to Registries → Add Registry in
a distinct `SETUP REQUIRED` callout; empty Registries exposes the
same action rather than drawing a blank screen. Add Registry collects alias, credential-free Git
URL, branch/tag and default choice, reviews the exact values and executes the same canonical
source-add transaction as the CLI. Local paths remain authoring Sources in Maintainer Mode. The two
apparent built-in registries were old entries
in the real user configuration, not package defaults: both were reviewed and removed through the
public command, their managed snapshots were discarded, and `source list` is now empty. The nine
nearest consumer/source suites pass 113 tests and typecheck is green. Await the operator's second
manual TUI pass before committing this feedback increment.

The complete operator pass is now the repeatable
`docs/testing/END_TO_END_ACCEPTANCE.md` procedure (D-172). It joins real author Git repositories,
an independently reviewed registry and an isolated consumer through installation, update, Doctor,
repair and removal. New observations go into the current section at the top of root `TODO.md` as
`QA-NNN` items; the older body of that file remains historical evidence only. This manual procedure
does not reopen CP-18 or replace the Product Specification.

Preparing the operator's TUI-first version of that walk exposed B-083 and B-084 (D-173). The TUI
can add an approved Registry and can synchronize an already-configured authoring Source, but it
cannot add that authoring Source; separately, a consumer cannot refresh a connected Registry after
a newer Git publication. The local walkthrough names one CLI fallback at each missing boundary and
tracks them as QA-009/QA-010 instead of crediting the later TUI screen with work the CLI performed.
Both are manual-acceptance follow-ups, not reasons to reopen verified CP-18.

OpenCode acceptance then exposed B-085/QA-011 (D-174). The Mac has OpenCode 1.18.29, but every
canonical project/user placement table refuses it and the TUI's fixed target set contains only
Claude and Tabnine. The old best-effort `_OPENCODE` profile is not safe authority: its generic MCP
entry does not match OpenCode's current typed local-server/command-array contract. The TUI-first
walk now declares OpenCode compatibility in its YAML fixtures, proves the refusal is inert, and
does not claim OpenCode coverage until a measured harness slice and TUI selector exist.

Codex has the same user-visible absence but not the same adapter (B-086/QA-012, D-175). Codex CLI
0.152.0 is installed on the Mac, while `codex` exists only as compatibility metadata: it is absent
from every canonical target table, the built-in profile registry and the TUI target set. Its
documented `.agents/skills`, layered `AGENTS.md` and TOML `mcp_servers` contracts require a separate
measured vertical slice; it must not be implemented as an alias for Claude or OpenCode.

The first real `registry init` added two more manual-acceptance findings. B-087/QA-013 records that
an init with no usage-reporting destination still generates an Issue Form and two inert workflows;
the default should require explicit opt-in for those optional assets. B-088/QA-014 records that the
confirmed human output repeats its warnings and path inventory and buries a successful result under
five follow-up commands. Neither blocks the current walk, and neither reopens CP-18.

The following audit of that valid empty Registry added B-089/QA-015. Its two warnings both mean
that there is nothing to assess yet, but terms such as `unassessed`, `partial` and a nonexistent
`security/index.json` make a passing empty state look broken. The audit model should distinguish
not-applicable checks from warnings while preserving real evidence gaps once artifacts exist.

B-090/QA-016 records the larger first-run gap around those commands: Maintainer screen 46 inspects
an existing Registry but cannot initialize one. A future TUI slice should collect the minimal
identity once, review once and drive init → lock → build → validate → audit as one fail-fast local
bootstrap, with an optional explicit local commit. Push, PR, merge and Git-host settings remain an
external publication handoff under 165.27 rather than hidden TUI side effects.

Two following interaction failures are now B-091/QA-017 and B-092/QA-018. Raw CLI remediation is
copied into Add Registry's TUI notice, and a refused preparation remains on a Review screen whose
Enter action can no longer succeed. TUI diagnostics need typed in-product actions, and a refusal
must return to the existing Registry row or editable form rather than advertise an impossible
confirmation. B-093/QA-019 separately preserves Git's symlink refusal while requiring it to name
that `AGENTS.md` is a symlink and state safe remediation.

**B-094/QA-020 is now the critical manual-acceptance blocker.** The clarified model is the accepted
one: Superpowers remains a monitored authoring Source, Sync discovers its explicit `aart.yaml`, a
Candidate appears, and only the selected promoted artifact becomes Registry content. The public
entrance refuses that valid shape before discovery because `source add` runs `load_native_source`
(canonical `artifact.json` packages) before Maintainer Sync can run `compile_author_source` (author
YAML). `registry scan` does not persist TUI history and direct vendoring skips the claim. Fix this
format/authority seam before continuing the Source → Candidate portion of the live pass.

**B-094/QA-020 and B-083/QA-009 are now fixed and awaiting manual retest (D-176, D-177).**
Authoring-Source admission is separated from consumer native-package validation:
`validate_authoring_source_candidate` still reads a tree that declares root `aart-source.json`
through `load_native_source`, admits any other tree when `discover_author_manifests` finds at least
one explicit `aart.yaml`/`aart.json`, and refuses by name a tree that declares neither. Admission is
discovery, not compilation — 164.2's `3 manifests · 1 invalid` Source row proves an invalid manifest
is a Candidate state rather than a subscription refusal. No boundary moved: symlinks and special
entries cannot reach validation because `source_snapshot_digest` refuses them and `SourceCandidate`
will not construct without that digest, and the E2E fails itself if the public path ever requests
weakened transport. An authoring Source's `declared_source_id` is its configured alias, so an
ordinary upstream commit is not read as an identity transition, and its consumer Marketplace
contribution is empty rather than an `Err` — the projection loop returns on the first `Err`, so the
old refusal would have let one subscribed author repository empty the whole Marketplace.

B-084/QA-010 and B-087/QA-013 are now **fixed and awaiting manual retest** (D-179, D-180). Screen 21
routes `s` to a distinct `REGISTRY_SYNC` action whose review (21c) names the ref that will be
fetched, states PS 161.7's rule that a registry refresh is not an artifact update, and says a failed
fetch keeps the snapshot already held; execution goes through `sync_configured_sources`, the single
transaction `aart source sync` also uses, and `_prepare_registry_refresh` refuses a row that is not
a connected registry, so INV-199 stays testable rather than asserted. `registry init` now writes the
usage-reporting Issue Form and its two workflows only when `--usage-reporting-repository` names a
destination, and the generated README describes the registry that was actually created. Evidence:
`tests/consumer_registry_refresh_test.py`, `tests/registry_init_scaffold_test.py`; targeted
mutations killed, focused suites green.

B-089/QA-015 and B-088/QA-014 are now **fixed and awaiting manual retest** (D-181, D-182). An empty
registry's audit reports the provenance-coverage and installation-risk checks as `info` notes —
what the audit did rather than what it found — and both become warnings again the moment an
external reference or an owned package exists. A confirmed Maintainer action states its result
once: the outcome no longer repeats the warnings its review just stated, drops an `observed:` count
equal to its own headline, and the follow-up commands are the AART pipeline without the `git diff`
line that re-listed every reviewed path. `registry init` also stopped warning that the
usage-reporting templates were inert, because D-180 no longer writes them. `--json` is unchanged
and still carries review and outcome in full. Evidence: `tests/registry_empty_audit_test.py`,
`tests/curation_outcome_brevity_test.py`, `tests/registry_cli_integration_test.py`; thirteen
targeted mutations, all killed; verified through the public CLI.

B-093/QA-019 is now **fixed and awaiting manual retest** (D-183). The Git acquisition refusal is
unchanged and still fail-closed, but each refused entry names the kind that was observed — symbolic
link, submodule, unsupported Git mode, unsafe path or excessive depth — and carries remediation for
that case. A symlink's target is never printed, because it has not passed the repository's
path-safety rules. Deciding the entry kind before reading the size also stopped reporting every
submodule as a malformed listing, since `ls-tree -l` gives a gitlink no size. Evidence:
`tests/git_unsafe_entry_diagnostic_test.py` and a real committed symlink driven through the public
`source add` in `tests/authoring_source_admission_e2e_test.py`; nine targeted mutations, all killed.

B-092/QA-018 is now **fixed and awaiting manual retest** (D-184). A preparation that refuses returns
the session to the screen the action was asked from and clears the pending action, so no screen goes
on advertising a confirmation for a plan that does not exist and a later Enter cannot reach the
execution boundary. For Add Registry that screen is the form, with the operator's values intact. The
notice is drawn there because `_ANSWERABLE` now includes `ACTION_REQUEST_SCREENS`, derived from
`_ACTION_REVIEW` rather than hand-listed twice. Two consumer E2Es were corrected to the new landing
screen — both of their names already described it — keeping every other assertion and gaining a
check that no action stays pending. Evidence: `tests/consumer_declined_preparation_test.py`,
`tests/consumer_application_e2e_test.py`; five targeted mutations, all killed.

B-091/QA-017 is now **fixed and awaiting manual retest** (D-185). `Diagnostic` carries an
`interactive` projection beside `remediation`: the same next step written for somebody already
inside the application. `_refusal` renders that when a diagnostic has it and otherwise only the
remediation steps that name no command, so an unconverted producer degrades to saying less rather
than to printing shell syntax, and a refusal whose every step was a command still says that the next
step lives elsewhere. The duplicate alias, duplicate origin and ref, changed declared identity and
the two unsynchronized-source catalog refusals now carry prose that names this machine's own state.
CLI and JSON remediation contracts are untouched. Evidence:
`tests/tui_has_no_cli_commands_test.py` — the projection, `QA-017`'s own scenarios, a sweep over
every `ConsumerScreen` and `MaintainerScreen` drawn with a command-carrying refusal on it, a
sensitivity test for that sweep, and a Hypothesis property for the universal half; seven targeted
mutations, all killed.

B-090/QA-016 is now **fixed and awaiting manual retest** (D-186). Maintainer screen 46 offers `n`
Initialize Registry: a form (46a) collecting the registry ID, display name, an optional
usage-reporting destination and the one opt-in local commit, and a review (46b) that names all five
stages and states that nothing will be pushed or merged. One confirmation runs init → lock → build →
validate → audit fail-fast through `agent_artifacts/io/registry_bootstrap.py`, which is the ordering
and nothing else: the three writing stages go through the same `LocalCurationService` prepare/
finalize pair the CLI drives and the two gates are the same planning functions, so there is no
second implementation of what a registry is. `registry_identity_refusal` judges the form's identity
through the very `RegistryInitOptions` `init` builds. The commit is part of the review digest, so
the two commit choices are two plans; the run records every `git` call it makes and a test asserts
none is `push` or `merge`. A partial run is a report rather than an exception — the stages are a
prefix of the five, nothing is re-read, and the result says which stage stopped it. Evidence:
`tests/maintainer_registry_init_test.py` (19 tests, including one end-to-end confirmation that
leaves four real files in a project checkout) and `tests/maintainer_navigation_test.py`; eleven
targeted mutations, all killed, three of which found claims that were not yet held.

B-095/QA-021's **application half is built and green** (D-187); its TUI half is the next piece of
work. `agent_artifacts/io/registry_adoption.py` gives a maintainer the second onboarding model beside
the monitored Source: `scan_repository` acquires one credential-free Git URL at one pinned commit,
compiles only committed `aart.yaml`/`aart.json` manifests through `compile_author_snapshot`,
reconciles and validates the resulting Candidates entirely in memory, and writes nothing — a test
compares `git status --porcelain` before and after and asserts no `aart.config.json` appears, because
looking at a repository once is not subscribing to it (INV-199/INV-200). Compiling needs a Source
name the repository does not have, so `_scan_alias` invents `scan-<slug>` for the life of the call;
what the registry publishes carries the registry's own alias, held by a test that reads every written
file and refuses to find the throwaway name in any of them. `prepare_adoption` turns a selection into
one atomic `plan_bulk_promotion` in VENDORED mode, so an artifact whose own plan refuses takes the
whole preparation down by name, and `apply_adoption` re-checks the review digest before
`finalize_promotion`. Only each manifest's declared `payload.include` is copied, because the compiled
canonical entries are carried rather than re-derived, and the adopted copy records the upstream URL,
resolved commit, manifest path and input digest as ordinary native provenance — which is what the
later explicit `Check upstream` action will compare against. Evidence:
`tests/registry_repository_scan_test.py` (14 tests over a real Git repository and a real registry
checkout created through `bootstrap_registry_workspace`); five targeted mutations, all killed, two of
which found claims that were not yet held.

QA-021's **TUI layer is now built and green** (D-188). Screen 46 advertises `s` Scan Repository;
`46c-scan-repository` collects a `RepositoryScanDraft(url, ref)` and states that the repository will
not become a Source; `46d-scan-result` renders every explicit manifest while admitting only
validation-cleared coordinates to `_SELECTABLE`; and `a` prepares `46e-review-adoption`, which names
every selected coordinate, the resolved commit and every path the local transaction will change.
The scan is a completed read-only preparation and clears its action rather than leaving a fake
confirmation pending; adoption is the separate review-digest checked mutation. The production
composition binds the two ports to the current project registry, and an E2E test substitutes only
Git transport while driving a real author repository and real registry checkout. Evidence:
`tests/maintainer_repository_adoption_test.py` (8 tests); three targeted mutations killed (route,
adoptability filter, exact selection crossing the port).

B-095/QA-021 is now **complete and awaiting manual retest** (D-192). `aart registry adopt` and
`aart registry check-upstream` are the machine-complete CLI projection, and they are a skin over
`io/registry_adoption.py` rather than a second implementation: no planning, discovery or provenance
logic lives in `commands/registry.py`, so the CLI and the TUI cannot drift into two answers about
what adopting means. `adopt` with no `--artifact` is a complete answer on its own — it lists every
declared coordinate and writes nothing — because an operator has to see what a repository declares
before naming any of it; repeating `--artifact KIND/NAME@VERSION` reviews exactly that selection and
reports the digest and the paths it would change; `--yes` is the only thing that writes. The three
phases (`scan`, `review`, `adopted-local`) are named in the payload rather than inferred from which
keys are present, and `applied` is stated in all three. `--expect` is optional but verified whenever
given, which is what makes `check-upstream`'s two acquisitions safe: a stale digest refuses instead
of adopting whatever upstream declares now. Upstream that changed without releasing proposes nothing
and says so, because INV-203 makes the published coordinate immutable. Evidence:
`tests/registry_adoption_cli_test.py` (8 tests over the real public CLI, a real Git repository and a
real Registry checkout, substituting only transport) and the action-set contract in
`tests/registry_cli_test.py`; five targeted mutations, all killed, three of which found unheld claims
— both `--expect` checks and the listing order.

B-086/QA-012's **Skills and instructions half is measured, built and green** (D-193). Codex CLI
0.152.0 was measured with `codex debug prompt-input`, which renders the model-visible prompt
including the skill roots it is about to read and the instruction files it has loaded, and which
contacts no network. That observation put four rows in `domain/harness.py`: Skills at
`.codex/skills/<name>` at both scopes, `AGENTS.md` at the repository root and `$CODEX_HOME/AGENTS.md`
for the user. `.agents/skills` is a real Codex root but is the cross-vendor interop directory the
same binary migrates other agents' installations from, so an installation asked for by harness name
lands in Codex's own first root instead. `$CODEX_HOME/instructions.md` is measured *not* read by
this build and is absent rather than listed. There is no guideline row (that build documents no
guidelines directory), no hook row (unmeasured), and no MCP row: Codex keeps servers as TOML tables
that `LocalHarnessRegistry` cannot edit without risking the keys around them, and INV-071 leaves no
room for a TOML dependency — `B-096` carries that finding, including that a project-scope
registration is inert until the operator trusts the project.

Harness selection stopped being an MCP question at the same time. `_canonical_marketplace_target`
derived the machine's harness set from `MCP_TARGETS` alone, so a harness AART can install Skills and
instructions into stayed invisible until it also started a server; it is now the union of every
measured table, which is what "harnesses this machine has measured" always meant. Evidence:
`tests/codex_harness_test.py` (10 tests, two of which build a temporary project and `CODEX_HOME`,
write into the destinations the table names and assert the installed Codex finds them); five
targeted mutations, all killed, three by the live observation alone.

B-085/QA-011's **Skills, instructions and MCP are measured, built and green** (D-194), by the same
method. OpenCode 1.18.29 ships `opencode debug skill`, `debug config` and `debug paths`, which name
the skills it found and the file each came from, print the merged configuration, and print the
roots; the runs used a temporary `HOME` with the XDG variables cleared. Six rows followed: Skills at
`.opencode/skills/<name>` and `.config/opencode/skills/<name>`, `AGENTS.md` at the repository root
and `.config/opencode/AGENTS.md`, and MCP under the `mcp` key of `opencode.json` and
`.config/opencode/opencode.json`. As with Codex, the roots belonging to other harnesses
(`~/.claude/skills`, `~/.agents/skills`) were observed working and deliberately not used.

The MCP half needed a contract change rather than a row: a local server in `opencode.json` is
`{"type": "local", "command": ["/path", "--flag"]}`, not a command string beside `args`. That
difference is the target's, so `McpTarget` gained an `entry_shape` (`McpEntryShape`, defaulting to
the shape already written) and `registration_entry` switches on it; nothing else in the pipeline
learned that harnesses differ. One measured contradiction is recorded rather than smoothed: this
build also reads `~/.opencode/opencode.json`, which its own shipped documentation denies, so the
user-scope row is a deliberate choice of the documented config root and a test says so. No guideline
row (no documented directory) and no hook row (unmeasured). Three tests that had used `"opencode"`
as the name of an unmeasured harness now name `cursor`, which genuinely is one. Evidence:
`tests/opencode_harness_test.py` (9 tests, two of which run the installed OpenCode); six targeted
mutations, all killed.

Codex hooks were then measured, and the measurement kept the row out rather than putting one in
(D-195, B-097). `codex features list` reports `hooks` stable and enabled — a first-class configured
capability, not a plugin extension, with twelve events and four handler kinds. What refuses it is
that the configuration is reached through a path key in `config.toml` (B-096's TOML problem
unchanged), that project-local hooks stay disabled until the operator trusts the project, and that
every new or changed hook is held for interactive review before it runs. AART could write the file
and report success, and the hook still would not run; a receipt for something that did not happen is
worse than a refusal by name, so `hook_target("codex", …)` keeps raising.

Both harnesses were then taken from measured tables to installed and read back (2026-09-09), which
is what the request "mcps, skills for opencode in first place then for codex" actually asks for and
what tables alone never prove.

That verification immediately found a defect in the OpenCode half that was already shipping
(`D-197`). Writing a registration had learned about `McpEntryShape`; reading one had not, so every
vector-shaped entry read back as nothing. The file was correct, the server started, and the
installation never converged — status showed drift that was not there and repair would have
rewritten a correct file forever. `registered_command` is now the inverse of `registration_entry`,
held by a property over every measured target, and `observed_command` moved onto the registry port
so whoever writes a harness's servers is who reads them back.

That move is also what let Codex MCP land (`D-196`), closing `B-096` by measurement rather than by
choice. Codex's own `mcp add`/`remove`/`list --json` keep the promise `LocalHarnessRegistry` makes
and a hand-rolled TOML writer could not — an operator's comment, an unrelated key, another server's
table and a following table all came back byte-identical around an add and a remove. So the target
names `McpEditor.HARNESS_COMMAND`, the registry routes to it, a missing Codex is named rather than
reported as registered, and there is no fallback to writing the file directly. User scope only,
because `codex mcp add` writes the global configuration and offers no project flag.

Both paths are now proven end to end: an author's manifest compiled, published, planned, installed,
and then the launcher that landed started and asked a question, answering with the arguments the
author declared, the config value supplied and the secret read at launch. OpenCode's Skill half goes
through the public command and lands in `.opencode/skills/<name>` and in neither `.claude` nor
`.agents`. Nine targeted mutations for Codex and six for OpenCode, all killed; three survived first
and each was a finding — a test that skipped where it should have failed, an unmeasured assumption
that `codex mcp add` refuses duplicates (it overwrites), and the reader defect above.

**Next:** OpenCode's guidelines and hooks are unmeasured, and Codex's hooks stay refused for the
review-gate reason in `D-195`/`B-097`, which delegation does not change. `B-098` notes that Claude
has no install-and-start MCP test of its own and that the three E2E modules want a shared fixture
before a fourth harness arrives; neither is on the critical path. Nothing in the QA-001–QA-021 batch
is open, so the batch is handed back for manual retest.

**Batch verified (2026-09-08).** With QA-011 and QA-012 landed, every QA-001–QA-021 finding has a
fix or a recorded, named refusal, so the full gates were run rather than the focused suites this
manual-acceptance batch had been using: `make quality` green (format-check, lint, typecheck, unit
— 3503 tests, validate, coverage 85.18%, packaging-check, docs-check, secret-shape-check) and
`make integration` green (357 tests). The batch is handed back for manual retest; TODO.md's Open
section is empty and its Fixed section is the retest list.

**Re-verified after the harness install work (2026-09-09).** `make quality` green (3538 unit tests)
and `make integration` green (369 tests), on the branch that carries `D-196` and `D-197`.


On top of that, Maintainer screen 31 now offers `a` Add Source: a separate `SourceDraft` form (31a)
and review (31b) that accept only `source-git`/`source-local`, refuse `registry-git` by name, never
set a default registry, and execute through the same `add_configured_source` transaction the CLI
uses. Add Registry is untouched; the 164.2 trust boundary between an authoring location and approved
content is held by a test rather than by convention.

Evidence: `tests/authoring_source_admission_e2e_test.py` (real temporary Git repository through the
real public command: add → sync → one Candidate → durable history → upstream movement → selected
promotion), `tests/source_validation_test.py` (Hypothesis property over generated trees),
`tests/consumer_runtime_test.py`, `tests/maintainer_source_addition_test.py`,
`tests/maintainer_navigation_test.py`. Ten targeted mutations were run across the two slices and all
are killed; the tenth (`source_kind` hardcoded to `source-git`) survived first and was closed by
running the composition test over both kinds. Focused suites, `ruff` and `mypy` are green; the full
`make quality`/`make integration` gates are deliberately deferred to the end of this
manual-acceptance batch, as the operator requested.

Two regressions in the uncommitted manual-acceptance work were found and repaired while proving this
increment (D-178): the first-run welcome panel replaced the Dashboard body on a machine that had no
configured source but did have an installation, and the deferral of `load_local_reporting_service`
into `completion_factory` outran a test seam that substituted it only around composition. The
deferral is correct and kept; the panel now also requires nothing installed.

B-095/QA-021 records the separate model the operator also wants: one-off scan of a repository that
is not saved as a Source, exact YAML/JSON manifest discovery, explicit multi-selection and atomic
vendoring of only `payload.include` with pinned provenance. Today's `scan`, `discover`, `vendor` and
`vendor-batch` each provide a piece but no public/TUI flow composes them. Later movement is checked
explicitly per vendored artifact; it is not described as continuous Source monitoring.

The first public pull-request run after closure exposed that local macOS verification had not
actually proved the advertised Linux/Python matrix (D-167). The failure is fixed and reproduced in
clean read-only Docker copies on Python 3.10, 3.11 and 3.14: all nine gates pass over 3,322 tests on
each interpreter, including a real Poetry wheel build. The fix locks the Poetry CLI itself in the
dev group, uses dev-only `tomli` on Python 3.10, accepts RFC 3339 `Z` timestamps there, makes
scripted Keychain tests inject host availability without changing the production probe, and removes
developer-machine configuration and platform assumptions from the affected fixtures. PR #1's title
is now the valid Conventional Commit `refactor(release): adopt Release Please and complete AART
refactor`.

Step 1 (INV-071, zero runtime dependencies) is done: `tests/runtime_purity_test.py` reads the
dev-group declaration off `pyproject.toml` and the import graph off the source with `ast`, because
a declaration is not a dependency graph (D-152).

Step 2 (INV-072-080, the CI/release profile contract) is done: `tests/enterprise_ci_template_test.py`
holds the five variable/secret/egress/thinness claims, and `tests/aggregate_gate_test.py` proves the
aggregate gate by extracting its shell from the YAML and *running* it (D-153). That found a shipped
defect -- the registry `aart registry init` emits had no requirable aggregate check name, and GitHub
counts a skipped required check as satisfied -- so the emitted registry now gets one too.

Step 3 (legacy removal) is done, and B-070's four unreachable modules are all decided.
`domain/ports.py` and `domain/collections.py` are removed. `domain/outcomes.py` is **kept**: the
release contract names it in `scripts/release.py:SCHEMA_INPUTS` and pins its sha256 in every issued
schema freeze, which is authority the import graph is structurally unable to see (D-154).
`profiles/loader.py` is **kept and is not legacy**: INV-001 requires enterprise profiles to live
outside the public tool and this is the only mechanism admitting one, so the finding is not a dead
module but an unwired invariant -- nothing calls it, and a project's `.agent-artifacts/profiles.json`
is parsed by three test files and ignored by the product (D-155, B-072).

Step 4 (docs reconciled) is done. It applied steps 1-3's method to prose — a document that names a
command is a checkable claim about `cli.build_parser()` — and compared both directions, because an
invented command wastes a reader's time while an omitted one is capability nobody can find. The
omission was `aart doctor`: the whole of CP-16, an entire top-level command, documented nowhere in
the README. The same comparison now covers the product's own user-facing strings, since a
remediation is documentation read at the worst possible moment. Four documents carried stale 0.1
verbs, and the three root trackers (`PLAN.md`, `PROGRESS.md`, `TODO.md`) pointed a newcomer at the
legacy repository's issues as "the source of truth" (D-156).

Step 5 (traceability) is complete. The matrix opened this step at 121 PARTIAL and now stands at
**234 EVIDENCED / 8 PARTIAL / 0 CONFLICT**. The method that produced it: read the invariant's own
words, find the flow that would break it, and only then look for a test -- not the reverse. Reading
tests first produces rows that cite whatever is nearby, which is how the ten TUI rows came to share
one copy-pasted verdict between them.

Four layer claims came out of it: `tui_boundary_test.py` (a screen module may not be an
implementation of infrastructure, may not reach `io/` outside the one declared seam at
`read_consumer_offers`, may not import dynamically, may not branch on the host, and must import with
`curses` absent), `presentation_is_not_semantics_test.py` (no deciding layer may name a presentation
profile at all -- the behavioural half of INV-158 was held, the reachability half was not),
`consumer_properties_test.py::OneCoreTwoSkinsTest` (the printed review and screen 09's Verbose half
are byte-identical, which is INV-061 made checkable), and the matrix guard now resolves cited test
*cases*, not just file names.

The eight rows still PARTIAL each name a flow that does not exist, with a backlog item: B-072
(profiles loader unwired), B-073 (no live smoke in CI), B-074 (no destructive credential verb),
B-075 (no TUI input-entry surface), B-076 (no Collection guidance consolidation), INV-069 (a process
rule with no runtime witness), INV-187 (the maintainer catalog is still being accepted) and INV-213
(B-067: no Collection can be installed, updated or repaired). Do not read them as eight pieces of
missing bookkeeping; every one is a measurement.

INV-081 through INV-105 are now EVIDENCED. Release Please is the sole version/changelog engine; the
reviewed squash title is its semantic input; its generated release PR is the explicit release
boundary; and release CI verifies the built wheel against the tag instead of comparing manually
maintained source values (D-160 through D-165). Issued schema freezes remain immutable.

The scoped mutmut run found and fixed a runner defect: asking for `scripts/release_artifact.py`
still copied only `agent_artifacts`, generated no useful mutants and then failed to import the
target. The runner now derives source roots from `ONLY`. The final run generated 373 mutants,
killed 174 and left four inspected equivalent/cosmetic survivors; the 195 real-install/entry-point
mutants are exercised once by the real artifact gate instead of reinstalling a wheel for every
mutation. Three deliberate mutations independently hold SemVer classification, runtime-dependency
refusal and release-workflow wiring.

Step 6 is verified: all nine quality gates are green over 3,322 tests (one skipped on macOS), branch
coverage is 85.35% locally and 85.09% in the Linux matrix, all 343 separate E2E tests pass,
`poetry check --lock` passes, and a real built
`aart_cli-0.0.1-py3-none-any.whl` passes the artifact verifier against tag `v0.0.1`. B-068 is closed
on the same critical path: the deep-quality workflow invokes mutmut unattended, so the Poetry lock
now includes mutmut 3.7 and Textual under a dev-only Python `<4.0` marker.

There is no next mandatory critical-path slice in `EXECUTION_PLAN.md`. Future work starts only by
deliberately promoting one of the measured BACKLOG capabilities; the eight PARTIAL traceability
rows are the honest map of those absent flows, not unfinished CP-18 bookkeeping.

The rule those four decisions produced, which the next agent should carry into steps 5-6: an
unreachable module is *replaced*, *unadopted*, or *unwired*, and only the middle case is safe to
delete. Unreachability is a reason to ask, never on its own an answer.

**The narrative below is kept as the record of CP-14 through CP-17.**

**CP-14 Maintainer TUI 30–53 is VERIFIED.** All seven steps are complete: screens 30–53 are live in
the one shared shell, and step 7's legacy retirement finished with the evidence-led orphan sweep of
`agent_artifacts/tui.py` (D-129), B-044 closed by D-128 and B-046 closed by D-130. The CP-14
narrative below is kept as the record of how it got there.

**CP-15 Accepted lifecycle/edge-case hardening 54–100 is VERIFIED.** The slice document is
`docs/refactor/slices/CP-15-edge-case-hardening.md`. It opened on a scenario map where sixteen
invariants (INV-210, 216, 218, 219, 221, 222, 223, 226, 231, 232, 233, 237, 238, 240, 241, 242) all
carried the same three words in their evidence column -- *scattered source/registry/lifecycle
safeguards* -- and that phrase was the slice's whole subject: a safeguard at a seam is worth what
the verb an operator actually runs makes of it. All sixteen now carry public-flow evidence, and the
narrative below is kept as the record of how each one got there.

**CP-16 Global doctor and supportability is VERIFIED.** Step 1 adds the public, read-only
`aart doctor` (D-139): one environment-wide observation of canonical project and user installations
feeds both the accepted screen-29 health projection and the existing minimal-reconciliation
planner. Its JSON carries every item, component drift and full repair plans; its human output names
the same artifacts and reasons. It resolves no Marketplace content and applies nothing. Step 1 is
VERIFIED: six real-machine E2E scenarios, a fresh 132-mutant pass, all nine quality gates (3,243
tests, 85.34% branch coverage) and 279 E2E tests are green. The active slice is
`docs/refactor/slices/CP-16-global-doctor-supportability.md`. Step 2 is VERIFIED (D-140): before
installation the same command now reports cached Source/artifact metadata, an exact approved
canonical payload and runtime-dependency evidence as three independent values. It reads every
enabled source once and performs no sync, object publication, package-manager call or install.
B-051 is closed and INV-223 is EVIDENCED; B-010 remains the deliberately separate durable
dependency-cache capability. Eight new E2E scenarios, both scoped mutation passes, all nine quality
gates (3,251 tests, 85.37% branch coverage) and 287 integration tests are green.

Step 3 is VERIFIED (D-141): `aart doctor --repair` reviews and applies exactly one minimal plan.
Review and confirmation are separate invocations and the review's digest is authorization input to
the confirmation; a review applies nothing, `--yes` without the digest is refused, and a machine
that moved returns the recomputed plan rather than applying the stale one. The staleness check
happens twice against two different things, which is the decision D-141 records: the command catches
drift between what the operator read and what they confirmed, and the lifecycle adapter re-observes
under its lease and refuses with `execution-review-stale`. INV-194 is EVIDENCED. The finding was in
the exactness test, whose name claimed source *and* version while only ever omitting the source, so
removing the version requirement killed nothing; it now runs both under-specified forms and each
mutation half kills its own subtest. B-059 records the one survivor left standing.

Step 4a is VERIFIED (D-142). `aart marketplace receipt verify` finds an interrupted run's working
copy only if the operator already knows which receipt to verify, because the probe filters the run
root by one receipt's `plan_hash[:16]` -- and being interrupted is usually the reason they stopped
watching. `aart doctor` is now told nothing and finds it anyway, naming the plan-hash prefix that
ties it back to its run. `LAF-61` and `LAF-66` are both preserved and both have a mutation proving
it. B-052 and B-055 were triaged and stay in the backlog: neither is reachable from a global report
and no mandatory invariant requires either.

The findings were methodological. A phantom-working-copy mutation survived not because a test was
weak but because a healthy machine leaves through the `FileNotFoundError` branch above the line that
changed -- an unexecuted mutation measures nothing, which is the mutation-testing counterpart of
D-138. And the scoped mutmut run then found four gaps the seven manual mutations had not: `readable`
falsey-but-not-`false` is `null` in JSON, and `continue`/`break` plus `or`/`and` at the loop guards
cannot be distinguished by a fixture holding a single working copy.

Step 4b is VERIFIED (D-143). The audit trail INV-191 names had `project_activity`,
`activity_from_receipts`, `activity_view_to_data` and `render_activity` all built and referenced
only by the TUI's assembly -- the third capability in this slice found at a seam with no verb
reporting it. `aart doctor` now carries the day-grouped timeline and each recorded action's own undo
answer, and INV-192 is held as a pair one flow produces: an install reports an undo naming
`delivery:claude` and `payload`, the uninstall that follows reports none. D-143 records the mistake
the first draft made -- cross-checking against `marketplace receipt show`, which returns the *setup*
receipt, a different record with no `recorded_at` or `undo` field at all. Two findings: removing the
"nothing has been recorded yet" line killed nothing, and the scoped run found `artifact` and
`status` published in the payload with no test reading either. B-060 records 84 survivors in step
3's `_run_repair`, which never had a scoped run of its own.

Step 4c is VERIFIED (D-144), and step 4 is complete. Two configurations were being honoured in
silence. A source with `enabled: false` is skipped by every other part of the report deliberately,
so an operator asking why nothing offers an artifact saw a report the source did not appear in at
all -- indistinguishable from never having configured it. And an organization policy that sets a
reporting field replaces the value in the user's own configuration file: `_locked_override_diagnostics`
refuses a contradicting `--reporting-mode` flag, but the configured path was silent, and
`EffectiveConfiguration.locked_fields` had no reader anywhere in the package. Credentials were the
fifth capability in this slice found built at a seam with no verb reporting it. Both are now in the
report, both empty cases are answered in words, and the credential projection's no-leak guarantee is
asserted structurally -- against `CredentialObservation`'s field names, so a future field called
`value` fails there rather than reaching the report. Two claims are held at the seam for reasons
named in the test file: the populated credential list would write to the developer's real Keychain,
and installing an organization policy would mean writing to a root-owned system path.

The finding came from the scoped run before a single mutant executed. Its baseline failed on step
2's `assertNotIn("installed", output.lower())`, which scanned the whole human report while claiming
something about the offline capabilities alone; the new credential section says "no installed
artifact references one", which is true and belongs. The assertion is now scoped to the offline
block and a mutation putting `installed` into that renderer still turns it red. D-144 records the
general form: scope an absence assertion to the surface whose claim it is. Every focused run for
step 4c was green -- only the file the step did not touch could see this.

The second finding repeats step 4b's exactly: six credential payload keys and the disabled source's
`kind` were published with nothing reading any of them, the human line for a credential nothing
depends on was unheld even though its JSON half was asserted, and the separator between dependants
was invisible to a fixture holding one. All 29 survivors inside this step's functions are closed and
re-verified -- 595 mutants, 450 killed, none left in the four functions. The remaining 145 are
B-060's 84 in `_run_repair` and 47 in the report composition, now B-061.

Step 5 is VERIFIED (D-145) and **CP-16 is VERIFIED**. Three things closed it.

The front door: `aart doctor --help` still described the step-1 report, naming one of the six
sections the command now carries, so four steps of newly reachable capability stayed undiscoverable
short of running the verb and reading its output. `tests/doctor_help_e2e_test.py` holds the help
against the report it fronts.

The universal halves: three times in this slice a scoped run found a gap whose immediate fix was to
add a second item to a fixture -- `continue`/`break` in 4a, the undo separator in 4b, the dependant
and locked-field separators in 4c. That fixes the instance, not the kind.
`tests/doctor_properties_test.py` states the claims as Hypothesis properties, and eleven targeted
mutations prove they hold; three of them (`disabled[:1]`, `dependants[:1]`, `runs[:1]`) are exactly
what a single-item fixture cannot express. D-145 records the reasoning.

That run then found two real gaps in step 4a's own claims. The unreadable-run-root branch had no
human-output assertion anywhere -- 4a asserted `readable is False` in JSON and stopped -- leaving the
report free to answer "I could not look" the same way it answers "there is nothing here", which is
the confusion D-142 exists to refuse, standing on the surface an operator actually reads. And
LAF-61's promise was held by the fragment "does not delete" rather than the sentence. Both closed;
`orphaned_runs.py` now kills 25 of 25, up from 40 of 43.

The walk: INV-189, INV-191 and INV-192 move to EVIDENCED. INV-190 stays PARTIAL deliberately -- its
sentence has two halves and a read-only report that lists affected consumers does not show that
`replace` and `verify` account for them.

**Next action: none in CP-16.** The plan's critical path is complete. What remains are backlog
items, none blocking a mandatory invariant: B-060 (84 unclassified mutation survivors in
`_run_repair`) and B-061 (47 in the report composition) are the two worth reading first, then B-062
(a machine with no credential provider reports no credentials rather than saying it could not look),
B-052, B-055 and B-059.

**CP-17 Git-backed live acceptance is IN PROGRESS.** Steps 1 and 2 now join Git acquisition to a
real public consumer install. Step 1 (`git_source_publication_e2e_test.py`) passes the complete
candidate returned by the system Git adapter through validation, publication and a fresh store read
without reconstruction. Step 2 (`git_backed_consumer_e2e_test.py`) commits a promoted vendored
registry to a real repository, configures its valid HTTPS identity, substitutes only the transport
port, and drives public source sync, Marketplace list and install. Sync, the Marketplace row, the
returned receipt and a fresh durable receipt read all name Git's actual SHA rather than
`"a" * 40`; the installed Skill bytes are the promoted payload.

Step 2 found and closed B-057's consumer-facing half. Promotion writes the versioned approved
registry representation required by the Product Specification, but source validation and the
read-only CLI Marketplace still interpreted it as the older compiled maintainer workspace. D-147
routes each shape through its writer's validator and reuses the canonical configured-registry
projection. The old `registry publish` command's disagreement remains backlog; 165.27/165.28 make
Git review/merge, not that command, the publication boundary. D-148 makes the synchronized source
revision an optional, digest-bound provenance value through resolution, planning and lifecycle
receipt serialization, so old receipts remain readable without invented history.

Steps 1 and 2 are VERIFIED. Step 2's full `make quality` is green with 3,295 tests, one skipped and
85.39% branch coverage; the separately run `make integration` is green with 324 E2E tests.

**CP-15 is VERIFIED — all eight steps done.** Step 8 is
`tests/credential_contract_migration_e2e_test.py`, closing INV-231 and INV-232 and the slice with
them. 165.19 says old credentials remain if still referenced by other installed artifacts, and
nothing held it for a structural reason: every credential test here has exactly one installation in
scope, and what happens to B when A changes cannot be measured with only an A. Nothing needed
changing — `marketplace uninstall` already says `credentials: retained` in both renderings, no verb
sets `delete_credentials`, and `_dependants` keys on the reference rather than the provider account.
The finding was in the third mutation: switching credential deletion on by default killed nothing,
because the fixture's Skill declares no inputs and the test asserted an absence that could never
have been present. It is now a pair of calls differing in one keyword, so the absence is evidence
only because the other call shows the deletion was reachable.

**Step 7 before it** is
`tests/promotion_publication_boundary_e2e_test.py`, and it is the one increment in this slice that
changed **no production code** — the finding, not a disappointment. `registry promote --yes` already
honoured 165.28's boundary exactly: it reports `commit: false` and `push: false`, makes no commit,
creates no branch, adds no remote, and leaves every path it wrote untracked for a person to stage.
Nothing said so, and the failure that guards against — a promotion quietly becoming visible to
consumers — is invisible in the maintainer's own terminal, where everything looks like it worked.

The arrangement carries the claim (D-137): the maintainer's checkout and the published registry a
consumer is subscribed to are two directories, because in production they are two states of one
repository separated by a push and a merge. The consumer re-synchronizes after the promotion and is
offered exactly what it was offered before, digest for digest, and still refuses to install the
promoted coordinate. Two of the nine tests were weaker than their names before their mutations
caught them: the evidence test omitted both required digests at once (so either could have been made
optional under a green test), and the install refusal was resting on a stale snapshot rather than on
the boundary. INV-238, 240, 241 and 242 move to EVIDENCED; the Git hop stays with CP-17, since
`git_location_parts` admits no `file://` remote. B-057 records that `registry promote` writes a
layout `registry publish` refuses.

**Step 6 before it** is
`tests/policy_drift_e2e_test.py`, and it closes two invariants with one fact. `aart marketplace
status` reported one word per installation and it was about the payload: an artifact installed under
a permissive policy, on a machine whose administrator later required `registry-reviewed` trust,
reported `current` while `marketplace install` would have refused the very same artifact. And
nothing said its content came from a mutable directory rather than a reviewed registry -- a thing
`marketplace list` has shown since the marketplace existed.

Every lifecycle item now carries a `PolicyStanding` (compliant / non-compliant with the unmet
requirement named / `not-evaluated`) plus the trust itself, in both renderings. It is a dimension
beside `status` rather than a new status value (D-136), and the rule is the installer's own:
`trust_shortfall` is public and `lifecycle` asks that function, so the gate and the health report
cannot drift apart. Nothing is mutated by the drift; 165.21 asks for a decision. INV-233 and INV-237
move to EVIDENCED. B-056 records that the domain `EffectivePolicy` never reaches the consumer path
at all -- both seams construct the permissive default -- so only the live organization policy is
judged.

**Steps 1, 2, 3, 4a, 4b and 5 before it.** Step 5 is
`tests/withdrawal_and_purge_e2e_test.py`, and 165.10's two statements needed measuring separately.
The purge half passed on shipped code and the reason is the strongest one available: there is no
`purge` verb anywhere in `agent_artifacts` -- the word does not appear -- and the registry lifecycle
only deprecates and revokes. So what the file measures is the *ordinary* withdrawal: an upstream
that deletes an artifact and re-points its Collection, then `aart source sync`. The artifact stops
being offered, installing it is refused with a remediation, **what is already installed is untouched
and reports `removed-upstream`**, the payload bytes stay in the object store, and `uninstall` still
works -- the last held by a deliberate special case, since uninstall resolves against the manifest
and never through the source.

The erasure half was red. The `embedded-credential` remediation said "remove the value, rotate it if
real", which names rotation but implies removing is what finishes the job; for content published
from a version-controlled source that is false in the way that costs the most. It now states the
Git-history non-guarantee and names the repository's own secret-removal procedure as still owed.
The ruleset label stays `baseline-v1.1` (D-135) because the digest already carries the change.
INV-221 and INV-222 both move to EVIDENCED. The scoped `make mutants` run over
`security/baseline.py` found its first real gap -- the assignment credential detector decided
nothing in any test -- and `security_baseline_test` gained the case that closes it. B-055 records
the unreachable `ArtifactLifecycle.REMOVED` merge path.

**Steps 1, 2, 3, 4a and 4b before it.** Step 4b is `tests/interrupted_execution_e2e_test.py`: a real
custom entrypoint whose apply fails and whose rollback then also fails, which is the one path that
raises without removing its run directory. So the working copy it asserts on is one the engine
really failed to clean up. `receipt verify` finds it, names the directory the engine actually
created, exits non-zero and leaves it in place; a retry re-plans rather than resuming. Writing it
found that `receipt show --json` ended in a `TypeError` for any receipt with a nested step, which
is every custom-protocol run. INV-226 moves to EVIDENCED.

**D-134** adds the two tools that check the tests themselves: `mutmut` behind
`make mutants ONLY=<path.py> TESTS="<test files>"`, advisory and always scoped, alongside Hypothesis
for universal claims. `AGENTS.md` and `CLAUDE.md` now require both. Neither replaces the targeted
per-claim mutation each slice records.

**Steps 1, 2, 3 and 4a before them.** Step 4a is `tests/verification_failure_e2e_test.py`: a declared
setup that writes one managed block and then fails one verification command. 165.12's report half
already held -- non-zero exit, `verification-failed` as its own status, the compensatable block
restored, the separately-placed payload still `current`. Its evidence half did not: the receipt
recorded the verification result and no applied effects at all, because the engine dropped the step
receipts whenever the rollback succeeded. D-133 keeps them, marked `compensated`, and moves
`rollback_command` to depend on the steps still standing.

**Steps 1, 2 and 3 before it.** Step 3 is `tests/offline_capability_test.py`: Product Specification
165.11 decomposes offline installability into metadata cached / canonical payload cached / runtime
dependencies cached, and AART holds all three as separate refusals under distinct codes even though
`--offline` is one boolean. The dependency layer had no test at all before this, so removing
`--no-index`/`--offline` from the installer argv would have left every gate green while every
`--offline` install silently reached the network. INV-223 stays PARTIAL against a named gap: nothing
*reports* the three before an install is attempted (B-051, for CP-16's `aart doctor`).

Step 2 is `tests/source_upstream_movement_e2e_test.py` plus one
promotion-planning claim: a moving upstream may offer new work and may not rewrite what an
installation says it was installed from, and D-089's rebinding of an already-approved record is
pinned to `registry_snapshot` alone with the promotion audit byte-identical. INV-219 moves to
EVIDENCED and INV-216's consumer half is closed.

Step 1 is `tests/source_sync_command_e2e_test.py`, which drives `aart source sync` over a real
source whose upstream published an invalid revision, and INV-218 moves to EVIDENCED. Writing it
found D-132: `could-not-check` -- the health an explicit last-known-good fallback produces -- was
read as "this source is gone" in three places, so one invalid upstream revision made
`aart marketplace status` report every installation as `source-unavailable` and made `install` and
`update` fail on a plan-construction invariant carrying no remediation. Product Specification
165.11 settles it.

Rewriting the operator's local TUI walkthrough for the whole QA-001–QA-021 batch found two more
defects, both of them created by earlier work in this same batch, and both fixed here as QA-022 and
QA-023. Measuring Codex put it in the shell's harness set, and because Codex hosts no project MCP
server, `placement_for` refused every MCP install the TUI could offer — Claude's and Tabnine's
included. `profiles_requested` now separates a profile somebody typed from one this build merely
measured (D-198). Separately, screen 28's `Default scope: Project/User` had been persisted, redrawn
and never read: the installation host was fixed at project scope, so a User install landed in the
project (D-199). Both are held by tests that were red first, and the full unit suite is green at
3,606 tests.

The walkthrough itself is now a TUI manual rather than a CLI script: registry creation, authoring
Sources, sync, promotion, one-off repository scan with selective vendoring, upstream checks,
consumer registry connection, refresh, scope selection, install, update, repair and uninstall are
all driven from screens, and the terminal is used only for Git/GitHub work AART deliberately does
not do and for reading back what the TUI wrote. It lives at
`.local/END_TO_END_ACCEPTANCE_M1F1_TUI.md`, which is excluded from the repository.


## Exact next action

**CP-18 step 5 — traceability for the remaining PARTIAL invariant rows.** Step 4 closed the
*names*: every command a doc or a diagnostic's remediation mentions resolves against
`cli.build_parser()`, in both directions, held by tests. What that method cannot do is step 5's whole
subject — a page whose every command exists can still describe behaviour those commands do not have,
and no parser comparison will say so.

Two constraints carried forward:

- Do not read the ~121 PARTIAL rows as 121 pieces of missing work. Every row audited across steps 2-4
  has been either stale bookkeeping or a real gap, roughly half and half.
- **INV-001 must not be marked covered by the existence of `profiles/loader.py`.** Nothing calls it,
  so the public tool currently admits no externally-defined profile at all (D-155, B-072).

The audit method that produced every verdict so far: read the invariant's own words, find the flow
that would break it, and only then look for a test. Not the reverse.

Then step 6: full quality, packaging, security and deep acceptance gates.

**The CP-17 narrative below is kept as the record of how that slice got there.**

**Step 2 has been independently reviewed (D-149) and the review added tests only.** D-148's two
guarantees -- that a revision is a pinned Source revision, and that every added field is optional so
existing receipt bytes keep their canonical form -- are claims about inputs the chain cannot
produce, so they were re-measured rather than accepted. They came apart: deleting the
`is_pinned_source_revision` clause from `ResolvedArtifact` left all 3,349 tests passing, and the
decode tolerance turned out to be held incidentally, by a round-trip whose name speaks of rebuilding
an activity entry over a fixture that happens to carry no revision.
`tests/git_revision_provenance_test.py` now states both, with three mutations each red only where
claimed and a scoped mutmut run leaving no survivor in the code those tests claim (its twelve, in
`_safe_line` and the sort keys, are B-063). D-149 records the general form: a claim held by a
fixture's accidental shape is one refactor away from being held by nothing.

**Step 3a is done; implement step 3b.** Step 3 bundles two things needing different fixtures --
the installed artifact *starting*, and the installation *following* the upstream repository -- so it
is split the way CP-16 step 4 was.

3a is the movement half. The same Git-backed fixture now re-promotes the registry with both
versions, replaces the repository's working tree and commits, so the second commit is a real SHA
distinct from the first. One continuous run holds five claims through public verbs: a second sync
reports the new commit; the delivered bytes are still the ones reviewed at install, so the sync
offered and applied nothing; `marketplace update` without `--yes` reviews, names 1.3.0 and writes
nothing; the confirmed update with the review's `--expect` digest converges the delivery and records
a receipt naming the new commit; and the durable trail holds both revisions at once.

The mutation that justifies the increment: writing the source store's current pointer once and never
advancing it turns this test red on a stale `1.2.0` offer **while step 2's chain test still passes**,
because a fixture that syncs once from an empty store cannot see a pointer that never advances.

A second instance of D-149's gap was found by going to look for it: `ApprovedRegistrySnapshot`
validates its `resolved_revision` exactly as `ResolvedArtifact` does, and deleting that guard also
left the whole repository green -- 3,357 tests. Both are now stated as properties in
`tests/git_revision_provenance_test.py`.

**3b is done, so step 3 is complete.** `git_backed_runtime_e2e_test` carries an MCP artifact
through the same real Git repository and installs it with public verbs only; the install's four
receipt effects (`copy-tree`, `create-python-environment`, `write-file`, `configure-harness`) show a
virtual environment was really built, and the launcher it wrote then answers `initialize`,
`tools/list` and `tools/call` over stdio. The server runs on the interpreter the install created,
with the `--strict` argument the manifest declared, and cannot import `agent_artifacts`. A second
test starts what `.mcp.json` names, which is the file a harness actually consults.

The artifact declares no inputs deliberately, and that is now a claim rather than a choice: the CLI
has no flag that answers a declared input, so an artifact declaring one is refused outright. The
finding is where that refusal lives -- disabling the adapter's guard in `io/configured_installation.py`
killed nothing, because the CLI never reaches it, and the refusal an operator meets is
`commands/marketplace.py`'s. B-064 records the capability question; B-065 records that
`marketplace list` publishes a provenance `resolved_commit` of all zeros beside the real
`source.resolved_revision`, which is the maintainer half of the chain still being synthetic.

Step 4's drift half is VERIFIED, and it is the first step in this slice to change production code.
Damaging the live Git-backed MCP installation four ways found that `aart doctor` reported
`health: ready, drift: []` for every kind of payload damage -- while the server exited 1 -- and was
precise about a rewritten launcher in the same report. D-150 has the cause and the fix: both
observers measure the payload, and both current-state builders discarded that measurement before
the comparison could read it, because a doctor supplies no `payload_source` and so nothing desires
the payload. Omitting it from the *desired* state is right; using that as a reason not to *report*
it is what INV-228 and INV-175 forbid. `_reported` now keeps a damaged undesired payload,
`compare_states` names it `missing`/`divergent` rather than `UNEXPECTED`, and `repairable` stays
false because nothing planned an effect -- which is exactly what INV-175 asks to be said aloud.
Three things fell out of it, all recorded in D-150: the first, wider attempt broke uninstall
convergence and would have called an unhashable tree broken, so the keep-rule is payload-only and
ABSENT/DIVERGENT-only; `placed_machine_e2e_test` was asserting `ready` over a payload digest of
`"a" * 64` while measuring the real tree only for its delivery; and
`InstallationObservation.payload_present` was a bool that made every partial observation claim the
payload was deleted, now `bool | None`. Four targeted mutations, each red only where claimed. B-066
records the remaining gap: no tree digest exists on the installation path, so an MCP payload
rewritten in place is still invisible and only whole-tree deletion is caught.

Step 4's uninstall and rollback halves are VERIFIED too, so **CP-17 step 4 is complete**.
Uninstall was already proven to be reverse reconciliation, but only against installations a fixture
assembled; `GitBackedUninstallE2ETest` starts the server first and then removes it through the
public verb -- four effects in reverse dependency order, the runtime gone, no `notes` left in
`.mcp.json`, and doctor reporting a clean machine rather than a record for something that no longer
exists. Rollback's honest answer for this artifact is that there is none, which is the claim worth
pinning: building a virtual environment is not reversible by anything retained, so the receipt says
`undo.available: false` naming `runtime-environment`, and asking anyway is refused as
`receipt-no-setup` while the server still answers afterwards (INV-192). Three more mutations, each
red only where claimed -- including the non-recursive tree removal, which fails honestly with
`Directory not empty` and a `partial` session rather than reporting success over a tree still there.

Step 5 split in two. Its **bulk half is VERIFIED**: `git_backed_bulk_install_e2e_test` publishes an
MCP server and a Skill into the one repository and installs both in one confirmed run, and each gets
the installation its kind needs -- the server built into a runtime that then starts beside the
Skill, the Skill placed with neither an environment nor a launcher, both carrying the same real
commit into one receipt, doctor reporting both `ready`. Forcing `_is_delivered` false turns all four
red with an honest `installation-not-described`; letting only an `mcp` member carry its revision
turns exactly the one test that claims it red.

Its **Collection half is blocked**, and that is the finding. A Collection cannot be installed
through the CLI for any registry content at all: `io/configured_selection.py` skips every approved
version whose kind is `collection` and leaves `ApprovedRegistrySnapshot.collections` at its default,
so the configured Marketplace every public verb reads carries none. `marketplace list` returns
`"collections": []` while offering both members, and installing one answers `collection-not-found`
with empty remediation. B-067 records it with the two things to fix together, and
`CollectionsAreNotReachableTest` pins the gap as an honest refusal so it cannot become a partial
install.

**B-067 is decided (D-151): not reclassified, and CP-17 step 5 is complete for what CP-17 can
prove.** Tracing it end to end shows this is not a projection bug. The maintainer side models
Collections and stops: `CollectionCandidate` appears in six modules and `promotion.py` is not one of
them, `collection_active` reaches candidate history and goes no further, so no collection candidate
is ever promoted, no registry version of kind `collection` is ever published, and no test anywhere
publishes one. Resolution is the one part already built, which is what makes the gap look smaller
than it is. Closing it means four layers together -- promotion, registry representation, the
configured projection, and install planning over members with ownership and INV-186's health
aggregation -- which is a vertical capability slice, not a step inside an acceptance slice. A step
cannot be blocked on an acceptance claim about a capability that does not exist; its premise was
wrong.

**CP-17 is complete.** Steps 1, 2, 3a, 3b, 4 and 5 are VERIFIED, with step 5's Collection half
pinned as an evidenced refusal by `CollectionsAreNotReachableTest` rather than left as prose.

**CP-18 Migration completion and release gate is IN PROGRESS.** The slice document is
`docs/refactor/slices/CP-18-migration-and-release-gate.md`, and it opens on the same finding CP-15
did: read the traceability table alone and CP-18 looks like eleven untouched invariants, but most of
INV-072-080 is already held by `enterprise_ci_template_test.py` (forty-odd assertions over the
emitted workflows: pip pointed at the configured index first, every variable documented and every
documented variable read, an exclusive container switch whose default shape carries no credentials,
both halves of an index credential remasked with no log line carrying the assembled URL) and by
`release_workflow_test.py`. Those rows are stale bookkeeping rather than missing work, and step 2
audits them one at a time.

**Step 1 is VERIFIED: INV-071 is now evidenced against the import graph rather than a declaration.**
`dev_tools_test` asserts `[project] dependencies = []` and `scripts/packaging_check.py` refuses a
non-extra `Requires-Dist` in the built wheel. Both are worth keeping and neither holds INV-071: a
runtime module that imports a development tool *inside a function body* declares nothing, adds no
`Requires-Dist`, ships in the wheel, and violates the invariant on the first call. Measured, not
supposed -- with `import hypothesis` inserted into a function body in
`agent_artifacts/application/installed_state.py`, `dev_tools_test` and `packaging_test` were green
and `packaging_check` said `packaging check OK`. `tests/runtime_purity_test.py` reads every module
under `agent_artifacts/` with `ast` and asserts none imports a development tool, the test suite or
the gate scripts; its forbidden set is derived from Poetry's dev group at test time rather than
hardcoded, and `ast` is deliberate, since import-time introspection sees only module-level imports
and would miss the one shape that defeats both incumbent checks. INV-071 moves to EVIDENCED.

The first draft read the dev group with `tomllib` and mypy refused it: `requires-python` is `>=3.10`
and `tomllib` arrived in 3.11, which `dev_tools_test`'s docstring already records for `poetry.lock`.
A test for *this* invariant that runs on only some supported interpreters is the wrong shape, so the
group is read by a flat-table shortcut with a claim of its own. Deriving the set also turned up
B-068 was found here and later closed by CP-18 step 6. It became critical when the new deep-quality
workflow started invoking mutmut unattended; the regenerated lock now provisions it explicitly.

**Step 2 is under way, and its first row justified the whole audit.** INV-077 (one stable required
gate) turned out to be two different situations. This repository's `pr-check` aggregate was already
right -- one stable name, `if: always()`, an explicit failure when both arms skip, an allowlist
rather than a check for `failure` -- and tested by nothing: `quality_gates_test` covers the matrix
default and the composite-action delegation, while the shell that decides the verdict, the one thing
branch protection depends on, was covered by nothing. `tests/aggregate_gate_test.py` now extracts
that script and *runs it under bash* for each combination of `needs.*.result`, which is INV-076
collecting on its own promise that such logic stays runnable outside GitHub Actions.

The second situation was a real defect. The CI `aart registry init` writes had no aggregate at all:
`registry-quality` and `registry-quality-private-image`, two container shapes of which one ever
runs, each a matrix -- so a registry owner protecting `main` had no name that is stable across
configurations, and naming an arm their deployment skips is worse than useless, because GitHub reads
a skipped required check as satisfied. `_aggregate()` now emits `registry-quality-gate`, and the
registry README names it, held to the workflow by a drift test rather than a repeated literal
(D-153). INV-077 is EVIDENCED for both.

**Step 2 is VERIFIED. INV-072 through INV-080 are all EVIDENCED.** The remaining rows were audited
the same way and, where the claim was universal, closed as a property over every CI source -- the
three workflows, every composite action, and the three templates `registry init` emits -- rather
than sampled one job at a time. INV-072: the only variables in any conditional are the container
switch and `AART_PAGES`, and the action that runs the gates reads none, so no settings change can
switch a check off. INV-073: every `secrets.` reference is `secrets[vars....]`, `GITHUB_TOKEN`
excepted because GitHub mints it per run. INV-074/078: every absolute URL is a variable default and
`pypi.org` is the only public host named anywhere. INV-076: every step in this repository's
workflows is a checkout or a composite action, and the single remaining inline script is the one
`aggregate_gate_test` executes. INV-079 and INV-080 follow from those plus the pre-existing
reporting tests.

Two findings worth carrying forward. **A mutation caught the test, not the code**: M18 wrote a
variable onto a gate step in the inline `- if:` spelling and walked straight past the INV-072 test,
which only read lines beginning `if:`. It was caught by the *documentation* test instead -- a
different claim that a fork writing the variable onto the page would have satisfied. The harvester
now reads both spellings and the guard test says so. **And a test overclaimed**: the first draft
asserted nothing names github.com, which failed on the untouched tree, because `cut-release` builds
the tagger's email as `...@users.noreply.github.com`. INV-078 is about egress and an email is
connected to by nothing, so the claim is now stated over URLs with that occurrence pinned. B-069
records the enterprise wart and says explicitly that it is not an INV-078 finding.

**CP-18 step 3 is PARTIAL.** Codex removed seven production modules and the five test files that
existed only to drive them (-2552 lines) and added `tests/legacy_authority_reachability_test.py`,
which builds the import graph from `agent_artifacts.cli` and `__main__` and asserts on an exact set
that every shipped module is reachable or named as an exception. That is the right evidence for this
step, and two mutations show it has teeth in both directions.

**Codex stopped on its weekly limit with the tree red.** Two failures, both repaired here:
`compiler_boundary_test` still named the deleted `application/compiler.py`, and
`docs/testing/PLAN-live-acceptance-v1.md` linked to the deleted `io/cache.py`. The doc's claim -- that
overriding `HOME` isolates the object cache -- is still true and now belongs to
`configuration/paths.py`, so the link was repointed rather than deleted; doing that surfaced a real
gap, since `XDG_CACHE_HOME` takes precedence over `HOME` there, so a shell exporting it leaves the
cache pointing at the real one while every other path moves. The plan now says to unset it.

**Next action: finish CP-18 step 3 by deciding B-070.** The exception list holds six names and only
two carried a reason. The other four -- `domain/ports.py`, `domain/outcomes.py`,
`domain/collections.py`, `profiles/loader.py` -- are production modules no runtime path reaches,
imported only by tests, which is the test's own definition of parallel authority. They were listed to
keep the set exact, not because anything was decided; the docstring now says so outright. Each is one
of: legacy to remove, the intended kernel that something else duplicates (in which case the
*duplicate* is the legacy), or a real build exception like `_commit`. Use step 2's method -- read what
the module claims authority over, find the runtime path answering the same question, then decide.

`domain/collections.py` is generic immutable collection helpers and has nothing to do with B-067's
Collection capability. The names collide; the subjects do not.

Then step 4 docs reconciliation, step 5 the remaining 121 PARTIAL traceability rows, step 6 the
closing gates.

Do not read the 121 as 121 pieces of missing work. Every CP-18 row audited so far has been either
stale bookkeeping or a real gap, roughly half and half, and the only way to tell them apart is the
one used here: read the invariant, find the flow that would break it, and only then look for a test.

The Collection capability may be scheduled ahead of the rest of CP-18. B-067 carries the four-layer
scope and is the natural candidate for a slice of its own: INV-186 and INV-213 cannot be evidenced
through any public verb until it exists, so it has to be built before either can move off PARTIAL.

Do not weaken `runtime_purity_test`'s two guards. Without them a rename of `agent_artifacts/` leaves
four green tests asserting nothing, which is the failure mode D-149 names.

Do not widen `_reported`'s keep-rule on either axis. Payload-only and ABSENT/DIVERGENT-only are
load-bearing, and D-150's mutation 4 is the uninstall and repair tests catching the widening.

Do not configure `file://` or a local path and do not set `allow_local_transport` through the public
flow. Both refusals remain security boundaries. Do not make the legacy `registry publish` command
part of the chain: the accepted publication authority is Git review/merge, and B-057 retains the
command disagreement as noncritical backlog.

The CP-14 record follows.


CP-14 step 6 is complete, and step 7 has started: the legacy curses wizard shell is removed
(D-113). `_run_curses` and the two setup shims it alone called are gone, along with the seven tests
that existed only to drive it; `run()`, `_run_text` and the wizard's curses primitives stay. B-039
is partly closed. The acceptance evidence pre-existed — `run()` never reached `_run_curses`, and
ERR05 is pinned on the canonical `run()` by `tests/tui_fallback_boundary_test.py` — so no new test
was needed for the removal.

B-038's screen-21 half is closed too (D-114). Screen 21 was reachable and drawing nothing: nothing
on the composition path projected the configured sources, so a machine with a configured registry
opened on an empty list and a dashboard reading "0 registries". `read_consumer_offers` now carries
the projected rows, `screens_from` takes them, and a row that is not a registry says so and offers
`details` only instead of a sync whose advertised effect it cannot have.

Step 7 then found why it could remove nothing further: everything it was aiming at was reachable
only through `_run_text`, which is built on `ConsumerApplicationService`. (The aim itself turned out
to be wrong — see D-117 below — but the blocker was real, and it was a missing replacement rather
than missing evidence.) So the text route is now the canonical application:
`_TextTerminal` adapts the shell's two-method terminal port to `write`/`read`, `run()` composes once
for whichever terminal answers, and its entire legacy tail is gone (D-115). ERR05 permits a text
fallback for one condition — the terminal cannot host curses — and says nothing about the product
changing.

That unblocked the removal, which is done: `_run_text`, `_runtime_source_stage_context`,
`_dispatch_result` and the 26 further definitions that became unreferenced once it was gone are
deleted, with the tests that existed only to drive them — about 2,200 lines, and `tui.py` down from
5,705 to 4,262. Each removed test's capability was checked against a public flow first: scaffolding
against `aart registry scaffold`, source maintenance against the `aart source` commands, vendoring
against its flags half, ERR04's legacy install state against four other modules, ERR06 refusals
against the canonical shell's drawn notice (D-116).

**B-044 is complete (D-128), and step 7 is finished apart from one mechanical sweep.** One
correction landed on review: the three acceptance tests that assert setup *ran* now carry the same
`skipUnless(darwin)` guard D-121 already carries, because the seam takes its platform from
`sys.platform` and a recipe may declare only `darwin` — measured by forcing the platform, where the
run comes back `unsupported` and the artifact is reported as still-pending setup with a retry
command rather than as a failed install.

The wizard front-end is gone (D-117): `_run_user_curses_wizard`, `_run_user_text_wizard`,
`_prompt_curation_request`, the `_curses_source_*` screens, and the 22 definitions that became
unreferenced once they were — 1,515 lines. `tui.py` is 2,747 lines, down from 5,705 when step 7
began. Two assertions the removed tests held alone were carried to the reachable surface first
rather than deleted with them: `registry init`'s default compatibility window, restated against the
CLI parser in `tests/registry_cli_test.py`, and the usage-report offer's consent-and-preview
boundaries, which had **no** CLI test at all and are now `tests/reporting_cli_offer_test.py`. Both
were verified red against the defect they exist to catch.

**Do not try to remove `consumer/application.py`, `lifecycle/*` or `setup_engine/*`.** This file
previously said nothing but the wizard reached them; that was wrong. `commands/marketplace.py` — the
public `aart marketplace install|update|uninstall|setup` — composes `ConsumerApplicationService`
directly and runs the setup queue through it, and `tui_marketplace.py`, which the canonical shell
imports, takes `LifecycleItem` and `InstallMode` from `lifecycle/model.py` and
`installation/model.py`. The stack is load-bearing for a public flow. Like `installation/*`, it goes
by symbol if at all, and not by package.

**B-044 was attempted and the attempt is preserved, not merged.** Codex began it and was cut off
mid-work by its own rate limit; the draft is on branch `codex-wip/b-044-draft` (`e40a80d`) with a
full review under B-044. The headline: **all 3,216 unit tests passed with it applied, while it
hardcoded `TrustClass.COMPANY_REVIEWED` into the setup policy check** -- the constant that makes
`_policy_allows`'s untrusted-source refusal unable to fire. Nothing in the suite exercises trust on
that route, which is the same blindness B-044 is about.

**The fixture and the characterization are now built, and they widen the item** (D-120). The
authoring format has no setup section at all — `setup` appears zero times in
`protocol/authoring.py` — so a declaration genuinely enters at packaging. `AuthoredSetup` and
`_with_setup` in `tests/configured_installation_draft_e2e_test.py` add it to the *compiled* package
(`artifact.json`'s `setup` reference, `setup/installer.json`, `SETUP.md`), recompile with
`compile_native_package`, and send the result through the whole real promotion transaction, so every
digest is derived rather than asserted. It is threaded through `_promote_one`,
`_published_registries`, `_published_registry` and `_environment(authored=..., setup=...)`, and
every existing caller is unchanged.

`tests/configured_setup_gap_test.py` is the characterization. Its first test guards the rest by
asserting the approved registry really does carry the declaration and its recipe; the other three
record the defect on **both** front ends.

**What it proved corrects D-118 and this file's earlier ordering.** `aart marketplace install` does
*not* carry setup for an approved registry coordinate: it reaches `_configured_lifecycle`, which
calls `complete_configured_installation` — the same seam `io/consumer_actions.py::_execute_installation`
uses — and reports `session_status: succeeded` with no `setup` key, no diagnostic, and the
configuration file the recipe declares unwritten. Setup runs only on the legacy path, which
`_configured_registry_selection` selects by returning `None` for a direct or local source. Nor is
there an operator recovery: `aart marketplace setup` afterwards refuses with `registry company has
invalid root manifests`, because it resolves through the legacy catalogue and a promoted registry
snapshot carries no root manifests.

So B-044 is one fix at one shared seam, not a TUI wiring gap. The Product Specification names
interactive setup as work AART performs and screens 09/11 summarize an install as "configured MCP
servers, isolated environments ... securely stored credentials", and neither shipped front end does
it. `_canonical_setup_run` and `_complete_canonical_consumer_action` are deliberately retained in
`tui.py` as the material (D-118); they take `ConsumerApplicationService`, `ConsumerReview` and
`ConsumerOutcome` and the canonical path has a receipt instead.

**The working route is proven too** (D-121). `marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest`
takes a declared setup through the CLI on a real machine over the legacy native-local-source route,
which nothing did before, and asserts all four gates on it: `install` names the setup it did not run,
an unreviewed source refuses without `--authorize-untrusted-source`, an authorized plan applies
nothing until its effects are separately approved, and both answers together write the delimited
managed block. It is `skipUnless(darwin)` because `setup.py:562` accepts only `['darwin']` recipes.
Applying the preserved draft's hardcoded `TrustClass.COMPANY_REVIEWED` fails two of the four — the
defect that passed 3,216 tests now has a test.

**The installed-record question is settled, and half of the answer has landed.** The question was
which durable record the setup engine should resolve an installed artifact from.
`setup_engine/application.py::_prepare_setup_object` resolves it from the install-state manifest
(`.agent-artifacts/manifest.json`), which only `installation/application.py` and
`lifecycle/application.py` write and which `io/consumer_machine.py` calls the *legacy* store; the
configured seam writes receipts instead. The deciding measurement was that **a canonical receipt
could not name the object that was installed**: after `aart marketplace install` of the fixture
Skill, `<data_root>/state/installations/*.json` held the coordinate, `payload_digest`, `root` and
the deliveries, and no object digest — while `install_state`'s `ArtifactEvidence` carries one. The
engine needs the object digest to `read_object` at all, so pointing it at the receipt store was not
a matter of reading the same facts from another file; the facts were not there.

The alternative — having the configured installation also write the install-state record — was
rejected on the ground that it writes new records into exactly the store the strangler is retiring.
(It would *not* have made canonical installs surface as unadopted: `read_consumer_machine` drops a
manifest record whose coordinate a canonical receipt already answers for,
`io/consumer_machine.py:362`, so the objection previously recorded here was wrong.)

**Landed (D-122):** `object_digest` on `PlacedArtifactReceipt` and `InstallationReceipt`, populated
by `intended_placement_receipt` / `intended_receipt` from the `RegistryArtifactVersion` the
Selection resolved — writing down what the installation already knew, deriving nothing. It is
optional, so receipts written before the field still read, and read back as *unknown* rather than
defaulted: an installation whose object nobody wrote down is honestly unknown, and a default would
put a dangling identity on a real installation. `tests/installed_object_identity_test.py` asserts
the recorded digest resolves to a real object in the store whose manifest is the installed
package's; each receipt shape has a round-trip, an older-document read and a malformed-digest
refusal.

**Landed (D-123): both front ends now name the setup they did not run.**
`complete_configured_installation` reads the objects it just recorded and carries what they declare
as `pending_setup`; `aart marketplace install` emits it as an additive `pending_setup` key and
renders it, and the persistent shell draws it under screen 11's success. This is what D-122 is
first spent on — setup is declared on the package manifest, not on anything the plan carries, so
answering "does this artifact declare setup" means going back to the object the receipt names. The
key is absent rather than empty when nothing declares setup, and the reading happens after
completion from the durable record rather than from the plan. Half of
`tests/configured_setup_gap_test.py` inverted; `tests/configured_setup_report_test.py` owns the
assertions that moved, and what remains characterized is that the work itself is still not done.

**The exact next step is (3b): actually perform it.** The first move has landed (D-124): the
engine's `_prepare_setup_object` no longer reads the install-state manifest or resolves the legacy
catalogue itself. Those are `_install_state_subject`, which returns a typed `_InstalledSubject`,
and the object validation now takes that subject -- so the canonical route has one seam to fill
rather than a function to fork. Three things are known to be needed, and the CP-14 slice's step 7i
carries the detail: canonical marketplace evidence (trust is answerable from the approved
snapshot's `RegistryTrust.REGISTRY_REVIEWED`; the indexed-declaration cross-check is not, because a
promoted snapshot *is* the package), a precondition that does not re-resolve through the legacy
catalogue at finalize time, and a durable setup record the canonical route can own. A canonical
`InstallationRecord` is constructible from the receipt; a faithful `manifest_digest` cross-check is
not, and its honest replacement is that the object the approved registry publishes must be the
object the receipt recorded. Two of those three are now closed as a shape (D-125): the engine
takes a `SetupSubjectPort` where it took a `MarketplaceCatalog`, `install_state_subject` is the
legacy implementation, and `_preconditions_current` re-asks that port instead of re-resolving the
catalogue and separately re-reading install state.

**The engine no longer names the store that recorded the installation** (D-126, D-127). The plan's
two remaining install-state-shaped fields are `installation_record_path` /
`installation_record_lock_path` — the durable file that says this artifact is installed here and
the lock that guards it, whichever store holds it — and the subject holds those two paths instead
of an `InstallStatePaths`. The identity JSON that derives `setup_state_ref` deliberately keeps its
old `install_state_path` key, because it is a digest input and renaming it would rename every
existing setup record. And the last check that only a separate index could satisfy is now a union:
`IndexedSetupDeclaration` keeps the legacy cross-check unchanged, `ApprovedObjectIdentity` checks
the loaded object against the digest the approved registry publishes for the coordinate — two
values from two documents, which is the honest check where the index *is* the package.

**Those two pieces have landed and B-044 is closed (D-128):**

1. **The canonical `SetupSubjectPort`.** Every field comes from the traced real source:
   the receipt store gives the record and `object_digest` (D-122); `load_configured_approved_marketplace`
   gives the approved `RegistryArtifactVersion` and `RegistryTrust.REGISTRY_REVIEWED`, which maps to
   `TrustClass.REGISTRY_REVIEWED` exactly as the legacy `marketplace/catalog.py::_trust` does;
   `SourceEvidence` is constructible from the configured source plus
   `CurrentSource.candidate.resolved_revision` and `declared_source_id`; and `manifest_digest` —
   previously recorded here as missing — **is** derivable, because
   `native_tree.py:512` defines it as `json_digest(artifact_manifest_to_json(manifest))` over the
   package's own `artifact.json`, which the object carries. `EffectProof`s come from the receipt's
   deliveries, and note `InstallationRecord.__post_init__` requires a project-scope destination to
   be a *safe relative path*, so the receipt's absolute destinations must be made relative to the
   project root. `declaration` is `ApprovedObjectIdentity(version.object_digest)`.
2. **Canonical `persist_setup`.** `setup_engine/io.py::LocalSetupAdapter.persist_setup` records
   that setup ran by taking the install-state lock, replacing the record's `setup_state_ref` and
   moving a CAS reference as one compensated unit. The canonical adapter writes the same setup
   record and moves the same reference, but its durable pointer belongs on the receipt rather than
   in an install-state manifest. `setup_receipt.locate_setup_record` reads that pointer for
   `aart marketplace receipt show|verify|undo` and needs a canonical equivalent (follow-up, not
   blocking the wiring). The receipt-backed equivalent is now B-046.

`io/configured_setup.py` implements both without writing install state. Install/update and the
explicit setup command run the public engine; the shell receives an injected typed completion and
uses only `draw`/`key`, with every key passing through `key_event`. Refusing effect consent leaves
the declaration pending, explicit approval configures it, and the usage-report offer defaults to
no, previews exact redacted bytes before provider invocation and remains advisory on failure.
`tests/configured_setup_gap_test.py`, `tests/configured_setup_subject_test.py` and
`tests/configured_setup_report_test.py` are the acceptance evidence.

A second measurement stands on its own account: the canonical seam registers **no CAS reference of
any kind** — no references file exists in the data root after a successful install — while the
legacy path registers `ReferenceKind.INSTALLED`. The object a canonical install materialized from is
unrooted in the store. That is **B-045**, independent of setup.

Every trust, evidence and policy check stays inside the engine; a third implementation of the
planning is what produced the hardcoded trust constant in the preserved draft.

The orphan sweep is **done** (D-129). Its estimate of "about 571 lines" was produced by a
single-pass reference scan and was wrong by a factor of three: the dead wizard definitions call
each other, so a one-pass check keeps whole clusters alive by their own internal references.
Reachability computed to a fixpoint from the module's live entry points found **1,680** lines, and
the sweep terminates with `0 dead definitions` over the remaining 1,087. `tui_search_test.py`,
`tui_wizard_curses_test.py`, `tui_install_scope_test.py` and `tui_receipt_test.py` are deleted;
`setup_receipt_cli_test.py` is new; five files are retargeted. `_canonical_setup_run` and
`_complete_canonical_consumer_action` are production-reachable through D-128 and were not orphans.

B-046 is **done** (D-130). `locate_receipt_setup_record` reads the pointer off the receipt;
`receipt_service.load_receipt` asks the canonical store first and falls back to the manifest, so a
machine holding only legacy installations answers exactly as before. No legacy install state is
written. `tests/configured_setup_gap_test.py::ConfiguredReceiptVerbsTest` installs through the
public command and drives all three verbs against what that install actually recorded.

**On B-038's remaining half**, measured rather than assumed: the direct-install residue is in
`commands/marketplace.py::_configured_registry_selection`, which returns `None` for direct and
local sources so their installs take the characterized legacy path. That is a public flow, not
anything left over from the deleted wizard. The characterization the item asked for already exists
-- `tests/marketplace_lifecycle_e2e_test.py` drives 27 end-to-end tests of this command against a
real synchronized `SOURCE_LOCAL` source -- and every one of them routes through that `None`. Two of
the seam's three declining reasons are unfinished canonical capabilities rather than policy: it
expands no Collection, and `_configured_lifecycle` refuses anything but `--mode copy`. So closing
B-038 by refusing direct installs would remove three characterized capabilities to settle one
question. Sequence the capabilities first. See BACKLOG B-038 and
`tests/marketplace_install_routing_test.py`, which pins each reason separately.

Behind it, step 6 left the surfaces complete: screen 53 is live (D-111) — the typed filter carries
all four facets the Product Specification names, `f` opens it from screen 35, `Space` toggles a
facet row, and screen 35 narrows accordingly — and screens 51–52 are reachable and proven end to
end, with `c` on screen 35 opening Collection Candidates and Enter resolving one against approved
registry state (D-112). What remains in CP-14:

1. **Step 7 is done.** The wizard front-end is removed (D-113, D-116, D-117), B-039 is closed,
   and the orphaned implementation behind it is swept (D-129). What it aimed at beyond that — `consumer/application.py`,
   `lifecycle/*`, `setup_engine/*` — is load-bearing for `aart marketplace` and is not removed.
   B-038's screen-21 half is done (D-114) and its remaining half is restated as an `aart marketplace
   install` question. B-044 is closed (D-128) and B-046 with it (D-130).
2. Preserve D-089/B-037 whenever promotion planning is touched: retained approved records rebind to
   the transaction snapshot as metadata only, and published package bytes do not change.

Noticed while proving the walk, not fixed here: screen 47 draws its "N selected" footer once of its
own and once from the shell chrome, so the count appears twice. Recorded in `BACKLOG.md`, with the
sweep's three further presentation findings — no match count on a filtered list (B-047), unwrapped
refusal lines (B-048), and the dot separator enforced on some projections but not others (B-049).

**QA-024/QA-025 (2026-09-09).** Screen 46's `b` now runs `lock`, `build`, `validate` and `audit` over
the registry — the whole sequence or one stage — through the same authority `init` uses (D-200), so
the walkthrough no longer ends in four typed commands and `B-099` is closed. Walking those keys in a
headless shell found that Enter confirmed nothing on screens 31b and 46b, that no review or result
screen off a hand-written list drew what it was asking about or reporting, and that the first
rebuild request inherited screen 46's focused registry alias instead of the stage under the cursor
(D-201). All three are fixed; the notice set and the request row are now derived rather than listed.

**Next executable work:** the operator's manual retest of QA-001–QA-025 against
`.local/END_TO_END_ACCEPTANCE_M1F1_TUI.md`. Nothing in this batch is on CP-14's critical path; new
findings go to root `TODO.md` as `QA-NNN`.

**QA-026 (2026-09-09).** The footer now answers the screen the operator is actually on (D-202).
Contextual actions are listed first and the universal movement/back/help/quit keys second; Space,
Enter and search appear only where the reducer can use them. The same binding value owns both a
letter key's event and its displayed label, while selectable/searchable/form/review keys derive
from the reducer's existing screen sets. Screen 46 no longer repeats its shortcuts as body text.
The RED was the fixed footer on every asserted screen; a `b` route mutation was killed by walking
the advertised Registry key through the real shell.

**Next executable work:** QA-027, generalizing screen 45's completed-sequence Enter route to every
terminal result screen, beginning with Source Sync Result (34). Continue with focused gates only;
the operator deferred the full suites until this manual-acceptance batch is handed back.

**CP-19 opened by operator direction (2026-09-09).** Post-refactor manual findings now have their
own execution slice and plan steps rather than living only in TODO/BACKLOG (D-203). Implementation
is paused while the operator continues discovery. QA-027's uncommitted RED draft was removed; no
production change for QA-027–QA-031 exists.

QA-031's operational checkpoint has been crossed: Registry PR #1 was merged at `f37d182` and the
subscription synchronized. Local `main` now has the MCP promotion commit `259af24`, one ahead of
published `origin/main`, plus the uncommitted repository adoption of
`skill/commit-message-discipline@1.0.0`. The operator is testing Check upstream next. From the
failed Review Rebuild screen, Escape twice returns to Registry Maintainer; `u` opens the adopted
artifact list. The later QA-031 implementation task still owes an honest diagnosis without
weakening the exact comparison.

**Next action:** continue manual discovery from the recorded CP-19 checkpoint and append new QA
findings. Do not implement the open steps until the operator starts the next work session.

**QA-032 / B-057 reclassified critical (2026-09-09).** Registry PR #1 is the first real promoted
artifact through the generated workflow. Both matrix arms fail because `registry init` generated
the legacy `format/validate/lock/build/audit/test` sequence over the canonical versioned output.
The exact remote branch is healthy through public `registry-git` acquisition, so this is a false
negative in the publication gate, not corrupt Registry content (D-204). CP-19 step 9 owns the fix.
The disposable manual run consciously merged PR #1 after independent consumer validation; full
CP-19 verification may not pass until the generated gate validates the canonical representation
without dropping its compatibility/audit claims.

**QA-033 / B-101 (2026-09-09).** The operator ran the Rebuild required by the acceptance procedure,
and its known legacy `lock` refusal exposed a separate state-machine defect. Execution
had ended and the adapter had discarded its pending plan, but the TUI remained on Review Rebuild,
said `press Enter to start it` and advertised `Enter Confirm`; another Enter can only report that
nothing was prepared. CP-19 step 10 must make a failed action an explicit terminal result across
action kinds. Do not implement it during the active discovery pass.

**QA-025 manual retest FAILED (2026-09-09).** The operator was not detouring: the acceptance
procedure explicitly required `b → Everything → review → run`. The focused increment proved that
screens 46h/46i route and preserve stage order, but the first real canonical promotion output made
`lock` refuse the missing legacy `artifact.json`. B-099 is reopened. CP-19 step 9 now owns both
local TUI maintenance and generated CI because each currently invokes the same wrong workspace
authority. Skip Rebuild and continue with Check upstream during discovery (D-205).

**Manual discovery handoff — QA-034 through QA-043 (2026-09-09).** The first clean Consumer is the
new blocking checkpoint. Its Registry connection is healthy at merged Git commit `f37d182`, and
the synchronized tree contains the promoted Skill's version, manifest and payload, yet both TUI
Marketplace and `marketplace list --json` contain zero artifacts. The record remains
`promoted-local`; no public Git review/merge path applies the Published transition. CP-17's fixture
called `publish_registry_version` internally before creating its repository and therefore did not
test the accepted chain. QA-034/B-102/D-206 make CP-19 step 8 the next implementation action.

The same walkthrough captured the remaining UX batch without implementing it: Dashboard grouping
(QA-035); workflow progress across every multi-step journey (QA-036); Candidate Back losing its
stable focus and rendering `That Candidate is not available` (QA-037); vertically readable help
(QA-038); an explanation of Vendored versus Referenced and an honest `m` toggle (QA-039); bounded
Registry rows and whitespace (QA-040); compact keycap footer hierarchy (QA-041); a visible cursor
on connected Registry rows (QA-042); and authoring Sources advertising an Enter/details route that
does not exist and leaks `no connected registry here is 21-registries` (QA-043). QA-027 also gains
the completed Candidate flow as evidence for returning directly to its owning list.

**CP-19 step 8 is DONE — QA-034/B-102 closed (2026-09-09).** There was no missing write. INV-242
defines published as presence on the canonical consumer-visible branch, which is a property of the
reading: the maintainer writes `promoted-local` before any review, and the merge that publishes it
moves a commit without editing a byte inside it. `load_published_registry_versions` now applies the
transition once, at the four consumer seams (`configured_offers`, `configured_selection`,
`configured_installation`, `offline_readiness`); the maintainer's workspace projection, source
validation, promotion planning and Candidate reconciliation keep the durable record as written
(D-207). `configured_offers` no longer declines anything for being unpublished, because nothing
reachable there can be.

`tests/git_publication_transition_e2e_test.py` is the evidence: one real promotion transaction on
`main`, a second committed to a review branch, `git merge --no-ff`, public `source sync`,
`marketplace list`, and an install whose receipt names the merged revision — plus the assertion
that the merged version records on disk still read `promoted-local`. It was RED with exactly the
reported symptom (`[] != ['company/skill/code-review@1.2.0']`). The fixture split that made this
possible lives in `configured_installation_draft_e2e_test`: `_promoted_local_registries` stops
where a maintainer stops, and `_published_registries` writes the publication half for the fixtures
that need a registry which already crossed the boundary.

`configured_selection_resolution_e2e_test.test_a_local_promotion_is_not_invented_into_a_published_offer`
asserted the replaced belief. It was rewritten, not deleted: the branch a consumer reads publishes
what it carries without rewriting it, and an artifact the branch does not carry is still not found.

**CP-19 step 9 is DONE — QA-025/QA-032/B-057/B-099 closed (2026-09-09).** The promoted registry was
never corrupt; maintenance reached the authoring workspace's reader over the approved
representation, so `lock` refused a path nothing writes any more and the Registry PR gate failed a
healthy branch. Every generated verb now dispatches on the representation it is handed (D-208):
`validate` drops the compiled-lock requirement, because `validate_promoted_registry` is the stricter
check; `build` derives exactly `registry/index.json` and `registry/snapshot.json`; `lock` is a
read-only prepared curation, since approved versions are pinned by their own records; `publish`
chains build, validate and audit with no lock half. Screen 46's Rebuild reaches the same authority
through `refresh_registry_workspace`, so it is repaired at the same seam.
`tests/promoted_registry_maintenance_e2e_test.py` drives the public `registry init` → `scan` →
`promote --yes` chain and then the six verbs in the generated workflow's order, and holds that
maintenance never writes `aart.lock.json` or `aart.index.json`. Four targeted mutations were killed.

**CP-19 step 10 is DONE — QA-033/B-101 closed (2026-09-09).** A refused run and a confirmation that
never happened arrived at the reducer as the same event, so it could only treat both as nothing.
`ACTION_FAILED` separates them: `action` clears, `failed_action` records which run this screen is
now the end of, the footer offers `Enter Back to list`, Enter navigates through the same
`_ACTION_RESULT` table a recorded run uses, and the prompt and heading say the run did not happen
(D-209). The screen deliberately does not move, because the refusal is drawn there. Held over four
confirmed action kinds in `tests/failed_action_terminal_state_test.py`, with `QA-024` preserved.

**CP-19 step 3 is DONE — QA-027 closed (2026-09-09).** Screen 34 binds `Enter → Sources`, with the
matching edge declared in the navigation map, because `_navigate` refuses an undeclared target and a
binding without the edge is the silent key being fixed. Registry Maintainer binds `c Candidates`, so
a finished promotion is one key from the next one; screen 45's Enter still goes on to Registry
(D-210).

**CP-19 step 4 is DONE — QA-028 closed (2026-09-09).** `_navigate` empties the draft the entered
form owns, and only that one; `_declined_preparation` and `_back` walk the session history and touch
no draft, so a refused form still holds everything typed (D-211). Both add forms say in words that
they add another one and change nothing already connected.

**CP-19 step 5 is DONE — QA-029 closed (2026-09-09).** The rule is stated once in the pure layout
kernel and applied at the seams every screen already passes through: `separate` joins blocks with
exactly one blank line and drops an empty one, `action_prompt` puts the facts, a blank, then the
single line saying what a key press will do, and `is_action_prompt` recognises that line from the
line itself so `CanonicalScreenSource.lines` can lift a screen's prompt and re-place it last — under
the notice it is about, not above it (D-212). Four review prompts stopped saying "below" about a
plan that is now above them; the two Source Sync screens were regrouped. Held as a sweep over every
Consumer and Maintainer screen with and without a notice, plus the three typed-view maintainer
reviews in every profile; six targeted mutations killed. B-048's refusal wrapping stays separate.

**CP-19 step 6 is DONE — QA-030 closed (2026-09-09).** The header is a row of the same grid rather
than a hand-spaced string, so `tui_layout.columns` lays it out with the rows it names and a long
name is cut in its own column instead of pushing the columns after it right. The row under the
cursor is repeated in full below the list, which is what makes cutting honest, and the verbose
per-row detail line was folded into that block. Screen 47's selectable rows moved onto the same grid
(D-213). Five targeted mutations killed; `B-107` updated with what the new property does and does
not hold.

**Superseded next action:** CP-19 step 6 — QA-030. The Candidates list holds its columns:
bound each column, truncate only the list row, and show the focused value in full below the list.
Survey the other Maintainer tables before choosing the shared projection boundary. `tui_layout`
already owns `columns`/`_column_widths`, and the scoped advisory mutation run found its width
arithmetic unheld (B-107), so state the column claims that step depends on rather than assuming the
kernel holds them. Then steps 7 and 11–14. Targeted tests and quality gates only until the batch is
handed back — and run the whole `tui`/`consumer`/`maintainer`/`source`/`registry`/`setup` test file
set, not only the files a step edits: step 5 found a step-4 fixture regression that way. Step 15
runs the full suites.

**Exact next action for Claude:** CP-19 step 7 — QA-031/B-100. Give the Registry baseline refusal an
honest diagnosis and a recovery path without weakening the exact equality check. Characterize
unpublished prior promotion, stale checkout, wrong workspace root and unrelated drift as separate
measured cases, and explain the Git publication → local update → Registry synchronization sequence
in product terms. No `aart ...` command text may reach a TUI frame. Then steps 11–14; step 15 runs
the full suites once the batch is handed back.

**CP-19 step 7 is DONE — QA-031/B-100 closed (2026-09-09).** The exact Registry snapshot equality
still decides whether promotion is safe. When it refuses, the configured seam now classifies the
real Git checkout as a clean unpublished descendant, a clean stale ancestor, uncommitted
managed-path drift or a different configured origin, and the pure application seam gives each a
different product-language recovery. Unpublished work names Git review/merge, local checkout update
and Registry synchronization in order, with no CLI command in the TUI (D-214). Four real-repository
tests were RED against the former generic answer; removing the observed context from the configured
call kills all four. The whole focused set is green at 1612 tests plus 639 subtests.

**Exact next action:** CP-19 step 11 — QA-036/QA-037. Add compact workflow progress derived from
the navigation state and make Back retain the stable Candidate/subject and already-observed model.
Cover Candidate promotion, Registry initialization/rebuild, Source add/sync and consumer install;
do not build a breadcrumb for one hard-coded route. Then steps 12–14 and the full gates at step 15.

**CP-19 step 11 is DONE — QA-036/QA-037/B-103 closed (2026-09-09).** Workflow routes are typed
application declarations checked against the live navigation graph, session history determines what
is completed, and shared frame chrome renders `✓`/`▸`/`·` with long paths bounded to the content
measure. Candidate, Registry init/rebuild, Source add/sync and consumer install are covered. Back
keeps the stable subject only within one of these routes; every Candidate-promotion reverse edge
retains the Candidate, while unrelated detail browsing still clears stale focus (D-215). Two
targeted mutations killed; 136 nearby tests plus 23 subtests are green.

**Exact next action:** CP-19 step 12 — QA-035/QA-038/QA-040/QA-041/QA-042. Establish one restrained
section/card/footer vocabulary, one help binding per line, compact keycaps and a visible cursor on
every actionable Registry row. Then steps 13–14; full gates run once at step 15.

**CP-19 step 12 is DONE — QA-035/QA-038/QA-040/QA-041/QA-042/B-104 closed (2026-09-09).** The
layout kernel now owns one restrained section rule and card grouping. Dashboard explanation and
activity are distinct regions; Registry rows are separate indented cards and show `>` on the real
focus; help has one binding per line; the footer is one adjacent, width-bounded `[Key] Action` block
with contextual actions first (D-216). Five independent mutations killed; 93 nearest tests plus 182
subtests are green.

**CP-19 steps 13–14 are DONE — QA-039/B-105 and QA-043/B-106 closed (2026-09-09).** Promotion
Review now projects both domain-owned mode explanations, marks the active mode and Vendored's
enterprise default, and labels `m` as `Toggle mode` (`D-217`). Registries now projects only
`registry-git` connections; filtering cannot hide a later Registry, and refresh availability plus
command focus both follow the visible row (`D-218`). The whole focused cross-family set is green at
1513 tests. Domain-default, projection-filter and stale-focus mutations each turn their named test
red.

**CP-19 step 15 checkpoint.** Final `make quality` is green across all nine gates: 3653 tests, one
skipped, 85.38% branch coverage, packaging/docs/secret checks clean. Two standalone
`make integration` runs reached 380/381 and then the real macOS Keychain E2E failed with
Security.framework `errSecParam`; that exact test passed alone and twice inside `make quality`.
B-108 records the order-dependent gate failure and the diagnostic narrowing.

**Exact next action:** resolve B-108 without skipping or weakening the real Keychain test, then run
`make integration` to green. After that, hand the Fixed list — including QA-039 and QA-043 — back
to the operator for manual retest. Do not reopen the completed CP-19 implementation unless that
retest supplies new evidence.

## CP-21 steps 4 and 5 landed; step 6 is next

The frame is settled: one skeleton every screen fills (`D-232`), a placed footer (`D-234`), the
launch directory above the keys (`D-235`) and a heading that is the trail the reader walked
(`D-236`). Step 6 landed too (`D-237`): the stack no longer keeps a finished sequence, and Esc from a list
reaches the dashboard that owns it. Step 7 is next — `QA-060`, `QA-075`, `QA-076`, `QA-077`: screens
telling the truth about promoted Candidates, empty connected-Registry blocks, stale Sources, and the
internal screen identifier leaking into an operator-facing message.

## CP-21 step 8 is diagnosed, not open

Do not re-derive `QA-078`. `D-231` holds the rule and the slice file holds the measurement: the fix
is a change to what the install *offers*, so it lands with CP-21 step 3's consumer setup and
remediation path, where it also settles `QA-080`. Building it at the placement boundary was tried and
backed out — the receipt and the host then disagree and `configured_consumer_completion` refuses.

## The immediate next move

1. Ask the operator to finish *"chcialbym zeby tez byla"* — the last of the seven findings is a
   sentence short.
2. Build `QA-098` on the answer: the registry as a cursor row carrying its sha, the repo URL and
   branch and remote-branch state in the block `[v]` opens, the initialization stage report ending
   in `committed <sha> locally; not pushed and not merged`, and the sentence that a change becomes
   available only once pushed — by the operator, never by AART. A maintainer may subscribe to a
   remote branch; a user only ever subscribes to a repository's `main`.
3. Re-run the operator's manual walk over `QA-044`…`QA-098` and close step 16.

Still open from step 13b: on three forms the key legend wraps to three lines with `[v] Fast /
Verbose` orphaned on the middle one. Moving `v` into the universal row closes it up and changes
every screen's footer, which is the operator's call rather than ours.

## CP-25 release-gate checkpoint — tasks 01–03 done (2026-09-17)

`docs/refactor/slices/CP-25-release-pull-request-gate.md`. A release pull request now runs
`packaging-check validate docs-check release-bump` on one interpreter instead of ten gates on three,
guarded by `scripts/release_pr_scope.py`, which reads the diff and refuses the narrow path for
anything but release bookkeeping.

It takes effect from the release *after* `v0.1.2`: #15 was already open when this landed and is
gated the old way. On the next release pull request, check that `pr-check` shows one `gates
(Python 3.11)` job, that its first step is the scope check, and that the whole thing finishes in
well under a minute. If the scope check ever fails on a genuine release pull request, read what it
names before widening `IN_SCOPE` -- a path it did not expect is the case the check exists for.

## Critical boundaries for this slice

- Product Specification is the sole product authority.
- Source, Candidate, Registry and Marketplace remain distinct values and screens (INV-199).
- Source Sync never promotes and never mutates approved registry state (INV-200).
- Discovery remains exact `aart.yaml`/`aart.json` only (INV-201).
- Maintainer review is semantic diff first and raw file diff only on demand (INV-202).
- Published coordinate/version content is immutable; digest conflicts are explicit, never repaired
  in place (INV-203/239).
- Superseded, rejected and source-removed records remain durable audit history (INV-229).
- Secret values never enter views, state, plans, receipts, logs, fixtures or committed files.
- `key_event` remains the only key interpreter; there is one reducer and one persistent stdlib TUI.
- Machine state is assembled once outside draw functions; application projections have no IO/clock.
- Candidate list narrowing stays typed application state; screen 53 edits `MaintainerCandidateFilter`
  when it lands rather than introducing a second filter model (D-098).
- Local Candidate promotion preserves D-096 through the discriminated audit provenance in D-107;
  the legacy Git field accepts Git revisions only.
- Do not retire legacy direct/local or Collection authority until the corresponding CP-14 public
  flow is proven. B-031, B-038 and B-039 remain ordered behind that evidence (D-091).
- Do not modify older AART repositories.

## Durable handoff rule

At the end of the next increment update `MIGRATION_STATUS.md`, this file, the CP-14 slice file,
`DECISIONS.md` for material choices and `BACKLOG.md` for noncritical discoveries. Run focused gates
after each TDD cycle and the full repository quality suite before calling a CP-14 segment verified.
