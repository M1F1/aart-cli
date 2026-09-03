# CP-15 — Accepted lifecycle/edge-case hardening 54–100
Status: IN PROGRESS (opened 2026-09-03)

## Goal

Take the accepted lifecycle edge cases of Product Specification sections 165.1–165.28 from
"the machinery holds it somewhere" to "the public surface holds it, measured". Every invariant
listed below is currently PARTIAL in `INVARIANT_TRACEABILITY.md` with the same three words in its
evidence column — *scattered source/registry/lifecycle safeguards* — and that phrase is the slice's
whole subject. A safeguard at a seam is worth what the verb an operator actually runs makes of it.

## Product Specification sections/invariants

Sections 165.1–165.28. Sixteen invariants are marked PARTIAL against CP-15: INV-210, 216, 218, 219,
221, 222, 223, 226, 231, 232, 233, 237, 238, 240, 241, 242.

Load-bearing statements:

- "Marketplace may continue using the last known valid local snapshot." (165.11)
- "Offline installability is decomposed into separate capabilities: metadata cached / canonical
  payload cached / runtime dependencies cached." (165.11, INV-223)
- "Registry changes may trigger health/policy findings, but installation mutations still require
  explicit reconciliation plans and applicable policy." (INV-210)
- "Validation gates activation of newly synchronized registry snapshots." (INV-218)
- "Successful effects followed by failed verification are not reported as clean success." (165.12)
- "AART does not claim transaction atomicity beyond actual effect guarantees." (165.13, INV-225)
- "Normal registry lifecycle uses deprecation, revocation and hiding from new installs rather than
  physical deletion." (165.10, INV-221)
- "Removing the current payload does not guarantee removal from Git history." (165.10, INV-222)

## Method

The same one CP-13 and CP-14 ended on, and the one D-091 states: a claim is not held until a public
flow proves it, and a test is not evidence until a real mutation of the code it names turns it red.
Each increment below therefore (a) names the verb an operator runs, (b) drives it over a real
temporary machine, and (c) records which mutation it was proven against.

## Scenario map at slice start

| Accepted scenario | Invariant | Evidence that existed | Gap |
|---|---|---|---|
| Source publishes an invalid revision | INV-218 | `source_store_adapter_test` (corrupt convergent snapshot never becomes current); `source_sync_application_test` (validation failure publishes nothing) | Both drive the seam. Nothing drove `aart source sync`. **Closed by increment 1.** |
| Registry change must not silently mutate installations | INV-210 | `canonical_lifecycle_test` covers a source that is missing, disabled or has moved origin | The state a refused sync actually leaves — `could-not-check` — was untested, and was being read as "source gone". **Closed by increment 1 (D-132).** |
| Registry unavailable / offline | INV-223, 165.11 | `--offline` installs from cached objects | Online-but-unreachable was a hard failure with an internal message. **Closed by increment 1 (D-132).** The three-way decomposition is **held and measured by increment 3**; what remains is *reporting* it before an install is attempted (B-051). |
| Registry rollback preserves history | INV-216 | promotion audit chain walks backwards from the approved snapshot (D-104) | **Closed for the consumer half by increment 2.** The Git revert/commit half waits on CP-17 |
| Provenance is not rewritten when upstream moves | INV-219 | typed Git/local audit pins (D-107) | **Closed by increment 2**, on both sides: the installation record, and the promotion audit under D-089's rebinding |
| Physical purge is exceptional | INV-221, INV-222 | none found: no test file matches `purge` | **Closed by increment 5.** No purge verb exists at all; what needed measuring was the ordinary withdrawal, and the erasure sentence 165.10 requires was missing (D-135) |
| Interrupted operations re-inspect before resume | INV-226 | CP-12 executor replans under lease; `receipt verify` carries a `no-orphan-run-directory` claim (`LAF-61`) | **Closed by increment 4b**, over a working copy the engine really failed to remove |
| Input/credential contract changes | INV-231, INV-232 | CP-08 credential lifecycle | No test that changing one artifact's contract leaves another's credential owned |
| Policy drift contributes to health | INV-233 | `EffectivePolicy` is read at validation time (D-099) | **Closed by increment 6** (D-136). The live policy is `OrganizationPolicy`; the domain `EffectivePolicy` never reaches the consumer path at all (B-056) |
| Development installs are visibly distinct | INV-237 | none found | **Closed by increment 6.** `marketplace list` always showed `trust`; what is *installed* did not |
| Promotion evidence, audit, Git authority, publication | INV-238, 240, 241, 242 | D-103–D-107 promotion records and local-commit boundary | **Closed by increment 7**, which changed no production code: the boundary was already right and nothing said so from the consumer's side. The Git hop stays with CP-17 |
| Exact collection drift | 165.x | none found: no test file matches `collection.*drift` | Waits on the Collection capability B-038 is sequenced behind (D-131) |
| Manual drift | INV-228 | canonical drift detection exists | No test file matches `manual.*drift` |

## Implementation steps

1. **DONE:** Registry state safety through the public source verb (INV-218, INV-210, 165.11).
2. **DONE:** Rollback and provenance under a moving upstream (INV-216, INV-219; INV-229 was already EVIDENCED by D-094).
3. **DONE:** Offline decomposition: metadata, payload and runtime dependencies as separate
   capabilities (INV-223).
4. Split when it was opened, because the two halves have different subjects.
   - **4a DONE:** verification failure and the compensatable restore (INV-224, INV-225;
     165.12, 165.13).
   - **4b DONE:** interrupted execution -- discoverable, and re-inspected before resume
     (INV-226; 165.14).
5. **DONE:** Purge boundaries and the erasure claim AART must not make (INV-221, INV-222).
6. **DONE:** Policy drift in installed health, and development installs kept visibly distinct
   (INV-233, INV-237).
7. **DONE:** Promotion evidence, audit and the local-promotion-is-not-publication boundary
   (INV-238, 240, 241, 242).
8. Input and credential contract migrations, and unrelated credential ownership
   (INV-231, INV-232) — the last two invariants in this slice's declared scope. The scenario map
   row has stood open since slice start: no test shows that changing one artifact's contract leaves
   another artifact's credential owned.

## Blockers

Exact-collection drift waits on the Collection capability that B-038 is sequenced behind (D-131).
Nothing else is blocked at slice start.

## Completed increments

### Step 1 — registry state safety through `aart source sync` (D-132)

`tests/source_sync_command_e2e_test.py` is the first thing anywhere to drive `aart source sync`
over a real source that turned invalid under it. The upstream publishes a new revision *and* an
`aart-registry.json` that does not parse, which is the `RS-08` refusal a real publisher can cause;
both halves are deliberate, because an invalid revision carrying the good bytes would pass every
assertion even if it had replaced the store.

What the eight tests hold:

- the refusal is per-source in the JSON payload and exits non-zero, and the human rendering carries
  the remediation rather than only the complaint;
- the store still points at the last good snapshot and `aart marketplace list` still offers every
  artifact of it, digest for digest;
- the source stops claiming to be healthy: `could-not-check` with a named `source-invalid`
  diagnostic, degraded rather than withdrawn;
- an installation made from the good snapshot is byte-identical, its recorded state is unchanged,
  and it still reports `current`;
- installing after the refused sync places the *accepted* revision's bytes, and updating is a no-op
  rather than a refusal;
- a repaired upstream publishes and the pointer moves, so the refusal was about the content rather
  than `sync` being inert.

Writing them found the defect D-132 records: `could-not-check` — which is exactly what the explicit
last-known-good fallback `SyncDisposition.RETAINED` produces — was read as "this source is gone" in
three places, so one invalid upstream revision made `aart marketplace status` report every
installation as `source-unavailable` and made `install` and `update` fail on a plan-construction
invariant with no remediation on it. Product Specification 165.11 settles it, and both sets now
admit it.

The two seams carry their own claims: `canonical_lifecycle_test` for reconciliation, and
`canonical_install_planning_test` for the plan invariant. Both were written red first.

Proven against a mutation: removing the `RS-08` refusal in `sources/validation.py` — so the invalid
revision publishes — turns all eight end-to-end tests red.

### Step 2 — what a moving upstream may and may not rewrite (INV-219, INV-216, INV-210)

`tests/source_upstream_movement_e2e_test.py` republishes into a real local source and asks the
public verbs what changed. Four claims:

- a sync that publishes a new revision leaves the installation record identical in every field, not
  just in its revision;
- the new revision is *offered* -- `status` says `update-available` and the file on disk is still
  the reviewed one -- because a registry change raises a finding and mutating an installation needs
  a plan (INV-210);
- an explicit `update` is what rebinds the record and places the new bytes, so the record is not
  frozen, it is only not rewritten behind the operator;
- an upstream rolled back to its first revision is new work rather than an erased event (INV-216).

The rollback case is the one worth reading twice. A snapshot is identified by its content, so
republishing the first revision's bytes republishes the first revision's *digest*: the store looks
exactly as it did before the second revision ever existed. Reconciliation that compared the store
against itself would call the installation current and quietly leave the superseded payload in the
project. It compares against the record, which is why the rollback is offered and then applied.

On the registry side, `promotion_planning_test::test_a_second_promotion_rewrites_one_field_and_no
_provenance` closes the other half. D-089's rebinding is the one place this codebase writes over an
already-approved record, and the sibling test beside it only proved the *package* does not move.
The new one proves the two documents that say where the package came from do not either: the
promotion audit comes back byte-identical -- byte equality on purpose, because a named-field
comparison cannot see a field being added, dropped or re-derived -- and the version record differs
in `registry_snapshot` and nothing else.

Proven against mutations: forcing `check_installations` to decide on version alone turns two of the
four end-to-end tests red; making the rebinding re-derive one further field of a retained record
turns the promotion test red, and it is the only one of that file's sixteen tests that catches it.
The first end-to-end test is a guard rather than a regression -- nothing on the sync path writes
install state today -- and its docstring says so, resting its non-vacuousness on the sibling that
changes the same fields through the same comparison.

### Step 3 — offline installability is three capabilities, not one flag (INV-223)

Product Specification 165.11 decomposes offline installability into *metadata cached*, *canonical
payload cached* and *runtime dependencies cached*, and says outright that a locally available
payload does not imply that package-manager dependencies can be installed offline. `--offline` is
one boolean, so the question this step had to answer is whether the three collapse into it.

They do not. `tests/offline_capability_test.py` pins each layer where it lives and, more to the
point, pins that they stay distinguishable from each other:

- a source whose metadata was never synchronized refuses by naming the *cache* -- `aart source
  sync` as the way forward -- rather than the artifact, because an artifact that was never offered
  cannot be the thing at fault;
- a cached-metadata, uncached-object install is a different refusal under a different code, and the
  words "while offline" are what separate it from the same object being missing while connected;
- the dependency installer is denied an index (`pip --no-index`, `uv --offline`) exactly when
  offline is asked for, in both backends, and that flag is the *only* difference between the
  connected and offline argument vectors -- so the test fails both if the flag disappears and if
  anything else moves with it;
- the three codes are asserted pairwise distinct, which is the invariant's actual prohibition:
  conflating them is what makes an operator re-sync a source to fix a missing wheel.

Layers 1 and 2 collapse *for a local source* -- the object store has nothing in it before the first
install, and the object is published from the cached snapshot during it -- so layer 2 is measured at
the planning seam rather than end to end. That is a property of the fixture, not of the code, and
the seam is where the refusal is constructed.

Proven against three separate mutations, one per layer: emptying `flags` in both branches of
`io/python_runtime.py::_install_argv` turns three of the four red; replacing `if offline:` with
`if False:` in `marketplace/catalog.py::_resolution_failure` turns one red; dropping the
`" while offline"` suffix in `installation/application.py` turns a different one red. Before this
step the dependency layer had no test at all -- `python_environment_integration_test` runs real
offline installs and would have stayed green with the flag removed, silently reaching the network
on every `--offline` install.

What is not closed: nothing *reports* the three capabilities before an install is attempted, which
is the reading 165.11 shows. Recorded as B-051 for CP-16, where `aart doctor` is the surface that
would carry it; INV-223 stays PARTIAL against it.

### Step 4a — effects that applied, then a verification that failed (INV-224, D-133)

`tests/verification_failure_e2e_test.py` runs a declared setup whose recipe writes one managed
block and then runs one command that exits non-zero. Both halves are chosen: the block is
compensatable, so 165.13's *"if all applied effects are safely compensatable, the previous state may
be restored"* is the branch taken and the file's absence afterwards is what proves the restore ran;
the failing command is `/usr/bin/false`, which needs no network, no tool and no secret, so nothing
about the machine can explain the failure except that verification failed. The payload is installed
first and separately, which is the shape 165.12 describes -- *"github-mcp was installed, but
verification failed"* -- and `marketplace status` afterwards still reports it `current`, so a failed
check on one transaction does not un-install what another already placed.

165.12 makes two claims and they came apart. The report half already held: `aart marketplace setup`
exits non-zero, `ok` is false, the item is `verification-failed` -- its own word, not
`apply-failed-rolled-back` and not `cancelled`, because an operator told the wrong one repairs the
wrong thing -- the counts read `configured=0, incomplete=1`, and the human rendering carries the
artifact and the retry rather than only a count.

The evidence half did not. The receipt recorded the verification result and the final health and
recorded *no applied effects at all*: `steps` was empty, because `_apply_effects` dropped the
receipt list whenever the rollback succeeded. So `receipt show` said a check had failed while saying
nothing about what had already been done to the machine before it did. D-133 fixes it by keeping the
steps and marking them `setup_disposition: "compensated"` -- the word the persistence-failure path
in `setup_engine/application.py` already writes, which all three readers already honour -- and by
deciding `rollback_command` from the steps still standing, so a fully compensated record offers no
undo to run.

Proven against mutations: the two evidence tests were red against the shipped code before the fix
and the four report tests were green, which is the split above measured rather than asserted;
reverting `standing` to `receipts` in `_record` turns the undo claim red on its own, and only that
one.

### Step 4b — the working copy a stopped run leaves, and what a retry does with it (INV-226)

`tests/interrupted_execution_e2e_test.py` reads 165.13 and 165.14 as one scenario at two moments.
The recipe carries a real custom entrypoint -- a shell script following the plan/apply/verify/
rollback protocol -- whose `apply` phase exits non-zero and whose `rollback` phase then also exits
non-zero. That is the one path that raises without removing its run directory, so the working copy
these tests assert on is one the engine really created and really failed to clean up. Patching the
cleanup away would have produced the same directory and proved nothing about *when* a directory is
actually left. It also had to be this route: a run directory is opened only by `custom.install@1`
and `docker.build@1`, so the managed-block recipe of step 4a can leave no orphan at all and the
`no-orphan-run-directory` claim answers `true` about a directory that was never made -- which is how
the first attempt at this step measured nothing.

Six claims:

- a failure whose compensation also failed is `rollback-incomplete` and not
  `apply-failed-rolled-back`, and it carries a recovery line. Those are two different promises about
  the machine, and an operator told the restoring one when the other is true stops looking (165.13);
- the working copy is still there afterwards;
- `aart marketplace receipt verify` finds it, exits non-zero, and names *the directory the engine
  actually created* -- asserted by identity, and cross-checked against the record's own plan hash;
- verify reports it and leaves it exactly where it is (`LAF-61`), because inspection that deletes
  its own evidence is worse than no inspection;
- the receipt reads back as JSON;
- a retry re-plans rather than resuming: the second run's review digest differs from the first
  because the plan binds the record the first run persisted, the protocol starts again from its
  first phase, and both working copies are then reported rather than the second hiding the first.

The JSON claim is there because writing this file found the defect. A parsed record's steps are
frozen recursively into `MappingProxyType` and the receipt projection copied each step shallowly, so
every nested object stayed a proxy and `json.dumps` refused it — `aart marketplace receipt show
--json` ended in a `TypeError` traceback for exactly the run whose evidence is hardest to
reconstruct by hand. `setup.py`'s `_plain` was already the inverse of `_freeze`; it is now public as
`plain_value` and the projection uses it.

Proven against three mutations, one per group: pointing the probe's run root at the project root
instead of the data root -- which is precisely the `LAF-66` defect class, at the one seam
`setup_verify_test` cannot reach -- turns two red; restoring the shallow `dict(step)` projection
turns two red; and calling an incomplete rollback a completed one turns two red. A fourth attempt,
removing the run directory on the failing path, killed nothing and is worth recording: the outer
`_rollback_all` re-creates it when it writes the receipt its own compensation attempt needs, so that
directory is the one the tests see. The claim that verify does not delete the evidence has no
available mutation -- nothing in the code deletes it -- and rests on its siblings, which move the
same directory through the same reader.

### Step 5 — what a withdrawal does, and the erasure claim AART must not make (INV-221, INV-222)

`tests/withdrawal_and_purge_e2e_test.py`. Product Specification 165.10 makes two statements that
pull in opposite directions, so the file has two halves and they were measured separately.

**The first half is characterization and it passed on shipped code.** There is no `purge` verb
anywhere in `agent_artifacts` — the word does not appear — and the registry lifecycle offers only
`deprecate_registry_version` and `revoke_registry_version`, both of which `replace()` state and
delete nothing. So "physical purge is exceptional" is held in the strongest available form, and what
needed measuring was the *ordinary* path: what a real upstream withdrawal does to a real machine.

The upstream deletes the artifact and re-points its Collection at the one that remains, which is what
a maintainer withdrawing one artifact would actually publish; the withdrawal has to be coherent to
be measured at all, because deleting the artifact alone leaves the graph invalid and emptying the
Collection is refused for its own reason, and both refusals arrive before any of these questions is
reached. Then `aart source sync`, and five claims:

- the artifact stops being offered by `aart marketplace list`, and the source keeps serving the rest;
- installing it is refused as `artifact-not-found` with a remediation on it, rather than as a crash;
- **what is already installed is not touched** — the placed files are byte-identical and
  `aart marketplace status` says `removed-upstream`, which is the honest word: not `current`, and
  not `broken`. A registry that could uninstall by publishing would be a registry that reaches into
  a project without a plan, which is the boundary INV-210 draws;
- the payload bytes stay in the content-addressed object store, which is what keeps that
  installation whole;
- and `aart marketplace uninstall` still works, because not-deleting must not become
  not-removable — withdrawal cannot be a way to pin something on a machine permanently. This one is
  held by a deliberate special case: uninstall resolves against the manifest and never through the
  source, with `commands/marketplace.py` saying so in its own comment.

**The second half was red, and 165.10 is why.** The one place AART tells anyone a credential is
sitting in artifact content is the `embedded-credential` baseline finding, and its remediation read
*"Remove the value, rotate it if real, and use runtime credential indirection."* That names rotation
and, by saying "remove" with no caveat, implies removing is what finishes the job. Artifact content
is published from a version-controlled source: removing the literal changes what is current and
leaves the object reachable in history. The sentence now says so, and names the repository's own
secret-removal procedure as still owed. Asserted over a real scan rather than over the rule table,
because the rule table is not what anybody reads — the finding on an assessment is, and
`tui_marketplace` renders its remediation verbatim under `remediation`.

The ruleset revision label stays `baseline-v1.1` (D-135): the remediation is inside
`BASELINE_RULES_DIGEST`, so recorded evidence goes stale on its own, and bumping the label would
signal a detection change to the published compatibility documents that did not happen.

Proven against six mutations, each killing the claims it should and no others: reverting the
remediation turns the two erasure tests red; reporting `REMOVED_UPSTREAM` as `CURRENT` turns the
status test red; dropping the artifact half of `_current_item`'s coordinate match turns it red the
other way; making `sync` keep the snapshot it already has turns three red (offered, refused,
status); purging the object store on sync turns the retention test red; and making uninstall resolve
through the catalog like every other verb turns the uninstall test red — one test each, which is
what says the special case is load-bearing.

Two findings worth recording. The object-store mutation **survived** on the first attempt and the
reason is a product property, not a weak test: the content-addressed store is written read-only, so
a plain `shutil.rmtree(..., ignore_errors=True)` deletes nothing and reports nothing. The mutation
had to `chmod` first to be a mutation at all. And the claim that the finding does not echo the
credential it reports has no available mutation — the remediation is a static string that never sees
the matched value — so it is a guard held by construction rather than evidence, and is recorded as
such.

B-055 records the unreachable `ArtifactLifecycle.REMOVED` merge path found while writing this.

`make mutants ONLY=agent_artifacts/security/baseline.py` was run over this module with the three
test files nearest it, per D-134: 1218 mutants, 335 survivors. The count means nothing on its own
(B-054), but one survivor did. Replacing the assignment-detector's result with `None` —

```python
        if not detected:
            detected = None       # was: any(not _placeholder(m.group(2)) for m in ...)
```

— changed nothing anywhere. `_SECRET_PREFIX` recognises the vendors whose tokens have a shape, and
every fixture in the suite happened to carry one, so the rule that catches *everything else* — a
long value next to a key named `password`, `secret`, `token`, `api_key` — was never the thing that
decided. `security_baseline_test` gained the case that isolates it, in prose rather than JSON,
because `_json_findings` raises the same rule for a credential member and a `.json` fixture passes
with the assignment branch deleted outright. That test is the mutant's only killer. The remaining
survivors are outside this slice's claims and stay under B-054.

### Step 6 — the policy in force, and where an installation's content came from (INV-233, INV-237)

`tests/policy_drift_e2e_test.py`. Two Product Specification sections, one fact about one
installation, which is why they are one increment. 165.21 says health includes effective policy
compliance and that drift produces a decision rather than a silent mutation; 165.23 says a
development install is clearly marked and keeps being surfaced afterwards. What both turn on is the
*trust* an artifact is installed at, and what the machine's policy says about that trust now.

Two of the eight claims passed on shipped code and they are the ones that matter as premises: a
policy that tightens after the fact changes nothing on disk, and `aart marketplace install` really
does refuse the same artifact under the new rule (`install-policy-denied`). Six were red. `aart
marketplace status` reported `current` and nothing else — not that the artifact would be refused
today, not the reason, and not that its content came from a mutable directory on somebody's disk
rather than a reviewed registry. `marketplace list` has shown `trust` since the marketplace existed;
the verb that says what a project is *running* did not.

The shape follows `setup_status`, which is already an orthogonal dimension carried beside `status`
rather than folded into it — an installation can be simultaneously out of date and no longer
compliant, and one status string cannot say both. So `LifecycleItem` gains a `PolicyStanding`
(status, detail, trust) and `ConsumerTerminalItem` gains the three flattened fields it serializes.

The compliance rule itself is not new code. `installation/application.py`'s user-scope trust check
became the public `trust_shortfall`, and `lifecycle` asks *that function*: health computed by a rule
slightly different from the gate's would be worse than no health, because an operator told an
artifact complies by a near-miss rule has been told something false in the most expensive way.

`not-evaluated` is the third value and it is not a pass. An artifact its source withdrew has no
current trust to judge, and calling that compliant would assert a measurement nobody took — the same
reasoning `InstalledHealth.UNKNOWN` already carries.

Proven against six mutations. Making the policy refuse nothing turns four red; calling everything
measurable compliant turns three; assuming the trust instead of reading it turns four; dropping the
human-rendering warning turns exactly one; and dropping the upstream standing where the merged
status is assembled turns five, which is what says the carry-through is load-bearing rather than
incidental.

The seventh mutation is the interesting one. Reporting an unmeasurable trust as compliant **killed
nothing**, and the reason was a real defect in the change: `_standing` had a `current is None`
branch that no caller could reach, because every path where the record resolves to nothing
`continue`s out of the loop earlier. The claim was being held by `LifecycleItem`'s default, not by
the code that looked like it held it. The unreachable branch is gone and the default is now what the
docstring points at — and mutating *that* default to a pass turns exactly the one test red.

`make mutants ONLY=agent_artifacts/lifecycle/application.py` then found one more, and it was inside
this slice's own new code: dropping the standing on the *other* branch of the merge -- the one taken
when the local installation is itself damaged -- killed nothing, because every test here had a
healthy payload. That is precisely the case D-136 exists for: a payload edited under AART's feet
owns the status, the policy question is about the artifact's origin and is answered the same either
way, and an operator deciding whether to repair or remove needs both halves at once. The ninth test
drives it, and it is the mutant's only killer. The other survivors in that module are outside this
slice and stay under B-054.

The remaining unproven claim is honest to state: that asking about compliance changes nothing on
disk has no available mutation, because nothing in the code mutates there. It rests on its
siblings, which drive the same verb over the same machine.

### Step 7 — promotion evidence, and the boundary a maintainer would assume the other way (INV-238, 240, 241, 242)

`tests/promotion_publication_boundary_e2e_test.py`. 165.27 splits the authority: AART owns artifact
and registry validation and preparation, and existing Git hosting owns branch protection, review and
merge authorization. 165.28 names what follows — a local promotion or commit is not yet Published;
publication is presence on the canonical consumer-visible branch, which a person or CI puts it there
by pushing and merging.

Every claim in this file passed on shipped code, and that is the finding rather than a
disappointment: D-103–D-107 built the promotion records and the local-commit boundary correctly, and
what was missing was any test that said so **from the consumer's side**. This increment changes no
production code. It is the one increment in CP-15 whose value is entirely in what it would catch
later, because the failure it guards against — a promotion quietly becoming visible to consumers —
is invisible in the maintainer's own terminal, where everything looks like it worked.

The arrangement is the point. A maintainer's writable registry checkout and the published registry a
consumer is subscribed to are **two directories**, because in production they are two states of one
repository separated by a push and a merge. An earlier draft promoted straight into the consumer's
source and got the right answer for the wrong reason: the consumer stopped seeing anything because
`registry promote` writes a versioned layout into a tree the source validator then rejects
(`artifact-invalid`, B-057), so "not published" was indistinguishable from "broken". A test that
measures a workflow nobody runs is worse than no test.

Nine claims, each proven against a mutation:

| Mutation | Turns red |
|---|---|
| The promoted-local payload reports `commit`/`push` as true | the payload claim, only |
| `promote --yes` also runs `git add -A` and `git commit` | the Git-authority claim, only |
| A simulated push: the promoted tree copied into the published registry | the three consumer claims, and only those |
| The review branch applies instead of reviewing | the dry-run claim, only |
| `--validation-report` made optional | the evidence claim |
| `--policy-result` made optional | the evidence claim |
| The two evidence digests written into each other's slot | the audit-record claim |
| `registry_snapshot_before` recorded as the after-snapshot | the audit-record claim |
| Provenance records a literal `HEAD` instead of the revision | the audit-record claim |
| The applied payload reports the snapshot it started from | the transaction-chain claim |

Two of those mutations found gaps in my own tests before they found anything else, which is the
whole reason for running them.

The evidence test first omitted **both** digests at once. Making either one optional on its own
survived it: the other was still required, so the CLI still refused, and a test named "promotion
without its evidence is refused" would have kept passing with half the requirement deleted. It now
asserts each digest independently, and — this mattered too — in its own workshop, because the first
subtest's refusal was measured against a checkout the second subtest had already promoted into.

The install-refusal test was resting on a stale snapshot rather than on the boundary. It refused
because the consumer had not re-synchronized, not because the promotion was unpublished, and the
simulated-push mutation left it green. It now synchronizes first, so the refusal it asserts is the
one 165.28 promises.

`make mutants ONLY=agent_artifacts/application/promotion.py TESTS=<this file>` was run per D-134:
1604 mutants, 388 killed, 842 skipped as uncovered, 374 survived. Read that figure for what it is —
the run was scoped to *these nine tests alone*, so a survivor means "these nine do not hold it", not
"nothing holds it", and nine end-to-end tests are not meant to hold a 1600-mutant module. The
survivors nearest this increment's claims are in `promotion_source_provenance`'s `local:` branch and
its rejection path, which a Git-revision fixture never reaches; the audit record's own fields are
held, which is what the three record mutations above measure directly. The rest stay under B-054.

**What stays with CP-17:** the Git hop itself. No test in this repository has a Git host to push to,
and `git_location_parts` admits no `file://` remote, so branch protection, pull requests and the
merge that constitutes publication cannot be driven here. This file proves the property that makes
the hop *necessary* — AART leaves the checkout with nothing committed, no branch and no remote, and
the consumer's view does not move — rather than the hop's outcome.
