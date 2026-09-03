# CP-16 — Global doctor and supportability
Status: IN PROGRESS (opened 2026-09-03)

## Goal

Implement `aart doctor` as an environment-wide inspection and reconciliation surface: readable
diagnostics for people, machine-complete JSON for automation, and safe repair entry points backed by
the canonical reconciliation engine. Doctor must never mean reinstall-all.

## Product Specification sections/invariants

- Section 161.11, accepted screen 29 / CLI equivalent `aart doctor`.
- INV-194: Doctor uses reconciliation, not reinstall-all.
- Section 165.11 / INV-223: offline installability remains three separately reportable
  capabilities -- metadata, canonical payload and runtime dependencies.
- INV-191 and INV-192: Activity and Receipt remain the audit and recovery evidence; Doctor must not
  invent stronger undo guarantees than a receipt carries.

## Legacy/current paths

- `application/consumer_views.py::project_doctor` and `tui_consumer.py::render_doctor` provide the
  accepted screen-29 projection and rendering.
- `io/consumer_machine.py::read_installed_inspections` observes durable canonical receipts.
- `application/reconciliation.py::plan_repair` is the sole minimal-repair planner, reached through
  `io/configured_repair_action.py::prepare_configured_repair`.
- `marketplace receipt show|verify|undo` and Activity views carry existing support evidence.

## Target paths/owners

- `agent_artifacts/commands/doctor.py` owns the public command composition and serialization.
- Existing application projections and reconciliation planning remain authoritative; the command
  does not calculate health or repair effects a second way.

## Non-goals

- Reinstall-all, implicit mutation, or applying a repair without review.
- Resolving Marketplace content merely to inspect what is already installed.
- Fixing noncritical supportability findings outside the active increment.

## Method

D-091 and D-134 apply. Each increment names the public verb, drives it over a real temporary
machine, and is proven red against a mutation of the behavior it claims. Hypothesis is used where a
claim is universal; scoped `make mutants` is advisory and its survivors are read as findings, not a
score.

## Implementation steps

1. **VERIFIED:** add the read-only, environment-wide `aart doctor` report over
   canonical project and user installations, using the existing health projection and canonical
   minimal-repair planner; expose complete JSON and readable screen-29 text.
2. **VERIFIED:** report 165.11's three offline capabilities before installation (B-051), without
   collapsing them into one online/offline answer.
3. **VERIFIED:** add safe repair review and finalize entry points. Re-inspect and re-plan under the same
   precondition discipline as every configured lifecycle action; apply only an explicitly reviewed
   minimal plan.
4. **VERIFIED:** make Activity, Receipt, configuration, credential and orphaned-run diagnostics
   usable from the global report without weakening their existing evidence or undo boundaries.
   Triage B-052 and B-055 here only where a mandatory invariant requires it.
5. Run the full public-flow, negative/property, integration and mutation-adequacy evidence; close
   the slice only when every declared invariant has a traceable public surface.

## Completed increments

### Step 1 — one observation feeds health and minimal repair planning (D-139)

`tests/doctor_command_e2e_test.py` installs two approved-registry Skills through the real public
command. On a healthy non-empty machine, `aart doctor` reports both and no repairs. After one
delivered file is edited outside AART, it reports one ready artifact and one needing attention,
names the divergent component, and serializes exactly one repair plan whose components equal the
observed drift. The human rendering lists the same two artifacts. A project installation and a
user-scope installation are both present in one run, proving "environment-wide" rather than merely
project-wide. Disabling the source after installation leaves Doctor functional, proving the read
does not turn into Marketplace resolution. Corrupting the real durable receipt yields a structured
`receipt-unreadable` refusal instead of an empty healthy machine.

The first characterization was RED because the top-level parser had no `doctor` command. Two
targeted mutations were then proven separately: including healthy plans made the healthy test RED,
and restricting the read to project scope made the project-plus-user test RED. Changing the state
directory's case survived on the case-insensitive Darwin filesystem and is equivalent on this
machine, so it is not claimed as evidence.

A fresh scoped run of
`make mutants ONLY=agent_artifacts/commands/doctor.py TESTS="tests/doctor_command_e2e_test.py"`
after the first five tests produced 132 mutants: 85 killed, 19 uncovered in the structured-error
branch, and 28 survivors. The receipt-corruption scenario was added specifically to execute that
branch. A second fresh run after its JSON and human assertions killed 104 and left 28 survivors,
with none untested. Survivors outside this increment's claims include equivalent JSON indentation,
unavailable platform credential providers, update metadata the current inspection does not compute,
and presentation whitespace. B-058 records that the wrapper otherwise reuses stale outcomes after
test-only changes.

### Step 2 — three offline capabilities remain three observations (D-140)

`tests/doctor_offline_readiness_e2e_test.py` drives the public `aart doctor` before any install. A
real approved vendored Skill reports source and artifact metadata cached, its canonical payload
cached, and runtime dependencies not required. A real referenced publication keeps the metadata
but reports the payload missing. A packaged MCP declaration proves that a cached payload does not
invent dependency readiness: because AART has no durable package-manager cache inventory, declared
dependencies are honestly `unverified`. Removing the real Source store reports cold metadata and
no invented artifacts. Human output names the same three capabilities separately and does not call
the artifact installed.

The observation is environment-wide rather than a single-source shortcut. One scenario configures
an ignored disabled registry, an unsynchronized registry, a synchronized local Source and the
approved registry; Doctor reports every enabled source and does not parse the ordinary Source as a
registry. A mixed referenced/vendored registry proves one missing payload does not stop later
artifacts from being reported. A real lifecycle transition to deprecated proves unavailable
metadata is not presented as installable offline.

The first five tests were RED with `KeyError: offline_readiness` (and absent human text). Three
manual mutations independently made the canonical payload always cached, dependencies always
`not-required`, and cold metadata cached; each turned only its named public claim red. Fresh scoped
mutation runs then found and closed the multi-source, ordinary-Source, multi-artifact and lifecycle
filter gaps. The pure application projection killed all 30 mutants. The final I/O run killed 73 of
76; two survivors alter the currently unproducible Collection filter spelling, and one changes
`False` to `None` in a falsey input whose public state is identically `missing/unverified`. Per
D-134 they are findings, not a score or a reason to invent a fixture outside the active capability.

### Step 3 — one reviewed plan is applied, and only that one (D-141)

`tests/doctor_repair_command_e2e_test.py` drives `aart doctor --repair` over a real canonical
installation whose delivered file has been removed outside AART. Review and finalize are two
separate command invocations, and the digest the first returns is authorization input to the second.

Without `--yes`, the command returns a complete plan — the review digest, the components changing,
and the same minimal plan the read-only report already serializes — and the delivered file is still
absent afterwards, so the review did not quietly apply its own repair. The human rendering names the
same delta, the review identity and the confirmation boundary, and neither surface contains the word
`reinstall`. With `--yes` and the matching digest, the repair runs, records a `repair` receipt whose
steps equal the observed drift, and a following `aart doctor` reports `{"ready": 1,
"needs_attention": 0}` — health measured by the same read that found the damage, not by the repair
reporting on itself.

The refusals are the substance. `--yes` without `--expect` is refused as `consumer-review-mismatch`
and repairs nothing. A machine moved between review and confirmation returns the *recomputed* plan
alongside the stale expectation instead of applying the old one, and leaves the new drift untouched.
And because a digest comparison in the command would only prove the command re-planned, the last
scenario moves the machine *after* the command's own re-plan, inside the lifecycle call: the effect
is refused as `execution-review-stale`, which is the adapter re-observing under its lease rather than
the command trusting what it computed a moment earlier.

Five mutations, each turning red only the claim it belongs to: inverting the review branch (7 tests);
never comparing `--expect` to the recomputed digest (2); dropping the version half of exactness (1
subtest); dropping the source half (1 subtest); and hardcoding project scope (1).

**The finding is in the exactness test.** It was named "source and version", but its only input
omitted the source — so removing the version requirement entirely killed nothing, and half the name
was unheld. It now runs both under-specified forms as subtests, and each half of the mutation kills
exactly its own subtest. This is the same shape as CP-15's D-138 finding, arriving from the opposite
direction: there an absence was asserted where it could not have been present, here a conjunction was
asserted with only one conjunct ever supplied.

One survivor is recorded rather than chased: weakening the exactly-one-match guard from `!= 1` to
`< 1` kills nothing, because a second installation of one identical coordinate in one scope is not
known to be representable. B-059 records it as defensive code of unproven reachability; per D-134 a
survivor outside the increment's claims is a finding, not a reason to invent a fixture.

### Step 4a — the working copy nobody knew to ask about (D-142)

CP-15 step 4b proved that `aart marketplace receipt verify <coordinate>` names the working copy an
interrupted run left behind. That claim carries a precondition inside it: the operator must already
know which receipt to verify. `setup_verify_probes.orphan_run_directories` filters the run root by
`plan_hash[:16]`, so without a plan hash it answers nothing — and being interrupted is usually the
reason an operator stopped watching, which makes the one fact they cannot supply the one the
existing surface requires.

`tests/doctor_orphaned_runs_e2e_test.py` drives `aart doctor`, which is told nothing: no
coordinate, no receipt, no plan hash. It reports the working copy at the path the engine actually
created, and names the plan-hash prefix that ties it back to its run, cross-checked against the
receipt's own `plan_hash`. A machine with no interrupted run reports none, which is what stops the
finding from being consistent with reporting one unconditionally.

Every scenario runs CP-15 step 4b's real failing custom entrypoint — `apply` exits non-zero,
`rollback` then also exits non-zero, the one path in `_custom_apply` that raises without removing
its run directory — so the directory asserted on is one the engine really created and really failed
to clean up. Patching cleanup away would produce the same directory and prove nothing about when
one is actually left.

`LAF-61` governs what Doctor may then do about it. The report names the working copy and leaves it:
one test compares the directory's contents before and after and asserts the human rendering says
AART does not delete them. An inspection that tidies away its own evidence is worse than none,
because the second operator finds a clean machine and no reason to doubt it.

`LAF-66` governs where it looks. That defect was one path composed in two places that disagreed —
the probe from the project root, the engine from the data root — so the claim answered `true` in
every scope without ever looking where runs are made. `read_orphaned_runs` takes the run root from
its caller for the same reason `orphan_run_directories` now does, and the E2E test asserts the
*identity* of the directory reported rather than merely that some path was.

"Nothing is there" and "we could not look" are kept apart, which is step 2's subject applied to a
different observation: an unreadable run root reports `readable: false` with no working copies, and
the projection refuses to construct an unreadable observation that also lists runs. An operator told
there are no leftovers stops looking for them.

Seven mutations, each red only where it belongs: the sweep never finding anything (3 tests); an
unreadable run root reported as empty (1); `LAF-66` reintroduced by taking the run root from the
project instead of the data root (4); `LAF-61` broken by having the report delete what it found (1);
the whole directory name reported in place of the plan-hash prefix (1); a phantom working copy
reported where the run root never existed (1); and that same absence reported as unknown (1). The
last two exist because the baseline test asserts an absence, which D-138 says is evidence only where
the fixture could have produced the thing — and both halves of what it claims, *not a phantom* and
*not merely unknown*, needed their own mutation.

**The finding is methodological.** The first attempt at that phantom mutation survived, and it was
not a weak test: it mutated the line reached when the run root exists, while a healthy machine has
never created one and leaves through the `FileNotFoundError` branch above it. The mutation was never
executed, so its survival measured nothing. A survivor is a finding only once the scenario is shown
to run the line that changed; otherwise it is noise that looks exactly like a gap. This is the
mutation-testing counterpart of D-138 — there an absence was asserted where nothing could have been
present, here a mutation was read as surviving where nothing could have executed it.

A fresh scoped `make mutants ONLY=agent_artifacts/io/orphaned_runs.py
TESTS="tests/doctor_orphaned_runs_e2e_test.py"` produced 43 mutants and found four real gaps that
the seven manual mutations had not, which is exactly the division of labour D-134 describes: the
targeted mutation proves the claim you made is load-bearing, the scoped run finds claims nobody
thought to make.

- `readable=False` becoming `readable=None` survived. `None` is falsey, so `assertFalse` passed --
  but in JSON the difference is `false` against `null`, and a consumer testing for `false` stops
  seeing the case. The projection now refuses a non-boolean and the test asserts `is False`.
- `continue` becoming `break` survived at both loop guards, and `or` becoming `and` survived at the
  second. One working copy alone cannot tell those apart: with `break`, anything sorting before the
  real directory hides it entirely. A stray file and a dashless directory, both named in all-zero
  hexadecimal so they sort ahead of any real plan-hash prefix, now sit beside the working copy; all
  three mutants turn that test red.

The run went from 36/43 to 40/43. The three that remain are classified rather than chased. Two
change `readable=False` in the `if not run_root:` guard, which no scenario executes because the run
root is always the data root -- the same unexecuted-line trap the phantom mutation fell into above,
and confirmed here by locating which of the two occurrences each mutant sits on rather than assuming.
The third replaces `partition("-")` with `rpartition("-")`, which is equivalent for every real run
directory: `tempfile.mkdtemp` draws its suffix from `abcdefghijklmnopqrstuvwxyz0123456789_`, so the
name has exactly one dash. That is a checked property of the naming, not a guess.

**Triage of the two backlog items this step names.** B-052 needs a public driver for interactive
per-effect consent, which is a CLI capability rather than a Doctor one, and B-055 concerns the
marketplace graph rather than the installed machine. Neither is reachable from a global report and
no mandatory invariant requires either, so both stay in the backlog rather than expanding the slice.

### Step 4b — the audit trail, and the undo Doctor must not invent (D-143)

`project_activity`, `activity_from_receipts`, `activity_view_to_data` and `render_activity` all
existed, and every one of them was referenced by `application/consumer_session.py` and by nothing
under `agent_artifacts/commands/`. The record of what AART did to a machine -- the trail INV-191
makes the audit evidence -- was reachable from the interactive shell and from nowhere else. That is
the same shape as steps 1, 2 and 4a, and the third time in this slice that a capability turned out
to exist at a seam with no verb reporting it.

`tests/doctor_activity_e2e_test.py` drives `aart doctor` over a real configured registry. The
report now carries the accepted day-grouped timeline and, beside it, each recorded action with the
undo answer its own receipt holds. The timeline and the action list are asserted to carry the same
recorded moments, so they are one observation rendered twice rather than two reads that can drift.
The trail is newest first and holds every action of the run.

**INV-192 is held as a pair produced by one flow.** An install that placed a payload and a delivery
reports `available: true` naming exactly `delivery:claude` and `payload`. The uninstall that follows
reports `available: false`, names nothing to reverse, and gives the receipt's own reason -- nothing
retained here can reverse a removal. The false half is evidence only because the true half sits
beside it in the same trail (D-138), and no fixture had to be invented for either: one install and
one uninstall produce both.

**What this deliberately does not claim.** `marketplace receipt show` is a different record -- the
*setup* receipt for one coordinate, with its own retry and rollback commands and no `recorded_at`
or `undo` field at all. The first draft of this file cross-checked Doctor's undo against it and was
wrong to; the two are different receipts about different things. The timeline carries lifecycle
receipts, which is what 165 means by Activity, and the honest cross-check is that the undo answer
*varies with what actually took effect* rather than that it matches a record it is not derived from.

Six mutations, each red only where it belongs: synthesizing the undo as always available instead of
reading the receipt (1 test); truncating the trail to its newest entry (2); building the timeline
from an empty trail (1); rendering every action as undoable (1); and re-deriving the recorded moment
from the clock instead of the receipt (2).

**The finding is in the empty case.** Removing the special-cased "nothing has been recorded on this
machine yet" line killed nothing: the baseline scenario asserted only the JSON, so the human
rendering was free to print a bare `Recent activity:` header with nothing beneath it. That reads as
a rendering that failed rather than as a machine that has done nothing -- the same "absence against
unknown" confusion step 2 refused for the offline capabilities and step 4a refused for the run root.
The baseline now asserts the words, and the mutation turns it red.

A scoped `make mutants ONLY=agent_artifacts/commands/doctor.py` over all four Doctor test files
produced 499 mutants, 354 killed. Nine survivors fall inside this step's two functions and three of
them were real:

- `_action_data` published `artifact` and `status`, and renaming either key killed nothing, because
  no test read either. A field the payload publishes that nothing holds is a contract nobody is
  keeping; both are now asserted.
- The human undo line joined its components with `", "`, and changing the separator killed nothing.
  With two components that separator is visible to the reader, and an operator deciding whether to
  undo needs to see what would be reversed. Now asserted in full.

The remaining six are string-spelling mutants that substring assertions cannot distinguish --
mutmut wraps a literal as `XXRecent activity:XX`, which still contains `Recent activity:` -- plus
one blank separator line. They are recorded, not chased: tightening an assertion to an exact line
would hold the rendering's whitespace rather than its meaning.

**Outside this step's claims:** 84 of the 145 survivors are in step 3's `_run_repair`, which was
proven by five targeted mutations and never given a scoped run of its own. That is a finding about
step 3's test depth rather than about step 4b, and it is recorded as B-060.

### Step 4c — what a machine ignores on purpose, and never says (D-144)

Two configurations are honoured silently. A source with `enabled: false` is skipped by every other
part of this report deliberately -- step 2's offline readiness iterates enabled sources only -- so an
operator asking why nothing offers an artifact sees a report in which that source does not appear at
all, which is indistinguishable from never having configured it. And an organization policy that
sets a reporting field replaces the value in the user's own configuration file: the runtime path is
answered, because `_locked_override_diagnostics` refuses a `--reporting-mode` flag that contradicts
policy, but the configured path is not. `EffectiveConfiguration` has carried `locked_fields` for
exactly this purpose and, before this step, `grep` found no reader of it anywhere in the package.

`project_credential_record` was the same shape once more: `application/consumer_session.py` was its
only caller, so credential health and its dependants were reachable from the interactive shell and
from nowhere else. That is the fifth capability in this slice found fully built at a seam with no
verb reporting it, after Doctor itself, offline readiness, the orphaned run root and the Activity
trail.

`aart doctor` now reports both, and the report answers the empty case in words rather than by
omission -- "every configured source is enabled and no field is policy-locked", "no installed
artifact references one" -- which is the same refusal of "absence against unknown" steps 2, 4a and
4b each made in their own section.

**Two claims are measured at the seam, and the reasons are concrete rather than convenient.** This
is the split CP-15 step 8 recorded for the same kind of reason, and each is named in the test file
so a later reader can retire it if the constraint goes away:

- The **populated credential list**. Recording a credential reference on an installation means
  running a setup recipe that declares a secret input and supplying a value for it, and
  `commands/marketplace.py` wires a real `MacOsKeychainProvider` on darwin -- so that flow would
  write into the developer's own login Keychain. Reading is safe, so the empty case runs through the
  verb end to end; the populated shape is projected directly.
- The **policy-locked field**. `resolve_config_paths` puts the organization policy at
  `/Library/Application Support/agent-artifacts/policy.json` on darwin and no CLI flag overrides
  that path, so no test can install one without writing to a root-owned system location.

The credential projection also carries a guarantee that is structural rather than asserted per
field: `CredentialObservation` "deliberately has no value field", so `_credential_data` has no
material available to leak. The test asserts the type's field names, which means a later field named
`value` or `secret` fails there rather than silently reaching the report.

Eight targeted mutations, each red only where it belongs: inverting the disabled-source filter (2
tests, the reported case and its baseline); publishing an empty `policy_locked_fields` (1); emitting
the all-clear line when something is in fact disabled or locked (2); naming no fields in the
locked-field explanation (1); publishing an empty dependant list (1); rendering a credential with
dependants as if it had none (1); inverting the empty-credential answer (1); and describing a
disabled source without naming which one (1). A ninth belongs to the finding below.

**The finding is what the scoped run caught before any mutant ran.** Its baseline stats pass failed
on `doctor_offline_readiness_e2e_test`, which held step 2's "cached is not installed" claim as
`assertNotIn("installed", output.lower())` over the whole human report. The new credential section
says "no installed artifact references one" -- true, and in the section whose subject genuinely is
installed artifacts. Nothing regressed: the assertion had been holding a claim about the report's
vocabulary while its name claimed something about the offline capabilities, and the two coincided
only while the report was short enough. It is now scoped to the offline block, which is a
strengthening rather than a weakening -- putting the word `installed` into the offline renderer
still turns it red -- and the general form is D-144. Worth recording twice over because the focused
runs for this step were all green: only the file the step did not touch could see it.

**The second finding repeats step 4b's exactly, which is what makes it a pattern rather than an
accident.** Once the run completed, 29 of its 595 survivors were inside this step's four functions,
and they said three things. Six credential payload keys -- `reference`, `provider`, `service`,
`account`, `provider_state`, `detail` -- and the disabled source's `kind` could each be renamed with
nothing turning red, because no test read any of them: a field the payload publishes that nothing
holds is a contract nobody is keeping, and that is the same defect step 4b found in `_action_data`.
The human line for a credential *nothing* depends on was unheld, though the JSON half of that case
was asserted -- and "deletable" is the entire point of that case. And the separator between
dependants, and between locked fields, was invisible to a fixture that only ever had one of each,
which is the shape step 4a hit at its loop guards.

All 29 are closed. The full-record and full-line assertions that close them are stated as
equalities rather than substrings, because for a section that is one or two lines the whole line is
the meaning -- unlike step 4b's multi-line block, where an exact match would have held whitespace.
A fresh scoped run confirms it: 595 mutants, 450 killed, and no survivor left in any of
`_credential_data`, `_credential_lines`, `_configuration_data` or `_configuration_lines`.

## Quality gates

- Baseline before CP-16: `make quality` green (3,237 tests, 1 skipped, 85.32% branch coverage) and
  `make integration` green (273 E2E tests) at `33054a0`.
- Step 1 focused: six Doctor E2E tests green; nearby consumer navigation/shell tests and typecheck
  were green before the final receipt-refusal addition. Fresh scoped mutation run: 132 total, 104
  killed, 28 survivors, none untested.
- Step 1 full gates: `make quality` green -- all nine gates, 3,243 tests, 1 skipped, 85.34% branch
  coverage -- and `make integration` separately green with 279 E2E tests.
- Step 2 focused: eight offline-readiness E2E tests and all 24 tests in the four nearest suites are
  green; ruff, mypy over 255 source files, repository validation and diff checks are green. Scoped
  mutation: application projection 30/30 killed; I/O observation 73/76 killed with three reviewed
  survivors.
- Step 2 full gates: `make quality` green -- all nine gates, 3,251 tests, 1 skipped, 85.37% branch
  coverage -- and `make integration` separately green with 287 E2E tests.
- Step 3 focused: eight repair E2E tests (ten including subtests) green; five targeted mutations each red only where claimed.
- Step 3 full gates: the first run failed on `source_remediation_test`'s repository-wide rule that every command string the package shows an operator must be one the parser accepts. The no-match remediation read `run aart doctor and choose one exact installed coordinate`, and the scanner's bare-command pattern runs to the first comma or semicolon, so it extracted the whole sentence as the command. Reworded to `run aart doctor, then pass one exact installed coordinate to --repair`, which leaves `aart doctor` as the runnable part. Worth recording because no focused run could have caught it: the rule lives in a test that scans every module, and the eight repair E2E tests were green throughout.
- Step 3 verified: `make quality` green across all nine gates -- 3,259 tests, 1 skipped, 85.37%
  branch coverage -- with the integration gate skipped as redundant because all 295 of its tests
  are among the 3,259 the unit gate runs.
- Step 4a focused: seven orphaned-run E2E tests green; seven targeted mutations each red only
  where claimed; ruff, format and mypy green over the four changed files. Fresh scoped
  mutation: 43 mutants, 40 killed, three reviewed survivors (two on an unexecuted guard, one
  equivalent under the run directory's naming).
- Step 4c verified: `make quality` green across all nine gates -- 3,281 tests, 1 skipped, 85.38%
  branch coverage -- with the integration gate skipped as redundant because all of its tests are
  among the 3,281 the unit gate runs.
- Step 4c focused: ten configuration/credential tests green; nine targeted mutations each red only
  where claimed. The scoped run over the whole command module with all six Doctor test files first
  refused to start -- its baseline caught the step-2 collision described above -- and then produced
  595 mutants at 421 killed, with 29 survivors inside this step's four functions. All 29 are now
  closed and re-verified by a fresh run: 595 mutants, 450 killed, and no survivor in
  `_credential_data`, `_credential_lines`, `_configuration_data` or `_configuration_lines`. The
  remaining 145 are B-060's 84 in `_run_repair` and 47 in `run` itself, recorded as B-061.
- Step 4b focused: five activity E2E tests green, all five RED against the previous commit;
  nine targeted mutations each red only where claimed. Scoped mutation over the whole command
  module with all four Doctor test files: 499 mutants, 354 killed; three real gaps inside this
  step's functions were found and closed, six string-spelling survivors recorded, and 84
  survivors in step 3's `_run_repair` handed to B-060.

## Remaining

Step 5. Step 4 is complete: the orphaned-run root (4a), the Activity trail with each action's own
undo answer (4b), and the disabled-source, policy-locked-field and credential diagnostics (4c) are
all reachable from the global report. What remains is the slice-closing evidence pass -- every
declared invariant traced to a public surface, with the full quality suite green.

## Known compromises

- The current canonical inspection does not calculate Marketplace update availability, so Doctor
  reports installed health and machine drift without an update offer.
- Credential state is observable only where the platform provider exists, so the report's
  credential section is empty on a machine with no provider rather than reporting that it could not
  look. Distinguishing those is not in this slice.
- Two step-4c claims are held at the seam rather than through the verb, for the reasons recorded in
  that step: driving a populated credential list through the CLI would write to the developer's real
  Keychain, and installing an organization policy would require writing to a root-owned system path.

## Backlog discoveries

- B-058: scoped mutmut results can remain stale after test-only changes.
- B-059: Doctor's exactly-one-match repair guard is defensive code of unproven reachability.
- B-060: step 3's `_run_repair` has 84 surviving mutants under a scoped run it never had.
- B-061: Doctor's `run` composition has 47 surviving mutants under the step-4c scoped run.
- B-062: a machine with no credential provider reports no credentials rather than saying it could
  not look.

## Blockers

None for step 5.

## Legacy removal criteria

This slice adds a public support surface; it authorizes no legacy deletion by itself.

## Handoff

- Current working state: steps 1, 2, 3 and 4 (4a, 4b, 4c) are VERIFIED; CP-16 remains IN PROGRESS
  with step 5 outstanding.
- Exact next action: step 5 -- walk every invariant this slice declares and show the public surface
  that holds it, then run the full quality suite on a clean tree and close the slice.
- Do not undo: one observed installation set feeds both `project_doctor` and
  `prepare_configured_repair`; offline readiness reuses the installation package verifier but stops
  before object publication; Doctor mutates nothing unless
  `--repair --yes --expect` are all present, and the lifecycle adapter, not the command, is what
  re-observes the machine under its lease before any effect runs.
- Tests last run/results: `make quality` -- 3,251 green, 1 skipped, 85.37%; `make integration` --
  287 green.
- Failure evidence: the report's absence was the initial RED; payload, dependency, cold-metadata,
  source-loop and artifact-loop mutations each turn their named E2E assertion RED.
