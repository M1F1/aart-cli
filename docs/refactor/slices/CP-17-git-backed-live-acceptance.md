# CP-17 — Git-backed live acceptance
Status: IN PROGRESS (opened 2026-09-03)

## Goal

Prove the whole chain as one continuous flow over a realistic temporary Git source repository:
source change -> candidate -> validation -> promotion/vendoring -> registry snapshot -> consumer
sync -> marketplace -> collection/bulk install -> MCP start -> receipt -> update -> drift/repair ->
rollback/uninstall.

Acceptance tests assert public contracts, not module layout.

## Product Specification sections/invariants

Identified per increment. The slice adds no new behavior; it asserts the behavior already accepted
by CP-02 through CP-16 survives being connected end to end. Step 1 begins INV-112 and INV-115: the
fixture is an ordinary repository with real commits, and the first cross-boundary value is Git's
actual output rather than a reconstructed candidate.

## What is already covered, and what this slice is actually for

The survey matters more here than in any previous slice, because the honest answer is that **every
stage of the chain already has end-to-end coverage somewhere**, and a slice that re-proved them one
at a time would be busywork dressed as acceptance.

- A real Git repository is really cloned. `git_source_adapter_test.py::test_system_git_updates_bare_mirror_and_resolves_branch_and_tag`
  runs the system `git` binary against a repository it builds, updates a bare mirror, and resolves a
  branch and a tag.
- A real MCP server is really launched. `mcp_stdio_e2e_test` creates a real virtual environment,
  writes a real launcher, merges a real harness settings file, and executes the recorded command as
  a subprocess speaking newline-delimited JSON-RPC over stdio, with almost no inherited environment.
- Source sync, promotion boundaries, marketplace install, collection membership, update, drift,
  repair, uninstall and purge each have their own E2E file, 46 of them in total.

**What nothing does is join them.** Every consumer-side E2E fixture publishes its snapshot directly
into the source store, and the commit it records is `"a" * 40` -- a literal placeholder. The seam
between what `acquire_git_snapshot` actually produces and what `publish_source_snapshot` consumes is
never exercised with real Git output; each stage is proven against a precondition a test synthesized
for it rather than against the artifact the previous stage really emits.

That is the same argument CP-15 made one invariant at a time -- a safeguard at a seam is worth what
the verb an operator runs makes of it -- raised to the scale of the whole chain: a stage proven
against a hand-built precondition is worth what the chain makes of it. `"a" * 40` is the tell.

## The transport constraint, established before writing anything

`aart source sync` cannot clone a local repository, and that is deliberate.
`application/sources.py:285` builds its `GitSnapshotRequest` without `allow_local_transport`, so the
default `False` stands, and `sources/git.py::_allowed_location` then requires
`git_location_parts` to accept the location -- `https://` or `ssh://` or SCP-style, with a real
hostname, no password, no query and no fragment. `file://` and absolute paths are refused. Nothing
in the package ever passes `allow_local_transport=True`: `curation/runtime.py` threads the flag
through but its only caller hard-codes `False`. The flag exists for the adapter's own tests.

So a hermetic test cannot drive a real `git clone` through the public sync verb. Reaching around it
-- patching the flag, or widening the allowlist for tests -- would be weakening a security boundary
to make a test pass, which the execution contract forbids outright.

### The second boundary, found before designing step 2

The transport allowlist is not the only refusal, and the other one is stricter. A configured source
must survive `parse_user_configuration`, and that parser calls `git_location_parts` on every
non-local source's location. Measured directly:

    'file:///tmp/repo.git'                          -> None
    '/tmp/repo.git'                                 -> None
    'https://company.example/agents/company.git'    -> ('company.example', 'agents/company')

So a consumer machine cannot even be *configured* with a local Git source. The refusal sits in the
configuration schema, before any transport decision is reached, which means step 2 cannot be written
the way step 1 is: step 1 hands a request straight to the adapter and may name a local location,
while step 2 must go through a real user configuration file and therefore must name a real hostname.

This is what fixes step 2's shape, and it is a better shape than step 1's. A source's identity --
the `source_instance_id` the store is keyed by -- is derived from its configured location, so the
configured location must be the real remote one for the consumer to find what the sync published.
The substitution therefore belongs at the transport, not at the identity: the port receives the
genuine `GitSnapshotRequest` for `https://...`, and clones a real local repository in place of
reaching the network. Configuration parsing, source identity, snapshot publication and every
consumer stage downstream then run unmodified against real Git output. Only the network is stood in
for, which is what a port is for -- as distinct from patching the allowlist, which would stand in
for the security decision itself.

The consequence is that CP-17's chain has one seam it must join from the adapter side rather than
through the verb, and that is recorded here the way CP-15 step 8 and CP-16 step 4c recorded theirs.
What remains fully achievable, and is the actual gap, is joining **real Git output** to everything
downstream: the snapshot entries `acquire_git_snapshot` really returned and the commit
`git rev-parse` really printed, carried through publish, consumer sync, marketplace, install and
receipt, instead of the `"a" * 40` placeholder every consumer-side fixture uses today.

## Method

D-091, D-134 and D-145 apply. One fixture builds a real Git repository, and each increment extends
how far a single continuous run gets through the chain, asserting the public contract at each stage
and never reaching behind a verb to arrange the next stage's precondition. Where an increment finds
a real defect it is fixed in the owning slice's terms and recorded here.

A stage that turns out to be genuinely unreachable end to end is recorded with the reason, following
CP-15 step 8's and CP-16 step 4c's precedent, not quietly dropped.

## Implementation steps

1. **DONE.** A real Git source repository, cloned by the real adapter, becomes the managed snapshot
   the source store holds -- the exact candidate `acquire_git_snapshot` returned and the commit
   `git rev-parse` printed, replacing the `"a" * 40` placeholder. An unchanged second acquisition
   converges without another snapshot, an upstream commit becomes current, and a fresh reader
   returns the complete candidate byte-for-byte.
2. **DONE.** That snapshot reaches a consumer: a real user configuration naming a real remote host, synced
   through the public verb with the transport port standing in for the network only, then
   marketplace listing and one install whose receipt names the real commit.
3. The installed artifact starts, updates when the upstream repository moves, and the update is
   traceable to the new commit.
4. Drift, repair, rollback and uninstall over the same live installation.
5. Collection/bulk install across the same source, and the full-chain assertion in one test.

## Step 1 evidence

`tests/git_source_publication_e2e_test.py` is the first test to pass a candidate returned by the
system Git adapter directly through native-source validation, atomic publication and a fresh store
read. It asserts full candidate equality, not just selected fields: source instance, alias, real
resolved commit, immutable-Git origin, snapshot digest, paths, bytes and executable metadata all
survive together. The first commit is explicitly not `"a" * 40`.

The correct implementation already composed, so RED was a deliberate mutation at the seam rather
than an invented production change. Replacing the resolved revision in `CurrentPointer` with
`"a" * 40` made both scenarios fail; restoring it returned them green. A fresh scoped mutation run
over `io/source_store.py` produced 669 mutants: 217 killed, 335 outside these two tests and 117
survivors. Tightening the assertions from truthiness and selected fields to exact booleans and full
candidate equality killed two additional normal-path mutants. The remaining normal-path differences
are permission/staging details outside this step, error-branch presentation, or the `source` / `SOURCE`
case mutation that is equivalent on the case-insensitive test volume; they are not a score and do
not broaden this slice.

No production code changed. `allow_local_transport=True` appears only on the adapter request in this
test, exactly where that test-only capability already existed; neither public source synchronization
nor configuration parsing was widened.

## Step 2 evidence

`tests/git_backed_consumer_e2e_test.py` commits a real promoted, vendored registry tree, writes a
real user configuration whose source is the valid remote identity
`https://company.example/agents/company.git`, and drives the public `aart source sync`,
`aart marketplace list` and `aart marketplace install` verbs. The only substitution is the
acquisition port: it first asserts that production supplied the remote URL with
`allow_local_transport=False`, then hands an otherwise identical request to the real system-Git
adapter with the temporary repository as transport. The public sync payload and Marketplace row
carry Git's real SHA, the Skill bytes are placed by the install, and both the returned lifecycle
receipt and a fresh `LocalReceiptStore` read name the same SHA.

The first RED stopped at source validation rather than the final receipt and made B-057 critical
for this increment: a promoted registry has the Product Specification's versioned
`artifacts/<kind>/<name>/<version>` and `registry/{versions,index,snapshot}` representation, while
the consumer was validating it as the older maintainer workspace with unversioned artifact roots
and `aart.{lock,index}.json`. D-147 routes each representation through the validator that writes
it, retains the legacy compiled form during the strangler migration, and reuses the shell's
approved-registry projection in the read-only Marketplace path. The remaining disagreement between
the old `registry publish` command and promotion stays in B-057; the accepted Git/PR publication
boundary does not require that command to turn a local promotion into publication.

The final RED was the missing provenance field. D-148 carries the synchronized source revision
through `ApprovedRegistrySnapshot`, `ResolvedArtifact` and the digest-bound `InstallPlan`, then
writes it on each receipt member. The field is additive and optional: older plans/receipts retain
their canonical bytes and still parse as unknown rather than receiving invented provenance.
Replacing the configured revision with `"a" * 40` made the E2E fail at the receipt assertion while
sync and Marketplace still reported the real SHA. A fresh scoped run over
`io/configured_selection.py` killed the mutation that omitted the new revision. A second fresh run
over `sources/validation.py` initially found that a valid non-empty registry could not tell whether
the explicit promoted-registry validator ran, because `load_registry_versions` already performs
that validation. The added empty/stale-catalog negative kills that omission and holds the case for
which the explicit call exists; the rerun produced 76 killed, 61 outside the selected tests and 25
survivors, none in the new representation dispatch.

### Step 2 review — the two halves of D-148, measured apart (D-149)

Step 2's evidence is a single continuous run, which is the right shape for a chain claim and the
wrong shape for two of the guarantees the step introduced. D-148 says the revision is a pinned
Source revision and that every added field is optional so existing receipt bytes keep their
canonical form. Neither is reachable from the chain: a real run builds exactly one well-formed
revision, and it cannot write a receipt from before the field existed. Both were re-measured rather
than accepted, and they came apart.

- **The shape guard was held by nothing.** Deleting the `is_pinned_source_revision` clause from
  `ResolvedArtifact.__post_init__` left the entire repository green -- 3,349 tests, one skipped.
- **The decode tolerance was held incidentally.** Removing the decoder's `"source_revision" not in
  row` guard does turn `installation_transaction_receipt_test` red, but by way of a round-trip whose
  name speaks of rebuilding an activity entry, over a fixture that happens to carry no revision.

`tests/git_revision_provenance_test.py` states both. The shape is a Hypothesis property over every
string that is not a pinned revision -- the guard admits an unbounded set and three examples cannot
say so (D-145) -- with a truncated SHA as the named near-miss a prefix check would admit. The
durability is the D-138 pair: a receipt carrying a revision reads it back, and the same receipt with
the key removed reads back as unknown rather than failing or guessing. A third claim separates a key
omitted from a key written as `null`, which is the same answer to a reader and different bytes on
disk.

Three mutations, each red only where claimed: deleting the shape guard turns the two property tests
red and no receipt test; refusing an absent key turns the two decode tests red; writing `null` in
place of omitting turns the byte-level test red on its own assertion. A scoped mutmut run over
`domain/selection.py` with the three files that claim it left no survivor anywhere in the code they
claim; its twelve survivors are in `_safe_line` and the two sort keys, recorded as B-063.

No production code changed. D-149 records the general form: a test that turns red under a mutation
shows that *something* holds the claim, not that the claim is stated, and a claim held by a
fixture's accidental shape is one refactor away from being held by nothing.

## Step 3a evidence — a real commit moves, and only an explicit update follows it

Step 3 as planned bundles two things: the installed artifact *starting*, and the installation
*following* the upstream repository. They need different fixtures -- starting means a real MCP
server with a real virtual environment, following means a second real commit -- so they are split
the way CP-16 step 4 was. 3a is the movement half and is done; 3b, MCP start over a Git-backed
source, remains.

`git_backed_consumer_e2e_test` now moves the real upstream repository: the registry is re-promoted
with both versions, its working tree replaced rather than added to (a promotion rewrites the index
and snapshot metadata, and leaving the old ones would publish a repository no maintainer could have
produced), and committed. The second commit is a real SHA distinct from the first.

One continuous run then holds five claims through public verbs. A second `source sync` reports the
new commit as the resolved revision. The delivered bytes are still the ones reviewed at install --
the sync offered and applied nothing. `marketplace update` without `--yes` reviews, names version
1.3.0 and still writes nothing. The confirmed update, with the review's `--expect` digest, converges
the delivery and records a receipt naming the *new* commit. And the durable audit trail holds both
revisions: the newest action names the commit it came from and the install before it still names
the one it came from.

`source_upstream_movement_e2e_test` already proved that a sync offers rather than applies. What it
could not show is that the revision an operator is offered, reviews and ends up with is the one Git
actually resolved, because every revision in it is a string that test chose.

Three mutations, and the third is the one that matters:

- Deleting the `ApprovedRegistrySnapshot` revision guard turns exactly the new property red.
- Stopping resolution from copying the registry revision onto artifacts turns both chain tests red.
- Writing the source store's current pointer once and never advancing it -- a sync that publishes a
  snapshot but never moves what the machine reads -- turns this test red on
  `1.2.0 != 1.3.0`, a stale offer, **while step 2's chain test still passes**. A fixture that syncs
  once from an empty store cannot see a pointer that never advances. That is D-145's argument at the
  scale of the chain, and it is why this increment is not a longer version of step 2.

## Step 3b evidence — the server an operator ends up running came out of a real commit

`mcp_stdio_e2e_test` starts a real MCP server and speaks JSON-RPC to it, but it assembles the
installation itself: it writes the payload by hand, creates the environment by hand and calls
`generate_launcher` directly. Nothing joined that runtime to the chain in front of it.
`git_backed_runtime_e2e_test` does. One real Git repository, synchronized and installed through
public verbs only, and then the launcher that install wrote is executed exactly as a harness would
execute it.

The install is real throughout: its receipt's four effects are `copy-tree`,
`create-python-environment`, `write-file` and `configure-harness`, so a virtual environment was
actually built rather than files merely placed. The server then answers `initialize`, `tools/list`
and `tools/call`; `serverInfo` is a literal in the author's `server.py`, so the bytes answering are
the ones the commit carried. It runs on the interpreter the install created rather than the one
running the tests, with the `--strict` argument the manifest declared, and `agent_artifacts` is not
importable inside it. A second test reads `.mcp.json`, the file a harness actually consults, and
starts what it names.

**Why the artifact declares no inputs, stated rather than assumed.** `aart marketplace install` has
no flag that answers a declared input -- the required-input form belongs to the persistent shell --
so an artifact declaring one cannot be installed through the CLI at all. The third test pins that
boundary: the refusal is `consumer-invalid`, it names each unanswered field and its kind, and
nothing is built for an install that cannot complete, with no runtime directory, no harness entry
and no receipt. The finding behind it is where the refusal lives. Disabling the adapter's own guard
in `io/configured_installation.py` killed nothing, because the CLI never reaches it; the refusal an
operator meets is `commands/marketplace.py`'s, and the adapter's is a second line of defence with no
public flow through it. B-064 records the capability question that leaves open.

Three mutations, each red only where claimed: pointing the launcher at the ambient interpreter turns
the runtime test red on the executable it reports; recording the payload entrypoint instead of the
launcher turns the harness test red on the command it names; and removing the CLI's unanswered-input
refusal turns the refusal test red.

B-065 records what the probe saw on the way past: `marketplace list` publishes a `provenance` block
whose `resolved_commit` is all zeros while `source.resolved_revision` beside it carries the real
commit. It is not a defect -- provenance describes the author repository at promotion time, and the
zeros come from the promotion-evidence fixture -- but it is this slice's own thesis pointing at the
half of the chain it does not reach.

## Quality gates

- Step 1 focused: 25 tests across the new Git-to-store E2E, Git adapter, source store and source
  acquisition suites are green; ruff format/check and mypy are green.
- Step 1 full gates: `make quality` is green across all nine gates -- 3,293 tests, one skipped and
  85.38% branch coverage -- and the separately run `make integration` is green with 323 E2E tests.
- Step 2 focused: 108 tests across Git publication, source validation/sync, both Marketplace
  projections, configured resolution/install and receipt round-trip are green; ruff and mypy are
  green. Full `make quality` is green with 3,295 tests, one skipped and 85.39% branch coverage;
  separately run `make integration` is green with 324 E2E tests.
- Step 2 review: `make quality` was re-run independently on the committed step 2 tree and is green
  across all nine gates -- 3,295 tests and 85.39% branch coverage -- before any review change was
  made. The review then added tests only, and `make quality` is green again afterwards with 3,302
  tests and 85.40% branch coverage.
- Step 3a: 24 tests across the Git-backed chain, Git publication, provenance, configured update and
  upstream movement are green; ruff format/check and mypy are green.
- Step 3b: the three runtime tests are green, each starting a real server from a real virtual
  environment the install built; ruff format/check and mypy are green.
- Step 4: all nine quality gates are green, and separately run `make integration` is green with 331
  E2E tests. The whole unit suite is green at 3,372 tests and one skipped. Step 4 found and fixed a
  real defect; D-150 records it, and the evidence below is what it turns on.

## Blockers

None. `git` is already a test dependency (`git_source_adapter_test`). The transport allowlist above
is a constraint on shape, not a blocker: it moves one seam from the verb to the adapter and leaves
every downstream stage reachable through public commands.

## Step 4 evidence -- drift over the live installation, and what it found

The measurement that started it. `aart doctor`, over the step 3b installation, under four kinds of
damage done to the real tree:

| damage | before | after |
|---|---|---|
| launcher rewritten | `broken`, divergent, repairable | unchanged |
| whole payload tree deleted | `ready`, `drift: []` | `broken`, missing, not repairable |
| one payload file rewritten | `ready`, `drift: []` | `ready` -- B-066 |
| one payload file deleted | `ready`, `drift: []` | `ready` -- B-066 |

In the rewritten case the server exits 1 while the report says ready. The launcher case was already
correct, which is what made the payload rows worth chasing rather than dismissing as "doctor is
shallow": the same report is precise about one component and silent about another.

**The defect and the fix** are D-150. In short: the payload was measured by both observers, then
discarded by `tuple(item for item in components if item.id in wanted)` before the comparison could
read it, because a doctor supplies no `payload_source` and so nothing desires the payload. Omitting
it from the *desired* state is right -- guessing where a tree came from would overwrite it from
somewhere nobody chose. That was being used as a reason not to *report* it, which is a different
claim, and INV-228 and INV-175 both speak to the reporting one.

**Scope taken, and why the first attempt was wrong.** The first version kept every damaged undesired
component. It broke 15 tests, and two of them were right to break:

- `installation_health` turns *any* unrepairable drift into `BROKEN`, including `UNVERIFIABLE`. A
  payload that resisted hashing would have been reported as broken. So the keep-rule is `ABSENT` and
  `DIVERGENT` only -- "measured and could not tell" is not damage.
- On a removal state, components absent by design are undesired and absent. Uninstall stopped
  converging. So the keep-rule is `Component.PAYLOAD` only, which on a removal state is desired and
  takes the ordinary branch.

**A fixture that was lying, exposed by the change.** `placed_machine_e2e_test` recorded
`ObjectDigest("sha256", "a" * 64)` as its payload digest while measuring the real tree only for the
delivery. Every `ready` it asserted was about a payload nobody had; the claim was invisible while the
observation was being dropped, and surfaced as `'ready' != 'broken'` the moment it was not. The
fixture now measures the tree it built. This is D-091's shape again, and worth noting as a pattern:
the fix did not just add coverage, it made an existing lie fail.

**A distinction the change forced.** `InstallationObservation.payload_present` was `bool = False`, so
any caller assembling a partial observation implicitly claimed the payload was deleted. The
regression test that describing less must not invent drift caught it. It is now `bool | None`, and
D-029's "nobody looked" is representable where it was not.

**Targeted mutations.** Four, each red only where it claims to be.

1. *Discard the observation again* -- `_reported`'s keep-rule reduced to `item.id in wanted`. Turns
   red: both payload cases and the health verdict in `placement_observation_test`, and both damage
   tests in `git_backed_runtime_e2e_test`, where doctor reports `'ok': True` over a deleted payload
   -- the original defect, reproduced exactly. Stays green: the drift-naming tests, which are about
   a different claim.
2. *Name damage `UNEXPECTED` again* -- the conditional in `compare_states` collapsed to the constant.
   Turns red: the naming claim at all three levels -- the domain subtests, both placement kind
   assertions, and `'missing' != 'unexpected'` through the public verb. Stays green: the health
   verdicts, which turn on `repairable` rather than on the kind.
3. *Report "nobody looked" as "gone"* -- `if observation.payload_present is not None` forced true.
   Turns red: the three D-029 regressions in `InstalledStateBridgeTest`, including the one whose
   name is that describing less must not invent drift. Worth noting that no new test was needed
   here: the existing regression already held the claim, which is why the conflation surfaced as a
   failure rather than as a silent widening.
4. *Widen the keep-rule* to every damaged undesired component -- the first attempt, restored. Turns
   red: uninstall convergence in `receipt_persistence_e2e` and `repair_e2e`. This is the mutation
   that makes the "do not undo" note below evidence rather than an opinion.

**What step 4 does not close.** B-066: the installation path has no tree digest on either the
observation or the receipt, so an MCP payload rewritten in place is still invisible and only
whole-tree deletion is caught. The observed component's detail says `presence only; this observation
carries no tree digest` rather than letting a partial check read as a full one.

**Uninstall, over the installation a real commit produced.** `receipt_persistence_e2e` and
`repair_e2e` already prove uninstall is reverse reconciliation, but against installations their own
fixtures assembled; removing an installation nobody could start proves less than removing this one.
`GitBackedUninstallE2ETest` starts the server first, so what follows is about a working
installation, then removes it through the public verb: four effects in reverse dependency order
(`unconfigure-harness`, then the launcher, then the environment, then the tree that contains it),
every step `applied`, the runtime gone, no `notes` left in `.mcp.json`, and doctor reporting a clean
machine rather than a record for something that no longer exists -- which after D-150 would now be
`broken` forever rather than merely stale.

Two mutations. Dropping the harness components from `removal_state_from_receipt` leaves `.mcp.json`
pointing at a launcher that has been deleted, which is the failure that test exists for. Removing
the artifact tree non-recursively turns all three red, and does it honestly: the step reports
`failed` with `Directory not empty` and the session goes `partial`, rather than reporting success
over a tree that is still there.

**Rollback.** The honest answer for this artifact is that there is none, and that is the claim worth
pinning. INV-192 is that AART must not invent stronger undo guarantees than a receipt carries;
building a virtual environment is not an act anything retained can reverse, so the install receipt
reports `undo.available: false` with a reason naming `runtime-environment` rather than refusing
generically. Asking anyway is refused by name -- `receipt-no-setup`, with remediation -- and changes
nothing: the tree is untouched and the server still answers `initialize` afterwards. A refusal that
left the installation half-reversed would be worse than no undo at all. Forcing `irreversible` empty
in `consumer_views.py` makes the receipt claim it can be undone and turns the first of those red,
while the second stays green, because they are claims about different things.

## Step 5 evidence -- more than one artifact, and the Collection that is not there

**Bulk install, over one real commit.** Every other Git-backed test in this slice installs a single
artifact, so what was unproven is that a run installing several keeps each one's kind straight. An
MCP server has to be built into a runtime; a Skill only has to be placed where a harness reads it.
`git_backed_bulk_install_e2e_test` publishes both into the one repository and installs them in one
confirmed run: both items `completed`, the server's four effects (`copy-tree`,
`create-python-environment`, `write-file`, `configure-harness`) against a Skill that gets neither an
environment nor a launcher, both artifacts carrying the same real commit into one receipt, the
server started beside the Skill still answering `initialize`, and doctor reporting both `ready`.

Two mutations. Forcing `_is_delivered` false in `installation_offer.py` -- every artifact built as a
runtime, whatever its kind -- turns all four bulk tests red, and does it honestly:
`installation-not-described`, because the Skill declares no way to start. Letting only an `mcp`
member carry the revision it came from turns exactly one test red, the one whose name is that both
carry the same commit, and leaves the other five green.

**The Collection half is a refusal, and that is the finding.** A Collection cannot be installed
through the CLI -- not for this fixture, but for any registry content at all.
`io/configured_selection.py::_approved_snapshot` skips every approved version whose kind is
`collection` and leaves `ApprovedRegistrySnapshot.collections` at its default, so the configured
Marketplace every public verb reads carries none. `marketplace list` returns `"collections": []`
while offering both members, and installing one answers `collection-not-found` with **empty
remediation**. The domain models Collections, the field exists, the coordinate form is documented,
and nothing on this path can populate it.

Recorded as B-067 rather than fixed here. This is a missing capability, not a defect in the chain
CP-17 exists to make real, and it is the same Collection work D-131 already sequenced B-038 behind;
closing it needs the promotion pipeline to publish a collection version as well as the projection to
carry it, and the authoring half is unexercised too. `CollectionsAreNotReachableTest` pins the
current behaviour so the gap stays an honest refusal -- it must not become a partial install of some
members, and must not silently succeed -- and B-067 also records the empty remediation, which is
worth fixing even while the capability is absent.

So step 5's bulk half is VERIFIED and its Collection half is BLOCKED on a capability outside this
slice. The step is not marked done.

## Handoff

- Current working state: steps 1, 2, 3a, 3b and 4 are VERIFIED. Step 4 is the first step in this
  slice to change production code (D-150), in `domain/reconciliation.py`,
  `application/installed_state.py` and `application/installation_verification.py`.
- Exact next action: step 5's Collection half, which is blocked on B-067 -- no approved Collection
  reaches the configured Marketplace, so no public verb can install one. Decide there whether CP-17
  closes with the bulk half plus a recorded capability gap, or whether B-067 is reclassified as
  critical and the Collection projection is built first. The bulk half is VERIFIED and needs
  nothing further.
- Do not undo, added by step 5: `CollectionsAreNotReachableTest` asserts a refusal, not a
  behaviour anyone wants. If B-067 is implemented, that class is what should turn red, and it
  should be replaced by the install it was standing in for -- not deleted to make room.
- Do not undo, added by step 4: the keep-rule in `_reported` is narrow on both axes on purpose --
  payload only, and `ABSENT`/`DIVERGENT` only. Widening either re-breaks uninstall convergence or
  reports an unhashable tree as broken; both failures are recorded in D-150 with the tests that
  caught them.
- Do not undo: the Git transport allowlist, and the configuration schema's refusal of local Git
  locations behind it. `file://` and local paths are refused on purpose at both layers, and no test
  may widen either to make itself hermetic. Substitute the transport port; never the verdict.
