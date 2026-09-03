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
  made. The review then added tests only.

## Blockers

None. `git` is already a test dependency (`git_source_adapter_test`). The transport allowlist above
is a constraint on shape, not a blocker: it moves one seam from the verb to the adapter and leaves
every downstream stage reachable through public commands.

## Handoff

- Current working state: steps 1 and 2 are VERIFIED, and step 2 has been independently reviewed
  (D-149), which added `tests/git_revision_provenance_test.py` and changed no production code.
- Exact next action: step 3 -- start the installed artifact, commit an upstream
  update, synchronize it and prove the explicit update plus its receipt bind the new Git commit.
- Do not undo: the Git transport allowlist, and the configuration schema's refusal of local Git
  locations behind it. `file://` and local paths are refused on purpose at both layers, and no test
  may widen either to make itself hermetic. Substitute the transport port; never the verdict.
