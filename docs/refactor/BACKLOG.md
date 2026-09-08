# AART Refactor Discovery Backlog

> This is deliberately **not** the critical path.
> Product Specification + EXECUTION_PLAN are mandatory.
> Agents append non-blocking discoveries here instead of expanding the active slice.

## Backlog admission rule

Add an item when it is valuable but **not required** to satisfy a currently mandatory Product
Specification invariant, acceptance criterion, security boundary or critical-path dependency.
Do not implement it merely because it is nearby.

Reclassify to critical path only with concrete evidence explaining what mandatory item cannot be
completed without it. Record that change in DECISIONS and EXECUTION_PLAN/NEXT.

## Required backlog item format

```text
B-XXX — Short title
Status: OPEN | DEFERRED | PROMOTED | DONE
Discovered in: CP-XX / file / test
Why useful:
Why noncritical now:
Potential approach:
Invariants touched:
Evidence/links:
Promotion condition:
```

## Seed backlog

### B-001 — Optional richer TUI framework
Status: DEFERRED
Why useful: Textual/Rich could improve visual complexity/accessibility.
Why noncritical now: accepted direction is to reuse/refactor the existing persistent TUI and
preserve zero runtime dependencies.
Promotion condition: explicit Product Specification change or proven inability of current TUI to
implement an accepted screen safely.

### B-002 — Namespaced multi-version active artifacts
Status: DEFERRED
Why useful: multiple active versions of one coordinate in one scope.
Why noncritical now: V1 explicitly assumes one active version per coordinate/scope.

### B-003 — Additional MCP distribution/runtime backends
Status: DEFERRED
Includes OCI/container, npm, standalone binaries and richer remote deployment helpers.
Why noncritical now: first production vertical slice is Python source-tree + stdio.

### B-004 — Additional secret providers
Status: DEFERRED
Includes Linux Secret Service, Windows Credential Manager and enterprise vault adapters.
Why noncritical now: macOS Keychain is the first required concrete interpreter.

### B-005 — Advanced dependency ecosystem support
Status: DEFERRED
Includes full Poetry/uv lock semantics, alternate resolvers and offline mirrors beyond initial
RequirementsFile/PyProject + pip/uv capability model.

### B-006 — Cryptographic signing / Sigstore-style attestation
Status: DEFERRED
Why useful: stronger supply-chain assurance.
Why noncritical now: provenance/digests/policy/immutable snapshots are mandatory first.

### B-007 — Hosted registry/search service
Status: DEFERRED
Why useful: large-scale discovery/search APIs.
Why noncritical now: registry is Git-backed and marketplace is an aggregated projection over
configured registries. Do not add download analytics/telemetry unless explicitly requested later.

### B-008 — Agent/A2A artifact type
Status: DEFERRED
Why noncritical now: explicitly out of scope.

### B-009 — Safe adoption of arbitrary manual drift
Status: DEFERRED
Why useful: adopt hand-edited generated state.
Why noncritical now: V1 detects drift and may restore/ignore.

### B-010 — Full offline dependency installation
Status: DEFERRED
Why useful: disconnected environments.
Why noncritical now: product must distinguish cached metadata/payload/dependencies, not promise
complete offline package installation.

### B-011 — Stronger generalized transaction/undo engine
Status: DEFERRED
Why useful: broader compensation.
Why noncritical now: AART must represent actual effect capabilities and never pretend universal undo.

### B-012 — Advanced Collection authoring UX
Status: DEFERRED
Why useful: richer maintainer editing/preview workflow.
Why noncritical now: collection semantics/candidate lifecycle/promotion are mandatory; a visual
authoring editor is not.

### B-013 — Performance profiling and large-registry optimization
Status: OPEN
Why useful: may matter at scale.
Why noncritical now: correctness/determinism/architecture first.
Promotion condition: benchmarks show a critical-path performance problem.

### B-014 — Plugin SDK for proprietary extensions
Status: DEFERRED
Why useful: custom enterprise integrations.
Why noncritical now: ports/adapters/configuration should cover ordinary extension; an unreviewed
plugin system adds security/compatibility surface.

## Newly discovered items

Append below this line. Keep IDs stable.

### B-015 — A non-interactive Keychain store path that does not use argv
Status: OPEN
Discovered in: CP-08 / `agent_artifacts/io/credentials.py` / `MacOsKeychainProvider.store`
Why useful: the default store path delegates to `security`'s own prompt, so the value never enters
this process or the process table. The non-interactive path — the one CI and unattended
reconciliation need — has to pass the value as `add-generic-password -w VALUE`, which publishes it
to the process table for the duration of the call. `store_exposure(interactive=False)` reports that
as `PROCESS_TABLE` so a policy can refuse it, but reporting the exposure is not removing it.
Why noncritical now: `security` offers no stdin or file-descriptor form of `-w`, so removing the
exposure means either a small helper that writes through the Security framework directly (a
compiled component, which the zero-runtime-dependency constraint currently rules out) or accepting
a different provider. The interactive default is what production takes, and the weaker path is
declared rather than hidden, which is what the Product Specification asks of a representable but
riskier operation.
Potential approach: an `expect`-style pseudo-terminal driver feeding the provider's own prompt,
which keeps the value off argv at the cost of a PTY dependency and the 128-byte prompt ceiling; or
a first-party helper invoked through a file descriptor.
Invariants touched: INV-048, INV-051, INV-053, INV-159, INV-160.
Evidence/links: D-016, D-017; `tests/credential_lifecycle_integration_test.py::
KeychainInterpreterTest::test_the_non_interactive_store_names_the_exposure_it_accepts`.
Promotion condition: a Product Specification screen or an enterprise policy requires unattended
credential storage under a policy that forbids `PROCESS_TABLE` exposure.

### B-016 — Address literals in URL host allow-lists
Status: OPEN
Discovered in: CP-08 / `agent_artifacts/domain/inputs.py` / `_url_host`
Why useful: `InputValidation(kind="url")` refuses `https://[::1]/` and any bracketed IPv6
authority, because an allow-list entry is validated as a hostname and cannot name one today.
Why noncritical now: no accepted screen configures an artifact against a raw address literal, and
refusing what the allow-list cannot express is the safe direction — the alternative is accepting a
form the checker and the later consumer might read differently.
Potential approach: give `InputValidation` a separate address-literal allow-list with its own
normalization, rather than widening the hostname character set.
Invariants touched: INV-057, INV-190.
Evidence/links: D-018.
Promotion condition: a Product Specification input or a real registry artifact needs to name an
address literal.

### B-017 — Windows environment layout for artifact-owned Python environments
Status: OPEN
Discovered in: CP-09 / `agent_artifacts/domain/python_runtime.py` / `ArtifactEnvironment`
Why useful: the derived interpreter path is `runtime/.venv/bin/python`, which is the POSIX layout.
Windows venvs put it at `runtime\Scripts\python.exe`, so an artifact installed on Windows would get
a path that does not exist.
Why noncritical now: the first credential provider is macOS-only and the first harness adapter is
not written yet, so a Windows layout alone would be a third of a working Windows install. Deriving
the path from the root is what makes adding the second layout a one-place change.
Potential approach: give `ArtifactEnvironment` a layout discriminator fed from `EnvironmentFacts.
platform`, and pick the subpath from it; keep the paths derived, never supplied.
Invariants touched: INV-044, INV-046.
Evidence/links: D-020.
Promotion condition: Windows appears as a supported consumer platform with a credential provider
and a harness adapter.

### B-018 — Installing a locked Python project
Status: OPEN
Discovered in: CP-09 / `agent_artifacts/io/python_runtime.py` / `install_dependencies`
Why useful: an artifact may declare `pyproject.toml + uv.lock`. The domain models it, planning
narrows the installer to uv, and the interpreter refuses it explicitly — so the contract is
reviewable but not yet installable.
Why noncritical now: §110 makes `requirements.txt` and `pyproject.toml` the V1 specifications, and
both are fully implemented for both backends. Refusing loudly keeps the lock's guarantee intact;
see D-021.
Potential approach: `uv sync --frozen` against the artifact-owned environment, with a test that a
pinned version in the lock is the version actually installed — the assertion that makes the
feature worth having.
Invariants touched: INV-042, INV-043, INV-047.
Evidence/links: D-021; `tests/python_environment_integration_test.py::RuntimeRefusalTest::
test_it_refuses_a_locked_project_rather_than_quietly_ignoring_the_lock`.
Promotion condition: a critical-path artifact declares a lock, or reproducibility review requires
lock-exact installation.

### B-019 — File-bound secrets in a generated launcher
Status: OPEN
Discovered in: CP-10 / `agent_artifacts/application/runtime_projection.py` / `generate_launcher`
Why useful: some servers accept a credential only as a file path. `FileBinding` and
`BindingExposure.OWNED_FILE` already model it, and planning already permits it, so the only missing
piece is a launcher that can materialize one safely.
Why noncritical now: no MCP server on the critical path needs it. Environment and argument bindings
cover the real ones, and the refusal is explicit (D-024) rather than a silent gap.
Potential approach: `umask 077`, a file under the artifact's own root, and a `trap` covering EXIT,
INT, TERM and HUP — with a test that kills the process and asserts nothing is left behind, which is
the assertion that makes the feature safe rather than merely present.
Invariants touched: INV-053, INV-054, INV-062.
Evidence/links: D-024; `tests/runtime_projection_test.py::GeneratedLauncherTest::
test_a_file_binding_is_refused_rather_than_quietly_writing_a_secret_to_disk`.
Promotion condition: a critical-path artifact declares a file-bound secret.

### B-020 — Measured MCP targets for OpenCode and Vibe
Status: OPEN
Discovered in: CP-10 / `agent_artifacts/domain/harness.py` / `MCP_TARGETS`
Why useful: `MCP_TARGETS` carries Tabnine and Claude Code. The legacy `profiles/builtin.py` also
carries OpenCode and Vibe, but marks their MCP keys and hook event model as unverified best-effort
defaults.
Why noncritical now: CP-10 needs one real harness adapter and Tabnine is measured. Copying an
unverified path into a canonical table would launder a guess into an authority (D-025).
Potential approach: install one server against a live build of each and read back what the harness
actually parsed, the way the Tabnine target was established.
Invariants touched: INV-058, INV-059.
Evidence/links: D-025; `agent_artifacts/profiles/builtin.py` OpenCode note at §19.
Promotion condition: a user targets OpenCode or Vibe on the critical path, or a live build becomes
available to measure.

### B-021 — A launcher for a platform without a POSIX shell
Status: OPEN
Discovered in: CP-10 / `agent_artifacts/application/runtime_projection.py` / `_render`
Why useful: the generated launcher is `/bin/sh`. Windows has no POSIX shell by default, so an
installation there has no runtime projection at all.
Why noncritical now: pairs with B-017 — the environment layout differs on Windows too
(`Scripts/python.exe`, not `bin/python`), so both are one piece of work, and neither is on the
critical path.
Potential approach: a second renderer selected by platform, with `shell_quote`'s property test
repeated against the real target shell rather than assumed.
Invariants touched: INV-060, INV-100.
Evidence/links: B-017; `agent_artifacts/domain/python_runtime.py` `_INTERPRETER_SUBPATH`.
Promotion condition: Windows enters the supported platform set.

### B-022 — Provider values whose trailing whitespace is significant
Status: OPEN
Discovered in: CP-10 / `agent_artifacts/application/runtime_projection.py` / `generate_launcher`
Why useful: the launcher captures a secret with `$(...)`, which strips trailing newlines. A value
that legitimately ends in one reaches the process altered.
Why noncritical now: this is standard POSIX behaviour, every provider CLI in scope emits a trailing
newline of its own that must be stripped, and CP-08 already measures stored length at the provider,
so a truncation is visible there.
Potential approach: a length check at launch against a length recorded in the receipt, or a
provider port that can say whether its output is newline-terminated.
Invariants touched: INV-055, INV-063.
Evidence/links: D-022.
Promotion condition: a provider or artifact is found where trailing whitespace is significant.

### B-023 — Detecting registrations nothing owns
Status: OPEN
Discovered in: CP-11 / `agent_artifacts/application/installed_state.py` /
`current_state_from_observation`
Why useful: `DriftKind.UNEXPECTED` exists and is tested, but nothing can currently produce it from
a real machine. `observe_installation` walks the registrations a receipt names, so a server entry
added by hand — or left behind by a failed uninstall — is invisible.
Why noncritical now: the repair path is about putting right what AART installed. Removing something
AART did not install is an uninstall question, and claiming a stray without a complete picture of
ownership is how a tool deletes somebody's own configuration (D-033).
Potential approach: read the harness settings file whole, subtract everything every receipt in
scope claims, and report the remainder — with ownership metadata so an entry a person wrote is
never mistaken for one AART abandoned.
Invariants touched: INV-058, INV-075, INV-079.
Evidence/links: D-033; `tests/reconciliation_test.py::ComparisonTest::
test_something_present_that_nothing_desires_is_named_and_not_repaired`.
Promotion condition: uninstall or scope-level doctor needs to report orphans (CP-12 or CP-16).

### B-024 — Marketplace and install-flow screens for the canonical consumer shell
Status: CLOSED (2026-08-31)
Discovered in: CP-13 / `agent_artifacts/tui_consumer.py` / `CanonicalScreenSource`
Why useful: the persistent consumer application drew Dashboard, Installed, Activity, receipts,
Registries, Settings and Doctor from canonical views, but screens 02–11 and 15–24 drew "… is not
available yet", and nothing assembled any of it from a real machine.
Resolution: every accepted screen 01–29 now draws from canonical views — Marketplace and
Collections from `MarketplaceEntry`/`MarketplaceCollectionEntry` offers (D-047), 05–11 from a
`ConsumerPlanView` (D-049), 14–20 from installed state and lifecycle views, 22–24 from
`CredentialRecordView` (D-048). `application/consumer_session.py` assembles one `ConsumerMachine`
from what was read of a machine and `tui_consumer.screens_from` turns it into `ConsumerScreens`
(D-051). Ownership had to be persisted first, so Installed can name the Collection that asked for
an artifact and uninstall can retain it (D-050).
Invariants touched: INV-149, INV-152, INV-153.
Evidence/links: D-047, D-048, D-049, D-050, D-051; `tests/consumer_marketplace_shell_test.py`;
`tests/consumer_install_flow_shell_test.py`; `tests/consumer_session_test.py`;
`tests/consumer_session_e2e_test.py` — a real installation, read back by a second process,
inspected, assembled and drawn, with the real secret on no screen.
Remaining: the flow that produces a live `ConsumerPlanView` when somebody starts an install is the
public-command wiring, tracked as CP-13 step 5 rather than here.

### B-025 — Routing the default TTY entry to the canonical consumer application
Status: CLOSED (2026-09-01) — promotion condition met and verified
Discovered in: CP-13 / `agent_artifacts/tui.py` / `run`
Why useful: `run_consumer` exists, is typed, and drives the canonical application over curses, but
nothing calls it — `run()` still opens the legacy wizard. Until it is routed, the canonical shell is
reachable only from tests and embedders.
Progress: `io/consumer_machine.py` reads canonical installation/action records, inspects each
recorded installation once, and assembles the immutable machine used by every screen (D-060).
The first routing attempt was reverted after characterization proved the shell has no action
command beyond navigation/load/quit, its composed source contains no configured Marketplace
offers, and existing public installs live only in the project/user installation manifest. Routing
that source would open an empty, read-only application and hide valid installed artifacts (D-062).
Invariants touched: INV-149, INV-168.
Evidence/links: B-024; D-060, D-061, D-062; `tests/consumer_machine_read_test.py`;
`tests/tui_consumer_entry_test.py`; `tests/consumer_shell_test.py`.
Promotion condition: the canonical shell has typed commands and injected handlers for install,
update, repair and uninstall; configured Marketplace offers are composed into its source; and
existing project/user installation records are adapted or migrated without disappearing.
Closed by: `io/consumer_actions.py` (the production `ConsumerActionHandler`, one composition per
machine), `io/configured_repair_action.py` (the third configured composition beside install and
uninstall, D-086), `io/configured_offers.py` (the Marketplace read, D-088), the `notice` field on
`ConsumerScreens` that draws a refusal instead of raising it (D-087), and the cutover in
`tui.py::run`, which takes the canonical route before any wizard composition so the same local
state is never opened twice. Evidence is `tests/consumer_application_e2e_test.py`: the shell the
curses adapter runs, over the production handler, on a temporary machine with a real configured
registry, object store and receipts -- install, reinstall-converges, verify/repair after a deleted
delivery, uninstall that leaves a neighbour standing, and two refusals drawn rather than raised.
`tests/tui_consumer_entry_test.py` proves the wizard is not even composed on a terminal, and
`tests/tui_fallback_boundary_test.py` proves the internal-failure and no-TTY boundaries on the live
route rather than on the retired one.
Left open by the closure: the shell declines a selection whose inputs it cannot collect (B-032),
`_run_curses` and the legacy wizard composition are now unreachable from `run()` on a TTY (B-039).

### B-026 — Canonical installation-receipt persistence
Status: CLOSED (2026-08-31) — promoted to the critical path and completed
Discovered in: CP-13 / B-024 / `agent_artifacts/io/`
Why useful: canonical installed state could be projected and verified but not kept. Every reader of
`InstallationReceipt` took one as an argument; nothing wrote one down and nothing read one back, so
no canonical installed state survived the process that produced it.
Promotion evidence: B-024 assembles `ConsumerScreens` over canonical services. Installed (12–14),
Updates (15–16) and Activity (25–27) are all projections of installed state and past actions, so
without persistence the canonical shell can only ever draw an empty machine — and CP-13 step 6
cannot retire legacy authority whose one remaining advantage is that it persists
(`receipt_service.py`, `setup_receipt.py`). CP-16 supportability has the same dependency.
Invariants touched: INV-149, INV-152, INV-169.
Evidence/links: D-044, D-045; `agent_artifacts/io/receipt_store.py`; `tests/receipt_store_test.py`.
Closed by: `io/receipt_store.py` (the store), `application/receipt_recording.py` (what a finished
action leaves behind, D-046) and `tests/receipt_persistence_e2e_test.py`, where a real installation
recorded by one store is read back by a second store built fresh over the same directory and every
later decision -- desired state, review digest, repair, timeline -- is made from the receipt on
disk. Assembling those reads into the consumer shell is B-024.

### B-027 — Poetry-locked artifacts have no installer backend
Status: OPEN
Discovered in: CP-13 / `protocol/authoring.py` / `_parse_dependencies`
Why useful: `poetry.lock` is common in the Python artifacts AART is meant to install. Today
`python.dependencies.type: poetry` is refused by name, so such an artifact cannot be authored
canonically at all and its author has to export a requirements file by hand.
Why noncritical now: `domain/python_runtime.LOCK_FORMATS` is `("uv",)` and no effect interpreter can
install from a poetry lock. Accepting the declaration without a backend would be worse than
refusing it: the installer would fall back to the loose `pyproject.toml` and install versions nobody
resolved, which is the exact failure a lock exists to prevent.
Potential approach: add a poetry entry to `LOCK_FORMATS` and an `InstallPythonDependencies`
interpreter path once one exists, then widen `_DEPENDENCY_KINDS`.
Invariants touched: INV-107, INV-108.
Evidence/links: D-055; `tests/authoring_inputs_test.py::DeclaredDependencyTest`.
Promotion condition: a Product Specification section or an acceptance artifact requires installing
from a poetry lock.

### B-028 — Cross-check an input's binding against the transport at authoring time
Status: OPEN (deliberately declined for now)
Discovered in: CP-13 / `protocol/authoring.py` / `_parse_injection`
Why useful: some declarations are decidable as impossible before anyone installs them — a `stdin`
binding on a `stdio` transport would compete with the protocol itself for the same stream, and a
`file` binding needs somebody to write that file, which a generated launcher does not do.
Why noncritical now: D-023/D-024 make the launcher generator the single authority on what a binding
can deliver. A second authority in the parser could disagree with it, and would be the copy nobody
updates when a generator learns a new delivery. The generator already refuses these, with the
artifact's real transport in hand — which the parser does not have at the point it reads `inject`.
Potential approach: if it is worth catching earlier, have the compiler ask the generator rather than
restate its rules, once a compiled artifact is lowered into a `PlannedInstallation`.
Invariants touched: INV-091.
Evidence/links: D-023, D-024, D-054.
Promotion condition: evidence that an artifact reached a consumer carrying a binding its transport
could never deliver.

### B-029 — Verify installed distributions against the declared descriptor
Status: OPEN
Discovered in: CP-13 / `application/installed_state.py` / `current_state_from_observation`
Why useful: the `runtime-dependencies` component is currently reported through the environment that
holds it (D-057), so a package somebody removed or upgraded by hand inside a healthy environment is
invisible. A dependency drifting under an installed artifact is exactly the failure a package
manager exists to catch.
Why noncritical now: the failure that matters most — the environment being gone — is detected and
repaired today, and the observation's detail states what was and was not checked rather than
claiming more than it measured. A real check needs to parse a requirements file or a lock and query
the environment's installed distributions, which is a descriptor parser this build does not have.
Potential approach: ask the environment's own interpreter which distributions it holds
(`importlib.metadata`) and compare against the names the descriptor declares; report
`UNVERIFIABLE` rather than `MATCHED` where a lock cannot be read.
Invariants touched: INV-107, INV-108.
Evidence/links: D-057; `tests/artifact_installation_e2e_test.py`.
Promotion condition: evidence that a silently drifted environment reached a consumer as healthy.

### B-030 — Aggregate installation execution and one transaction receipt
Status: DONE (2026-08-31)
Discovered in: CP-13 / `agent_artifacts/application/consumer_ui.py` / production action handler
Why useful: `InstallationProposal` already holds one bulk `InstallPlan` and all per-artifact
`LifecyclePlan`s, but execution and action recording currently accept only one `LifecyclePlan` and
produce one artifact action receipt. A handler that loops those APIs would turn one reviewed
Selection into N independently recorded actions.
Promotion evidence: INV-130 requires one coherent bulk plan/review boundary and INV-138 requires
one receipt explaining Selection provenance, resolved artifacts, effects and final ownership. The
canonical shell now emits one `EXECUTE_ACTION` for its whole Selection (D-063), so no compliant
production handler can be connected until the application layer can preserve that transaction as
one outcome while retaining per-artifact effect and compensation evidence.
Potential approach: add an immutable installation-transaction outcome keyed by the proposal review
digest; compare every lifecycle plan under one scope lease, execute deterministically, preserve
each artifact outcome and any compensation, then atomically record one action receipt plus the
resulting per-artifact installation records. Project screens 10/11 and Activity from that aggregate
rather than selecting an arbitrary member outcome.
Invariants touched: INV-130, INV-133, INV-138, INV-149, INV-152.
Evidence/links: D-052, D-059, D-063, D-064, D-065; `tests/consumer_ui_actions_test.py`;
`tests/consumer_action_shell_test.py`; `tests/installation_transaction_test.py`;
`tests/installation_transaction_receipt_test.py`; `tests/consumer_transaction_screens_test.py`;
`tests/artifact_installation_e2e_test.py`.
Outcome (2026-08-31): aggregate execution under one lease (D-064), one Activity receipt plus one
installed record per applied member, screens 10/11 drawn from that transaction (D-065), and a real
recorded install re-read from disk into Installed, Collections and Activity (D-066) are verified for
single and multi-artifact Selection, including the partially-applied and never-attempted cases. The
reload needed no new production code, only the acceptance evidence that the stored transaction is
what the next machine reads.
Unblock condition: aggregate execution, durable recording and screen projections are verified for
single and multi-artifact Selection, including partial execution and compensation evidence, and a
recorded transaction is visible to the next assembled machine without hand-built state.

### B-031 — Versioned Collections across the Marketplace composition seam
Status: OPEN
Discovered in: CP-13 / `agent_artifacts/tui_consumer.py` / `read_consumer_offers`
Why useful: the canonical shell now composes real artifact offers from configured sources (D-068),
but not Collections. A protocol-v1 compiled Collection is identified by source and name alone,
while the canonical `Collection` CP-06 established is versioned and bound to the registry snapshot
it was read from. Nothing in the compiled graph supplies that version, so screens 04/04a have no
Collection to draw from a real source.
Why noncritical now: producing one would mean inventing the version that tells two Collections
apart, which is exactly the fabricated identity D-044/D-045 refuse. Declining by name keeps the
absence visible and keeps every offer that *can* be made honest. No accepted screen is blocked from
being reachable; only its content from a live source is.
Potential approach: carry the Collection version and registry snapshot through the compiled graph,
or read Collections from `aggregate_approved_marketplace` directly and let the artifact rows keep
coming from the characterized loader until both move together.
Invariants touched: INV-130, INV-138.
Evidence/links: D-044, D-045, D-068, D-088; `agent_artifacts/io/configured_offers.py::_declined`,
which now declines a canonical Collection by coordinate rather than dropping it.
Re-triaged 2026-09-01 (D-091): the missing version is not fabricated identity, it is an unbuilt
authoring field. Product Specification 145.1 says "A Collection is a versioned set of artifact
selectors/constraints" and its example declares `version: 2.1.0`, but `CollectionManifest` has no
version, `discover_author_manifests` never looks at a collection root, and no Collection has ever
been compiled, promoted or published as a versioned registry artifact. EXECUTION_PLAN CP-14 owns
"collection candidates", so this is CP-14 work rather than an open product question. CP-13 declining
a Collection by coordinate stays correct until a registry publishes one.
Promotion condition: CP-14 reaches collection candidates, at which point the decline in
`io/configured_offers.py::_declined` is removed and screens 04/04a draw from a real published
Collection.

### B-032 — Live input-source and provider-entry boundary for screen 07
Status: PROMOTED TO CP-13 (2026-08-31)
Discovered in: CP-13 / production consumer action handler
Why useful: `placement_for` reads an artifact's declared `InstallDescription`, but
`plan_artifact_installation` correctly refuses a required input with no `InputValueSource`.
Existing screen-07 tests draw already-bound plans, and the authored-package E2E supplies its config
value and provider reference directly; the live shell has no boundary that produces either. A
handler wired without one could browse an MCP offer but could not prepare the accepted Required
Inputs flow, or would have to invent values/references inside planning.
Promotion evidence: accepted screen 07 is on CP-13's mandatory path, and the first production MCP
vertical slice declares both config and secret inputs. The production action cannot reach Ready or
execute that artifact without this boundary, so this is not optional UX polish.
Required shape: derive input rows from the verified install descriptions; prefill only declared
config defaults or previously persisted safe config; bind secrets to explicit provider references;
inspect provider state without reading a value; and let provider-owned interactive entry store or
replace a value without it entering application state, plans, receipts, logs or JSON. Required
config with no value must remain an unanswered form field, never a guessed default.
Invariants touched: INV-132, INV-149, INV-155, INV-156, INV-157, INV-165.
Evidence/links: D-054, D-056, D-074; `application/input_binding.py`;
`tests/artifact_installation_e2e_test.py`; accepted Product Specification screen 07.
Unblock condition: the real action adapter can prepare and complete an authored MCP with config and
secret declarations through provider references/provider-owned entry, while the secret value is
absent from every application value and serialized/drawn surface.

### B-033 — Canonical installation is MCP-shaped and cannot record four of the five kinds
**Classification: CRITICAL PATH.** Reclassified from backlog on evidence, per the rule that an item
becomes critical when it can be shown that a critical-path slice cannot complete without it.

**Status: COMPLETED and verified.** `PlacedArtifactReceipt`, delivery effects, receipt persistence,
observation, placement/interpreter composition and the configured action now carry Skills and
guidelines. A real authored Skill crosses compile/scan/promote/publish, configured resolution,
review, execution, durable reload, drift detection and reverse uninstall. Hooks and shared-file
memory remain B-034 because they require merge semantics rather than replacement delivery.

Before B-033, the canonical install pipeline refused any artifact that did not declare a launch
contract:

- `plan_artifact_installation` returns `INSTALLATION_NOT_DESCRIBED` when `description.contract is
  None` -- "does not declare how it starts, so there is no launcher to generate and nothing for a
  harness to run";
- `PlannedInstallation` requires both a `LaunchContract` and a `RuntimeProjection`;
- `InstallationReceipt` requires `launcher`, `launcher_digest`, `interpreter` and `transport`, none
  of which a Skill, guideline, hook or memory has.

A manifest may declare five kinds (`skill`, `guideline`, `mcp`, `hook`, `memory`). Only `mcp` starts
a process. So four of the five cannot be planned, executed, recorded or reconciled canonically, and
`install_state` remains the only thing that can describe them -- which is why D-069 had to carry
them as unadopted rather than adopt them.

**Why this blocks the critical path.** `NEXT.md` item 6 retires the legacy consumer authority path
by path, each removal preceded by a public-flow test proving the canonical path already carries that
behavior. For a Skill there is no such test to write: routing `install` to the canonical adapter
would refuse four kinds that install correctly today. Item 6 is the bulk of what remains in CP-13,
and it cannot start on the artifact kinds that are not MCP servers.

**Shape of the work.** An installation whose payload is placed and registered but which starts no
process: a receipt whose launcher/interpreter/transport are absent rather than invented, a desired
state built from payload and placement without a launcher component, and reconciliation that does
not read the absence of a process as drift. The narrowest safe version keeps `InstallationReceipt`
as the MCP case and introduces the kind-neutral record beside it; widening the existing type by
making four required fields optional would let an MCP receipt lose its launcher without any type
noticing.

**Alternative if this is deferred.** Route only `mcp` coordinates through the canonical adapter and
leave the other four kinds on the legacy path, with the split made explicit at the seam rather than
implicit. That is a strangler boundary rather than a workaround, but it leaves two installers live
for longer and `install_state` cannot be retired while it holds records nothing canonical can read.

## B-034 — A hook and a shared memory file need a merge effect, not a delivery

**Classification: CRITICAL PATH for `NEXT.md` item 6, after B-033. DONE — memory under D-084,
hooks under D-085.**

**Memory is closed.** `MergeManagedBlock`/`UnmergeManagedBlock` at `CONFIGURATION_MUTATION`, the
`ManagedBlockInterpreter` bound to the (destination, region) pairs it was given, `MEMORY_TARGETS`
measured per harness and scope, `package_merge` reading the body back out of the compiled package,
`ArtifactMerge` on the placed receipt, and a `MERGE` reconciliation component measured by digesting
the region rather than the file. A memory artifact now installs, reports health, detects an edited
block as drift, ignores the user's own notes beside it, and uninstalls leaving the file standing --
proven end to end through the public command in `tests/merged_installation_e2e_test.py`.

**Hooks are closed too.** `MergeSettingsEntry`/`UnmergeSettingsEntry` at `CONFIGURATION_MUTATION`,
a `SettingsEntryInterpreter` bound to the `(destination, path, entry)` triples it was given,
`HOOK_TARGETS` holding the script directory, settings file, event map and entry shape as one
measured fact, `package_hook` reading the declaration back out of the compiled package,
`ArtifactSettingsEntry` on the placed receipt, and a `SETTINGS` reconciliation component measured
against the entry as the file spells it now. The entry is typed rather than rendered from a
`${...}` template, so nothing untyped sits between the review and the write. A hook now installs
both halves together, reports health, detects an edited entry as drift, ignores another hook added
beside it, and uninstalls taking its entry and its script while leaving the settings file and every
other hook intact -- proven end to end in `tests/hook_installation_e2e_test.py`.

`payload/hook.json` was strengthened rather than worked around: `event` and `matcher` are now
required beside `name` and `command`, because without them a package compiles into something
nothing can place, and the author is the only person who can still fix that.

B-033 makes an artifact installable by being delivered where a harness reads it, which is the whole
of a Skill and a guideline. Two of the five kinds are not only that:

- a **hook** is a script placed in `hooks/<name>/` *and* an entry merged into a list inside a
  settings file (`.claude/settings.json` at `hooks.PreToolUse`, `.tabnine/agent/settings.json` at
  `hooks.BeforeTool`), with an identity of `(matcher, command)` and a profile-owned entry template;
- every measured **memory** target is `kind="file"` -- `CLAUDE.md`, `TABNINE.md`, `AGENTS.md` --
  where the artifact's body is inserted as a delimited block into a file the user owns and edits,
  not written as a file of its own. Only a profile in directory mode makes memory a delivery.

Neither is `DeliverArtifact`, which replaces a destination. Replacing `CLAUDE.md` would destroy
everything the user wrote in it, and replacing `settings.json` would remove every hook and MCP entry
in it. `ConfigureHarness` is the nearest canonical effect and it is MCP-shaped: it takes an
`McpRegistration` and writes one server under a key.

**Shape of the work.** A merge effect that owns a named region of a file it does not own: the key
merge `ConfigureHarness` already performs, a list merge with an identity tuple, and a delimited
block in a text file. Withdrawal removes only that region, and the rest of the file is evidence that
must survive. The legacy engine already does all three (`installation/application.py`
`_render_template`, `_memory_block`, and the merge specs in `profiles/builtin.py`), so this is
characterization before replacement rather than new semantics.

**Why it is deferred rather than folded into B-033.** The Product Specification's own migration
order is MCP, then skills, then guidelines/rules, then memory, then hooks. Delivery closes skills
and guidelines with the effect they actually need; inventing a merge effect at the same time would
be designing for hooks before anything exercises them. Item 6 can retire legacy authority for the
delivered kinds first, and this item is what unblocks the last two.

## B-035 — Canonical public installation has no symlink placement effect

**Classification: BACKLOG; required before removing the legacy install route if `--mode symlink`
remains part of the public contract.**

The first direct-RegistryGit command route deliberately supports copy mode. The canonical delivery
and owned-payload effects materialize copies and record their digests; no reviewed effect describes
a live symlink or its target ownership. Silently accepting `--mode symlink` and making a copy would
therefore execute a different plan from the one the operator requested, so D-079 refuses it by name.

Before the legacy route can be removed, either characterize and implement a symlink placement,
observation, receipt and safe withdrawal path, or explicitly remove the option through a product
decision. Do not approximate it with `DeliverArtifact`: the Product Specification distinguishes the
copy/symlink relationship, and CP-04's package boundary forbids importing source symlinks for a
different reason.

## B-036 — Registry lifecycle has nowhere to appear on a Marketplace row

**Classification: BACKLOG; required before a registry can deprecate a version and still have it
installable through the canonical shell.**

`MarketplaceArtifactRow` carries trust, compatibility, digests and installed status, but nothing
that says the registry has deprecated a version or named a replacement. `RegistryLifecycle` is
`published | deprecated | revoked`, and the compiled graph's `ArtifactLifecycle` only distinguishes
available from removed, so the two facts cannot be rendered as one.

Until the row can say so, `read_configured_marketplace` declines a deprecated version by name rather
than offering it silently (D-088). Offering it without the warning would be the Fast projection
hiding material risk; dropping it without a word would read as a registry that approved nothing.
A revoked version stays declined regardless.

**Shape of the work.** Carry `RegistryLifecycle` and `lifecycle_reason`/`replacement` through
`IndexArtifact` into `MarketplaceArtifact`, add them to the row, and render the reason on screens
03/04a beside compatibility. Then offer deprecated versions again, ranked below published ones when
choosing which version a row stands for.

Evidence/links: D-088; `tests/consumer_marketplace_composition_e2e_test.py::ComposedMarketplaceTest
::test_a_deprecated_version_is_declined_by_name_rather_than_offered_silently`.

## B-037 — Incremental promotion left earlier version records bound to a stale snapshot

**Classification: PROMOTED TO CRITICAL PATH, then FIXED. Reclassified 2026-09-01.**

**Why it was reclassified.** Filed as backlog on the belief that only fixtures were affected. It is
in fact a correctness defect on a routed public command. `RegistryArtifactVersion.registry_snapshot`
binds every approved version to one digest of the registry's `artifacts/` and `references/` trees.
`plan_bulk_promotion` rewrote `registry/versions/*.json` only for the versions in its own
transaction, while `registry/index.json` and `registry/snapshot.json` received the new content
digest. So the *second* promotion into any registry left every earlier record naming a digest that
no longer existed, and `load_registry_versions` refused the whole snapshot with "registry versions
do not bind one exact approved content snapshot". Every consumer of that registry was then locked
out -- not just a test fixture. Reachable from `aart registry promote`
(`agent_artifacts/commands/registry.py:800`). That is a mandatory-invariant break on the critical
path, so it was promoted and fixed rather than deferred.

**Fix.** `plan_bulk_promotion` now rebinds every retained approved record to the snapshot the same
reviewed transaction produces, inside that transaction, and writes those records as mutable changes.
The version record set and the catalogs therefore always agree. This is metadata only: the package
at a published coordinate never moves. Recorded as D-089.

**Evidence.** RED-first in `tests/promotion_planning_test.py`:
`test_a_registry_stays_readable_after_a_second_promotion` (two transactions, both coordinates read
back, one shared `registry_snapshot`) and
`test_a_second_promotion_leaves_the_first_package_byte_identical` (the rebinding does not touch
published content). Three-transaction fixture proven through the real pipeline in
`tests/configured_installation_draft_e2e_test.py::_published_registries`.

**What it unblocked.** `tests/consumer_marketplace_composition_e2e_test.py::
test_a_row_stands_for_the_highest_approved_version_of_its_identity` -- the end-to-end evidence for
D-088's rule that a row is the highest approved SemVer of an identity and an older approved version
is superseded, not declined.

Evidence/links: D-088, D-089; `agent_artifacts/application/promotion.py::plan_bulk_promotion`,
`::validate_promoted_registry`, `::load_registry_versions`.

## B-038 — Native source content has no canonical consumer path

**Classification: PARTLY CLOSED (2026-09-02) — screen 21 now lists the configured sources and says
why a native one offers nothing (D-114). What remains is in `aart marketplace install`, not in the
now-deleted wizard — see the restated section below. Was re-triaged 2026-09-01 as a CP-14 dependency
rather than an open product question; see D-091.**

Under INV-026 the canonical Marketplace projects configured *registries*, so an enabled
`SourceKind.SOURCE_GIT` or `SOURCE_LOCAL` source now contributes its health to the source list and
offers nothing (D-088). The legacy read-only loader did offer its artifacts, but nothing downstream
could install them: `resolve_configured_selection` acts only on approved `registry/versions/*`
records, so those offers were advertising an action the shell had to refuse afterwards.

**What the Product Specification already answers.** Section 1737 lists Source as the set of
origins a *registry* pulls from (GitHub, GitLab, internal Git, HTTP, OCI, PyPI, npm, local), and
INV-019 through INV-026 describe consumer installation entirely over approved registry content:
"Installing an approved vendored registry artifact uses the registry snapshot, not the author
repository" (INV-021). CP-14 owns the Sources screens 31-34. So a direct source is a maintainer's
Candidate feed, and the canonical consumer seam listing it while offering nothing is the specified
behavior, not a gap.

**Done (D-114).** Screen 21 says it. Fixing the wording first exposed that the screen was drawing
nothing at all: nothing on the composition path ever projected the configured sources, so a machine
with two configured registries opened on an empty screen 21 and a dashboard reading "0 registries".
`read_consumer_offers` now carries `project_registries` output on `ConsumerOffers`, `screens_from`
takes it, and a row that is not a registry says so and offers `details` only rather than a sync
whose advertised effect it cannot have.

**What is left, restated (2026-09-02).** This said the remaining work was to remove the *legacy
route's* direct-install authority. That route is gone — the wizard front-end was deleted in D-117 —
and the residue is not where this item put it. It is in a public flow:
`commands/marketplace.py::_configured_registry_selection` returns `None` for a direct or local
source, which sends `aart marketplace install` down the characterized path that installs from it.
Its own docstring says as much: "Collections and direct/local sources stay on the characterized path
until their own public replacement evidence exists."

Screens 31–34 hold the canonical Source capability (D-093–D-097), including a real local Source Sync
that creates Candidates without promotion, so the evidence the docstring waits on now exists for
Sources. The remaining step is therefore a characterized test of `aart marketplace install
<direct-source-artifact>` and then the decision INV-021 already implies: a direct source is a
maintainer's Candidate feed, so installing from one is refused rather than routed. Collections are a
separate half and stay sequenced behind their own evidence.

**What is left, measured (2026-09-03).** The step above asked for "a characterized test of `aart
marketplace install <direct-source-artifact>`, and then the decision". The characterization already
exists and is thorough: `tests/marketplace_lifecycle_e2e_test.py` configures one real
`SourceKind.SOURCE_LOCAL` source, synchronizes it for real, and drives 27 end-to-end tests of this
exact command against it -- copy install, collection install, managed-symlink install, user-scope
install, update, forced reinstall, uninstall, setup review and authorized setup. Every one of them
routes through the `None` this item names, because `_configured_registry_selection` returns `None`
as soon as no enabled `REGISTRY_GIT` source exists.

So what remains is only the decision, and the decision is not a small one. Two of the three reasons
the seam declines are **missing canonical capabilities, not policy**:

- **Collections.** `_configured_registry_selection` returns `None` for any collection selector. The
  canonical seam expands no Collection, so `test_collection_install_materializes_every_expanded_
  member` has no canonical equivalent to move to.
- **Symlink mode.** `_configured_lifecycle` refuses anything but `--mode copy` outright
  ("approved registry installation currently supports copy mode only"), so
  `test_managed_symlink_install_produces_a_link_into_the_object_store` has none either.

Refusing direct-source installs today would therefore remove three working, characterized
capabilities at once -- direct/local installs, Collection installs and symlink installs -- and only
the first of those is what INV-021/INV-026 argue about. The other two are the canonical route not
being finished. **Sequence the capabilities first**; the routing question is answerable cheaply once
they exist, and is a product decision either way.

The routing decision itself is now pinned by `tests/marketplace_install_routing_test.py`, which
names each reason separately, so closing either capability turns exactly one test red rather than
leaving the route to be re-derived.

**Why it is noncritical now.** Nothing installable was lost: the CLI still operates direct and local
sources, and the canonical shell no longer offers what it cannot carry out.

Invariants touched: INV-026, INV-024.
Evidence/links: D-088, D-093–D-097, D-114; `tests/consumer_registries_screen_test.py`;
`tests/consumer_marketplace_composition_e2e_test.py::ComposedMarketplaceTest
::test_a_source_that_is_not_a_registry_is_configured_but_offers_nothing` and
`tests/maintainer_composition_e2e_test.py`.

## B-039 — The legacy wizard is unreachable from the default terminal route

**Classification: CLOSED (2026-09-02) — the wizard front-end is gone (D-113, D-116, D-117). The
stack it stood on is not legacy and stays: see the corrected finding below.**

With B-025 closed, `run()` composes `_canonical_consumer_actions` and calls `run_consumer` before
any wizard composition, and the legacy `try: _run_curses(...)` block was deleted. `_run_curses`
itself remained defined and exercised by `tests/tui_curation_test.py`,
`tests/tui_wizard_curses_test.py` and `tests/tui_fallback_boundary_test.py`.

**Done (D-113).** `_run_curses` is deleted, with `_legacy_setup_stage_failure` and
`_run_post_install_setup` (it was their only caller) and the five tests that existed solely to drive
it. The acceptance evidence pre-existed and needed no new test: `run()` never reached it, and ERR05
is pinned on the canonical `run()` by `tests/tui_fallback_boundary_test.py`. The wizard's curses
*primitives* stay — they are still composed by the surviving stages and still covered.

**Done (D-115, D-116, D-117).** The text route became the canonical application, which unblocked
the removal of `_run_text` and then of the wizard stages themselves. `tui.py` falls from 5,705 lines
to 2,747. Do not remove the text *route*: no-TTY is a supported environment, and it is now the
canonical application.

**Corrected finding.** This item said to "retire the wizard's semantic authority path by path --
`consumer/application.py`, `lifecycle/application.py`, `installation/*`, `setup_engine/*`". That is
wrong and is not remaining work. `commands/marketplace.py` — the public `aart marketplace
install|update|uninstall|setup` command — composes `ConsumerApplicationService` directly and runs
the setup queue through it, and `tui_marketplace.py`, which the canonical shell imports, takes
`LifecycleItem` and `InstallMode` from `lifecycle/model.py` and `installation/model.py`. The stack
is load-bearing for a public flow; it is not legacy authority awaiting a strangler. What it *does*
expose is B-044: the canonical shell reaches none of it, and so performs no post-install setup and
offers no usage report.

Evidence/links: D-062, D-087, D-113, D-115, D-116, D-117, D-118; B-025, B-044;
`agent_artifacts/tui.py::run`.

## B-040 — The secondary file-diff bound is spent in path order, not shared between files

**Classification: NONCRITICAL.** INV-202 requires the raw canonical file diff to be bounded for
terminal rendering, and it is: `_file_changes` spends one global budget of `_MAX_FILE_DIFF_LINES`
(200) across the whole Candidate, per-line truncation at 512 characters, and a 256 KiB per-file
content ceiling above which the file reports "binary or oversized content differs".

The budget is consumed in manifest path order, so one large early file can exhaust it and leave
every later changed file rendering "content omitted by the global diff bound" — including a small,
security-relevant change that a maintainer specifically opened the diff to read. The status line for
each file is still correct and the semantic diff, which is the primary review surface, is unaffected.

A fairer spend would be per-file rather than global, or a bound the maintainer can move on demand
for one focused file. Neither is required to satisfy INV-202 or to complete any CP-14 screen, so
this stays off the critical path.

Discovered while wiring screens 35–37 (D-098).
Evidence/links: `agent_artifacts/application/maintainer_views.py::_file_changes`; INV-202; 164.5.

## B-041 — A local-Source Candidate has no promotion audit record

**COMPLETE 2026-09-02 (D-107).** This was critical before screens 41–47 could be called complete.

A promotion audit recorded only a 40-hex Git revision, while a local Source carries
`local:<snapshot-sha256>` (D-096). `plan_candidate_promotion` therefore refused a local-origin
Candidate by name, and screen 43 stated that refusal. This was found by regression, not by review:
the planner *raised* on such a
Candidate rather than returning an error, and `read_maintainer_views` caught the `ValueError` and
failed the whole Maintainer composition — which stalled the Source Sync walk at screen 33 with no
message. The E2E that syncs a real local Source is what caught it.

The original unblock condition was to give the audit record a place for local provenance so local
Candidates could be promoted without disguising a local snapshot as a commit, then replace the
refusal. Two direct unit cases were dropped because the fixture for a local authoring Source needed
a filesystem `source` rather than a Git URL; the behaviour was covered only by
`tests/maintainer_composition_e2e_test.py`'s local-sync walk.

Resolution: `PromotionAudit` now carries a discriminated `source_provenance`. Git provenance has a
40-hex `git_revision`; local provenance has a typed SHA-256 `snapshot_digest`. New audit JSON uses
that structured shape, canonical legacy Git-only records remain readable, and the reader explicitly
rejects a local pin in the legacy Git field. The single and bulk by-name refusals are gone without
adding a second planner or transaction path. Direct planning/projection tests use a filesystem
source location, and the production E2E now takes a real local Source through sync, promotion,
registry validation and one clean local commit while matching the audit digest back to the durable
Candidate-history pin.

## B-042 — A multi-registry installation cannot attribute its checkout to a registry

Discovered while landing screen 46. D-103 binds promotion to the configured installation's project
root as the one writable registry checkout, and the accepted configuration schema carries a registry
source URL but no per-registry checkout path. With two or more registries configured there is
nothing that says which one the project root is, and guessing would report a divergence that is
really a mismatch of registries. Screen 46 therefore observes the checkout only when exactly one
registry is configured and reports it unobserved otherwise.

What remains: give a configured registry an explicit checkout path, or identify a checkout from the
registry it declares itself to be, so working-tree state is answerable for every registry. Not
required for CP-14: promotion itself already targets one Candidate's registry through the project
root, and the single-registry case is what the accepted flow supports.

## B-043 — Screen 47 draws its selection count twice

Discovered while proving the bulk transaction end to end. `render_maintainer_bulk_promotion` ends
with its own `"N selected"` line and the shell chrome appends the same count, so the frame reads
"2 selected" twice. It is cosmetic and no test depended on the duplicate, so it was left alone
rather than widened into the transaction increment.

What remains: decide which of the two owns the count -- the chrome states it for every selectable
screen, so screen 47's own line is the likely one to drop -- and pin it with a rendering test.

## B-045 — A canonical install roots nothing in the content store

Measured while building B-044's fixture, and independent of it. After `aart marketplace install`
of a registry Skill there is no references file anywhere in the data root: the configured seam
registers no `ReferenceKind.INSTALLED` for the object it materialized from, while the legacy path
does (`installation/io.py:495`). Every reference kind that exists -- `INSTALLED`, `SETUP`,
`SOURCE_CURRENT`, `RETAINED`, `ROLLBACK`, `TRANSACTION` -- is written by legacy modules or the setup
engine, none by `io/configured_installation_action.py`.

So an object a canonical installation depends on is unrooted. Nothing observed here collects it, so
this is not a live defect today; what it means is that the reference store's account of what is
in use is silent about every canonical install, which is exactly the thing a future collector would
consult.

What remains: decide whether the canonical seam should register an `INSTALLED` reference, and if so
where it is released -- uninstall and update both have to move it, which is why this is not a
one-line addition. Related to B-044's installed-record question, but not the same question: this one
is about the store's rooting, that one is about the receipt naming the object at all.

## B-044 — The canonical consumer shell runs no setup queue and offers no usage report — CRITICAL

**Resolved on 2026-09-03 (D-128).** Both configured front ends now compose the public setup engine
from receipt-backed evidence and offer privacy-bounded usage reporting. Explicit CLI effect
approval and shell terminal consent are proven on the real promoted fixture; omission/refusal
applies no setup effect; `marketplace setup` recovers the declined canonical install. The detailed
history below is retained because it records the RED and the rejected planner fork.

Discovered while retiring the wizard front-end (D-117), recorded in full as D-118. **Reclassified
from backlog to critical path:** the Product Specification names interactive setup as work AART
performs, and screens 09 and 11 summarize an install's outcome as "configured MCP servers, isolated
environments ... securely stored credentials". Since D-115 put the canonical application on both
terminal routes, `io/consumer_actions.py::_execute_installation` reaches
`complete_configured_installation`, which runs no setup queue and offers no usage report — so an
artifact installed from the TUI that declares setup requirements lands unconfigured. That is a
mandatory invariant a shipped path no longer satisfies, which is the evidence the reclassification
rule asks for. ~~The public `aart marketplace install` carries both and is unaffected.~~ That
last sentence is false and was corrected on 2026-09-02: `install` carries setup only for a
direct or local Selection. For an approved registry coordinate it reaches the same configured
seam the shell does and skips setup identically — see the fixture evidence below and D-120.

### Review of the first attempt (2026-09-02) — preserved, not merged

Codex began this and was cut off mid-work by its own rate limit, so what follows reviews a **draft**,
not a submitted result. It is preserved on branch `codex-wip/b-044-draft` (`e40a80d`) rather than
discarded: the diagnosis in it is right even where the implementation is not.

It added a `_ConfiguredSetupService` inside `io/consumer_actions.py` that reimplements the setup
engine's planning against the configured installation's receipt, plus a `completion` on
`ConsumerActionUpdate` that the shell runs with the terminal. **All 3,216 unit tests passed with it
applied**, which is the most important thing the review found: nothing in the suite exercises trust
or authorization on the new route, so the gap this item describes is invisible to the gates.

Blocking defects, worth naming so the next attempt does not repeat them:

1. **The untrusted-source authorization gate is bypassed.** The draft calls
   `_policy_allows(request, TrustClass.COMPANY_REVIEWED, ...)` with that trust as a literal, and
   writes `trust=TrustClass.COMPANY_REVIEWED.value` into the persisted setup record.
   `setup_engine/application.py::_policy_allows` refuses setup from `UNVERIFIED`, `LOCAL` or
   `DIRECT_SOURCE` unless `authorize_untrusted_source` is set — a refusal that can never fire when
   the trust is a constant. It also passes the registry snapshot digest as
   `trust_evidence_digest`, which is a different value space, so the engine's own re-check that
   trust has not moved since review (`application.py:599`) would compare against something that
   never described trust.
2. **Evidence is fabricated to satisfy a type.** `ConsumerReview` is built with
   `sha256_bytes(b"unreviewed-consumer-action")` as its review digest and literal
   `"company-reviewed"` / `"low"` per item. A review digest exists to bind a review; a placeholder
   in that field is worse than an absent one.
3. **The layering inverts.** `io/consumer_actions.py` imports `agent_artifacts.tui` (lazily, inside
   a method, to dodge the cycle) so the IO layer depends on the terminal module.
4. **A second key interpreter.** `key_event` grows a `prompt=True` mode that returns
   `PROMPT_INPUT` for any printable key, bypassing the state machine, and it is called from the
   action handler while `completion.run(terminal)` drives `terminal.key()` straight from the shell
   loop. "`key_event` remains the only key interpreter" is a critical boundary of this slice.
5. Private cross-module imports (`installation.io._write_atomic`,
   `setup_engine.application._planned_capabilities` and `._policy_allows`), an unguarded
   `next(...)` over recipe entries that raises `StopIteration` when the entry is absent, and
   `platform = "darwin" if sys.platform == "darwin" else "linux"`, which makes Windows Linux.

**What the draft got right, and what it exposes.** Its own docstring names the real obstacle: "The
setup engine's public facade still reads the older install-state manifest. The configured
installation is authoritative in the receipt store instead." That is exactly the problem, and it is
why this is a slice rather than a wiring change. `setup_engine.application.prepare_setup` is already
the correct entry — it derives real trust from `item.trust.kind`, checks that the indexed setup
recipe, platforms and capabilities match the compiled object, and binds policy before planning — but
`_prepare_setup_object` reaches the installed record through `ports.read_state(...)` on the
install-state manifest, which only `installation/application.py` and `lifecycle/application.py`
write. The canonical configured installation writes receipts instead, and nothing in
`agent_artifacts/` writes install state on that path.

So the slice is about reconciling those two records, and the choice is between: (a) having the
configured installation also write the install-state record the engine reads, or (b) widening the
engine's object preparation so the installed record can be named from the receipt store as well —
keeping every trust, evidence and policy check inside the engine either way. What must not happen is
a third implementation of the planning that re-derives those checks, because that is where the trust
constant came from.

### Why there was no test to catch this (2026-09-02)

Two facts found while trying to write the characterization test. Both change what this item costs,
and the first one has to be settled before any of it can be proven end to end.

**Nothing published through the authoring pipeline can declare setup.** The string `setup` does not
appear anywhere in `agent_artifacts/protocol/authoring.py`: the authored `aart.json` accepts
`transport`, `runtime`, `launch`, `requirements`, `inputs`, `python`, `credentials`, `compatibility`
and `install`, and no setup reference. `compile_author_snapshot` therefore never emits one. The
native and registry schemas do support it -- `protocol/native_schema.py` parses a setup reference on
an artifact manifest, `protocol/registry_schema.py` parses it on the registry index, and
`setup_engine/application.py::_prepare_setup_plan` checks the *indexed* setup recipe, platforms and
capabilities against the compiled object -- so a setup-declaring artifact reaches a registry through
a native promotion (`registry promote-native`, `vendor`, `scaffold`), never through author-compile.

Every consumer E2E harness publishes through `_published_registry(...)`, which is the author-compile
route. So none of them can produce a setup-declaring artifact, and the first deliverable of this
item is a fixture that puts one into a published registry through the native route. It must go
through the real promotion pipeline: hand-patching a `setup` block into a published snapshot changes
the package, and the version record's canonical, payload and object digests would no longer resolve.

**No end-to-end test anywhere installs a setup-declaring artifact from a registry -- on any route,
CLI included.** (Closed on 2026-09-02 for the native-source route; see below.) The closest is
`marketplace_lifecycle_e2e_test.py::test_setup_on_an_artifact_that_declares_none_completes_with_an_empty_queue`,
which is the empty case, and `marketplace_lifecycle_cli_test.py`'s planning-failure assertions,
which are unit-level against a hand-built fixture. So the setup path has never been proven from a
published registry at all. That is why the gap this item describes was invisible, and it is also why
the fixture above is worth more than the wiring: it is the missing evidence for the CLI route as
much as for the TUI one.

**The route in.** `--setup-recipe` is on `aart registry vendor`, not `registry scaffold`
(`cli.py:1035-1054`; an earlier revision of this entry named the wrong subcommand).
`registry_commands/planning.py` requires the named recipe and a `SETUP.md` beside it (line 872) and
carries `manifest.setup.recipe` and `.platforms` into the built index (line 1122).

### The fixture exists, and the gap is wider than this entry said (2026-09-02)

`tests/configured_setup_gap_test.py` now installs a setup-declaring registry artifact on both
routes, and `tests/configured_installation_draft_e2e_test.py` grew the fixture that makes one:
`AuthoredSetup` plus `_with_setup`, threaded through `_promote_one`, `_published_registries` and
`_published_registry`, and through `_environment(authored=..., setup=...)` in
`tests/configured_install_command_e2e_test.py`.

The fixture does not hand-patch a published snapshot. It adds the declaration between compiling and
promoting -- `artifact.json` gains its `setup` reference, `setup/installer.json` and `SETUP.md`
arrive beside the payload, and `compile_native_package` recompiles the package around them, so every
digest is derived rather than asserted and the recipe goes through the same strict parse a vendored
one does. The payload is untouched, so the payload digest still describes it. The whole real
promotion transaction then runs: `reconcile_source_scan` -> `assess_candidate` ->
`plan_bulk_promotion` -> `publish_registry_version` -> `plan_registry_lifecycle`, and the published
snapshot carries `artifacts/skill/code-review/1.2.0/setup/installer.json`.

Two constraints found while building it, both enforced by `compile_native_package`: a setup
declaration's platforms must be a subset of the artifact's, and `setup.py:562` requires the recipe's
own `platforms` to be exactly `['darwin']`. An artifact whose `aart.json` declares no
`compatibility.platforms` therefore cannot declare setup at all, which is why the fixture Skill
names its platforms where `AUTHORED_SKILL` does not.

**What the fixture proves changes this entry's headline.** `aart marketplace install` does *not*
carry setup for an approved registry coordinate. It reaches `_configured_lifecycle`, which calls
`complete_configured_installation` and emits its receipt payload -- there is no `setup` key in it
and no diagnostic -- exactly as the shell's `_execute_installation` does. Setup runs only on the
legacy path, which `_configured_registry_selection` routes to by returning `None`, and it returns
`None` only for a direct or local source. So the gap is the configured canonical seam itself, not
the shell's use of it, and both front ends report a finished install of an unconfigured artifact.

`aart marketplace setup` does not recover it either: run against the same machine afterwards it
refuses with `registry company has invalid root manifests`, because it resolves through the legacy
catalogue, which reads root manifests a promoted registry snapshot does not carry. So there is no
operator move that finishes the install by hand.

### The working route is now proven, and every gate on it (2026-09-02)

`tests/marketplace_lifecycle_e2e_test.py::DeclaredSetupE2ETest` takes a declared setup all the way
through the CLI on a real machine, which nothing did before: the only existing coverage over a real
machine was the empty case, and everything else was unit-level against a hand-built install state.
It uses the writable copy of the shared native-source fixture that `_Environment`'s docstring
described and no test had taken, taught to declare setup the way a native source carries one -- a
`setup` reference on `artifact.json`, `setup/installer.json` beside the payload, a package-root
`SETUP.md` -- so the source is compiled, validated and synchronized as it stands.

Four boundaries, each asserted rather than assumed:

- `install` on this route **names the setup it did not run**, under a `setup` key with the reason.
  The same install through the configured seam emits no `setup` key at all. That contrast is the
  clearest statement of this item.
- Setup from a source that is not company-reviewed **refuses without `--authorize-untrusted-source`**,
  even with the effects approved.
- Authorizing the source produces a reviewed plan and **applies nothing**: the review names each
  effect's target, capability and recovery, and the run reports `cancelled` with the file absent.
  Trusting a source and approving an exact change to an exact file are two answers.
- Both together write the delimited managed block, and `configured` is 1.

The class is `skipUnless(darwin)` because `setup.py:562` accepts only `['darwin']` recipes, so a
non-macOS run is refused for the platform before any of these boundaries is reached.

**This is the test the preserved draft needed.** Applying that draft's hardcoded
`TrustClass.COMPANY_REVIEWED` in `_prepare_setup_plan` now fails two of the four -- the trust gate
stops refusing and the install stops reporting why setup is outstanding -- where previously all
3,216 tests passed with it in place.

### The installed-record question, measured (2026-09-02)

The entry above framed this as a choice between two equally-informed options. It is not: one of them
has a fact against it.

**A canonical receipt does not name the object that was installed.** After `aart marketplace
install` of the fixture Skill, `<data_root>/state/installations/*.json` holds the coordinate with its
version, `payload_digest`, `root` and the deliveries -- and no object digest, no manifest digest.
`install_state`'s `ArtifactEvidence` carries `manifest_digest`, `payload_digest` and `object_digest`.
`_prepare_setup_object` needs the object digest to `read_object` at all, and the manifest digest to
cross-check what it compiled. So widening the engine to read the receipt store is not reading the
same facts from a different file; the facts are not recorded.

**And the canonical seam registers no CAS reference at all.** There is no references file in the
data root after a successful configured install, while the legacy path registers
`ReferenceKind.INSTALLED` (`installation/io.py:495`). The object a canonical install materialized
from is therefore unrooted in the content store. That is worth examining on its own account,
separately from setup.

So the two answers, with their real costs:

- **Give the canonical receipt the object identity it lacks**, then widen the engine's object
  preparation. This is the honest fix for the finding above -- a receipt that records what the
  effects left behind but not which immutable object they came from cannot support setup, and
  arguably cannot support a faithful repair either. It is a schema addition to a durable store, so
  existing receipts must stay readable. The other half is still anchored on the manifest: `persist_setup`
  (`setup_engine/io.py:89`) records that setup ran by replacing `setup_state_ref` inside the
  install-state record under its lock, and `setup_receipt.locate_setup_record` reads that pointer
  for `aart marketplace receipt show|verify|undo`.
- **Have the configured installation also write the install-state record.** This does *not* make
  canonical installs surface as unadopted -- `read_consumer_machine` drops a manifest record whose
  coordinate a canonical receipt already answers for (`io/consumer_machine.py:362`) -- and the seam
  holds every required field truthfully at completion, `EffectProof` destinations and digests
  included. It is the smaller change and makes the whole existing setup subsystem work at once. It
  also writes new records into the store the strangler is retiring.

Ordering that now follows: (1) done -- the fixture and the characterization are in
`tests/configured_setup_gap_test.py`, which asserts the absent configuration file on both routes and
guards itself with a test that the approved registry really does declare setup; (2) done -- the
canonical receipt now names its object (D-122): `object_digest` on both receipt shapes, populated
from the `RegistryArtifactVersion` the Selection resolved, optional so records written before it
still read, and pinned end to end by `tests/installed_object_identity_test.py`, which asserts the
recorded digest resolves to a real object whose manifest is the installed package's; (3a) done --
both front ends now *name* the setup they did not run (D-123): `complete_configured_installation`
reads the objects it recorded and carries `pending_setup`, `aart marketplace install` emits an
additive `pending_setup` key and renders it, and the shell draws it under screen 11's success.
Half of `tests/configured_setup_gap_test.py` inverted; what it still characterizes is that the work
is not done; (3b) reach the setup engine from the configured-installation action so the work is
actually performed, and invert the rest.

Two things step (2) deliberately did not do, and step (3) still has to answer. The engine takes a
legacy `MarketplaceCatalog` (`resolve_artifact` plus `_marketplace_evidence`), which cannot read a
promoted registry snapshot; `RegistryArtifactVersion` carries `object_digest` and `payload_digest`
but no `manifest_digest`, so the canonical evidence is not a field-for-field substitution. And
`setup_engine/io.py:89 persist_setup` records that setup ran by replacing `setup_state_ref` inside
the legacy install-state record under its lock, which `setup_receipt.locate_setup_record` reads for
`aart marketplace receipt show|verify|undo` -- the canonical route has no such pointer and needs its
own durable setup record.

What remains: give the canonical action handler its own setup and reporting completion.
`_canonical_setup_run` and `_complete_canonical_consumer_action` are deliberately retained in
`agent_artifacts/tui.py` as the material for it — they are the only implementation of the
capability — but they take `ConsumerApplicationService`, `ConsumerReview` and `ConsumerOutcome`,
and the canonical path has a receipt instead. So this is a slice, not a wiring change: either the
setup engine is reached from the configured-installation action directly, or the action produces
the outcome value the existing completion already accepts.

### Completion (2026-09-03)

The receipt-backed subject and persistence adapter are `io/configured_setup.py`; no legacy install
state is written. The setup engine still performs every trust, policy, declaration, object,
capability, precondition and effect-consent decision. `setup_state_ref` is now an optional field on
both canonical receipt shapes, with round-trip, old-document and malformed-value tests. A forced
CAS-reference failure proves receipt and setup-state compensation. The public configured install,
update and explicit setup routes use the adapter. The shell runs the retained canonical completion
through a typed action completion and its `draw`/`key` terminal port; `key_event` remains the only
key interpreter. Reporting defaults to no, displays the exact payload before provider invocation,
and is advisory on provider failure. Acceptance is
`tests/configured_setup_gap_test.py`, `tests/configured_setup_subject_test.py` and
`tests/configured_setup_report_test.py`.

## B-046 — Canonical setup receipts are not yet found by receipt show/verify/undo

Discovered while closing B-044 and explicitly outside that wiring slice. Canonical setup now stores
the same setup record and CAS reference as the legacy route, but its durable pointer is the
installation receipt's `setup_state_ref`. `setup_receipt.locate_setup_record` still reads that
pointer only from the retiring install-state manifest, so `aart marketplace receipt
show|verify|undo` cannot yet locate a setup run made by a configured install. Add a receipt-backed
locator (without writing legacy install state), characterize all three public verbs, and preserve
the existing review-before-undo and stale-record checks.

Evidence/links: D-126, D-128; B-044; `agent_artifacts/setup_receipt.py`,
`agent_artifacts/io/configured_setup.py`.

### Completion (2026-09-03)

Closed by D-130. `setup_receipt.locate_receipt_setup_record` reads the pointer off the receipt;
`receipt_service.load_receipt` asks the canonical store first and falls back to the manifest, so a
machine holding only legacy installations answers exactly as before. No legacy install state is
written. Acceptance is `tests/configured_setup_gap_test.py::ConfiguredReceiptVerbsTest`, which
installs through the public command and then drives all three verbs against what that install
recorded, plus `tests/setup_receipt_cli_test.py::CanonicalReceiptCommandTests` (every legacy
assertion re-run over a canonical receipt) and `::CanonicalReceiptAbsenceTests`.

## B-047 — The canonical shell never says how much of a list a filter matched

Discovered during the `agent_artifacts/tui.py` orphan sweep (D-129). The retired wizard answered
every query with a count -- `2 of 4 match 'review'.`, `Nothing matches 'kubernetes'. 4 entries
searched.` -- so a person could tell an empty screen caused by a typo from one caused by having
nothing installed. `CanonicalScreenSource.rows` filters and returns; `frame()` draws `Filter: <q>`
and the surviving rows, and nothing anywhere reports how many were hidden.

The safety half of the wizard's behaviour does hold and is now pinned: a filter that matches
nothing yields no rows, so no row can be acted on, and the screen does not change
(`tests/consumer_shell_test.py::test_a_filter_that_matches_nothing_empties_the_screen_without_leaving_it`).
Only the count is missing, which is why this is noncritical: no invariant depends on it.

Evidence/links: D-129; `agent_artifacts/tui_consumer.py` `CanonicalScreenSource.rows`, `frame`;
the removed `tests/tui_search_test.py::test_the_answer_says_how_much_of_the_list_matched` and
`::test_a_query_that_matches_nothing_says_so_and_keeps_the_prompt`.

## B-048 — A refusal line longer than the content measure is neither wrapped nor elided

Also from the D-129 sweep. `tui._source_flow_diagnostics` wrapped a refusal to `CONTENT_MEASURE`
so a long remediation stayed readable and was provably not truncated. The shipped shell renders
every declined action through `io/consumer_actions.py::_refusal`, which splits on newlines only:
a single long remediation becomes one long row, and what happens to the overflow is the curses
adapter's business rather than a decision anything states or tests.

The half that matters -- the remediation survives beside the message, in order, with nothing
elided -- is carried in `tests/tui_source_lifecycle_test.py::SourceRefusalWayOutTests`. Wrapping
is a presentation choice with no invariant behind it, so it stays here until a screen needs it.

Evidence/links: D-129; `agent_artifacts/io/consumer_actions.py` `_refusal`, `_lines`;
`agent_artifacts/tui_layout.py` `CONTENT_MEASURE`, `wrap`.

## B-049 — `tui_maintainer.py` uses the dot separator the other projections forbid

Noticed while deciding which chrome guards to carry in D-129. `tests/tui_marketplace_test.py::
test_no_projection_uses_the_dot_as_a_separator` still holds for the marketplace projection, and
the retired `tui_wizard_curses_test.py` held the same rule over `tui.py`. `tui_maintainer.py`
contains seven ` · ` separators, so the rule is now enforced on some screens and not others.

Which way it should be resolved is a product question, not a cleanup: the Product Specification's
own screen mockups use ` · ` (for example its dashboard and review summaries), so the wizard-era
prohibition may be the thing that is wrong rather than the maintainer screens. Decide once, then
either drop the marketplace guard or change the maintainer projections -- not both by accident.

Evidence/links: D-129; `docs/product-specification/PRODUCT_SPECIFICATION.md` screen mockups;
`agent_artifacts/tui_maintainer.py`; `tests/tui_marketplace_test.py`.

## B-050 — `aart source health` has no public-flow test

Found while opening CP-15, when `aart source sync` turned out to have none either and step 1 wrote
the first. `source health` is the other verb in `commands/source.py` that nothing drives through
`cli.main`: `tests/source_cli_command_test.py` covers `add`, `list`, `remove`, `resubscribe` and
the marketplace browse, and asserts the health *projection* through `source list`, but `_health`
itself -- its per-alias selection, its `degraded` exit condition, and the JSON shape it prints --
is reached by no test.

Noncritical because the health assessment it renders is well covered at the application seam
(`tests/source_sync_application_test.py`) and because `source list` proves the same values reach a
public payload. What is unproven is only this verb's own selection and exit code. CP-15 step 1's
`_source`/`_source_json` helpers in `tests/source_sync_command_e2e_test.py` are the runner it
needs -- the source verbs take no `--project`, which is why the lifecycle harness's own `run` could
not be reused.

Evidence/links: D-132; `agent_artifacts/commands/source.py` `_health`;
`tests/source_cli_command_test.py`; `tests/source_sync_command_e2e_test.py`.

## B-051 — The three offline capabilities are refusable but not reportable

Status: CLOSED by CP-16 step 2 / D-140.

Found closing INV-223 in CP-15 step 3. Product Specification 165.11 shows the decomposition as
something an operator *reads*:

```text
metadata cached
canonical payload cached
runtime dependencies cached
```

AART implements all three and distinguishes all three, but only at the moment one of them fails:
`source-not-synchronized` names a cold cache, `install-object-unavailable` says "while offline",
and the dependency layer denies the installer an index and reports whatever it says. Nothing
answers "is this artifact installable offline" before an install is attempted, so the three lines
above have no producer.

Noncritical because the invariant's prohibition -- the capabilities must not be conflated -- is now
held and tested (`tests/offline_capability_test.py`), and nothing depends on the display. It is
recorded here rather than added to CP-15 because it is an inspection surface rather than an
edge-case behaviour, which is what CP-16 (`aart doctor` as environment-wide inspection with
machine-complete JSON) exists to build. Whoever opens CP-16 should read this item first.

Resolution: `aart doctor` now reports source/artifact metadata, exact approved canonical payload
and runtime-dependency readiness as separate fields in both renderings before installation. It
verifies vendored bytes against the approved object digest without publishing them. Declared
runtime dependencies remain `unverified`, rather than guessed cached or missing, until the deferred
B-010 capability supplies durable package-manager cache evidence. Public E2E scenarios hold cold,
referenced, dependency-free, dependency-declaring, multi-source and multi-artifact states.

Evidence/links: INV-223; `docs/product-specification/PRODUCT_SPECIFICATION.md` 165.11;
`agent_artifacts/marketplace/catalog.py` `_resolution_failure`;
`agent_artifacts/installation/application.py` `INSTALL_OBJECT_UNAVAILABLE`;
`agent_artifacts/io/python_runtime.py` `_install_argv`; `tests/offline_capability_test.py`.

## B-052 — Cancel-after-partial-apply has no public flow to test it

Found in CP-15 step 4a. `_apply_effects` handles two rollback paths: a step that failed, and a
person who declined consent for the *next* effect after earlier ones already applied. D-133 gives
both the same compensated-evidence retention, and only the first has an end-to-end test.

The second is unreachable from the CLI: `--approve-setup-effects` is one flag for the whole plan,
so a non-interactive run either approves every effect or none, and a cancel therefore always lands
before the first effect applies -- which is exactly what
`marketplace_lifecycle_e2e_test::test_an_authorized_plan_is_reviewed_and_applies_nothing_until_its
_effects_are` measures. Per-effect consent is the interactive wizard's, and nothing drives that
route over a real machine.

Noncritical because the branch is one line different from the tested one and both go through the
same `_compensated` helper and the same `_record`. It is recorded so that whoever adds a
public-flow driver for interactive per-effect consent knows there is a claim waiting for it.

Evidence/links: D-133; `agent_artifacts/setup_runtime.py` `_apply_effects`;
`tests/verification_failure_e2e_test.py`.

## B-053 — `CLAUDE.md` carries a section `AGENTS.md` does not

`CLAUDE.md` opens by saying it mirrors `AGENTS.md` and must be corrected to match whenever the two
diverge. They diverge today: `CLAUDE.md` ends with a **Repository commands** section — the `make`
target table — that `AGENTS.md` has never had. Noticed while adding `make mutants` to both under
D-134, which is why only one file needed the table row.

The section is useful, so the fix is to add it to `AGENTS.md` rather than to delete it. Noncritical:
nothing depends on the table being in both, and the two files agree on every rule that binds
behaviour. Recorded so the next person to touch either file does not have to rediscover which
direction the correction runs.

Evidence/links: `CLAUDE.md` header paragraph; `AGENTS.md` ends at *Durable handoff*.

## B-054 — No module has a trustworthy mutation baseline

D-134 added `make mutants` and it has been run twice, both times scoped to `setup_render.py` and
`receipt_service.py` with only the two or four test files nearest the current slice selected. Those
runs proved the tooling works — a `rollback_command` key mutant is killed by
`verification_failure_e2e_test`, a `coordinate` key mutant survives — but their survivor counts (719
of 1436, then 728 of 1121) say nothing about those modules, because the selected tests are not the
tests that actually cover them.

A baseline worth keeping would run one module against every test that touches it, and record the
survivors that matter as backlog items. Noncritical because the per-claim targeted mutations each
slice records are what make its evidence load-bearing, and those are unaffected. Worth doing for a
module the critical path is about to change — `setup_runtime.py` and `installation/application.py`
are the two with the most behaviour and the least direct unit coverage.

Evidence/links: D-134; `scripts/mutants.py`; `make mutants`.

**Addendum (CP-15 step 5).** The third scoped run — `security/baseline.py` against the three test
files nearest it — was the first to pay for itself: 1218 mutants, 335 survivors, and one of them was
a real gap that a test now closes (the assignment credential detector, see the slice document).
Three others in the same function are worth a look when someone next touches it and are recorded
here rather than acted on: `entry.kind is not FILE and not _text_like(entry)` in place of `or`
(nothing distinguishes them, so no fixture pairs a real file with an unreadable suffix);
`_finding(reason, path=None)` and `_finding(reason)` on the decode-failure path (the
`text-decode-failed` test asserts the rule fires but never which file it names); and `break` in
place of `continue` there (no fixture has two undecodable files). All three are about the skipped
branch, which is the part of the scanner that decides what it did *not* look at.

## B-055 — `ArtifactLifecycle.REMOVED` is unreachable in production

`compiler/graph.py:641` marks a withdrawn artifact `REMOVED` rather than dropping it, but only when
`compile_marketplace_graph` is given `previous=`, and none of the three production callers passes it
(`io/configured_offers.py:257`, `consumer/runtime.py:810`, `consumer/runtime.py:919`). So in a real
machine a withdrawn artifact is simply absent from the recompiled graph, `marketplace/catalog.py`'s
three `REMOVED` filters never see one, and there is no `--include-removed` flag to ask for the
history either.

This is dead machinery, not a defect: CP-15 step 5 measured the withdrawal end to end and every
claim 165.10 makes holds without it. But it means the graph carries a lifecycle vocabulary nothing
populates, which is the kind of thing a future change will read as load-bearing. Either wire the
previous graph in and give operators a way to see what a source withdrew — which is the useful
version, and would let `marketplace list` explain an absence rather than just having one — or delete
the merge path and the enum member together.

Noncritical: no invariant needs it, and the two that cover withdrawal (INV-221, INV-222) are
EVIDENCED without it.

Evidence/links: `tests/withdrawal_and_purge_e2e_test.py`; CP-15 step 5; `compiler/graph.py:49,641`.

## B-056 — `EffectivePolicy` never reaches the consumer path

`commands/marketplace.py` constructs `EffectivePolicy()` — the permissive default — at both the
install seam (line ~1067) and the uninstall seam (line ~1408), and nothing anywhere composes one
from configuration. So `forbidden_effects`, `risk_ceiling`, `allowed_runtimes`,
`allowed_network_hosts` and the rest of the domain policy are inert for a consumer: `compose_policy`
and `PolicyOverlay` exist and are tested at the seam, and no operator can set any of them.

The policy that *is* live is `OrganizationPolicy`, read from the administrator's `policy.json`, and
that is what CP-15 step 6 built the compliance report on — `minimum_trust_for_user_scope` is the one
lever it carries that applies to an installation rather than to adding a source. So the invariant is
held by the policy AART actually enforces.

What is missing is the wiring, not the machinery: a configuration surface for `EffectivePolicy` and
a composition at the consumer seam would let `165.21`'s worked example — *"external launch scripts
are no longer allowed"*, a `forbidden_effects` rule — become reportable, which it is not today.
`_standing` is the one place that would then have more to say.

Noncritical: INV-233 is EVIDENCED through the live policy, and no other invariant needs the
domain policy to be configurable. Worth doing before CP-16's doctor, which is the other place a
policy finding would surface.

Evidence/links: `agent_artifacts/commands/marketplace.py`; `agent_artifacts/domain/policies.py`;
D-136; CP-15 step 6.

## B-057 — `registry promote` and `registry publish` disagree about the registry layout

Found while building CP-15 step 7, by running the two verbs against one checkout.

`registry promote` writes a **versioned** layout: `artifacts/<kind>/<name>/<version>/artifact.json`.
`registry publish` over the same checkout refuses with `required file is missing: artifact.json` at
`artifacts/<kind>/<name>/artifact.json` — the **unversioned** path. So the output of the first verb
is not an input the second accepts, and a maintainer following the obvious sequence gets a refusal
naming a file they have no reason to think should exist.

The asymmetry has a second half. `registry publish` requires an `aart-registry.json` workspace
marker and refuses without one (`registry workspace requires aart-registry.json`, remediated by
`registry init`); `registry promote` requires no such marker and will happily write into a bare
`git init` directory. The two verbs disagree about what a registry checkout *is*.

A third consequence surfaced in the same probing: promoting into a directory that is simultaneously
a consumer's `source-local` source leaves that source failing validation with `artifact-invalid`,
because the versioned layout is not a valid native source tree. That arrangement is not one anybody
should run — CP-15 step 7 deliberately keeps the maintainer's checkout and the published registry
separate for exactly this reason — but the diagnostic an operator would get says nothing about the
cause.

**Not critical path.** No Product Specification invariant requires the two verbs to compose, and
step 7's boundary claims are unaffected: they are about what promotion does *not* do, and it does
not do it under either layout. This becomes critical if CP-17's Git-backed acceptance drives
`promote` and `publish` in sequence over one repository, which is the natural way to write it —
whoever opens CP-17 should read this first.

**CP-17 step 2 update.** The consumer consequence became critical and is closed: public source
validation and Marketplace projection now recognize promotion's versioned approved-registry shape
and validate it with `load_registry_versions` / `validate_promoted_registry` (D-147). The original
command disagreement remains here: the older `registry publish` verb still expects the compiled
maintainer-workspace shape. CP-17 follows the accepted 165.27/165.28 boundary instead -- promotion
prepares local state and Git review/merge publishes it -- so making that legacy verb compose is not
required to continue the live chain.

## B-058 — Scoped mutmut can reuse stale outcomes after test-only changes

Found in CP-16 step 1. After adding assertions to `tests/doctor_command_e2e_test.py`, rerunning the
same `make mutants ONLY=agent_artifacts/commands/doctor.py TESTS="tests/doctor_command_e2e_test.py"`
completed at zero mutants per second and returned the previous verdicts. Moving the ignored
`mutants/` directory aside forced a fresh run and killed eleven additional mutants. The wrapper's
`finally` then restores `setup.cfg`, so a later `mutmut show` cannot load the scoped source path
either; the generated mutant files have to be inspected directly.

The tool should have an explicit fresh/invalidation mode and a supported way to inspect survivors
after the tracked configuration is restored. Until then, move the ignored mutation cache aside
before assessing a run whose tests changed and record whether the result was fresh. Noncritical:
D-134 keeps mutation testing advisory, and targeted manual mutations remain the evidence for each
declared claim.

Evidence/links: D-134; CP-16 slice step 1; `scripts/mutants.py`.

## B-059 — Doctor's exactly-one-match repair guard has unproven reachability

Found in CP-16 step 3. `commands/doctor.py` refuses when `len(matches) != 1` for an exact
source-qualified coordinate within one scope. Weakening the guard to `< 1` survives every test in
`tests/doctor_repair_command_e2e_test.py`, because no fixture produces two installations of one
identical coordinate in one scope, and it is not established that the canonical state store can
represent that at all.

Either the duplicate state is representable, in which case the `> 1` half is a real refusal that
deserves a fixture and a test, or it is not, in which case the guard is equivalent to `< 1` and the
survivor is correct to survive. Deciding requires reading the state store's uniqueness guarantees,
which is outside step 3's claims.

**Not critical path.** No Product Specification invariant requires the duplicate case, and the guard
is conservative either way — it refuses rather than repairing an ambiguous target. Per D-134 this is
recorded as a finding, not repaired by inventing a fixture the capability does not support.

Evidence/links: D-134; D-091; CP-16 slice step 3; `agent_artifacts/commands/doctor.py`.

## B-060 — Step 3's repair command was never given a scoped mutation run

Found in CP-16 step 4b. Running `make mutants ONLY=agent_artifacts/commands/doctor.py` over all four
Doctor test files produced 499 mutants and 145 survivors, of which 84 are in `_run_repair` — step
3's reviewed-repair entry point. Step 3 was proven by five targeted mutations, each red exactly
where claimed, and that remains true; what it never had was a scoped run to find the claims nobody
thought to make, which is the other half of what D-134 asks for.

The survivors are unclassified. Step 4b's own nine broke down as three real gaps and six
string-spelling artifacts, so a similar split is plausible here — but plausible is not measured, and
84 is large enough that assuming would be the wrong move. What is needed is one scoped run of
`_run_repair` against `tests/doctor_repair_command_e2e_test.py` alone, with the survivors read and
split into real gaps, equivalent mutants and presentation noise.

**Not critical path.** INV-194 is EVIDENCED on public-flow evidence and five mutations that each
turn red only their own claim; no Product Specification invariant depends on closing these. It
becomes critical if any of the survivors turns out to be a reachable defect in the confirmation
boundary, which is the part worth reading first: the `--expect` comparison, the scope selection and
the exactly-one-match guard that B-059 already questions.

Evidence/links: D-134; D-091; B-059; CP-16 slice steps 3 and 4b; `agent_artifacts/commands/doctor.py`.

## B-061 — Doctor's `run` composition has 47 surviving mutants under a scoped run

Found in CP-16 step 4c. The scoped run over `commands/doctor.py` with all six Doctor test files
produced 595 mutants; 47 of the survivors are in `run` itself — the function that assembles the
report from seven observations and serializes it two ways.

This is a different question from B-060. `_run_repair` is one guarded operation whose survivors are
about a confirmation boundary; `run` is composition, where many mutants are plausibly equivalent by
construction (reordering independent reads, changing a local name, altering a blank separator line
between sections). What is not known is how many. Every step of this slice that read its own
survivors found at least one real gap hiding among the noise — published payload keys nothing read,
twice — so the noise assumption is exactly the one that has failed here before.

What is needed: read the 47, split them into equivalent, presentation-only and real, and either
close the real ones or record why each stands.

**Not critical path.** Every claim the slice declares is held by a public flow and by targeted
mutations that turn red only where claimed; these survivors are about depth beyond those claims.

Evidence/links: D-134; D-091; B-060; CP-16 slice steps 4b and 4c; `agent_artifacts/commands/doctor.py`.

## B-062 — A machine with no credential provider reports no credentials rather than saying it could not look

Found in CP-16 step 4c. `aart doctor` reports credential health from
`read_installed_inspections`, which observes references only where a provider exists —
`MacOsKeychainProvider` on darwin, nothing elsewhere. On a machine with no provider the report says
"no installed artifact references one", which is the same answer it gives when there genuinely are
none.

That is the "absence against unknown" confusion this slice refused three times in its own new
surfaces: step 2 kept "missing" distinct from "not looked at" for the offline capabilities, step 4a
kept "no working copy" distinct from "the run root could not be read", and step 4b answered the
empty activity trail in words. The credential section is the one place in the report where the two
are still spelled the same, because the distinction lives upstream in the inspection reader rather
than in the projection this step added.

Fixing it means the inspection result carrying whether a provider was available at all, then the
report distinguishing "none referenced" from "cannot observe credentials on this platform".

**Not critical path.** No Product Specification invariant requires the distinction, and the report
under-claims rather than over-claims: it never says a credential is healthy when it could not look.

Evidence/links: D-138; D-140; D-142; CP-16 slice steps 2, 4a and 4c;
`agent_artifacts/io/consumer_machine.py`; `agent_artifacts/commands/doctor.py::_credential_lines`.

## B-063 — Twelve unclaimed mutation survivors in `domain/selection.py`

A scoped run over `agent_artifacts/domain/selection.py` with the three test files that claim it
(`git_revision_provenance_test`, `selection_domain_test`, `installation_proposal_test`) left twelve
survivors, none of them in the code those files claim: eight in `_safe_line` and two each in
`artifact_request_sort_key` and `artifact_coordinate_sort_key`. Ordering is exercised widely
elsewhere in the repository, so these are survivors of the *scope*, not necessarily of the suite.

Reading them means running the same module against the broader set of tests that construct
selections and asserting ordering directly, which is a different question from CP-17's.

**Not critical path.** No Product Specification invariant depends on it, and D-134 makes an
out-of-scope survivor a backlog note rather than a finding.

Evidence/links: D-134; D-149; CP-17 step 2 review; `agent_artifacts/domain/selection.py`.

## B-064 — The CLI cannot install any artifact that declares an input

`aart marketplace install` has no flag that answers a declared input: the required-input form belongs
to the persistent shell. An artifact declaring one is therefore refused outright, with
`consumer-invalid` naming each unanswered field and its kind. The refusal is correct and is now
pinned by `git_backed_runtime_e2e_test`, including that nothing is built for an install that cannot
complete -- no runtime directory, no harness entry, no receipt.

What it means in practice is that the CLI can install artifacts that need no configuration, while
the most common MCP shape -- a server needing a token -- is reachable only from the shell. Whether
the CLI should grow a way to answer the form, or should keep sending an operator to the shell for
it, is a Product Specification question rather than a defect.

**Not critical path.** No mandatory invariant requires the CLI to answer inputs, and the boundary
fails closed and says why.

Evidence/links: CP-17 step 3b; `tests/git_backed_runtime_e2e_test.py`;
`agent_artifacts/commands/marketplace.py`; `agent_artifacts/io/configured_installation.py`.

## B-065 — Marketplace provenance names a synthetic author commit

`marketplace list` publishes a `provenance` block per artifact carrying `origin_url`, `path` and
`resolved_commit`. Over the CP-17 Git-backed chain it reads
`{"origin_url": "https://git.example/servers.git", "resolved_commit": "000...0"}` while
`source.resolved_revision` alongside it carries the real commit.

That is not a defect: provenance describes the *author* repository a candidate was scanned from at
promotion time, which is a different repository from the one a consumer synchronizes, and the zeros
come from the promotion-evidence fixture rather than from the code. But it is CP-17's own thesis
pointing at the half of the chain this slice does not reach: the maintainer side is still proven
against a precondition a test synthesized, and a `resolved_commit` of all zeros is the same tell
`"a" * 40` was on the consumer side.

Closing it means a maintainer-side fixture that scans and promotes from a second real Git
repository, so that the provenance an operator reads is a commit that exists.

**Not critical path.** CP-17's chain is the consumer's; no mandatory invariant requires the author
repository to be real in these fixtures.

Evidence/links: CP-17 step 3b probe; D-091; `tests/promotion_planning_test.py::_evidence`;
`tests/git_backed_runtime_e2e_test.py`.

---

## B-066 — An MCP payload rewritten in place is still invisible to doctor

D-150 stopped `aart doctor` reporting `ready` over a payload that is gone. On the placement path the
fix is complete: `PlacedArtifactReceipt.payload_digest` exists, so the observer measures a tree
digest and both deletion and rewriting are caught.

The installation path has no such digest on either side. `InstallationObservation` carries
`payload_present` and no tree digest, and `InstallationReceipt` records `object_digest` -- the
immutable package the installation was materialized *from* -- which is not the digest of the
installed tree and cannot be compared against one. So for an MCP installation the claim is presence
only, and the measured table after D-150 reads:

| damage | doctor |
|---|---|
| launcher rewritten | `broken`, divergent, repairable |
| whole payload tree deleted | `broken`, missing, not repairable |
| one payload file rewritten | `ready` -- the directory is still there |
| one payload file deleted | `ready` -- the directory is still there |

The observed component says so in its detail (`presence only; this observation carries no tree
digest`) rather than letting a partial check read as a full one, which is the B-029 pattern.

Closing it means recording the installed tree's digest on `InstallationReceipt` at install time and
measuring it in `observe_installation` -- a receipt schema change, so it carries a migration for
receipts already written, which is why it is not folded into D-150.

**Not critical path.** INV-228 is satisfied for the damage that is detectable without a schema
change, and the remaining gap is stated in the component detail rather than claimed as health. It
becomes critical if a slice needs an MCP installation's tree to be verifiable.

Evidence/links: D-150; D-029; B-029; CP-17 step 4 probe; `agent_artifacts/application/installed_state.py`.

---

## B-067 — An approved Collection never reaches the configured Marketplace

CP-17 step 5 set out to install a Collection through the public chain and found it cannot be done,
anywhere, for any registry content.

`io/configured_selection.py::_approved_snapshot` skips every approved version whose
`coordinate.artifact.kind` is `"collection"`, and constructs `ApprovedRegistrySnapshot` without a
`collections` argument, so the field keeps its default `()`. That snapshot is what
`load_configured_approved_marketplace` aggregates and what every public verb reads. The skip carries
no comment, and nothing else on the configured path populates the field.

The consequence is not a broken Collection but an absent one. The domain models `Collection`,
`ApprovedRegistrySnapshot` carries a `collections` field, `marketplace_resolution` defines
`COLLECTION_NOT_FOUND`, and `aart marketplace install <source>/collection/<name>` is a documented
coordinate form -- and the answer is always `collection-not-found`, regardless of what a maintainer
approved. Measured against a real Git-backed registry publishing two artifacts:
`marketplace list` returns `"collections": []` while offering both members.

**Corrected scope (D-151).** This first read as a projection bug. It is not: tracing it end to end
shows nothing in the product can produce an approved Collection for the projection to carry.

The maintainer side models Collections and then stops. `domain/collection_candidates.py` defines
`CollectionCandidate`, `compile_author_source` returns `.collections`, `reconcile_source_scan`
accepts them and produces `collection_active`, and the maintainer TUI shows them --
but `CollectionCandidate` appears in only six modules and `promotion.py` is not one of them.
`collection_active` reaches candidate history, which is an audit record, and goes no further. No
collection candidate is promoted, so no registry version of kind `collection` is ever published,
and no test anywhere publishes one. Resolution is the one part already built, which is what makes
the gap look smaller than it is.

Four layers, to be built together as their own vertical slice:

1. **Promotion.** A `CollectionCandidate` has to become an approved registry version -- today it
   reaches history and nothing else.
2. **Registry representation.** A published collection version, and the manifest read that turns
   one back into a `Collection`.
3. **The configured projection.** `_approved_snapshot` must populate
   `ApprovedRegistrySnapshot.collections` instead of skipping kind `collection`.
4. **Install planning over members**, with the ownership graph uninstall already respects, and the
   member-health aggregation INV-186 requires.

Separately, and worth doing while the capability is absent: the refusal's remediation is empty.
`collection-not-found` gives an operator no next step, where the neighbouring `receipt-no-setup`
gives three.

**Not critical path for CP-17 (D-151).** CP-17's subject is that each stage of the chain is real
rather than fixture-assembled, and its bulk-install half is proven over a real commit. A step cannot
be blocked on an acceptance claim about a capability that does not exist -- its premise was wrong,
which is what D-151 records. Building this inside an acceptance slice is the big-bang expansion
CLAUDE.md's migration discipline forbids; it is the same Collection capability D-131 already
sequenced B-038 behind, seen from the consumer end.

It becomes critical when a slice must satisfy INV-186 (collection health derives from member state)
or INV-213 (exact Collections preserve exactness) through a public verb, since neither can be
evidenced while no Collection is reachable. Those two invariants are the reason this is a capability
worth scheduling rather than a curiosity.

`CollectionsAreNotReachableTest` pins the current behaviour so the gap stays an honest refusal: it
must not become a partial install of some members, and must not silently succeed.

Evidence/links: CP-17 step 5; D-131; B-038; INV-186; INV-213;
`agent_artifacts/io/configured_selection.py`.

## B-068 — `mutmut` is declared in the dev group but absent from `poetry.lock`

Found: CP-18 step 1 (2026-09-03) · Reclassified: CP-18 step 6 (2026-09-04) · Status: **closed**

D-134 added `mutmut` to Poetry's dev group and put `make mutants` behind it. `poetry.lock` was never
regenerated, so it carries no `mutmut` entry, and `scripts/dev_tools.py::requirements("dev")` --
which reads the lock and is the list a provisioned environment installs from -- returns twelve pins
with `mutmut` not among them:

```text
coverage, exceptiongroup, hypothesis, librt, mypy, mypy-extensions,
pathspec, poetry-core, ruff, sortedcontainers, tomli, typing-extensions
```

An environment provisioned by that path therefore cannot run `make mutants` at all; it fails on the
missing module rather than reporting an unadequate suite.

It became critical in CP-18 step 6 when `.github/workflows/deep-quality.yml` made mutation adequacy
an unattended, explicitly requested CI run. At that point the missing pin was no longer a local
developer surprise: the shipped workflow could not start the tool it claimed to run.

Closed by regenerating the lock, not hand-editing it. `mutmut==3.7.0` and its Textual dependency
are now provisioned by `scripts/dev_tools.py`. Their dev-only marker is `python >=3.10,<4.0` because
Textual does not claim Python 4 compatibility while AART's runtime range intentionally remains
open-ended. The marker changes no production dependency: `[project] dependencies` remains empty.

D-167's later clean-runner audit found the same class one layer earlier: the wheel gate invoked the
Poetry CLI while the dev lock provisioned only `poetry-core`. The closed remedy is the same — Poetry
2.4.1 and the Python-3.10-only `tomli` reader are explicit locked dev tools, while the runtime
dependency list remains empty.

Evidence/links: D-134; D-166; INV-071; INV-080; `pyproject.toml` `[tool.poetry.group.dev.dependencies]`;
`poetry.lock`; `scripts/dev_tools.py`; `scripts/mutants.py`.

## B-069 — the release tagger's email hardcodes github.com's noreply domain

Found: CP-18 step 2 (2026-09-03) · Severity: low · Status: open

`.github/actions/cut-release/action.yml` names the tagger as:

```bash
git config --global user.email "$GITHUB_ACTOR_ID+$GITHUB_ACTOR@users.noreply.github.com"
```

On a GitHub Enterprise Server instance the noreply domain is the instance's own, so a release cut
there records a committer email pointing at a domain that instance does not own. Nothing breaks: the
tag is created, the release is published, and the address is never delivered to.

**This is not an INV-078 finding, and the distinction is the point.** INV-078 is about egress -- the
profile must be able to run with no public network. A committer email is written into a commit and
connected to by nothing. `NoPublicHostIsReachedThatAVariableCannotRetargetTest` states the egress
claim over URLs and pins this one occurrence explicitly, so a real `github.com` URL added anywhere
fails immediately while this string does not have to be excused each time.

Fixing it means deriving the domain from `GITHUB_SERVER_URL` the way `GH_HOST` already is, or
naming a variable for it. Worth doing when the release action is next touched; it needs a real
Enterprise run to confirm the derived form, which is why it is not being guessed at now.

Evidence/links: INV-078; INV-074; `.github/actions/cut-release/action.yml`;
`tests/enterprise_ci_template_test.py::NoPublicHostIsReachedThatAVariableCannotRetargetTest`.

## B-070 — four unreachable production modules are listed as exceptions without a decision

Found: CP-18 step 3 (2026-09-03) · Severity: medium · Status: **closed** — all four decided

**Verdicts so far (D-154).** `domain/ports.py` and `domain/collections.py` are removed: no
importer, no path-based consumer, and the generic Protocol pair and sorted-collection helpers
they defined had no caller. `domain/outcomes.py` is **kept** — it is not legacy, it is named by
`scripts/release.py:SCHEMA_INPUTS` and pinned by sha256 in every issued schema freeze, which the
import graph cannot see; retiring it is a release-contract change, filed as B-071.
`profiles/loader.py` is **kept and is not legacy** (D-155): INV-001 requires enterprise profiles to
live outside the public tool, and this is the only mechanism by which an externally-defined profile
can enter it. The real finding is that nothing calls it — B-072.

`tests/legacy_authority_reachability_test.py` builds the import graph from `agent_artifacts.cli`
and `agent_artifacts.__main__` and asserts that every shipped module is reachable, or named in an
exception list. Six names are listed. Two carry a reason:

- `agent_artifacts._commit` — written by the build, which stamps a commit into release artifacts.
- `agent_artifacts.application.credential_lifecycle` — retained deliberately, because the
  credential lifecycle is incomplete and removing it would claim a replacement that has not
  happened.

The other four have no reason recorded, and the first draft of the test's docstring said "two
exceptions remain deliberate" while the list held six:

| module | lines | reached by |
|---|---|---|
| `agent_artifacts/domain/ports.py` | 26 | `domain_kernel_test` only |
| `agent_artifacts/domain/outcomes.py` | 104 | `domain_kernel_test` only |
| `agent_artifacts/domain/collections.py` | 21 | tests only |
| `agent_artifacts/profiles/loader.py` | 147 | tests only |

Each fits that test's own definition of parallel authority: a production module no runtime path
reaches, whose callers have already disappeared. Note `domain/collections.py` is *generic immutable
collection helpers*, not the Collection capability of B-067 — the names collide and the two are
unrelated.

**The decision has not been made, and the exception list must not be read as making it.** Each of
the four is one of: legacy to remove, the intended kernel that something else currently duplicates
(in which case the duplicate is the legacy), or a genuine build/tooling exception like `_commit`.
Telling them apart needs the same audit CP-18 step 2 used — read what the module claims authority
over, find the runtime path that answers the same question, and only then decide which one goes.

It becomes critical for CP-18 step 3's completion: the step is "remove only legacy code whose
authority has been replaced and verified", and four modules sitting in an exception list with no
verdict is the step not finished rather than the step passed.

Evidence/links: CP-18 step 3; B-067 (unrelated despite the name);
`tests/legacy_authority_reachability_test.py`; `tests/domain_kernel_test.py`.

## B-071 — retire `domain/outcomes.py` from the release contract under a new contract version

Found: CP-18 step 3 (2026-09-03) · Severity: low · Status: open

`agent_artifacts/domain/outcomes.py` is reached by no runtime import. Its live counterpart is
`reporting/model.py`'s `SessionOutcome`, which carries a `no-op` state the domain enum never had,
so the shipped session vocabulary is elsewhere and this module is a duplicate nothing serializes.

It cannot simply be deleted. `scripts/release.py:31` declares it in `SCHEMA_INPUTS`, and its
sha256 is pinned in fifteen issued `docs/release/schema-freeze-v*.json` documents including the
live v18. Those documents are immutable evidence (`scripts/release.py:22`): a new release series
adds its own contract beside the frozen ones and never regenerates them. Removing the module is
therefore a contract change — a new `RELEASE_CONTRACT_VERSION` with its own freeze, compatibility
document and checklist — and the same cut should be reviewed for whether any *other* entry in
`SCHEMA_INPUTS` has likewise stopped describing a wire surface.

Not critical: the module costs 104 lines and no behaviour, the reachability test states its
position honestly, and `TheDeclaredSchemaInputsExistTest` now prevents the deletion being
attempted by accident. It becomes critical only if a Product Specification invariant turns on the
release contract naming exactly the wire schema and nothing else.

Evidence/links: D-154; B-070; `scripts/release.py:22-45`; `tests/release_test.py`
(`TheDeclaredSchemaInputsExistTest`).

## B-072 — the only mechanism for externally-defined profiles is never called

Found: CP-18 step 3 (2026-09-04) · Severity: medium · Status: open

INV-001 requires enterprise profiles to live outside the public tool.
`agent_artifacts/profiles/loader.py` implements that: `load_profiles(project)` overlays
`<project>/.agent-artifacts/profiles.json` onto the built-ins, validates the records, and rejects
malformed `unsupported` reasons with a stable user-facing message.

Nothing calls it. `agent_artifacts/consumer/runtime.py:947` passes `builtin()` directly into the
`ConsumerContext`, and `load_profiles` appears in no other production module. A project that
writes `.agent-artifacts/profiles.json` today gets silence: the file is parsed only by
`tests/profiles_test.py`, `tests/memory_profiles_test.py` and `tests/install_scope_test.py`.

So the public tool currently admits no externally-defined profile at all, and the capability that
INV-001 asks for exists as code with no route from a user to it.

The work is to decide where the overlay is read — the consumer runtime is the obvious place, but
the enterprise story in the specification is a private *repository* of profile files, not a single
project-local JSON, so the location and format deserve a deliberate choice rather than wiring
whatever WP-8 happened to build. It should also decide whether a malformed overlay fails the
command or degrades to built-ins, since `load_profiles` currently raises `ValueError`.

Not critical to CP-18, whose step 3 is removal rather than construction. It *is* critical to any
claim that INV-001 is satisfied: the CP-18 step 4 traceability row for INV-001 must not be marked
covered by the mere existence of `profiles/loader.py`.

Evidence/links: D-155; B-070; INV-001 (`PRODUCT_SPECIFICATION.md:5577`); the private layout at
`PRODUCT_SPECIFICATION.md:1806`; `agent_artifacts/consumer/runtime.py:947`.

## B-073 — no live smoke scenario runs in CI, and there is no workflow that could carry one

Found: CP-18 step 5 (2026-09-04) · Severity: low · Status: open

INV-123 asks that mandatory PR verification "retain a fast feedback path with selected live smoke
scenarios", with broader expensive matrices allowed to run in "deep-quality, scheduled or
release-candidate workflows".

The fast half is satisfied: `pr-check.yml` runs the whole deterministic gate set, and the E2E suite
is inside it (the `integration` gate is skipped as *contained* by `unit`, which `quality.py` checks
at runtime rather than assuming). What is missing is the live half. Live acceptance in this
repository is `docs/testing/PLAN-live-acceptance-v1.md`, a manual walk a person performs; no
scenario touching a real remote runs automatically anywhere. There are three workflows —
`pr-check` (pull request), `release` (tag) and `cut-release` (manual dispatch) — and none is
scheduled, so there is also no place a broader matrix could live.

This is a genuine tension with INV-078, which requires the supported enterprise profile to run with
no public egress, so "add a live scenario to `pr-check`" is not the answer on its own: any live
smoke would have to be gated on a variable-supplied endpoint and skip visibly when unconfigured
(INV-080), which is the same shape the private-image arm already uses.

Not critical: the deterministic suite is thorough (3,364 tests, 50 acceptance files, real Git
repositories in temporary directories rather than mocks), and the live plan exists and has been
walked. It becomes critical if a release is ever gated on live evidence that nothing produces.

Evidence/links: INV-123; INV-078 and INV-080; `docs/testing/PLAN-live-acceptance-v1.md`;
`.github/workflows/pr-check.yml`; `scripts/quality.py` `redundant_gates`.

## B-074 — INV-057's warning has no destructive credential flow to attach to

Found: CP-18 step 5 (2026-09-04) · Severity: low · Status: open

INV-057 requires that "deleting/replacing/rebinding a credential reference warns about artifacts
that depend on the same reference before destructive mutation".

Half of it ships. `application/consumer_session.py` computes `credential_dependants`, and
`aart doctor` reports each credential reference with its health and the installations that depend
on it — `doctor_configuration_credentials_e2e_test.py` holds that.

The other half has nothing to attach to, because no public verb performs the destructive mutation.
`plan_removal` takes `delete_credentials`, and its docstring records the choice deliberately: it
"defaults to False everywhere: a credential outliving its last dependant is the documented
behaviour, not an oversight to be corrected by whoever calls this". No CLI flag sets it —
`aart marketplace uninstall --help` offers none — and `application/credential_lifecycle.py`, which
would own rotation and rebinding, is one of the three modules `legacy_authority_reachability_test.py`
lists as deliberately unreachable, for exactly this reason.

So the invariant is not violated; the flow it governs does not exist yet. The work is the credential
lifecycle itself, and when it lands, the dependants warning is a precondition of its review step
rather than a feature to remember afterwards — `credential_dependants` already returns what that
warning needs.

Not critical to CP-18. It becomes critical the moment any public verb can delete, replace or rebind
a credential reference.

Evidence/links: INV-057; `agent_artifacts/application/removal_proposal.py:99-106`;
`agent_artifacts/application/consumer_session.py:146`; B-070's `credential_lifecycle` exception.

## B-075 — The TUI has no input-entry surface, so INV-067's UI clause has nothing to project

INV-067 says the UI "must not collapse secret inputs and non-secret configuration into one generic
'variables' concept". The distinction is held where it originates: `authoring_inputs_test.py`
asserts that a secret input cannot declare a value, a default or an example, that its guidance says
where to get one rather than what one looks like, and that a config input carries default,
validation and guidance. That is a type-level separation the compiler enforces, and nothing
downstream can merge the two without discarding a field.

What does not exist is the projection. `wizard.py`'s `WizardInputKind` is
`confirm | back | quit | add | sync | resubscribe | remove | retry` — navigation, not data entry —
and no screen module mentions a secret at all. Secret collection lives in the setup engine and the
`marketplace` command surface, which the TUI does not drive yet.

So the invariant is not violated; the artifact-input surface it constrains is not built. The
registry-onboarding form added by B-082 collects only credential-free source configuration and
validates it through `configured_source_from_input`; it neither collects nor represents setup
inputs. When artifact input entry reaches the TUI, the UI clause needs its own evidence: a screen
catalog in which a secret field and a configuration field are visibly different things, not two
rows of one list.

Not critical to CP-18. It becomes critical when a TUI screen first collects an artifact setup
input value.

Evidence/links: INV-067; `agent_artifacts/wizard.py:36-38`; `tests/authoring_inputs_test.py:94-146`;
`tests/tui_boundary_test.py`.

## B-076 — Collection input guidance neither consolidates nor names its dependants

INV-164 asks bulk installation to "consolidate equivalent input guidance while preserving which
artifacts depend on the input". Neither half exists, measured rather than supposed:
`project_required_inputs` given two artifacts that declare the same `InputId` returns two rows with
the same id, the same label and the same example, and `ConfigInputView`/`CredentialInputView` have
no owners field to say which artifacts wanted it.

The consequence is small today and grows with Collections: installing a Collection whose members
share one `github-org` asks for it once per member, and a reader who wants to know *why* it is being
asked has nowhere to look. `RequirementView` already carries `owners` and the remediation views
carry theirs, so the shape to copy is in the same module.

Consolidation must be by identity, not by label: two inputs with the same id but different bindings
are two different deliveries and must stay two rows, or the projection would merge a stdin secret
into an environment one.

Not critical to CP-18. It becomes critical when a Collection with shared inputs is first installed
through the TUI, which is where the duplicate prompts become visible.

Evidence/links: INV-164; `agent_artifacts/application/consumer_views.py:336-353`;
`agent_artifacts/application/consumer_views.py:279-312`; INV-131's aggregation clause.

## B-077 — The canonical TUI hides its navigation instructions behind an undiscoverable `?`

Found: manual first-run acceptance (2026-09-04) · Severity: high · Status: done

Running bare `aart` opens the accepted persistent TUI, but its first frame contains no navigation
legend. The complete key list exists only after pressing `?`, while nothing on screen advertises
that `?` opens help. A new user therefore cannot discover how arrows, Enter, Esc or quit work from
the interface itself. The removed frontend had a bottom status bar, and the pure layout kernel still
contains its status-bar machinery, but the canonical shell never renders it.

This crosses the accepted screen-01 contract rather than being cosmetic: Product Specification
161.1 names arrows, Enter, Esc, `/`, `?` and `q` as the global interaction vocabulary, while
INV-187 protects its navigation semantics. The repair is a permanently visible, concise footer for
movement, forward navigation, selection/toggle via Space, back, full help and quit; `?` retains the
contextual list. In curses
the footer is chrome pinned below a clipped body, not another body line that can disappear on a
short terminal. The text fallback renders the same shell frame.

Evidence/links: Product Specification 161.1; INV-187; `tests/consumer_shell_test.py`;
`tests/tui_consumer_entry_test.py`; D-168; manual first-run acceptance. The two regression tests
were first observed red against the shipped frame/clipping behavior, then passed with the footer.
All nine quality gates pass over 3,324 tests at 85.35% branch coverage, as do all 343 separate
integration tests.

## B-078 — Escape inherits curses' long escape-sequence delay

Found: manual TUI acceptance (2026-09-04) · Severity: high · Status: done

Pressing Esc to return from a detail screen pauses noticeably before the prior screen appears.
The reducer and machine reload are not the source: ncurses holds a lone escape byte while waiting
to see whether it begins a function-key sequence. The curses entry boundary should set an explicit
short delay once, before the shell starts, without moving key interpretation out of `key_event`.

Evidence/links: Product Specification 161.1; INV-187; `agent_artifacts/tui.py::run_consumer`;
`tests/tui_consumer_entry_test.py`; D-169; manual acceptance. Curses now uses a 50 ms escape
prefix delay; the focused terminal-entry test was red before the setting existed.

## B-079 — Dashboard navigation names destinations without explaining them

Found: manual TUI acceptance (2026-09-04) · Severity: high · Status: done

The first screen lists Marketplace, Installed, Updates, Registries, Credentials, Activity, Doctor
and Settings, but a first-time user is expected to know the product vocabulary already. Moving the
cursor should show one stable, short explanation of the highlighted destination. The explanations
are presentation only and must not derive health, actions or policy decisions.

Evidence/links: Product Specification 161.1 and 161.2–161.11; INV-062; `CanonicalScreenSource`;
`tests/consumer_shell_test.py`; D-170; manual acceptance. Moving from Marketplace to Installed now
changes the displayed explanation in the headless public shell test.

## B-080 — An empty first run looks like an already-configured machine with zero results

Found: manual TUI acceptance (2026-09-04) · Severity: high · Status: done

With no configured source, Marketplace cannot offer anything, but the Dashboard only reports zero
counts. The empty state should briefly explain what AART installs, recognize that no source is
configured and point to the real setup entry point. It initially named `aart source add --help`;
B-082 subsequently built the same transaction into screen 21, so the current next step is
Registries → Add Registry. Manual acceptance places this as a `SETUP REQUIRED` callout before the
navigation menu, so the prerequisite is read before the unavailable destinations.

Evidence/links: Product Specification 161.1, 161.2 and 161.7; INV-026; B-075;
`tests/consumer_shell_test.py`; D-170/D-171; manual acceptance. The empty Dashboard and empty
Registries screen independently name the TUI source-add entry point.

## B-081 — Manual acceptance inherited two old user-level registry subscriptions

Found: manual TUI acceptance (2026-09-04) · Severity: medium · Status: done

The apparent built-in sources are not package defaults. `aart source list --json` found two entries
persisted in the real macOS user configuration on 2026-08-15: `registry` points at
`M1F1/agent-artifacts-registry-2`, and `registry-a` points at `M1F1/agent-artifacts-registry`.
Both currently report `could-not-check`. A clean first-run acceptance session must remove those
subscriptions through `aart source remove`; future scripted acceptance continues to use isolated
temporary homes so it cannot seed a developer's configuration.

Evidence/links: the public `aart source list/remove` output; configuration path contract;
manual acceptance. Both removals were separately reviewed and finalized through the public command;
the final `aart source list --json` returned an empty `sources` array and both managed snapshots
were discarded. Installed artifacts and project files were outside the command's effect contract.

## B-082 — Registries can be inspected in the TUI but not connected there

Found: manual TUI acceptance (2026-09-04) · Severity: high · Status: done

Screen 21 explained that Marketplace depends on approved registries, then required a new user to
leave the application and reconstruct a long `source add` command. It now exposes Add Registry,
collects alias, credential-free Git URL, branch/tag and default choice, shows an exact review, and
connects only after Enter confirms it. The operation reuses the CLI's canonical source-add
transaction rather than duplicating policy, synchronization or compare-and-swap behavior.

A local path remains deliberately unavailable here. Product Specification 164.2 says a Source is
an authoring/discovery location and not an approved registry; local and direct Sources stay in
Maintainer Mode. The existing Git-location schema and transport allowlist are unchanged.

Evidence/links: Product Specification 161.7 and 164.2; INV-026; D-171;
`tests/consumer_registry_addition_test.py`; `tests/source_cli_command_test.py`. The focused 113-test
consumer/source set and typecheck are green; full quality and integration were intentionally not
run before the operator's requested manual pass.

## B-083 — Maintainer Sources can be synchronized but not added in the TUI

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: resolved
(D-177; awaiting manual retest as QA-009)

The requested real chain starts with two external author repositories carrying `aart.yaml`
manifests. Maintainer → Sources can inspect a configured authoring Source and `s` prepares its
reviewed synchronization, but there is no Add Source action or form. `key_event` exposes `a` only
on consumer Registries and the only action reachable from Maintainer Sources is `SOURCE_SYNC`.
Consequently the TUI cannot create the precondition its own Candidate and Promotion screens need.

This must remain distinct from B-082. Add Registry accepts only an approved remote Git registry;
widening it to accept `source-git` or local authoring paths would erase the Product Specification
164.2 trust boundary. The missing surface is a Maintainer form that explicitly chooses
`source-git` or `source-local`, reviews the identity and uses the same configured-source authority
as the CLI.

Resolved by `MaintainerScreen.SOURCE_ADD`/`SOURCE_ADD_REVIEW` (31a/31b), `SourceDraft`,
`ConsumerActionKind.SOURCE_ADD` and the `source_connection` port, which reaches
`add_configured_source` — the same authority the CLI uses. The form accepts only
`AUTHORING_SOURCE_KINDS` and refuses `registry-git`, so the 164.2 boundary this entry names is
held by a test rather than by convention. Evidence: `tests/maintainer_source_addition_test.py`.

Evidence/links: Product Specification 164.2; `ConsumerScreen.REGISTRY_ADD`;
`MaintainerScreen.SOURCES`; `application/consumer_ui.py::key_event`; QA-009; D-177.

## B-084 — A consumer Registry cannot be refreshed from the TUI

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: resolved
(D-179; awaiting manual retest as QA-010)

Add Registry fetches the initial approved snapshot, so the first Marketplace install is complete.
After maintainers merge a newer registry commit, however, the consumer needs `aart source sync` to
observe it before Updates can offer the new version. The Registries screen has Add and details but
no reviewed Sync action; `s` is routed exclusively from Maintainer authoring Sources and does not
make a configured consumer registry refreshable.

This is a shipped interactive lifecycle gap rather than an automatic-background-sync request.
The TUI should expose an explicit refresh whose review states which registry and ref are fetched,
preserves last-known-good state on failure and reloads Marketplace/Updates after success. Until
then the manual TUI pass uses one named CLI fallback rather than silently claiming the update was
performed through the interactive application.

Evidence/links: Product Specification 161.7; `ConsumerScreen.REGISTRIES`;
`ConsumerActionKind.SOURCE_SYNC`; `application/consumer_ui.py::key_event`; QA-010.

## B-085 — OpenCode is named by a dormant profile but absent from canonical installation targets

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: open

OpenCode 1.18.29 is installed on the acceptance Mac, and an artifact may declare `opencode` in its
compatibility. Nevertheless every canonical placement lookup refuses it: `MCP_TARGETS`,
`DELIVERY_TARGETS`, `MEMORY_TARGETS` and `HOOK_TARGETS` contain no OpenCode entry at either scope.
The public CLI therefore accepts `--profile opencode` syntactically and then returns a named
unmeasured-target refusal without writing. The TUI cannot even request that refusal: its fixed
`MarketplaceTarget` is derived from the MCP table and contains only Claude and Tabnine, with no
harness selector.

`profiles/builtin.py` is not an implementation to reconnect. It labels its OpenCode paths
best-effort/unverified, and its MCP projection is behind the current OpenCode contract: a local
server in `opencode.json` is an object with `type: "local"` and a `command` array, not the generic
string `command` plus optional `args` that `registration_entry` writes. The official OpenCode docs
do confirm the Skill paths and `AGENTS.md` locations represented there, but guidelines and hooks
need translation decisions rather than blind copies into directories OpenCode does not promise to
read.

Close this as a vertical harness slice: measure both scopes against a real OpenCode process; add
Skill and memory targets; extend MCP registration to its native shape; decide guideline and plugin
semantics honestly; expose harness selection in the TUI; then run the installed Skill and MCP from
OpenCode itself. Do not add table rows whose only evidence is the old dormant profile.

Evidence/links: Product Specification multi-harness contract; `domain/harness.py` target tables;
`io/artifact_placement.py::placement_for`; `tui.py::_canonical_marketplace_target`;
`profiles/builtin.py::_OPENCODE`; official OpenCode Skill, Rules and MCP documentation; QA-011.

## B-086 — Codex is accepted as a compatibility name but has no canonical installation adapter

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: open

Codex CLI 0.152.0 is installed on the acceptance Mac, and authoring already permits `codex` as a
compatibility string. That declaration does not make it an install target. Codex is absent from
`MCP_TARGETS`, `DELIVERY_TARGETS`, `MEMORY_TARGETS` and `HOOK_TARGETS`; unlike OpenCode, it is also
absent from the dormant built-in profile registry. The CLI can therefore carry the name as metadata
but canonical placement refuses it, while the TUI offers only the Claude/Tabnine set derived from
the MCP table.

The adapter must be native rather than an alias for Claude. Current Codex documentation discovers
repository Skills under `.agents/skills` and user Skills under `~/.agents/skills`, layers
`AGENTS.md` instructions, and represents MCP servers as `mcp_servers.<id>` entries in Codex TOML
configuration with a command and argument array. Those destinations and merge formats differ from
the two harnesses AART currently measures. Hook and scope behavior likewise need measurement rather
than guessed table rows.

Close this as its own vertical harness slice: measure both install scopes against the real Codex
CLI; implement Skill, instruction, MCP and supported hook projections; expose explicit harness
selection in the TUI; verify uninstall and reconciliation; then invoke the installed Skill and MCP
from Codex itself. This may share generic placement primitives with the OpenCode slice, but must not
share an invented configuration format or one harness's verdict.

Evidence/links: Product Specification multi-harness contract; `domain/harness.py` target tables;
`io/artifact_placement.py::placement_for`; `tui.py::_canonical_marketplace_target`;
`profiles/builtin.py`; official Codex Skills, AGENTS.md and configuration documentation; QA-012.

## B-087 — Registry initialization emits inactive usage-reporting assets without opt-in

Found: whole-product TUI acceptance, first real Registry init (2026-09-08) · Severity: medium ·
Status: resolved (D-180; awaiting manual retest as QA-013)

Running `aart registry init` without `--usage-reporting-repository` still emits an Issue Form and
two GitHub Actions workflows for usage validation and dashboard publication. The command immediately
describes those files as inert because no destination was advertised. This makes a minimal new
Registry carry automation the operator did not request for a capability that is not part of the
current acceptance pass.

The Product Specification's references to telemetry constrain secret safety; they do not require a
usage dashboard in every Registry. At minimum, omit the three usage-reporting assets unless the
operator explicitly supplies the existing opt-in flag. Before removing more authority, characterize
whether configured reporting still has a supported public flow and preserve its consent, payload
preview and failure-is-advisory boundaries. Default Registry CI validation remains separate and
must stay.

Evidence/links: `registry_commands/templates.py::REGISTRY_INIT_TEMPLATES`;
`curation/runtime.py::_prepare_init`; `tests/registry_init_scaffold_test.py`; QA-013.

## B-088 — Confirmed Maintainer commands render review detail again as success output

Found: whole-product TUI acceptance, first real Registry init (2026-09-08) · Severity: medium ·
Status: resolved (D-182; awaiting manual retest as QA-014)

The successful `registry init --yes` path prints the complete review and then a second outcome. In
the observed nine-file initialization, three long warnings appeared in both blocks, `observed: 9
review paths` repeated the plan count, and the `git diff` follow-up repeated every path already
listed. Four more follow-up commands followed it. The success signal is present but buried.

Human success output should be progressive: one short result, concise warnings once, and the next
action the operator normally needs. Exact review detail must remain available before mutation and
machine-complete JSON must remain complete; additional post-init commands and digests can be exposed
through an explicit verbose/help route. Apply this consistently to Maintainer actions rather than
special-casing one printed transcript.

Evidence/links: `curation/model.py::render_curation_review`;
`curation/model.py::render_curation_outcome`; `commands/registry.py`; QA-014.

## B-089 — Empty Registry audit presents non-applicable checks as alarming warnings

Found: whole-product TUI acceptance, first audit of an initialized Registry (2026-09-08) ·
Severity: medium · Status: resolved (D-181; awaiting manual retest as QA-015)

`aart registry audit` passes a newly initialized empty Registry, then emits two long warnings. One
says installation risk is unassessed because `security/index.json` was not supplied. The other says
provenance coverage is partial because there are no external references, followed by remediation
that admits there is nothing to correct. For this machine state both mean the same simple fact:
there are no artifact objects or external references to assess yet.

Do not hide a real unassessed-risk or provenance gap once a Registry contains relevant objects.
Instead, distinguish `not-applicable` from `warning` in the audit result and render an empty valid
Registry as one concise success note. Human output should state the consequence in operator terms;
JSON may retain the complete typed check results. A mutation should prove that adding an auditable
object restores the warning when its evidence is actually absent.

Evidence/links: Product Specification evidence honesty rules; `registry audit` public output;
the empty `aart-test-registry` manual transcript; QA-015.

## B-090 — Maintainer TUI cannot bootstrap a Registry workspace

Found: whole-product TUI acceptance, first Registry bootstrap (2026-09-08) · Severity: high ·
Status: open

The first-run Registry path currently requires the operator to leave the TUI and coordinate
`registry init`, `lock`, `build`, `validate` and `audit` manually. The acceptance branch then needs a
Git commit/push and two GitHub repository variables. Screen 46 can inspect an existing Registry but
offers no initialization action, so the TUI-first procedure begins with its longest CLI detour.

Add a Maintainer Registry bootstrap flow over the existing canonical command/application authority:
a short form with safe inferred defaults for workspace, source ID and display name; optional
capabilities off unless explicitly selected; one digest-bound review and confirmation; then a
fail-fast pipeline through init, lock, build, validate and audit. Render one concise local-ready
result and keep detailed diagnostics behind the relevant review/detail surface. An explicit final
action may create the local Git commit, which Product Specification 164.7 permits.

Do not silently push, create a PR, merge or mutate Git-host repository settings. Product
Specification 165.27 assigns publication authorization to existing Git hosting. The TUI should end
with a short publication handoff and may provide copyable commands for the current host. The two
`gh variable set` calls in the local acceptance guide are branch/tool-delivery configuration, not
universal Registry identity, and must not be baked into the generic form.

Evidence/links: Product Specification 164.7, 164.8 and 165.27–165.28;
`MaintainerScreen.REGISTRY`; `tui_consumer.py::ConsumerScreenSource`; the manual bootstrap
transcript; QA-016.

## B-091 — Interactive notices leak CLI remediation syntax into the TUI

Found: whole-product TUI acceptance, Add Registry result (2026-09-08) · Severity: high ·
Status: resolved (D-185; awaiting manual retest as QA-017)

Adding an alias or origin already present in configuration produces domain diagnostics whose
remediation strings are literal `aart source sync`, `resubscribe` and `remove` commands.
`io/consumer_actions.py::_refusal` flattens messages and remediations into one tuple, so the TUI
draws the CLI instructions verbatim. The observed line was long enough to be clipped after
`aart source remove`, making both the diagnosis and the next action harder to understand.

Keep domain diagnostics useful to the CLI, but give the interactive adapter a TUI-native
projection. A duplicate connection should say that the Registry is already connected, focus or
link to its existing row, and expose supported actions as contextual keys/buttons. If an action is
not yet present in the TUI, state the limitation plainly and track the missing surface; do not turn
the interactive application into a list of shell commands. Model typed remediation actions where
needed instead of parsing command strings in a renderer.

Audit every TUI-visible diagnostic/remediation route and add a property that no rendered TUI frame
contains an `aart ...` command. CLI and JSON rendering retain their complete remediation contracts.

Evidence/links: `tui_sources.py::plan_source_addition`;
`io/consumer_actions.py::_refusal`; `tui_consumer.py::ConsumerScreenSource.body`; QA-017.

## B-092 — A declined preparation remains on a confirmation screen with nothing to confirm

Found: whole-product TUI acceptance, duplicate Add Registry (2026-09-08) · Severity: high ·
Status: resolved (D-184; awaiting manual retest as QA-018)

The Add Registry reducer navigates to Review before asking the action adapter to prepare the exact
transaction. When preparation refuses a duplicate alias/origin, `_declined` clears the pending
action and emits `ACTION_PREPARED` with no review digest. `_action_prepared` correctly refuses to
record that as a valid review, but leaves the session on `REGISTRY_REVIEW`. The screen still tells
the operator to press Enter to connect; doing so reaches the execution boundary without a pending
action and prints `nothing was prepared for this action; review it again`.

A declined preparation must leave no confirmable-looking screen. For duplicate Registry identity,
return to Registries and focus the already connected row. For correctable form input, return to the
Add form with values preserved and the relevant field identified. Esc/back must remain visible in
the screen chrome, but it is not the repair for a state machine that advertises an impossible
confirmation.

Characterize the exact public shell walk first. Its negative should prove that a failed preparation
cannot emit an execute command on a subsequent Enter and that no failed path silently writes
configuration.

Evidence/links: `consumer_ui.py::_request_action`, `_action_prepared`, `_confirm_action`;
`io/consumer_actions.py::_declined`, `_execute`; QA-018.

## B-093 — Git acquisition calls a symlink unsafe without identifying the file kind

Found: whole-product TUI acceptance, adding the Superpowers Source (2026-09-08) · Severity: medium ·
Status: resolved (D-183; awaiting manual retest as QA-019)

The Superpowers fork contains one symlink, root `AGENTS.md -> CLAUDE.md` (Git mode `120000`). AART
correctly refuses it at the Git snapshot boundary, but reports only `Git tree contains an unsafe
entry: 'AGENTS.md'`. The operator cannot tell whether the problem is a symlink, executable, special
file, path traversal or malformed Git mode, and therefore cannot choose a safe correction.

Keep the fail-closed rule. Make the diagnostic name the observed entry kind and explain the safe
options without suggesting that AART follow or materialize an unreviewed link: replace it in the
source repository with a committed regular file, remove it if unused, or choose a source without
symlinks. Preserve the exact path but never print the link target unless it has separately passed
the repository path-safety rules.

Evidence/links: `sources/git.py` Git tree parsing; Git mode `120000` in
`M1F1/superpowers-aart-test`; QA-019.

## B-094 — YAML authoring Sources are refused before Candidate discovery — CRITICAL

Found: whole-product TUI acceptance, Superpowers Source onboarding (2026-09-08) · Severity:
blocking · Status: resolved (D-176; awaiting manual retest as QA-020)

The intended flow is exactly Product Specification 72.1/164.2: subscribe to an author repository,
discover only explicit `aart.yaml`/`aart.json`, compile Candidates, promote selected Candidates into
the Registry, and detect later upstream changes without rewriting the approved version. The
repository remains a Source of Candidates; only promoted artifact payloads become Registry content.

The public path cannot admit that repository. `source add --kind source-git` validates its acquired
tree through `validate_source_candidate`, which calls `load_native_source`. That loader requires a
root `aart-source.json` and canonical native packages under declared roots —
`<root>/<kind>/<name>/artifact.json` plus `payload/`. An author repository containing the accepted
YAML manifest shape is rejected before Maintainer Sync reaches `compile_author_source`, the code
that actually knows how to discover and compile the YAML. Adding only `aart-source.json` changes
the error but does not bridge the two formats.

`registry scan` is not the public-flow substitute: it can compile YAML from a local checkout, but
it only prints Candidates and does not persist the Source/Candidate history the Maintainer TUI
reads. `registry vendor` can copy one subtree into the Registry, but that deliberately bypasses the
monitoring and Candidate lifecycle being tested. Neither may be credited as evidence for the
mandatory flow.

Reclassify this as critical because it blocks the accepted Source Repository → Manifest Discovery →
Candidate → Promotion workflow and INV-201 at its public entrance. Characterize RED with a real
temporary Git repository containing only a valid `aart.yaml` and payload. Separate authoring-Source
admission from consumer-native-package validation without weakening symlink, special-file, identity,
transport or last-known-good checks; then prove initial add/sync, one Candidate, upstream movement,
selected promotion and unchanged approved history through the shell/TUI.

Resolved by `sources/validation.py::validate_authoring_source_candidate`: a tree declaring
`aart-source.json` is still read by `load_native_source`, any other tree is admitted when
`discover_author_manifests` finds at least one explicit manifest, and a tree declaring neither is
refused by name. Its `declared_source_id` is the configured alias, so an ordinary upstream commit
is not read as an identity transition. The consumer Marketplace projection for an authoring Source
is empty rather than an `Err`, which is what stops one subscribed author repository from emptying
the Marketplace. Evidence: `tests/authoring_source_admission_e2e_test.py` (real temporary Git
repository, real public command, add → sync → Candidate → upstream movement → promotion),
`tests/source_validation_test.py`, `tests/consumer_runtime_test.py`.

Evidence/links: Product Specification 72.1 and 164.2; INV-199–INV-201;
`sources/validation.py::validate_source_candidate`; `protocol/native_tree.py::load_native_source`;
`io/maintainer_sync.py`; `protocol/authoring.py::compile_author_source`; QA-020; D-176.

## B-095 — One-off YAML repository scan cannot feed selective Registry vendoring

Found: whole-product TUI acceptance, external artifact onboarding clarification (2026-09-08) ·
Severity: high · Status: open

Besides monitored Sources, the operator needs an artifact-scoped adoption path for repositories
that must not remain configured Sources. Given a credential-free Git URL/ref, AART should discover
only explicit `aart.yaml`/`aart.json`, show the resulting artifacts, let the maintainer select one or
more, and vendor only the files each selected manifest declares in `payload.include`. Registry
content then owns those immutable bytes and records the upstream URL, resolved commit, manifest
path/input digest and vendoring provenance.

The component capabilities exist but do not compose. `registry scan` compiles explicit author
manifests from a clean local checkout and only prints its Candidates. `registry discover` produces
a vendor-batch manifest from conservative conventional-shape inference rather than consuming author
YAML. `registry vendor` acquires and copies one path but ignores the manifest and asks the operator
to repeat its metadata as flags. `vendor-batch` applies a separately authored decision document.
None is the requested public or TUI flow.

Add `Scan Repository` to Maintainer Registry and a machine-complete CLI equivalent. Acquisition
remains hardened and read-only; discovery remains exact-manifest-only; selection is explicit; the
review names every chosen coordinate, resolved commit and copied path; one confirmation applies the
whole selection atomically. Do not create a configured Source or require root `aart-source.json`.
The author manifest itself is evidence/provenance, not payload unless it includes itself.

Because the repository is not subscribed, do not imply continuous monitoring. Expose an explicit
per-artifact `Check upstream` action using recorded provenance. A changed manifest/payload proposes
a new Registry version and never rewrites the immutable published version; missing/unreachable and
unchanged remain distinct. This complements rather than replaces critical B-094's monitored Source
flow.

Evidence/links: `registry scan`, `discover`, `vendor`, `vendor-batch`;
`protocol/authoring.py::compile_author_snapshot`; `registry_commands/planning.py`;
`MaintainerScreen.REGISTRY`; QA-021.
