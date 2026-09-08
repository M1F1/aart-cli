# AART Refactor — Next Work

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

**Next on QA-021:** the TUI layer. `46c-scan-repository` (a `RepositoryScanDraft(url, ref)` form
reached with `s` from screen 46), `46d-scan-result` (a selectable list of `ScannedArtifact`s, added
to `_SELECTABLE`, where `a` requests adoption), `46e-review-adoption` (naming every chosen
coordinate, the resolved commit and the copied paths), plus `ConsumerActionKind.REPOSITORY_SCAN` and
`REPOSITORY_ADOPT` wired through `_ACTION_REVIEW`/`_ACTION_RUNNING`/`_ACTION_RESULT` and two ports on
`LocalConsumerActions`. After that, `Check upstream` and a machine-complete CLI equivalent, both of
which `B-095` still carries.

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
