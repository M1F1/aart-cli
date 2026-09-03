# AART Refactor — Next Work

## Current objective

**CP-14 Maintainer TUI 30–53 is VERIFIED.** All seven steps are complete: screens 30–53 are live in
the one shared shell, and step 7's legacy retirement finished with the evidence-led orphan sweep of
`agent_artifacts/tui.py` (D-129), B-044 closed by D-128 and B-046 closed by D-130. The CP-14
narrative below is kept as the record of how it got there.

**CP-15 Accepted lifecycle/edge-case hardening 54–100 is now IN PROGRESS**, per
`EXECUTION_PLAN.md`'s dependency order. The slice document is
`docs/refactor/slices/CP-15-edge-case-hardening.md`, and it opens with the scenario map: sixteen
invariants (INV-210, 216, 218, 219, 221, 222, 223, 226, 231, 232, 233, 237, 238, 240, 241, 242) all
carry the same three words in their evidence column -- *scattered source/registry/lifecycle
safeguards* -- and that phrase is the slice's whole subject. A safeguard at a seam is worth what
the verb an operator actually runs makes of it.

**Step 1 is done.** `tests/source_sync_command_e2e_test.py` drives `aart source sync` over a real
source whose upstream published an invalid revision, and INV-218 moves to EVIDENCED. Writing it
found D-132: `could-not-check` -- the health an explicit last-known-good fallback produces -- was
read as "this source is gone" in three places, so one invalid upstream revision made
`aart marketplace status` report every installation as `source-unavailable` and made `install` and
`update` fail on a plan-construction invariant carrying no remediation. Product Specification
165.11 settles it.

## Exact next action

**Continue CP-15 with step 2 of `slices/CP-15-edge-case-hardening.md`**: rollback, superseding and
provenance under a moving upstream (INV-216, INV-219, INV-229). The shape step 1 established is the
one to repeat -- name the verb an operator runs, drive it over a real temporary machine, and prove
each test red against a real mutation of the code it names, not against a broken fixture.

Two things step 1 measured that step 2 starts from. The `_environment_over_a_writable_source`
helper in `tests/source_sync_command_e2e_test.py` already gives a real synchronized local source
that a test may republish into, which is what "upstream moves" needs. And the coverage sweep found
whole scenarios with no test file matching them at all -- `purge`, `collection.*drift`,
`manual.*drift` -- so steps 5 and 6 are greenfield rather than re-characterization.

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
