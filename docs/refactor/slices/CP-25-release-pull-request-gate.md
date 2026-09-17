# CP-25 — release gating, usage-reporting withdrawal, and post-release field reports

Status: IN PROGRESS — tasks 01–03 done (D-290), 04–07 done and committed as `7af06be` (D-292),
08 done (D-293), 09 done (D-294); 10 part-done (D-295) — the scope seam is complete and held, the
screen that lets somebody use it is not written; tasks 11–14 are planned and not started.

The slice carries two unrelated subjects because the owner added the second while the first was in
flight. They share nothing but the release they will go out in, and they are ordered so that the
first is complete and committed before the second begins.

Date: 2026-09-17. Authority: the product owner, watching `pr-check` re-run the whole suite on the
`chore: release main` pull request for `v0.1.2` — *"niech w przypadku release'a będą odpalane tylko
te testy które sprawdzają podbicie wersji a nie wszystko? przecież odpalanie wszystkiego jest strata
czasu"* — and their choice, given the options, of the narrow gate set with INV-096 rewritten to
match rather than an exception carved around the existing wording.

## Goal and scope

A release pull request rewrites four files: the version literals in `pyproject.toml`,
`agent_artifacts/__init__.py` and `.release-please-manifest.json`, and `CHANGELOG.md`. It changes no
code. The tree underneath it is the tree the last ordinary pull request merged, and that tree passed
all ten gates on three interpreters to get there.

Proving it again is what INV-097 and INV-102 already forbid — repeating the complete source suite
for a tree that has passed it, and conflating one pipeline into another. So INV-096, which asked for
"a required quality gate" without saying what it must cover, was in tension with its own
neighbours. This slice resolves that in the specification first and then in the workflow.

Out of scope: the release run itself (`release.yml` is unchanged — it still proves the artifact),
branch protection, and the `v0.1.2` release in flight, which is deliberately gated the old way.

## Product contract

Specification references: INV-096, INV-097, INV-102.

INV-096 now names what the gate must prove and what it must not repeat, and makes the narrowing
conditional: *"Narrowing the gate is conditional on the release PR changing nothing but release
bookkeeping: a release PR that touches anything else MUST be gated as an ordinary change."*

That condition is the whole slice. The branch name is not evidence — anyone who can push can push a
commit onto `release-please--branches--main`, and a gate that skips the suite because of a branch
name is a way into `main` rather than a gate. The diff is evidence.

## Ordered tasks and acceptance criteria

### 01 — INV-096 states the contract a release pull request must satisfy

Rewritten in `PRODUCT_SPECIFICATION.md`; `INVARIANT_TRACEABILITY.md` row 107 repointed at
`.github/workflows/pr-check.yml` and `scripts/quality.py`, evidence `release_pr_gate_test.py`;
D-290 records why the narrowing resolves a contradiction rather than weakening the contract.

### 02 — The gate runner can run the release-bump gate alone

`scripts/quality.py` gained `SELECTABLE_GATES = QUALITY_GATES + ("release-bump",)` and a
`release-bump` gate over `release_policy_test`, `release_test`, `packaging_test` and
`install_commands_test`.

Selectable by name but **not** part of `make quality`: every module it names is already discovered
by `unit`, so including it in the full run would prove one thing twice. `select_gates` validates
against `SELECTABLE_GATES`, so an unknown name is still refused.

Acceptance: `python scripts/quality.py release-bump` passes; `select_gates(())` still returns
exactly `QUALITY_GATES`.

### 03 — A release pull request runs that gate set and nothing else

`scripts/release_pr_scope.py` reads `git diff --name-only <base>...HEAD` and refuses the narrow path
for any path outside the four files release bookkeeping touches. An empty diff fails too, with its
own exit code: nothing changed means the comparison did not work — a wrong base, an unfetched
history — and a gate that proves nothing must not pass.

Its permitted-path list is derived, not remembered:
`release_policy_test.test_the_narrow_release_gate_covers_exactly_what_the_engine_rewrites` builds
the same set out of `release-please-config.json` and requires the two to be equal, so a fifth
`extra-files` entry fails there rather than silently widening what may skip the suite.

`.github/actions/quality` gained two inputs — `gates` (empty means the full canonical run) and
`scope-base` (setting it turns the scope check on) — and the scope check runs before the developer
tools are installed, because a pull request that fails it has nothing to gain from an interpreter.

**Where the condition lives.** Not in a third job. `container.credentials` cannot be made
conditional, which is why the gate job already appears twice; a `release-gates` job would have
needed a `release-gates-private-image` beside it, giving four gate jobs and a rewritten aggregate —
or, without it, a fork on a private image losing release gating entirely. So both existing jobs
narrow through `with:`, and `pr-check` still speaks for every shape with
`needs: [gates, gates-private-image]`.

Acceptance: `packaging-check validate docs-check release-bump` in **15.26 s** against roughly
17 minutes for the full gate.

## Targeted semantic mutations

| Task | Mutation | Result |
|---|---|---|
| 02 | — covered by 03's whitelist mutation, which reaches the gate list through `release_policy_test` | |
| 03 | `fetch-depth: … && '0' \|\| '1'` → `&& 0 \|\| 1` | `test_the_release_branch_is_checked_out_with_the_history_the_diff_needs` red, alone. This is a real bug, not a notational one: `0` is falsy, so `x && 0 \|\| 1` evaluates to `1` on **both** branches and the release job would have been checked out shallow — the scope check would then fail every release pull request |
| 03 | `.release-please-manifest.json` removed from `IN_SCOPE` | `test_release_bookkeeping_alone_is_in_scope` and `test_the_narrow_release_gate_covers_exactly_what_the_engine_rewrites` red — the derived list catches the drift as well as the direct assertion |
| 04 | `"reporting"` removed from the organization policy's `optional` set | `test_an_organization_policy_written_before_the_withdrawal_still_loads` red, alone |
| 05 | `"reporting"` removed from the user configuration's `optional` set | `test_a_configuration_written_before_the_withdrawal_still_loads` red in both subtests, and `test_the_block_is_read_to_nothing_rather_than_to_a_setting` with them. Three reds for one field is not a blunt mutation: the field is either accepted or it is not, and the second test holds the other half of the claim — that accepting it is not the same as honouring it |
| 06 | `--usage-reporting-repository` added back to the `registry init` parser | `test_init_rejects_the_withdrawn_usage_reporting_option` red, alone |
| 07 | `TelemetryDelivery("disabled", 0)` → `("delivered", 0)` in `DisabledActivityTelemetry.publish` | `test_the_default_adapter_is_explicitly_disabled_and_has_no_callback` red, alone. This is the load-bearing one of the four: it holds the promise that nothing leaves the machine unless a caller injects an adapter on purpose |
| 08 | `CandidateState.APPROVAL_REQUIRED` moved from `ACTIVE_CANDIDATE_STATES` into `SETTLED_CANDIDATE_STATES` | **Survived**, and that was the finding. A Candidate stopped for manual approval is the most literally pending state there is, so classing it as settled would have hidden the very work issue #9 is about — while fixing issue #9. Two tests now hold it (`…_a_candidate_waiting_on_a_human_decision_is_awaiting_action` and `…_an_approval_required_candidate_is_counted_as_awaiting_action`), and the mutation is red in both (D-293) |
| 10 | `_host` ignores its `chosen` argument and reads `settings.default_scope` again | **Survived** every unit-level test in the module, because none of them installed anything. The test that kills it drives the real TUI from a Project default to a User install and asserts the files reached the home and not the project. Writing it also found a third `PREPARE_ACTION` site — the re-prepare after harness selection — that did not carry the scope, where the choice would have silently reverted (D-295) |
| 09 | `"Installed: " + ", ".join(row.installed_statuses)` → `"Installed"` on the Fast row | Three tests red, all of them about that one claim: `…_a_current_installation_is_named_with_its_harness`, `…_an_update_available_installation_is_not_flattened_into_installed` and `…_the_renderer_reports_exactly_what_the_projection_recorded`. Flattening the status loses the difference between `current` and `update-available`, which is the difference between nothing to do and something to do (D-294) |

**Where 04–07 ran.** In a copy of the working tree under the session scratchpad, not in the
repository, because a full `make quality` was running at the time and `scripts/quality.py` fails any
run whose tracked files change under it. The copy also settles the restore problem recorded below:
with no `.git` in it there is no `git checkout` to reach for, each file is copied aside and copied
back, and the interpreter still comes from the real project because Poetry keys its virtualenvs by
path. The baseline was confirmed green in the copy first — a mutation that "kills" an already-red
test proves nothing.

**A correction worth recording.** Restoring the first mutation with `git checkout
.github/workflows/pr-check.yml` reverted the file to `HEAD`, discarding the whole task's work
alongside the mutation, because none of it was committed yet; and the same command on the untracked
`scripts/release_pr_scope.py` silently did nothing, leaving the second mutation in place. For
uncommitted work, copy the file aside before mutating. This is D-286's trap in a new shape: the
restore is the risky half, not the mutation.

## Evidence

* `tests/release_pr_gate_test.py` — 17 tests: the selectable gate, the scope rule, and the workflow
  shape asserted against the folded YAML value rather than the line breaks it is typed in.
* `tests/release_policy_test.py` — the whitelist agrees with the release engine's own configuration.
* `docs/ci/workflows-v1.md` — what `pr-check` runs on a release pull request, and why the branch
  name is not what makes it safe.

## What this does not claim

That the release pull request is gated *less*. It is gated on a different subject: INV-096's own
list — the release identity, the artifact that identity produces, the documents it rewrites — plus
a check that the subject really is that and nothing more. A release pull request carrying one line
of source is gated exactly as it was before.

---

# Part two — withdrawing usage reporting (tasks 04–07)

Date added: 2026-09-17. Authority: the product owner — *"możesz jeszcze [włączyć] wywalenie tego
mechanizmu dashboardu i tych issue po stronie registry bo to jest strasznie immature i nikt z tego
nie będzie korzystać, w przyszłości będę chciał dołożyć prawdziwą telemetrię i śledzić instalacje
artefaktów np. z loga aktywności — bo ten oczywiście powinien zostać"*.

## What is being withdrawn

An optional, prompt-only flow in which a consumer submits a redacted usage report as a **GitHub
issue** to a registry that advertises `github-issues`, a scaffolded registry-side workflow that
validates and labels those issues, a second workflow that exports them and builds a **static
dashboard**, and its publication to GitHub Pages.

| Surface | Files |
|---|---|
| domain/application | `agent_artifacts/reporting/` — nine modules, 1,696 lines |
| command | `agent_artifacts/commands/reporting.py` (114 lines), the `aart reporting` verb and its `validate-issue`/`aggregate` actions in `cli.py`, `--usage-reporting-repository` |
| consumer surfaces | the offer and its screens in `application/consumer_ui.py`, `consumer_views.py`, `consumer_session.py`, `tui_consumer.py`, `tui_maintainer.py` |
| registry scaffolding | `registry_commands/templates.py` — both generated workflows, the `usage-dashboard/` directory, the `usage-report` label, the `AART_PAGES` variable; `io/registry_workspace.py` |
| protocol | the `github-issues` special case in `protocol/registry_schema.py` and `registry_commands/planning.py`, and its paragraph in `docs/protocol/registry-v1.md` |
| docs | `docs/reporting/usage-reporting-v1.md`, plus references in the rollout page, `registry-v1.md`, `maintainer-commands-v1.md`, three tutorials, the system matrix and the manual acceptance pages |
| tests | eleven dedicated `reporting_*_test.py` modules; passing references in about thirty-eight more |

## What stays, and why the distinction matters

**The activity log stays.** Receipts, `receipt_store.py`, the Doctor activity report and the TUI
activity log are untouched. They are the record of what this installation did on this machine —
first-party, local, already durable — and the owner names them as the seam real telemetry will be
built on later. Withdrawing the reporting flow must not touch a line of that, and task 07 pins the
distinction with a test rather than leaving it to prose.

**The advertisement is not a protocol break.** `ServiceAdvertisement.kind` is any lowercase slug;
only `github-issues` carries the extra "requires a repository" rule. A published registry that
advertises it therefore still compiles after the withdrawal — it becomes an advertisement nothing
consumes. So no snapshot in the wild is invalidated, and no compatibility shim is needed. Removing
the special case is a tidy-up, not a migration.

## Ordered tasks

Outside-in, so nothing is ever left dangling: the offer goes before the thing it offers, the
package before the scaffolding that calls it, the documents last.

### 04 — A consumer is no longer offered a usage report

The offer is not in the TUI. It lives in `agent_artifacts/commands/marketplace.py`, as
`_CliReporting`, `_prepare_cli_reporting`, `_reporting_plan_data`, `_json_reporting_data`,
`_read_reporting_consent` and `_render_cli_reporting` — the `aart marketplace install` path (D-117;
the legacy wizard's offer is already unreachable). That block goes.

`--usage-reporting-repository` is *not* part of this task: it hangs on `aart registry init`, where a
maintainer scaffolds a registry, so it goes with task 06.

**Two greps lie, and a future agent will fall for both.** `ProgressReportingHandler` in
`tui_consumer.py` is CP-24.06's installation progress and has nothing to do with this; the
`reporting` field on `MaintainerScreen.REGISTRY_INIT` is the maintainer typing a repository while
scaffolding a registry, which belongs to task 06. Neither is a consumer offer. Match on
`agent_artifacts.reporting`, `UsageReport` and `ReportingMode` rather than on the word.

**The part that is not a deletion.** `ReportingSettings`, `ReportingMode` and `ReportingPolicy` live
in `configuration/model.py`, and `configuration/schema.py` lists `reporting` in the *optional* field
set of the user configuration and the organization policy. `validate_object_fields` refuses any
field outside `required | optional`, and `write` emits a `reporting` block unconditionally — so
**every user configuration on disk today carries one**. Dropping the field from the accepted set
therefore makes AART refuse to load every existing configuration. Verified, not assumed:

```text
{"schema_version": 1, "reporting": {"mode": "prompt"}}
  with the field known   -> Ok
  with the field removed -> Err
```

So the field stays accepted and becomes ignored: parsed to nothing, never written again, and a test
that names the reason. An old configuration keeps loading, a new one stops growing the block, and
the block disappears from disk the next time anything writes. Removing it from the accepted set is a
separate change that needs a deprecation window, and it is not in this slice.

Red first: `aart marketplace install` offers nothing and mentions no report in either rendering; a
configuration carrying a `reporting` block still loads; a configuration written afresh carries none.

### 05 — The `aart reporting` verb and its package are removed

Delete `agent_artifacts/reporting/` and `agent_artifacts/commands/reporting.py`, the `reporting`
entry in the CLI dispatch table and its parser. Delete the eleven `reporting_*_test.py` modules.

**One type has to come out of the package first.** `SetupReportState` lives in
`reporting/projection.py` but is not about usage reporting: it is the setup queue's per-item status,
and `agent_artifacts/tui.py` builds it in eight places (`tui.py:149` types a whole field on it).
Deleting the package with it inside breaks the TUI. Move it to where the setup queue's own types
live and re-point `tui.py` and `marketplace.py`, as a separate commit before the deletion, so the
move is reviewable on its own and the deletion stays a deletion.

`configured_setup_report_test.py` and `configured_setup_gap_test.py` follow that type rather than
the package, and stay.

Red first: `aart reporting` is an unknown command, `agent_artifacts.reporting` does not import, and
the setup queue still reports its statuses in the TUI.

### 06 — A scaffolded registry no longer carries the issue and dashboard workflows

Remove both generated workflows, the `usage-dashboard/` directory, the `usage-report` label and the
`AART_PAGES` variable from `registry_commands/templates.py` and `io/registry_workspace.py`; the
`--usage-reporting-repository` option on `aart registry init` (`cli.py`); and the
`ServiceAdvertisement("usage_reporting", "github-issues", ...)` a scaffolded registry emits
(`registry_commands/planning.py`). Red first: a freshly scaffolded registry workspace contains
neither workflow, no Pages permission, and advertises no usage service.

This closes **B-134** (the registry Pages trap) by removing what it was a trap about.

### 07 — The documents stop promising it, and name the activity log as the seam

Delete `docs/reporting/usage-reporting-v1.md`; purge the references listed above; drop the
`github-issues` paragraph from `docs/protocol/registry-v1.md` and the special case from the schema.
Add the decision record: what was withdrawn, why, and that the activity log is where telemetry will
be picked up. Pin the distinction with a test asserting the activity log surfaces are intact.

The owner clarified after reviewing the plan that the removed GitHub implementation must not erase
the future integration seam. Add a transport-neutral application port over Activity records and a
disabled/no-op adapter. It owns no URL, authentication, network client or GitHub vocabulary and is
not an implicit telemetry opt-in; it is the injection boundary a future explicitly configured HTTP
adapter can implement. The old `UsageReport` payload and GitHub-issue provider do not survive under
a new name. D-292 records this distinction.

## Open decisions for the owner

1. **The version this releases as.** Removing a public CLI verb is a breaking change. This
   repository sets `bump-minor-pre-major: false`, so a `!` in the pull request title takes `0.1.x`
   straight to **`1.0.0`**. The alternatives are to accept that, or to classify it as `feat:`
   (`0.2.0`) on the argument that `aart reporting` was never in the Product Specification and so was
   never part of the contract a version promises. This is the owner's call, not a derivable one.
2. **Whether to keep the `github-issues` special case** in the registry schema as a no-op, so an
   existing registry's advertisement still validates with its repository coordinate required. The
   recommendation is to remove it: nothing consumes it, and a validation rule that guards nothing is
   the drift this repository keeps finding.

## What the acceptance record already says

**QA-013** in `docs/testing/manual-acceptance.md` records that `registry init` generated the
usage-reporting Issue Form and both workflows *by default*, and that this was narrowed so they are
generated only when `--usage-reporting-repository` names a destination. The owner's judgement that
nobody uses this is therefore not a fresh opinion: the scaffolding is already opt-in, and the
withdrawal removes an option rather than something in everybody's way.

The consumer TUI has no usage-reporting screen, so INV-187 (accepted TUI behaviour is a product
contract) is touched in one place only: the maintainer's Initialize Registry form (46a) loses its
`reporting` row, and `TUI_MANUAL_WALKTHROUGH.md:143` loses the line telling a tester to leave it at
`not enabled`. Both belong to task 06.

## What the Product Specification says about it

Nothing. `telemetry` appears in it four times, every one of them in the list of places a secret
value must never appear. There is no section, and no invariant, describing a usage-reporting flow.
So the withdrawal is a scope reduction rather than a specification change — which is also the
strongest argument for the `feat:` reading of decision 1.

---

# Part three — field reports from the released TUI (tasks 08–14)

Date added: 2026-09-17. Authority: the product owner's instruction to make CP-25 the active stream
and add every currently open product issue in `M1F1/aart-cli`. The source reports are issues
[#9](https://github.com/M1F1/aart-cli/issues/9),
[#10](https://github.com/M1F1/aart-cli/issues/10),
[#11](https://github.com/M1F1/aart-cli/issues/11),
[#12](https://github.com/M1F1/aart-cli/issues/12),
[#16](https://github.com/M1F1/aart-cli/issues/16), and
[#17](https://github.com/M1F1/aart-cli/issues/17). D-291 records why issue #11 is two tasks and why
the whitespace reports remain separate.

These tasks start only after the owner reviews this written scope. They do not silently alter the
open release-version decision above.

### 08 — The Maintainer Dashboard explains Candidate counts by lifecycle state (#9)

The current dashboard says only `Candidates: N`. That number includes durable Candidate history,
so two promoted Candidates still read as two unexplained Candidates even though neither is waiting
for maintainer action. Deleting or ceasing to count the records everywhere would violate the audit
contract: Promoted, Superseded, Rejected and Source Removed are durable lifecycle states.

The dashboard will distinguish Candidates that still require or permit maintainer action from
historical/disposition states. A source with two promoted Candidates must not look as though two
Candidates are still pending. Fast mode gets a compact, state-aware summary; Verbose may carry the
full lifecycle breakdown. `Validation failures` and `Ready for promotion` remain derived from the
same Candidate set, so the displayed arithmetic cannot contradict itself.

Red first: compose a real Maintainer Dashboard with two promoted Candidates and assert the active
count is zero while the promoted count is two; mix Ready, Invalid and Promoted records and assert
the summary totals. The projection owns the arithmetic once; the renderer does not reclassify
Candidate records, and the durable records remain visible in the Candidate history.

### 09 — Marketplace rows prioritize installation state and compatible harnesses (#10)

The Marketplace list currently places the complete artifact description on every row and repeats
it in the focused block. That makes the list hard to scan while omitting the two facts the owner
needs there: whether the artifact is installed and which harnesses it can target.

Fast rows will prioritize coordinate, installation state and compatible harnesses. The focused
description is progressively disclosed only in Verbose mode; Enter continues to open Artifact
Details for the complete record. Search and filtering still operate on the approved summary even
when it is not rendered in Fast mode. Installed state comes from the canonical lifecycle view and
harness compatibility from the approved artifact projection — the renderer neither probes the
machine nor guesses from the artifact kind.

Red first: render uninstalled, current, update-available and multi-harness artifacts; assert Fast
contains their state and harnesses but not the long summary, while Verbose contains the focused
summary exactly once. Hold narrow terminal widths so removing the duplicated prose actually fixes
the reported layout rather than only the wide fixture.

### 10 — Installation scope is an explicit per-install choice seeded by Settings (#11a)

`Settings.default_scope` is currently a silent decision for the install flow. It becomes a default,
not an irrevocable choice. Before Ready/Review, installation exposes Project/User scope when the
resolved selection supports both. The Settings value is initially selected, the user may change it
for this operation, and changing it re-prepares the plan so review, paths, effects and receipt all
name the chosen scope. The preference itself is not rewritten by a one-off choice.

The choice is bounded by the resolved artifacts' declared scopes and by whether a project target
exists. A selection with only one valid scope discloses that scope without offering an impossible
alternative; a multi-artifact selection offers only the intersection supported by every member.

Red first: drive the real TUI from a Project default to a User install and from a User default to a
Project install, then assert only that scope's files and receipt exist. Add one-scope and mixed-scope
negative cases, and a property over declared scope sets proving the offered choices are exactly the
non-empty intersection.

### 11 — The Python dependency backend is an explicit per-install choice seeded by Settings (#11b)

Issue #11 also asks for a default `pip`/`uv` choice in Settings and a one-operation override during
installation. This is separate from scope: it changes dependency remediation and runtime effects,
not installation ownership or paths. B-132 is therefore scheduled here rather than hidden inside
task 10.

Settings will carry a preferred Python installer. When the selected artifacts need Python
dependencies and more than one policy-allowed, available backend can satisfy the same contract,
the install flow offers those backends with the preference initially selected. The chosen value is
fed into the existing `chosen_installer` rule and the plan is re-prepared. Review continues to show
one backend and execution runs that same backend — never two dependency changes to approve. A
one-off choice does not rewrite Settings, and an unavailable or policy-denied preference is not
offered as though it could run.

Red first: exercise pip-default/uv-choice and uv-default/pip-choice paths through review and a fake
interpreter, plus single-backend, policy-denied, unavailable and no-Python-dependency cases. The
targeted mutation changes the selected preference after review and must make the execution test red.

### 12 — User Variables and Credentials separates artifact rows visually (#12)

Screen 22 renders each installed artifact as a multi-line group, but adjacent groups touch. Insert
exactly one empty line between artifact groups so the coordinate, Configuration summary and
Credentials summary remain visually owned by one row. Do not add leading/trailing blank rows or
change the empty state, cursor identity, search, selection or Fast/Verbose semantics.

Red first: exact-line assertions for zero, one and two artifacts, including a focused second row and
a narrow frame. A targeted mutation removing the separator must fail only the multi-artifact case.

### 13 — Artifact Variables and Credentials separates Configuration from Credentials (#16)

Screen 22a has two semantic sections but renders their headings against their first rows and against
each other. Insert one empty line after `Configuration`, one between the completed Configuration
block and `Credentials`, and one after `Credentials` before its first row, matching the owner's
accepted example. Preserve the credential boundary: only reference/health text is shown, never a
secret value.

Red first: exact-line fixtures for configuration plus credentials, configuration only, credentials
only and neither. Section spacing must not manufacture an empty value row, and narrow rendering
must preserve the same block structure.

### 14 — Installed Artifact Details names the exact owned installation paths (#17)

The Installed Artifact view reports health and configuration but does not answer where AART placed
the artifact. Add an Installation section derived from the canonical installed observation and
receipt ownership data. Fast names the actual user-facing payload and harness locations together
with Project/User scope; Verbose adds every owned component path and its role. Paths are observed or
recorded facts — never reconstructed from a guessed harness layout.

If an owned path is missing or divergent, the view still names that expected/recorded location and
its measured state rather than claiming the artifact is installed there. Shared or unowned files
are not attributed to the artifact. No file content, configuration value or credential material is
read into the view.

Red first: project- and user-scope installations, one payload with multiple harness projections,
a missing owned component and a shared/unowned path. Drive at least one installation through the
public TUI and reopen Installed Artifact Details in a new session so the paths are proven durable,
not borrowed from the just-completed plan.
