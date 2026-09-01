# AART Refactor — Next Work

## Current objective

Start **CP-14 Maintainer TUI 30–53**.

**CP-13 Consumer TUI 01–29 is done except for a removal that CP-14 has to come first for.** Steps
1–5 are verified; B-033, B-034 and B-025 are all closed; every accepted screen 01–29 now draws from
canonical views over a real machine, and screen 28 keeps what it is told (D-090). The coverage table
in the slice file records what closed each row.

What is left of CP-13 is retiring legacy consumer authority, and the two routes that still reach it
-- Collections, and direct/local sources -- are exactly the two CP-14 gives a canonical home
(D-091). Both were filed as open product questions; both are already answered by the Product
Specification, and both answers land in CP-14:

- **Collections (B-031).** Section 145.1: "A Collection is a versioned set of artifact
  selectors/constraints", with `version: 2.1.0` in its example. `CollectionManifest` has no version
  field and `discover_author_manifests` never looks at a collection root, so no Collection has ever
  been compiled, promoted or published as a registry artifact. CP-14 owns "collection candidates".
- **Native sources (B-038).** Section 1737 lists Source as the origins a *registry* pulls from, and
  INV-019–INV-026 put consumer installation entirely over approved registry content (INV-021:
  installing an approved vendored registry artifact uses the registry snapshot, not the author
  repository). CP-14 owns Sources screens 31–34. The canonical consumer seam offering nothing from
  a native source is specified behavior; the legacy route's direct native install is what has no
  basis.

So the legacy stack stays until CP-14 exists, each removal then preceded by a public-flow test
proving the canonical path already carries it. Nothing installable is lost meanwhile.

## Immediate next actions

The renderers are not the missing layer. A package can be compiled, published, read back and
installed end to end (D-056), and a flow holds that install for the screens that draw it (D-059).
The missing layer is typed application commands/handlers that turn selection and confirmation into
that flow and execution, plus composition of real Marketplace and installed-state sources.

1. **DONE:** RED interaction tests now cover Marketplace selection → Review, Ready → execute,
   Installed → verify/repair/uninstall, and recorded outcome → refreshed Success/Activity routing.
   `PREPARE_ACTION` and `EXECUTE_ACTION` carry only typed intent, coordinates/selection and review
   identity. The reducer remains pure, `key_event` remains the sole key interpreter, and the shell
   accepts matching prepared/recorded updates only through an injected handler (D-063).
2. **DONE (transaction half):** `execute_installation` runs a whole `InstallationProposal` under
   one CP-12 scope lease with every member's precondition compared before the first effect, and one
   transaction becomes one Activity receipt plus one installed record per member that applied
   (D-064). A member that never ran stays named in the receipt as `not-attempted`; a member that
   applied but has no receipt is refused rather than forgotten; undo is the weakest member's answer.
   `ConsumerFlow` now holds that transaction receipt, and screens 10/11 draw it: every member is
   named with its status and steps, a member that never ran is drawn rather than dropped, and undo
   is offered only where the transaction can be reversed (D-065). The authored-manifest E2E installs
   through `execute_installation` and draws those screens from the receipt that run produced.
   A real install recorded as a transaction is re-read from disk by `read_consumer_machine` and
   appears in Installed, Collections and Activity with the token absent from every surface (D-066),
   so B-030 is closed. Configured Marketplace offers are now composed into the same source and drawn
   on screens 02–04a (D-068). **DONE**, except that Collections do not cross that seam: they are
   declined by name until a versioned Collection reaches it (B-031).
3. **DONE:** the strangler boundary for existing project/user installation manifests is defined
   and tested. `read_consumer_machine` reads both manifests beside the receipt store, and every
   record no canonical receipt already answers for is carried into the same `machine.installed`
   list as an unadopted installation: health `unknown`, one `unobserved` drift that is not
   repairable, and no offered action. The absence of a canonical MCP receipt is therefore never
   evidence that a Skill/guideline/hook/memory installation does not exist (D-069). The legacy
   path remains the one that operates them; the canonical shell shows them without claiming to
   understand them.
4. **IN PROGRESS.** Route the public consumer commands (`install`, `update`, `uninstall`,
   `status`) through `offer_installation`/`begin_installation`/`execute_installation`/
   `record_installation` rather than the legacy setup queue, projecting their output with
   `consumer_plan_to_data` and `receipt_detail_to_data` so text, curses and `--json` are three
   renderings of one plan. `render_install_plan` is already the whole-plan review a non-interactive
   command prints (D-049).

   The composition those callers were missing now exists: `offer_installation` plans a whole
   Selection, measures this machine once, lists what would have to be agreed to and observes what is
   already at the paths the install would occupy, and `observe_planned_installation` is its adapter
   (D-070). The real E2E proves the composed offer reaches the same answer as the hand-wiring it
   replaces and installs for real through it.

   **DONE:** the remaining composition seams now exist. `placement_for` reads each resolved
   artifact's verified object and install description, applies the scope/profile root and measured
   harness targets (D-071), and `interpreters_for` builds the capability-bound adapter set for the
   whole Selection while refusing a missing credential provider before mutation (D-073). The real
   authored-package E2E installs through that assembler rather than a hand-wired tuple.

   **DONE (application half):** `prepare_installation_action` and
   `complete_installation_action` now preserve one structural review identity across offer,
   confirmation, aggregate execution and durable transaction/member recording (D-074). A mismatch
   refuses before the mutation lease, and the real authored-package E2E uses this operation plus
   the D-073 assembler rather than test-only orchestration.

   **DONE (source half):** `configured_selection` resolves a Selection from configured approved
   registry snapshots, taking approval identity only from validated `registry/versions/*` records so
   a legacy Marketplace row is never upgraded into an approval by inference; `installation_inputs`
   owns the pre-plan form state screen 07 needs, where unanswered fields stay visible and a secret
   can become configured only through a `SecretProviderReference`; and `configured_installation`
   drafts the installation from both. That work also proved the approved-version and store-object
   digests are two different values (D-075), which had made `placement_for` unable to find the
   object it had just resolved.

   **DONE (composition):** `prepare_configured_installation` and
   `complete_configured_installation` are that single adapter (D-076). `InstallationHost` derives
   the state root, harness root and lock scope from the data/project/home roots and the scope, so
   preparation and completion cannot act on different machines; unanswered inputs come back as the
   screen-07 form rather than a refusal; completion executes only the confirmed review digest and
   re-reads the machine from disk. The E2E installs a configured approved artifact end to end and
   checks the machine rather than the executor's verdict.

   **Routing has started.** A direct artifact whose explicit source -- or configured default -- is
   an enabled `RegistryGit` source now enters this adapter from public `marketplace install`
   (D-079). Its JSON review is `consumer_plan_to_data`, its text review renders that same plan, its
   completion carries `receipt_detail_to_data`, and a stale digest refuses before mutation. Direct
   and local sources plus Collections stay on the characterized legacy route.

   **Status is routed for the same approved-registry authority** (D-080). A later invocation reads
   canonical receipts through `read_consumer_machine`, re-inspects the installed targets, filters
   by the requested scope/profile and renders the resulting `InstalledArtifactView`; an edited
   Skill delivery therefore reports measured `attention` rather than receipt-derived success.
   Direct/local status, `update`, `uninstall` and the default TTY have not moved yet.
5. **DONE:** public-flow characterization now pins each command seam before its dispatch changes --
   durable `status` (a later invocation names what an earlier one installed, and names nothing after
   an uninstall), one envelope across all four seams, a review that names the artifacts it would
   install, refusals reported in the envelope rather than as a crash, `--json` and text carrying one
   review digest, and fail-closed review that finalizes nothing and writes nothing while still
   carrying the digest a later invocation must match.
6. **IN PROGRESS; B-033 is complete.** Route the default TTY and retire legacy
   consumer semantic authority (`consumer/application.py`, `installation/*`, `setup_engine/*`,
   `lifecycle/application.py`) path by path, each removal preceded by a public-flow test proving
   the canonical path already carries it.

   The canonical pipeline refused any artifact that declares no launch contract, so Skills,
   guidelines, hooks and memory could not be planned, executed or recorded through it at all.
   B-033 closes that, and its completed increment table lives in the CP-13 slice file. What exists
   now: a
   `PlacedArtifactReceipt` with no launcher field to leave empty; `DeliverArtifact`/
   `WithdrawArtifact` at `CONFIGURATION_MUTATION`, so a policy ceiling that refuses to register an
   MCP server also refuses writing a Skill into the directory that harness reads (D-077); a
   `DeliveryEffectInterpreter` bound to the deliveries it may make; `plan_artifact_placement`,
   which refuses anything that starts a process, declares dependencies nothing would load or names
   a secret with no launcher to resolve it into; `DELIVERY_TARGETS`, measured per harness, scope
   and kind; `package_delivery`, which reads what a package offers a harness back out of the
   package; a receipt-store codec and machine reader for placed installations; placement-aware
   observation, resolution and interpreter composition; and a real authored Skill taken from its
   author tree through promotion, configured resolution, review, installation, durable reload,
   drift detection and uninstall. Withdrawal restores owner access only inside the exact read-only
   tree it is removing and never follows a symlink (D-078).

   Public direct approved-registry `install`, `status`, `update` and `uninstall` are now all live
   (D-079, D-080, D-081, D-083). `update` rebuilds its Selection from the canonical records, pins
   no version unless somebody pinned one, and lets `supersession_intent` decide update / repair /
   refused-downgrade (D-081); converging in place also forced the payload to be judged by content
   rather than presence (D-082). `uninstall` plans from receipts alone and runs through the same
   executor (D-083), so removing the source that delivered an artifact no longer strands it.

   **Memory now installs canonically (D-084).** `MergeManagedBlock`/`UnmergeManagedBlock`,
   `MEMORY_TARGETS`, `package_merge`, `ArtifactMerge` on the placed receipt and a `MERGE`
   reconciliation component close the first half of B-034: a memory artifact is installed by owning
   a delimited region of a file the user writes in, measured by digesting that region rather than
   the file, and uninstalled by taking the region back and leaving the file. Proven end to end
   through the public command in `tests/merged_installation_e2e_test.py`.

   **Hooks now install canonically too (D-085), and B-034 is closed.** A hook is the one kind that
   is both halves at once: its script is delivered into a directory named for the artifact, and
   `MergeSettingsEntry`/`UnmergeSettingsEntry` own one entry of one list inside a settings file the
   harness and its user share, identified by `(matcher, command)` and typed rather than rendered
   from a template. `HOOK_TARGETS` holds the script directory, settings file, event map and entry
   shape as one measured fact per harness/scope; `package_hook` reads the declaration back out of
   the package; a `SETTINGS` reconciliation component measures the entry as the file spells it now.
   Proven end to end through the public command in `tests/hook_installation_e2e_test.py`, including
   that a hook the user installed by hand survives both install and uninstall.

   **Every artifact kind the Product Specification defines can now be installed, measured, repaired
   and removed canonically** -- MCP, skills, guidelines/rules, memory and hooks, in that order,
   which is the Product Specification's own.

   **The default TTY route is live (B-025 closed, 2026-09-01).** `run()` composes
   `_canonical_consumer_actions` -- machine, offers, configuration and credential adapters read once,
   together, so the same local state is never opened twice -- and calls `run_consumer` before any
   wizard composition. The legacy `try: _run_curses(...)` block is gone; `_run_text` remains the
   documented degradation when curses is unavailable, because no-TTY is a supported environment
   rather than a broken one.

   Three things made the route safe to take. A repair is bounded by what its receipt records, so it
   works when the source is unsubscribed and fails closed on anything the receipt cannot describe
   (D-086). A refusal is drawn under the screen it was asked from rather than raised, so a failed
   resolution cannot take the session down (D-087). And the Marketplace is now the configured
   *registries'* approved published versions (D-088, INV-026), so what is browsed is installable --
   previously the shell offered artifacts from native sources the install seam could not resolve,
   and refused outright on a canonical published registry.

   **The next executable work is retiring legacy consumer authority path by path** --
   `consumer/application.py`, `lifecycle/application.py`, `installation/*`, `setup_engine/*` -- each
   removal preceded by a public-flow test proving the canonical path already carries it. `_run_curses`
   and the wizard composition are now unreachable from `run()` on a terminal but still have direct
   test callers (B-039); they are the last thing to go, not the first.

   Two gaps the closure left open and did not paper over: the shell declines a selection whose
   inputs it cannot yet collect (B-032, already promoted), and a deprecated registry version is
   declined by name because the Marketplace row has nowhere to render the warning (B-036).

   **B-037 was promoted and fixed (2026-09-01), not deferred.** It was filed as a fixture problem
   and re-triaged as a correctness defect on `aart registry promote`: `plan_bulk_promotion` rewrote
   version records only for its own transaction while the catalogs took the new content digest, so
   the second promotion into any registry made it unreadable to every consumer. Every retained
   approved record is now rebound to the snapshot its transaction produces, as metadata only, with
   the published package proven byte-identical (D-089). A registry can now hold many approved
   versions across many transactions -- which is what an identity with more than one released
   version needs -- and that supplied D-088's last piece of evidence: a Marketplace row stands for
   the highest approved SemVer of an identity, and an older approved version is superseded rather
   than declined.
7. **DONE (2026-09-01).** The CP-13 coverage table records what closed each screen row. The last
   one was screen 28: four accepted controls with a cursor, Enter moving the one under it, `v` and
   Detail level as a single preference, and a durable `<data_root>/state/consumer-settings.json`
   read strictly rather than repaired (D-090). Maintainer Mode is the boundary CP-14's whole surface
   sits behind, so an opt-in that had to be re-chosen every session was a CP-14 prerequisite too.

## Do not do yet

- no replacement with Textual/Rich or a second TUI framework;
- no Maintainer Mode screens 30–53 (CP-14), beyond preserving the existing opt-in boundary;
- no broad package moves or deletion of legacy authority before public replacement evidence;
- no second place where a key's meaning is decided: `key_event` is the only one (D-041);
- no clock in `application/`: `today` and a record's own timestamp are supplied (D-039);
- no new transport, credential provider, installer backend or unmeasured harness target;
- no Docker/OCI foundation (B-003), orphan classifier (B-023) or other backlog work;
- no changes to older AART repositories.

## Carried forward

- Product Specification is the only product authority; accepted screen numbers are contracts, not
  optional mockups.
- Fast and Verbose share selection, requirements, policy, plan digest, risks, effects and execution;
  only detail changes. Fast may compress review but never bypass it or hide material risk.
- Secret values never enter view models, history, snapshots, receipts or JSON. Credential UI is
  reference/provider/health/dependant oriented.
- CP-12 absent desired targets and reverse teardown order stay intact. Uninstall retains artifacts
  with remaining ownership and credentials by default.
- Scope mutations use compare-under-lock reviewed execution. Interrupted work is re-inspected and
  replanned; no UI action resumes an imperative instruction number.
- The legacy curses behavior is characterization evidence. Reuse it until canonical public-flow
  tests prove a specific path replaceable.
- Persisted identity is structural, never a printed form re-parsed (D-044); an unreadable record is
  reported rather than skipped, because a skipped receipt reads as an installation that never
  happened (D-045).
- An action that took effect is recorded even when it did not finish, and a rolled-back update
  leaves the previous record standing (D-046). Health is inspected, never inferred from the
  existence of a record.
- A screen is implemented when it is reachable by the accepted navigation map, not when a renderer
  draws it from a state handed to it directly. Presentation words (credential health) are decided
  in the renderer; the projection keeps the canonical state a machine consumer reads (D-048).
- Ownership is persisted beside the receipt, and only intents that speak to it may change it: a
  repair that carried the nothing it knows would release a Collection's claim (D-050).
- The machine is assembled once and never inside a draw (D-051). Collection membership comes from
  recorded ownership, not from a Collection's current manifest.
- One lowering stands behind the plan somebody reviews and the effects that run (D-052): the review
  is derived from the reconciliation against a real inspection, never assumed from a fresh install,
  and `InstallationProposal` refuses to exist when the two disagree. An artifact nobody observed is
  refused rather than assumed absent.
- The payload is its own component, established from plan knowledge (`payload_source`) and observed
  as the payload directory rather than the root beside it (D-053).
- The domain keeps the rules an input has to satisfy; the authoring parser only decides which fields
  a kind may carry, and surfaces the domain's refusal as a diagnostic (D-054). A secret's field set
  omits `default` and `value` entirely, so there is no field a real credential could be written
  into. Declarations reach the input digest exactly as the author wrote them, in declared order.
- A descriptor an artifact points at travels inside its payload, or the manifest is refused at
  compile time (D-055). A resolver with no installer backend is refused by name, never approximated.
- One value stands between what an artifact declares and what a machine offers (D-056). The
  description is read back out of the package with the parsers that wrote it, never re-derived from
  the author's repository, which the installing machine has not seen.
- Dependencies are reported through the environment that holds them (D-057). Losing the environment
  is drift; a package changed by hand inside a healthy one is not yet detected, and the observation
  says so instead of claiming more than it measured (B-029).
- A package carrying no authoring extension is refused rather than read as declaring nothing
  (D-058): an artifact that needs nothing and a package that never recorded what it needs are
  different facts, and only one of them is safe to install.
- A flow is held beside the machine, never derived inside a draw (D-059): screens 05–11 project one
  `InstallationProposal`, and an outcome may only be reported under the review it belongs to.
- The transaction is the unit recorded because it is the unit reviewed (D-064): one confirmation
  leaves one action receipt naming the Selection, with every member accounted for beneath it and one
  installed record per member that applied. Screens 10 and 11 draw that transaction; 17 and 19 stay
  on one artifact's lifecycle action (D-065).
- Reading offers is an effect and happens once at composition, never inside a draw (D-068). What a
  source published but this seam cannot offer is declined by name, because an offer missing with no
  explanation reads as a source that published nothing.
- The Marketplace projects configured registries and does not restate their trust decisions
  (D-088, INV-026). An offer is an approved published version, its compatibility is recompiled from
  the package the registry published, and its trust class comes from the promotion record that
  approved it -- never from `review=None`, which understates it to `unverified`.
- A repair is bounded by its receipt (D-086): it re-measures nothing, resolves nothing, and refuses
  by name what the receipt cannot describe rather than approximating it.
- A refusal is drawn where it was asked, never raised (D-087). The reducer already reads an empty
  review digest as "nothing was established"; an action that threw would lose the session.
