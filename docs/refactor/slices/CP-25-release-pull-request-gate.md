# CP-25 — A release pull request is gated on what it changes; usage reporting is withdrawn

Status: IN PROGRESS — tasks 01–03 done (D-290); tasks 04–07 added 2026-09-17 and not started.

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
