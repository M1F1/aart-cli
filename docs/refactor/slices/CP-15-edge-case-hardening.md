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
| Physical purge is exceptional | INV-221, INV-222 | none found: no test file matches `purge` | Whole scenario unmeasured |
| Interrupted operations re-inspect before resume | INV-226 | CP-12 executor replans under lease; `receipt verify` carries a `no-orphan-run-directory` claim (`LAF-61`) | No public-flow interruption test. **Step 4b.** |
| Input/credential contract changes | INV-231, INV-232 | CP-08 credential lifecycle | No test that changing one artifact's contract leaves another's credential owned |
| Policy drift contributes to health | INV-233 | `EffectivePolicy` is read at validation time (D-099) | Installed-artifact health does not consult current policy |
| Development installs are visibly distinct | INV-237 | none found | Whole scenario unmeasured |
| Promotion evidence, audit, Git authority, publication | INV-238, 240, 241, 242 | D-103–D-107 promotion records and local-commit boundary | No test that *local promotion is not publication* from the consumer side |
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
   - **4b:** interrupted execution -- discoverable, and re-inspected before resume
     (INV-226; 165.14).
5. Purge boundaries and the erasure claim AART must not make (INV-221, INV-222).
6. Policy drift in installed health, and development installs kept visibly distinct
   (INV-233, INV-237).
7. Promotion evidence, audit and the local-promotion-is-not-publication boundary
   (INV-238, 240, 241, 242).

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
