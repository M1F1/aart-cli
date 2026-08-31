# AART Refactor — Next Work

## Current objective

Finish **CP-13 Consumer TUI 01–29**. Steps 1–4 and the durable canonical machine reader are
verified, but public-entry characterization found that the canonical shell only navigates and
renders: it cannot start or apply lifecycle actions, has no configured Marketplace in its composed
source, and cannot yet see existing project/user install records. The premature default-TTY route
was therefore removed under D-062 and B-025 is open again.

What remains is the wiring that makes the canonical application the one a person actually reaches.

## Immediate next actions

The renderers are not the missing layer. A package can be compiled, published, read back and
installed end to end (D-056), and a flow holds that install for the screens that draw it (D-059).
The missing layer is typed application commands/handlers that turn selection and confirmation into
that flow and execution, plus composition of real Marketplace and installed-state sources.

1. Add RED interaction tests for the accepted action transitions: Marketplace selection → Review,
   Ready → execute, Installed → verify/repair/uninstall, and outcome → refreshed machine/Activity.
   Extend `ConsumerUiCommandKind` only with semantic application requests; the reducer still does
   no I/O and `key_event` remains the sole key interpreter.
2. Add an injected consumer application handler that builds `ConsumerFlow` with
   `begin_installation`, executes its reviewed lifecycle plans under the existing CP-12 lock, calls
   `record_installation`, and reloads the durable machine. Compose configured Marketplace offers
   into the same source. Do not route `run()` until these live-flow tests pass.
3. Define and test the strangler boundary for existing project/user installation manifests. They
   must remain visible and operable until a kind-neutral canonical receipt/observation replaces
   them; never treat the absence of a canonical MCP receipt as evidence that a Skill/Rule/Hook/
   Memory installation does not exist.
4. Route the public consumer commands (`install`, `update`, `uninstall`, `status`) through
   `begin_installation`/`execute_lifecycle`/`record_installation` rather than the legacy setup
   queue, projecting their output with `consumer_plan_to_data` and `receipt_detail_to_data` so
   text, curses and `--json` are three renderings of one plan. `render_install_plan` is already the
   whole-plan review a non-interactive command prints (D-049).
5. Add public-flow characterization at each command seam before changing its dispatch, including
   non-interactive fail-closed review, machine-output completeness, and a real persisted install
   that a subsequent `status` invocation reads without in-memory state.
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
