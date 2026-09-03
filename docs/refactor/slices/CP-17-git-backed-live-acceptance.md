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
2. That snapshot reaches a consumer: a real user configuration naming a real remote host, synced
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

## Quality gates

- Step 1 focused: 25 tests across the new Git-to-store E2E, Git adapter, source store and source
  acquisition suites are green; ruff format/check and mypy are green.
- Step 1 full gates: `make quality` is green across all nine gates -- 3,293 tests, one skipped and
  85.38% branch coverage -- and the separately run `make integration` is green with 323 E2E tests.

## Blockers

None. `git` is already a test dependency (`git_source_adapter_test`). The transport allowlist above
is a constraint on shape, not a blocker: it moves one seam from the verb to the adapter and leaves
every downstream stage reachable through public commands.

## Handoff

- Current working state: step 1 VERIFIED; no production code changed.
- Exact next action: step 2 -- public source sync, Marketplace listing and one
  install over the real Git candidate, with only the network transport substituted.
- Do not undo: the Git transport allowlist, and the configuration schema's refusal of local Git
  locations behind it. `file://` and local paths are refused on purpose at both layers, and no test
  may widen either to make itself hermetic. Substitute the transport port; never the verdict.
