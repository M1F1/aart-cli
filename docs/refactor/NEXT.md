# AART Refactor — Next Work

## Current objective

Finish **CP-13 Consumer TUI 01–29**. Steps 1–4 and the durable canonical machine reader are
verified, but public-entry characterization found that the canonical shell only navigates and
renders: it cannot start or apply lifecycle actions. Its composed source now carries the configured
Marketplace (D-068) and existing project/user install records (D-069), but the premature default-TTY
route was removed under D-062 and B-025 stays open until a real action handler exists.

What remains is the wiring that makes the canonical application the one a person actually reaches.

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

   The next RED seam is the production adapter around that action: bridge a configured approved
   Marketplace Selection to `ResolvedSelection` and placements without fabricating registry
   identity, bind the accepted screen-07 input sources/provider references, then reload one
   immutable machine after completion. The shell and public commands must call that one adapter
   rather than recompose its steps independently. B-032 records the input boundary that this audit
   proved is on the critical path.
5. **DONE:** public-flow characterization now pins each command seam before its dispatch changes --
   durable `status` (a later invocation names what an earlier one installed, and names nothing after
   an uninstall), one envelope across all four seams, a review that names the artifacts it would
   install, refusals reported in the envelope rather than as a crash, `--json` and text carrying one
   review digest, and fail-closed review that finalizes nothing and writes nothing while still
   carrying the digest a later invocation must match.
6. Only then route the default TTY and retire legacy consumer semantic authority (`consumer/application.py`,
   `installation/*`, `setup_engine/*`, `lifecycle/application.py`) path by path, each removal
   preceded by a public-flow test proving the canonical path already carries it.
7. Update the CP-13 coverage table as each command and screen group moves from projection to live
   public flow.

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
