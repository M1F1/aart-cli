# AART Refactor Discovery Backlog

> **CP-26 consistency audit (2026-09-19):** Current acceptance follows Product Specification §169
> and D-332–D-335. B-144/B-150 belong to 19, B-143 to 20, and B-151 remains a precondition of 21.
> B-121 is absorbed into 19; B-076 concerns explanatory guidance only. Historical findings do not
> authorize shared runtime inputs. See `CONTRACT_ALIGNMENT.md`; no implementation issue was closed
> by this documentation audit.

> This is deliberately **not** the critical path.
> Product Specification + EXECUTION_PLAN are mandatory.
> Agents append non-blocking discoveries here instead of expanding the active slice.

## Backlog admission rule

CP-23 follow-up (2026-09-14, D-250): all-screen Frame/Verbose compliance and explicit credential
purpose/acquisition guidance are mandatory tasks 14 and 13, respectively. Do not defer failures
of those acceptance criteria here as presentation polish or optional documentation. No unrelated
new backlog item was discovered during this planning update.

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
Discovered in: CP-08 / `aart_cli/io/credentials.py` / `MacOsKeychainProvider.store`
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
Discovered in: CP-08 / `aart_cli/domain/inputs.py` / `_url_host`
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
Discovered in: CP-09 / `aart_cli/domain/python_runtime.py` / `ArtifactEnvironment`
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
Discovered in: CP-09 / `aart_cli/io/python_runtime.py` / `install_dependencies`
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
Discovered in: CP-10 / `aart_cli/application/runtime_projection.py` / `generate_launcher`
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
Discovered in: CP-10 / `aart_cli/domain/harness.py` / `MCP_TARGETS`
Why useful: `MCP_TARGETS` carries Tabnine and Claude Code. The legacy `profiles/builtin.py` also
carries OpenCode and Vibe, but marks their MCP keys and hook event model as unverified best-effort
defaults.
Why noncritical now: CP-10 needs one real harness adapter and Tabnine is measured. Copying an
unverified path into a canonical table would launder a guess into an authority (D-025).
Potential approach: install one server against a live build of each and read back what the harness
actually parsed, the way the Tabnine target was established.
Invariants touched: INV-058, INV-059.
Evidence/links: D-025; `aart_cli/profiles/builtin.py` OpenCode note at §19.
Promotion condition: a user targets OpenCode or Vibe on the critical path, or a live build becomes
available to measure.

### B-021 — A launcher for a platform without a POSIX shell
Status: OPEN
Discovered in: CP-10 / `aart_cli/application/runtime_projection.py` / `_render`
Why useful: the generated launcher is `/bin/sh`. Windows has no POSIX shell by default, so an
installation there has no runtime projection at all.
Why noncritical now: pairs with B-017 — the environment layout differs on Windows too
(`Scripts/python.exe`, not `bin/python`), so both are one piece of work, and neither is on the
critical path.
Potential approach: a second renderer selected by platform, with `shell_quote`'s property test
repeated against the real target shell rather than assumed.
Invariants touched: INV-060, INV-100.
Evidence/links: B-017; `aart_cli/domain/python_runtime.py` `_INTERPRETER_SUBPATH`.
Promotion condition: Windows enters the supported platform set.

### B-022 — Provider values whose trailing whitespace is significant
Status: OPEN
Discovered in: CP-10 / `aart_cli/application/runtime_projection.py` / `generate_launcher`
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
Discovered in: CP-11 / `aart_cli/application/installed_state.py` /
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
Discovered in: CP-13 / `aart_cli/tui_consumer.py` / `CanonicalScreenSource`
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
Discovered in: CP-13 / `aart_cli/tui.py` / `run`
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
Discovered in: CP-13 / B-024 / `aart_cli/io/`
Why useful: canonical installed state could be projected and verified but not kept. Every reader of
`InstallationReceipt` took one as an argument; nothing wrote one down and nothing read one back, so
no canonical installed state survived the process that produced it.
Promotion evidence: B-024 assembles `ConsumerScreens` over canonical services. Installed (12–14),
Updates (15–16) and Activity (25–27) are all projections of installed state and past actions, so
without persistence the canonical shell can only ever draw an empty machine — and CP-13 step 6
cannot retire legacy authority whose one remaining advantage is that it persists
(`receipt_service.py`, `setup_receipt.py`). CP-16 supportability has the same dependency.
Invariants touched: INV-149, INV-152, INV-169.
Evidence/links: D-044, D-045; `aart_cli/io/receipt_store.py`; `tests/receipt_store_test.py`.
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
Discovered in: CP-13 / `aart_cli/application/consumer_ui.py` / production action handler
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
Discovered in: CP-13 / `aart_cli/tui_consumer.py` / `read_consumer_offers`
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
Evidence/links: D-044, D-045, D-068, D-088; `aart_cli/io/configured_offers.py::_declined`,
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
out -- not just a test fixture. Reachable from `aart-cli registry promote`
(`aart_cli/commands/registry.py:800`). That is a mandatory-invariant break on the critical
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

Evidence/links: D-088, D-089; `aart_cli/application/promotion.py::plan_bulk_promotion`,
`::validate_promoted_registry`, `::load_registry_versions`.

## B-038 — Native source content has no canonical consumer path

**Classification: PARTLY CLOSED (2026-09-02) — screen 21 now lists the configured sources and says
why a native one offers nothing (D-114). What remains is in `aart-cli marketplace install`, not in the
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
source, which sends `aart-cli marketplace install` down the characterized path that installs from it.
Its own docstring says as much: "Collections and direct/local sources stay on the characterized path
until their own public replacement evidence exists."

Screens 31–34 hold the canonical Source capability (D-093–D-097), including a real local Source Sync
that creates Candidates without promotion, so the evidence the docstring waits on now exists for
Sources. The remaining step is therefore a characterized test of `aart-cli marketplace install
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
wrong and is not remaining work. `commands/marketplace.py` — the public `aart-cli marketplace
install|update|uninstall|setup` command — composes `ConsumerApplicationService` directly and runs
the setup queue through it, and `tui_marketplace.py`, which the canonical shell imports, takes
`LifecycleItem` and `InstallMode` from `lifecycle/model.py` and `installation/model.py`. The stack
is load-bearing for a public flow; it is not legacy authority awaiting a strangler. What it *does*
expose is B-044: the canonical shell reaches none of it, and so performs no post-install setup and
offers no usage report.

Evidence/links: D-062, D-087, D-113, D-115, D-116, D-117, D-118; B-025, B-044;
`aart_cli/tui.py::run`.

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
Evidence/links: `aart_cli/application/maintainer_views.py::_file_changes`; INV-202; 164.5.

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

Measured while building B-044's fixture, and independent of it. After `aart-cli marketplace install`
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
rule asks for. ~~The public `aart-cli marketplace install` carries both and is unaffected.~~ That
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
3. **The layering inverts.** `io/consumer_actions.py` imports `aart_cli.tui` (lazily, inside
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
`aart_cli/` writes install state on that path.

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
appear anywhere in `aart_cli/protocol/authoring.py`: the authored `aart.json` accepts
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

**The route in.** `--setup-recipe` is on `aart-cli registry vendor`, not `registry scaffold`
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

**What the fixture proves changes this entry's headline.** `aart-cli marketplace install` does *not*
carry setup for an approved registry coordinate. It reaches `_configured_lifecycle`, which calls
`complete_configured_installation` and emits its receipt payload -- there is no `setup` key in it
and no diagnostic -- exactly as the shell's `_execute_installation` does. Setup runs only on the
legacy path, which `_configured_registry_selection` routes to by returning `None`, and it returns
`None` only for a direct or local source. So the gap is the configured canonical seam itself, not
the shell's use of it, and both front ends report a finished install of an unconfigured artifact.

`aart-cli marketplace setup` does not recover it either: run against the same machine afterwards it
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

**A canonical receipt does not name the object that was installed.** After `aart-cli marketplace
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
  for `aart-cli marketplace receipt show|verify|undo`.
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
reads the objects it recorded and carries `pending_setup`, `aart-cli marketplace install` emits an
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
`aart-cli marketplace receipt show|verify|undo` -- the canonical route has no such pointer and needs its
own durable setup record.

What remains: give the canonical action handler its own setup and reporting completion.
`_canonical_setup_run` and `_complete_canonical_consumer_action` are deliberately retained in
`aart_cli/tui.py` as the material for it — they are the only implementation of the
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
pointer only from the retiring install-state manifest, so `aart-cli marketplace receipt
show|verify|undo` cannot yet locate a setup run made by a configured install. Add a receipt-backed
locator (without writing legacy install state), characterize all three public verbs, and preserve
the existing review-before-undo and stale-record checks.

Evidence/links: D-126, D-128; B-044; `aart_cli/setup_receipt.py`,
`aart_cli/io/configured_setup.py`.

### Completion (2026-09-03)

Closed by D-130. `setup_receipt.locate_receipt_setup_record` reads the pointer off the receipt;
`receipt_service.load_receipt` asks the canonical store first and falls back to the manifest, so a
machine holding only legacy installations answers exactly as before. No legacy install state is
written. Acceptance is `tests/configured_setup_gap_test.py::ConfiguredReceiptVerbsTest`, which
installs through the public command and then drives all three verbs against what that install
recorded, plus `tests/setup_receipt_cli_test.py::CanonicalReceiptCommandTests` (every legacy
assertion re-run over a canonical receipt) and `::CanonicalReceiptAbsenceTests`.

## B-047 — The canonical shell never says how much of a list a filter matched

Discovered during the `aart_cli/tui.py` orphan sweep (D-129). The retired wizard answered
every query with a count -- `2 of 4 match 'review'.`, `Nothing matches 'kubernetes'. 4 entries
searched.` -- so a person could tell an empty screen caused by a typo from one caused by having
nothing installed. `CanonicalScreenSource.rows` filters and returns; `frame()` draws `Filter: <q>`
and the surviving rows, and nothing anywhere reports how many were hidden.

The safety half of the wizard's behaviour does hold and is now pinned: a filter that matches
nothing yields no rows, so no row can be acted on, and the screen does not change
(`tests/consumer_shell_test.py::test_a_filter_that_matches_nothing_empties_the_screen_without_leaving_it`).
Only the count is missing, which is why this is noncritical: no invariant depends on it.

Evidence/links: D-129; `aart_cli/tui_consumer.py` `CanonicalScreenSource.rows`, `frame`;
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

Evidence/links: D-129; `aart_cli/io/consumer_actions.py` `_refusal`, `_lines`;
`aart_cli/tui_layout.py` `CONTENT_MEASURE`, `wrap`.

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
`aart_cli/tui_maintainer.py`; `tests/tui_marketplace_test.py`.

## B-050 — `aart-cli source health` has no public-flow test

Found while opening CP-15, when `aart-cli source sync` turned out to have none either and step 1 wrote
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

Evidence/links: D-132; `aart_cli/commands/source.py` `_health`;
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
edge-case behaviour, which is what CP-16 (`aart-cli doctor` as environment-wide inspection with
machine-complete JSON) exists to build. Whoever opens CP-16 should read this item first.

Resolution: `aart-cli doctor` now reports source/artifact metadata, exact approved canonical payload
and runtime-dependency readiness as separate fields in both renderings before installation. It
verifies vendored bytes against the approved object digest without publishing them. Declared
runtime dependencies remain `unverified`, rather than guessed cached or missing, until the deferred
B-010 capability supplies durable package-manager cache evidence. Public E2E scenarios hold cold,
referenced, dependency-free, dependency-declaring, multi-source and multi-artifact states.

Evidence/links: INV-223; `docs/product-specification/PRODUCT_SPECIFICATION.md` 165.11;
`aart_cli/marketplace/catalog.py` `_resolution_failure`;
`aart_cli/installation/application.py` `INSTALL_OBJECT_UNAVAILABLE`;
`aart_cli/io/python_runtime.py` `_install_argv`; `tests/offline_capability_test.py`.

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

Evidence/links: D-133; `aart_cli/setup_runtime.py` `_apply_effects`;
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

Evidence/links: `aart_cli/commands/marketplace.py`; `aart_cli/domain/policies.py`;
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

**Originally not critical.** No Product Specification invariant required the two verbs to compose,
and CP-15 step 7's boundary claims were about what promotion does *not* do. The item explicitly
became critical if a later live chain put promotion's output through a publication gate.

**CP-17 step 2 update.** The consumer consequence became critical and is closed: public source
validation and Marketplace projection now recognize promotion's versioned approved-registry shape
and validate it with `load_registry_versions` / `validate_promoted_registry` (D-147). The original
command disagreement remains here: the older `registry publish` verb still expects the compiled
maintainer-workspace shape. CP-17 follows the accepted 165.27/165.28 boundary instead -- promotion
prepares local state and Git review/merge publishes it -- so making that legacy verb compose is not
required to continue the live chain.

**CP-19/QA-025/QA-032 reclassification — CRITICAL (2026-09-09).** The real local Rebuild and
Registry PR reached both deferred boundaries. `registry init` generated
`.github/workflows/aart-registry.yml`, and both of its
matrix jobs validate every PR with the legacy `registry format/validate/lock/build/audit/test`
sequence. A TUI promotion writes the accepted versioned representation, so the first real promoted
artifact fails both jobs with the missing unversioned `artifact.json` and mismatched legacy lock and
index. Screen 46's Rebuild sends the same canonical output through the same legacy maintenance
authority and stops at `lock` for the same reason. Both the local TUI maintenance path and generated
publication gate therefore reject the output of canonical promotion.

This is not evidence that the promoted Registry is corrupt. The public `source add --kind
registry-git` path acquired remote branch `qa/publish-v1` at exact revision `cc7c01d` and reported
it healthy, exercising `load_registry_versions` and `validate_promoted_registry`. It is evidence
that maintenance invokes the wrong authority. CP-19 must provide representation-appropriate
deterministic maintenance and public read-only validation of the checked-out promoted Registry,
then have the TUI and generated workflow use them. Do not restore green by emitting a second legacy
representation or weakening either validator.

Evidence/links: QA-025; QA-032; GitHub Actions run `34341007222`; D-147; D-204; D-205;
CP-19 step 9.

**CLOSED by CP-19 step 9 (2026-09-09).** Maintenance now dispatches on the representation it is
handed rather than assuming the authoring workspace (`D-208`). `is_promoted_registry` recognizes the
approved shape; `validate` stops requiring a compiled lock and index for it; `build` derives exactly
`registry/index.json` and `registry/snapshot.json`; `lock` is a read-only prepared curation, since
the approved version records already pin what `aart.lock.json` used to; `publish` runs the same
build, validate and audit without the lock half. The verbs' names and the generated workflow are
unchanged, so registries already scaffolded keep working, and the authoring workspace keeps its
existing path untouched. `tests/promoted_registry_maintenance_e2e_test.py` runs all six generated
verbs over a workspace built by the public `init → scan → promote` chain and holds that maintenance
never writes the older representation. The third consequence above -- a checkout that is also a
consumer `source-local` source -- stays out of scope: that arrangement is the one CP-15 step 7
deliberately does not support.

## B-058 — Scoped mutmut can reuse stale outcomes after test-only changes

Found in CP-16 step 1. After adding assertions to `tests/doctor_command_e2e_test.py`, rerunning the
same `make mutants ONLY=aart_cli/commands/doctor.py TESTS="tests/doctor_command_e2e_test.py"`
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

Evidence/links: D-134; D-091; CP-16 slice step 3; `aart_cli/commands/doctor.py`.

## B-060 — Step 3's repair command was never given a scoped mutation run

Found in CP-16 step 4b. Running `make mutants ONLY=aart_cli/commands/doctor.py` over all four
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

Evidence/links: D-134; D-091; B-059; CP-16 slice steps 3 and 4b; `aart_cli/commands/doctor.py`.

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

Evidence/links: D-134; D-091; B-060; CP-16 slice steps 4b and 4c; `aart_cli/commands/doctor.py`.

## B-062 — A machine with no credential provider reports no credentials rather than saying it could not look

Found in CP-16 step 4c. `aart-cli doctor` reports credential health from
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
`aart_cli/io/consumer_machine.py`; `aart_cli/commands/doctor.py::_credential_lines`.

## B-063 — Twelve unclaimed mutation survivors in `domain/selection.py`

A scoped run over `aart_cli/domain/selection.py` with the three test files that claim it
(`git_revision_provenance_test`, `selection_domain_test`, `installation_proposal_test`) left twelve
survivors, none of them in the code those files claim: eight in `_safe_line` and two each in
`artifact_request_sort_key` and `artifact_coordinate_sort_key`. Ordering is exercised widely
elsewhere in the repository, so these are survivors of the *scope*, not necessarily of the suite.

Reading them means running the same module against the broader set of tests that construct
selections and asserting ordering directly, which is a different question from CP-17's.

**Not critical path.** No Product Specification invariant depends on it, and D-134 makes an
out-of-scope survivor a backlog note rather than a finding.

Evidence/links: D-134; D-149; CP-17 step 2 review; `aart_cli/domain/selection.py`.

## B-064 — The CLI cannot install any artifact that declares an input

`aart-cli marketplace install` has no flag that answers a declared input: the required-input form belongs
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
`aart_cli/commands/marketplace.py`; `aart_cli/io/configured_installation.py`.

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

D-150 stopped `aart-cli doctor` reporting `ready` over a payload that is gone. On the placement path the
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

Evidence/links: D-150; D-029; B-029; CP-17 step 4 probe; `aart_cli/application/installed_state.py`.

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
`COLLECTION_NOT_FOUND`, and `aart-cli marketplace install <source>/collection/<name>` is a documented
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
`aart_cli/io/configured_selection.py`.

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

`tests/legacy_authority_reachability_test.py` builds the import graph from `aart_cli.cli`
and `aart_cli.__main__` and asserts that every shipped module is reachable, or named in an
exception list. Six names are listed. Two carry a reason:

- `aart_cli._commit` — written by the build, which stamps a commit into release artifacts.
- `aart_cli.application.credential_lifecycle` — retained deliberately, because the
  credential lifecycle is incomplete and removing it would claim a replacement that has not
  happened.

The other four have no reason recorded, and the first draft of the test's docstring said "two
exceptions remain deliberate" while the list held six:

| module | lines | reached by |
|---|---|---|
| `aart_cli/domain/ports.py` | 26 | `domain_kernel_test` only |
| `aart_cli/domain/outcomes.py` | 104 | `domain_kernel_test` only |
| `aart_cli/domain/collections.py` | 21 | tests only |
| `aart_cli/profiles/loader.py` | 147 | tests only |

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

`aart_cli/domain/outcomes.py` is reached by no runtime import. Its live counterpart is
`reporting/model.py`'s `SessionOutcome`, which carries a `no-op` state the domain enum never had,
so the shipped session vocabulary is elsewhere and this module is a duplicate nothing serializes.

It cannot simply be deleted. `scripts/release.py:31` declares it in `SCHEMA_INPUTS`, and its
sha256 is pinned in fifteen issued `docs/release/schema-freeze-v*.json` documents including the
live v18. Those documents are immutable evidence (`scripts/release.py:22`): a new release series
adds its own contract beside the frozen ones and never regenerates them. Removing the module is
therefore a contract change — a new `RELEASE_CONTRACT_VERSION` with its own freeze, compatibility
document and checklist — and the same cut should be reviewed for whether any *other* entry in
`SCHEMA_INPUTS` has likewise stopped describing a wire surface.

**Update (D-275, 2026-09-15).** The numbered contract series is gone. Retiring the module is now
removing it from `SCHEMA_INPUTS` and running `make release-freeze` in the same change; the review
of the other inputs still applies.

Not critical: the module costs 104 lines and no behaviour, the reachability test states its
position honestly, and `TheDeclaredSchemaInputsExistTest` now prevents the deletion being
attempted by accident. It becomes critical only if a Product Specification invariant turns on the
release contract naming exactly the wire schema and nothing else.

Evidence/links: D-154; B-070; `scripts/release.py:22-45`; `tests/release_test.py`
(`TheDeclaredSchemaInputsExistTest`).

## B-072 — the only mechanism for externally-defined profiles is never called

Found: CP-18 step 3 (2026-09-04) · Severity: medium · Status: open

INV-001 requires enterprise profiles to live outside the public tool.
`aart_cli/profiles/loader.py` implements that: `load_profiles(project)` overlays
`<project>/.agent-artifacts/profiles.json` onto the built-ins, validates the records, and rejects
malformed `unsupported` reasons with a stable user-facing message.

Nothing calls it. `aart_cli/consumer/runtime.py:947` passes `builtin()` directly into the
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
`PRODUCT_SPECIFICATION.md:1806`; `aart_cli/consumer/runtime.py:947`.

## B-073 — no live smoke scenario runs in CI, and there is no workflow that could carry one

Found: CP-18 step 5 (2026-09-04) · Severity: low · Status: open

**2026-09-19 scope clarification (D-348).** CP-26.20a / Product Specification §170 adds an
owner-invoked local CLI for already installed MCPs and requires direct/harness live acceptance.
It does not add scheduled CI or automatically test uninstalled Candidates. That accepted product
work is mandatory in CP-26, while this scheduled/CI automation finding remains open and
noncritical; completion of 20a alone must not close B-073.

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

> Historical resolution under the former INV-057. D-333 now requires mutation of one sole
> installation owner; CP-26.19 supplies new evidence. The shared-reference requirement quoted
> below is historical and must not be reintroduced.

Found: CP-18 step 5 (2026-09-04) · Severity: low · Status: resolved 2026-09-14 (CP-23 task 12, D-262)

Resolution: screen 24's Replace and Delete rows plan through `plan_credential_mutation`. The
replacement review names every dependant before confirmation, and deletion of a reference anything
uses is refused by the planner, which the TUI never acknowledges. `credential_lifecycle` is off the
deliberate non-runtime list.

INV-057 requires that "deleting/replacing/rebinding a credential reference warns about artifacts
that depend on the same reference before destructive mutation".

Half of it ships. `application/consumer_session.py` computes `credential_dependants`, and
`aart-cli doctor` reports each credential reference with its health and the installations that depend
on it — `doctor_configuration_credentials_e2e_test.py` holds that.

The other half has nothing to attach to, because no public verb performs the destructive mutation.
`plan_removal` takes `delete_credentials`, and its docstring records the choice deliberately: it
"defaults to False everywhere: a credential outliving its last dependant is the documented
behaviour, not an oversight to be corrected by whoever calls this". No CLI flag sets it —
`aart-cli marketplace uninstall --help` offers none — and `application/credential_lifecycle.py`, which
would own rotation and rebinding, is one of the three modules `legacy_authority_reachability_test.py`
lists as deliberately unreachable, for exactly this reason.

So the invariant is not violated; the flow it governs does not exist yet. The work is the credential
lifecycle itself, and when it lands, the dependants warning is a precondition of its review step
rather than a feature to remember afterwards — `credential_dependants` already returns what that
warning needs.

Not critical to CP-18. It becomes critical the moment any public verb can delete, replace or rebind
a credential reference.

Evidence/links: INV-057; `aart_cli/application/removal_proposal.py:99-106`;
`aart_cli/application/consumer_session.py:146`; B-070's `credential_lifecycle` exception.

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

Evidence/links: INV-067; `aart_cli/wizard.py:36-38`; `tests/authoring_inputs_test.py:94-146`;
`tests/tui_boundary_test.py`.

## B-076 — Consolidate repeated input guidance while preserving installation owners

Status: OPEN, NONCRITICAL — explanatory presentation only (scope clarified by D-333, 2026-09-19).

INV-164 permits equivalent help text to be displayed once with the affected installation owners
identified. Input fields, answers and provider references must stay distinct: separate prompts per
installation are required behavior, including Collection members and multi-harness selection.
The old suggestion to remove duplicate prompts by grouping values under InputId is withdrawn.

The remaining opportunity is to reduce repeated explanatory text without hiding each target's
alias, artifact, harness/profile, scope and root. It is not required to complete CP-26.19 as long as
all owners and their independent inputs are clear. New shared-input machinery is out of scope.

Evidence/links: Product Specification §§154.6/169; INV-164/246; D-333; B-144.

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

**Extended by QA-026/D-202 (2026-09-09).** The always-visible route remains, but it is no longer a
fixed promise that hides local actions and advertises inert ones. Each frame now draws contextual
bindings first and the universal movement/back/help/quit set second. The contextual letter binding
contains both its event and its label, so keyboard handling and the footer cannot acquire separate
screen maps; structural bindings derive from the same screen sets and review map as the reducer.

## B-078 — Escape inherits curses' long escape-sequence delay

Found: manual TUI acceptance (2026-09-04) · Severity: high · Status: done

Pressing Esc to return from a detail screen pauses noticeably before the prior screen appears.
The reducer and machine reload are not the source: ncurses holds a lone escape byte while waiting
to see whether it begins a function-key sequence. The curses entry boundary should set an explicit
short delay once, before the shell starts, without moving key interpretation out of `key_event`.

Evidence/links: Product Specification 161.1; INV-187; `aart_cli/tui.py::run_consumer`;
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
configured and point to the real setup entry point. It initially named `aart-cli source add --help`;
B-082 subsequently built the same transaction into screen 21, so the current next step is
Registries → Add Registry. Manual acceptance places this as a `SETUP REQUIRED` callout before the
navigation menu, so the prerequisite is read before the unavailable destinations.

Evidence/links: Product Specification 161.1, 161.2 and 161.7; INV-026; B-075;
`tests/consumer_shell_test.py`; D-170/D-171; manual acceptance. The empty Dashboard and empty
Registries screen independently name the TUI source-add entry point.

## B-081 — Manual acceptance inherited two old user-level registry subscriptions

Found: manual TUI acceptance (2026-09-04) · Severity: medium · Status: done

The apparent built-in sources are not package defaults. `aart-cli source list --json` found two entries
persisted in the real macOS user configuration on 2026-08-15: `registry` points at
`M1F1/agent-artifacts-registry-2`, and `registry-a` points at `M1F1/agent-artifacts-registry`.
Both currently report `could-not-check`. A clean first-run acceptance session must remove those
subscriptions through `aart-cli source remove`; future scripted acceptance continues to use isolated
temporary homes so it cannot seed a developer's configuration.

Evidence/links: the public `aart-cli source list/remove` output; configuration path contract;
manual acceptance. Both removals were separately reviewed and finalized through the public command;
the final `aart-cli source list --json` returned an empty `sources` array and both managed snapshots
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
After maintainers merge a newer registry commit, however, the consumer needs `aart-cli source sync` to
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

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: open —
Skills, instructions, MCP and harness selection are measured, built, installed end to end and green
(D-194, D-197); guidelines and hooks remain unmeasured and refuse by name

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
`profiles/builtin.py::_OPENCODE`; official OpenCode Skill, Rules and MCP documentation; QA-011;
`D-194`; `tests/opencode_harness_test.py`.

Measured and closed (2026-09-08): `opencode debug skill`, `debug config` and `debug paths` against
OpenCode 1.18.29 gave both scopes for Skills, `AGENTS.md` and MCP. The entry-shape suspicion in this
entry was correct and is now `McpEntryShape.TYPED_COMMAND_VECTOR` on the target itself. Still open
in this entry's original scope: a guideline decision — that build documents no guidelines directory,
so the honest answer so far is refusal rather than a translation — and the plugin/event model, which
nothing here measured.

## B-086 — Codex is accepted as a compatibility name but has no canonical installation adapter

Found: whole-product TUI acceptance preparation (2026-09-08) · Severity: high · Status: open —
Skills, instructions and harness selection are measured, built and green (D-193); MCP (B-096) and
hooks remain unmeasured and refuse by name

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

Running `aart-cli registry init` without `--usage-reporting-repository` still emits an Issue Form and
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

`aart-cli registry audit` passes a newly initialized empty Registry, then emits two long warnings. One
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
Status: fixed, awaiting manual retest (D-186)

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
remediation strings are literal `aart-cli source sync`, `resubscribe` and `remove` commands.
`io/consumer_actions.py::_refusal` flattens messages and remediations into one tuple, so the TUI
draws the CLI instructions verbatim. The observed line was long enough to be clipped after
`aart-cli source remove`, making both the diagnosis and the next action harder to understand.

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
Severity: high · Status: fixed, awaiting manual retest — application (D-187), TUI adoption
(D-188/D-189), upstream check (D-190/D-191) and the CLI projection (D-192) are all built and green

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

**Built so far (D-187).** `aart_cli/io/registry_adoption.py` is the application half:
`scan_repository` (in-memory, writes nothing, saves no Source, refuses a repository declaring no
`aart.yaml`/`aart.json` by name), `prepare_adoption` (one atomic `plan_bulk_promotion` in VENDORED
mode over the chosen coordinates) and `apply_adoption` (review-digest checked, then
`finalize_promotion`). `tests/registry_repository_scan_test.py` holds it with 14 tests and five
killed targeted mutations.

**TUI built (D-188).** Screen 46 advertises `s` Scan Repository; 46c collects the credential-free
URL/ref and states that this is not a subscription; 46d renders every explicit manifest and makes
only validation-cleared rows selectable; `a` prepares one transaction for the selection; and 46e
names every coordinate, the resolved commit and every changed path before Enter applies the exact
review digest. The scan completes as a read-only preparation and deliberately leaves no pending
mutation; adoption is a separate prepare/confirm action. One composition test substitutes only the
Git transport and drives the production ports over a real repository and registry checkout.

**Upstream identity recorded (D-189).** Native provenance already held the URL, resolved commit,
manifest path and input digest, but not the branch/tag whose movement must be checked. Each new
adoption now adds immutable `aart.repository-adoption: {ref: ...}` provenance. It is package
metadata rather than Source configuration and does not change the author's canonical input digest.

**Application check built (D-190).** `list_adopted_artifacts` reads only packages carrying the
adoption record from a validated Registry snapshot. `check_adopted_upstream` resolves the recorded
ref once and compares the manifest's exact input digest, so unrelated commit movement stays
unchanged. Changed, missing, unreachable and invalid-manifest are distinct. A changed declaration
at the published version carries no plan and says a new version is required; a validated version
bump carries an ordinary `PreparedAdoption`, still behind its review digest.

**TUI check built (D-191).** Registry action `u` opens screen 46f over only repository-adopted
packages; Enter performs the explicit check and screen 46g preserves every typed disposition. A
proposal is still a read until `a` opens the existing exact adoption review and Enter confirms its
digest. The production-composition E2E adopts 2.1.0, moves real Git `main` to 2.2.0, then adds the
new immutable package while retaining 2.1.0.

**Still open.** The complete scan/select/adopt/check contract needs a machine-complete CLI
projection.

Evidence/links: `registry scan`, `discover`, `vendor`, `vendor-batch`;
`protocol/authoring.py::compile_author_snapshot`; `registry_commands/planning.py`;
`MaintainerScreen.REGISTRY`; `io/registry_adoption.py`; QA-021; D-187.

## B-096 — Codex keeps its MCP servers in TOML, which AART cannot edit safely yet

Found: QA-012 harness measurement (2026-09-08) · Severity: medium · Status: closed (2026-09-09,
D-196) — AART still does not write this file; Codex's own editor does, and user-scope registration
is measured, built and green

`LocalHarnessRegistry` is a JSON interpreter. Its whole contract is that the file belongs to the
harness and the person using it, so unrelated keys survive, permissions survive, and a file it
cannot parse is reported rather than replaced. Codex CLI 0.152.0 keeps servers as
`[mcp_servers.<id>]` tables in TOML — measured with `codex mcp add` against an isolated
`CODEX_HOME`, which wrote `command = "..."`, `args = [...]` and a nested `[mcp_servers.<id>.env]`
table — and there is no way to honour that contract with the standard library. `tomllib` reads TOML
but only from 3.11, while `requires-python` is `>=3.10`; nothing in the standard library writes it
at any version; and INV-071 forbids a runtime dependency. Hand-rolling a TOML editor that preserves
comments, ordering and unrelated tables is the kind of thing that silently destroys a person's
configuration, which is exactly what the JSON interpreter refuses to risk.

Until that is resolved, `mcp_target("codex", …)` raises the ordinary "nobody has measured this"
`KeyError` and Skills and instructions install normally. A Codex MCP artifact is therefore refused
by name rather than written to a file Codex does not read.

Two further facts were measured and belong to whoever picks this up. Codex reads
`[mcp_servers.…]` from a project `.codex/config.toml` **only when that project is trusted** in
`~/.codex/config.toml` (`[projects."<path>"] trust_level = "trusted"`) — verified by listing with
and without the trust entry — so a project-scope registration AART writes is inert until a decision
that is the operator's to make. And Codex ships `codex mcp add`/`codex mcp remove`, the harness's
own supported editor for that file; delegating to it would avoid hand-rolling a TOML writer
entirely, at the cost of making an installation depend on the harness binary being present and on
its CLI contract. Neither option should be chosen without measuring it.

Evidence/links: `domain/harness.py::MCP_TARGETS`; `io/harness.py::LocalHarnessRegistry`;
`tests/codex_harness_test.py`; QA-012; B-086; D-193.

Closed by the second of the two leads this entry recorded, and closed by measuring it rather than
by choosing it. `codex mcp add`/`remove`/`list --json`, run against an isolated `CODEX_HOME`, keep
exactly the promise `LocalHarnessRegistry` makes and a hand-rolled TOML writer could not: a config
file holding an operator's comment, an unrelated `model` key, another server's table and a
following `[tui]` table came back byte-identical after a server was added and removed. So the row
delegates: `McpEditor.HARNESS_COMMAND` on the target, routed by the registry, with `harness-editor-
missing` named when Codex is not installed and no fallback to writing the file directly. The first
lead — a TOML editor that preserves what it did not write — was not taken and is not needed.

The trust finding in this entry is why there is still no project row: `codex mcp add` writes the
global configuration and offers no project flag, and a project registration would be inert until the
operator trusts the project. `mcp_target("codex", Scope.PROJECT)` keeps raising. See `D-196`, and
`B-097` for hooks, which delegation does not help because the blocker there is a review gate rather
than a file format.

## B-097 — Codex hooks exist and are enabled, but a written file cannot make one run

Found: QA-012 harness measurement (2026-09-08) · Severity: medium · Status: open

`D-193` left the Codex hook row absent on the grounds that nothing had been measured. Measuring it
changes the reason rather than the answer, so this entry records what was found so that the absence
is a decision and not an omission.

`codex features list` reports `hooks` as `stable` and enabled, and `plugin_hooks` as `removed` —
hooks are a first-class configured capability of Codex CLI 0.152.0, not a plugin extension. The
shipped binary names twelve events (`PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`,
`PostCompact`, `SessionStart`, `SessionEnd`, `SubagentStart`, `SubagentStop`, `Stop`,
`UserPromptSubmit`, `Interrupt`) and four handler kinds (command, async, MCP server, managed).

Three properties, read out of that build, are why no row was added:

1. The hook configuration is reached through a `hooks` key in `config.toml` whose value is a path.
   That is the same TOML editing problem `B-096` documents, with the same `tomllib`/INV-071 answer.
2. Project-local hooks are disabled until the project is trusted: "Project-local config, hooks, and
   exec policies are disabled in the following folders until the project is trusted, but skills
   still load." The same trust decision `B-096` measured for MCP applies here and is the operator's.
3. Every new or changed hook is held for interactive review before it can run — the build carries
   "New hook - review required", "*n* hooks need review before they can run" and a
   `--dangerously-bypass-hook-trust` escape hatch that exists precisely to skip it.

So even with a valid file in the right place, an AART-written Codex hook would not run until a human
opened Codex and trusted it. Writing one and reporting success would be a receipt for something that
did not happen. A future slice should decide whether AART installs a hook and tells the operator
plainly that Codex will ask them to review it, which is a defensible product answer, but it is a
product decision and not a table row.

Not measured, and the first thing to measure next: whether the hooks file has a default location
(`$CODEX_HOME/hooks.json` was written into an isolated `CODEX_HOME` and neither confirmed nor
refused, because the `hooks/list` app-server method did not answer the probe's request shape), and
whether that file is JSON or TOML — the binary contains both "failed to serialize hooks.json" and
"failed to parse TOML hooks in", so it may accept either or the pointer and the file may differ.

Evidence/links: `codex features list`; strings measured from Codex CLI 0.152.0;
`domain/harness.py::HOOK_TARGETS`; `tests/delivery_targets_test.py`; QA-012; B-086; B-096; D-193.

## B-098 — A harness is not integrated until something installs through it and reads it back

Found: OpenCode/Codex install verification (2026-09-09) · Severity: medium · Status: open

`D-197` records a defect that neither harness table nor either harness's tests could have caught:
writing an MCP registration learned about `McpEntryShape` and reading one did not, so a correct
OpenCode registration observed as missing and every install of one ended partially-applied. Both
halves were individually right. Only installing through them and reading the result back found it.

Two harnesses now have that end-to-end proof — `tests/opencode_installation_e2e_test.py` and
`tests/codex_installation_e2e_test.py` — and Tabnine has had it since
`tests/artifact_installation_e2e_test.py`. Claude has target rows exercised everywhere and no test
that installs an MCP server for Claude and then starts what landed in `.mcp.json`. That is very
likely fine, since Claude's shape is the one the writer was built around, but "very likely fine" is
what was true of the reader too.

The three E2E modules are also now substantially the same file: compile an authored manifest,
publish it, describe it, plan against a target, install, assert. The differences worth keeping are
the target and the assertions about that harness. A shared fixture would make adding the fourth
harness cheap and would make the missing Claude case obvious rather than invisible.

Do this when a fourth harness arrives, or sooner if the duplication starts drifting. It is not on
the critical path: the two harnesses this work was asked for are proven, and nothing in the Product
Specification is unsatisfied without it.

Evidence/links: `D-197`; `tests/harness_registration_roundtrip_test.py`;
`tests/opencode_installation_e2e_test.py`; `tests/codex_installation_e2e_test.py`;
`tests/artifact_installation_e2e_test.py`.

## B-099 — Whether a TUI promotion leaves generated registry files complete — CLOSED

**Closed by CP-19 step 9 (2026-09-09).** Screen 46's Rebuild reaches the same curation authority the
CLI does, through `refresh_registry_workspace`, so the representation dispatch that closed `B-057`
repairs it at that one seam rather than in a second place (`D-208`).
`test_screen_46_rebuilds_the_registry_a_promotion_left_behind` calls that port over a really
promoted checkout and holds that lock, build, validate and audit all pass in canonical order. The
original question this item asked -- whether a promotion alone leaves the generated files complete
-- is answered on screen 46h by a rebuild reporting that nothing needed changing.

**Reopened by real manual retest (`D-205`).** D-200 supplied the missing route, but its focused
fixture never fed it the Registry that canonical promotion actually writes. The first real run
reached legacy `lock`, refused the missing unversioned `artifact.json` and stopped. Screens 46h/46i
exist and preserve ordering, but cannot maintain their own preceding workflow's output. QA-025 is
open again and this item joins B-057 in CP-19 step 9.

**Earlier closure (`D-200`).** Superseded rather than answered: screens 46h/46i now run lock, build,
validate and audit over the registry from the TUI, so the walkthrough no longer ends in four typed
commands whether or not they would have changed anything. Whether a promotion alone leaves the
generated files complete is now the maintainer's own observation on screen 46h — a rebuild that
reports "nothing needed changing" for every stage says so directly.

The original note follows.

The operator's walkthrough runs `registry lock`, `build`, `validate` and `audit` from the CLI after
promoting through the TUI, inherited from the pre-TUI version of that procedure. The promotion
already writes the approved registry state, revalidates the persisted tree and makes the local
commit, so those four commands may be writing nothing at all. The manual pass will say which:
`git status --short` immediately after the TUI's Registry Commit answers it.

If they change nothing, the walkthrough should drop them and the TUI is complete for that boundary.
If they do change something, the gap is real and this becomes a QA finding rather than a backlog
note. Not on the critical path either way — the Git publication boundary is deliberately manual.

## B-100 — A safe Registry baseline refusal does not identify the state that caused it

Found: manual TUI acceptance, QA-031 (2026-09-09) · Severity: high · Status: CLOSED by CP-19 step 7

**Closed (2026-09-09).** The baseline comparison remains byte-for-byte exact. The configured IO
seam now observes the checkout's Git top level, configured origin, worktree status, HEAD and merge
base only to classify a mismatch; the pure application seam owns the corresponding product-language
refusal. A clean descendant is unpublished work awaiting Git review/merge, a clean ancestor is a
stale checkout, managed-path changes are uncommitted drift, and a mismatched origin is the wrong
workspace. The first case explicitly orders publication, local update and Registry synchronization
without putting an `aart ...` command into the TUI (`D-214`).

The second real promotion stopped at screen 43 with `registry workspace does not match the
synchronized approved baseline`. The check is load-bearing and must remain exact: preparing another
transaction on top of Registry bytes consumers have never synchronized would make its reviewed
baseline false. The lab established the specific, legitimate mismatch. The writable checkout is
clean at local commit `cc7c01d` on `qa/publish-v1`, containing the first Skill promotion, while
`origin/main` and the approved Registry observation remain at `027ba7f`.

The defect is diagnosis and recovery, not the refusal. The screen shows a complete transaction and
then offers one generic sentence that cannot distinguish an unpublished prior promotion, a stale
local checkout, an accidentally selected workspace root or unrelated local drift. Those cases need
different operator choices; saying only “synchronize or restore” leaves the operator guessing which
state is authoritative and risks discarding an intentional promotion.

The CP-19 increment began with characterization over the four states above and kept the
baseline equality check intact. For the measured unpublished-commit case, the TUI should explain in
product terms that the prior Registry change must complete Git review/publication, the checkout must
observe that published state, and the Registry subscription must synchronize before another
promotion can be reviewed. Interactive guidance must contain no `aart ...` command text (D-185).

Evidence/links: QA-031; `tests/registry_baseline_diagnosis_test.py`;
`application/maintainer_promotion.py::prepare_promotion_transaction`;
Product Specification 161.7 and 165.28; D-103; D-137; CP-19 step 7.

## B-101 — A failed TUI action retains a confirmation for a plan that no longer exists

Found: manual TUI acceptance, QA-033 (2026-09-09) · Severity: high · Status: CLOSED by CP-19 step 10

**Closed (2026-09-09).** The two facts a review needed to tell apart -- a confirmation that never
happened and an attempt that is over -- arrived as the same event, so the reducer could only treat
both as nothing. `ACTION_FAILED` separates them, `failed_action` records which run this screen is
now the end of, and the confirmation disappears from the footer, from `key_event` and from the
review's own prompt (`D-209`). Held across four confirmed action kinds in
`tests/failed_action_terminal_state_test.py`, which also holds `QA-024`: an unconfirmed review
still asks for its confirmation.

The real Registry rebuild ran `lock`, received the known QA-032/B-057 representation refusal and
stopped. Its adapter correctly cleared `_pending` and `_pending_action`, but `_failed` emitted an
`ACTION_RECORDED` event with no text. `_action_recorded` treats that as no transition and leaves the
reducer on `REGISTRY_REBUILD_REVIEW` with its action and review digest intact. The static review
header still says to press Enter to start, and `_CONFIRM_SCREENS` still advertises `Enter Confirm`.
A second Enter therefore submits a confirmation the adapter can only reject as `nothing was
prepared for this action`.

This is independent of why the action failed. CP-19 must characterize a failed run as a terminal
state distinct from an unexecuted review, remove the stale confirmation and provide an honest route
to the owning list or a newly prepared retry. It belongs beside QA-027's successful-result exits,
but one must not be implemented as though the other had succeeded.

Evidence/links: QA-033; `io/consumer_actions.py::_failed`;
`application/consumer_ui.py::_action_recorded`; CP-19 step 10.

## B-102 — Git publication has no public transition from promoted-local to published — CLOSED

Closed by CP-19 step 8 (2026-09-09): there is no missing write. Publication is presence on the
canonical consumer-visible branch (INV-242), so it is a fact about the reading, and
`load_published_registry_versions` now applies it at the four consumer seams while every
maintainer-side reader keeps the durable record as written (D-207).
`tests/git_publication_transition_e2e_test.py` proves it across a real branch, `git merge --no-ff`,
public sync, Marketplace and an install receipt, and asserts the merged version records still say
`promoted-local` on disk. The original note follows.

Found: manual TUI acceptance, QA-034 (2026-09-09) · Severity: blocking · Status: closed

Registry PR #1 merged the real TUI promotion into `main`, the clean Consumer synchronized exact Git
revision `f37d182`, and source health is `healthy`. The synchronized snapshot contains the version
record, vendored `artifact.json` and payload. Marketplace nevertheless returns no artifacts because
the durable record still says `publication: promoted-local`, while `configured_selection` and
`configured_offers` admit only `PublicationStage.PUBLISHED`.

This is not a missing second PR: even the first merged Skill is absent. The public chain has no
operation that applies `publish_registry_version`. CP-17's Git-backed acceptance fixture concealed
the gap by calling that pure function internally before materializing the Git repository, so the
repository began life with `published` records instead of observing review/merge make them public.

CP-19 step 8 must start RED over the actual sequence: TUI-equivalent promotion output committed to
one branch, Git review/merge into the configured publication branch, public Source sync and
Marketplace read. Local promotion must remain non-public before the boundary (INV-242); the fix may
not make the local writer claim Git did something it did not do.

Evidence/links: QA-034; Product Specification 165.28; INV-137; INV-242;
`io/configured_selection.py::_approved_snapshot`; `io/configured_offers.py`;
`tests/git_backed_consumer_e2e_test.py::_registry_snapshot`; CP-19 step 8.

## B-103 — Workflow chrome and Back do not preserve operator context

Found: manual TUI acceptance, QA-036/QA-037 (2026-09-09) · Severity: high · Status: CLOSED by CP-19 step 11

**Closed (2026-09-09).** Typed workflow routes are checked against `navigation_targets` before they
are projected, and session history supplies which stages were actually visited. Shared frame chrome
marks completed/current/upcoming stages and bounds long trails to the content measure. Back retains
focus only across two screens of the same route, so Candidate identity survives every reverse edge
without making an unrelated Activity detail leak focus back to its list (`D-215`).

The Candidate flow shows only the current page title, so a maintainer cannot see completed,
current and upcoming review stages. Worse, pressing Escape from a later Candidate screen can return
to a prior screen whose stable Candidate focus is gone, producing `That Candidate is not
available.` A progress trail and correct Back behavior are one state problem: both must derive from
the navigation graph and the subject carried through it, never from renderer-local labels.

CP-19 step 11 owns a workflow-wide solution. Test at least Candidate promotion, Registry
initialization/rebuild, Source addition/sync and consumer installation; a breadcrumb that is right
for one hard-coded sequence is not the requested capability.

## B-104 — TUI lacks one readable visual hierarchy for sections, rows, help and key chrome

Found: manual TUI acceptance, QA-035/QA-038/QA-040/QA-041/QA-042 (2026-09-09) · Severity: medium/high
· Status: CLOSED by CP-19 step 12

**Closed (2026-09-09).** The layout kernel now names one restrained section rule and card grouping.
Dashboard explanation and activity, Registry records, help and footer all compose those primitives:
one explanatory region between rules, one blank between cards, one help binding per line, and one
compact width-bounded footer with `[Key] Action` labels. Registry card heads receive the screen's
stable focus and render `>` on the actual target (`D-216`).

The Dashboard has no visual boundary between navigation explanation and machine summary; Registry
items concatenate into a wall of text; the help overlay packs unrelated actions onto the same line;
and the contextual footer leaves a large void between `Keys here` and `Keys always`. Connected
Registry rows also omit the cursor entirely, making the focused action target invisible.

CP-19 step 12 must establish a small shared layout vocabulary: restrained section separators,
bounded rows/cards, visible focus, one help binding per line and compact keycaps such as `[Enter]
Open`. The exact separator glyph is presentation, but the grouping and focus are behavioral claims
and need renderer/property evidence across screen families.

## B-105 — Promotion mode names a storage strategy without explaining the decision

Found: manual TUI acceptance, QA-039 (2026-09-09) · Severity: high · Status: CLOSED by CP-19 step 13

**Closed (2026-09-09).** `promotion_mode_consequences` is the domain-owned explanation of both
choices. The Maintainer projection carries every choice and its selected state, and the review
renders ownership, payload availability and upstream dependence before confirmation. Vendored is
identified as the enterprise default and the footer says `Toggle mode` (`D-217`).

`vendored` and `referenced` change ownership, installed payload availability and the relationship to
upstream, yet Promotion Mode displays only the label. `m Mode` silently toggles it; when Referenced
is shown, pressing `m` simply produces Vendored with no preview of the consequence. CP-19 step 13
must explain both choices before confirmation, keep the active value visible and label the toggle
honestly. The explanation must come from the domain distinction rather than duplicate policy in the
renderer.

## B-106 — Registries advertises details for authoring Sources that it cannot open

Found: manual TUI acceptance, QA-043 (2026-09-09) · Severity: high · Status: CLOSED by CP-19 step 14

**Closed (2026-09-09).** Product Specification 161.7 defines screen 21 as Registry connections, so
`project_registries` now excludes every authoring Source kind. The projection continues after a
Source so ordering cannot hide a later Registry. Registry Sync is a row-owned request and its
availability and command focus both use the visible row, never stale navigation focus (`D-218`).

Screen 21 includes `source-git` authoring Sources beside `registry-git` connections and prints
`Actions: details.` for them. Its Enter router, however, accepts only `[ Add Registry ]`; attempting
to act on such a row leaves the internal diagnostic `no connected registry here is 21-registries`.
CP-19 step 14 must settle the Product Specification's Source/Registry distinction at this surface:
either exclude authoring Sources, or render and route them deliberately without presenting a false
action. Internal enum values may never reach operator-facing prose.

## B-107 — The layout kernel's width arithmetic is unheld by its own tests

Found: CP-19 step 5 scoped `make mutants` over `aart_cli/tui_layout.py` (2026-09-09)
Severity: medium · Status: open

The scoped advisory run reports survivors concentrated in the width arithmetic that predates this
slice: `_ellipsize`, `wrap`, `measure`, `_column_widths`, `columns`, `field_block`, `status_bar` and
`pane_budget`. Off-by-one bounds, swapped comparisons and dropped gap constants all pass, which
means the module's bounds are asserted at a few chosen widths rather than as claims. Nothing is
known to be wrong: a survivor is an unheld claim, not a defect.

CP-19 step 6 (QA-030) put the Candidates list and screen 47 on `columns`/`_column_widths` and
stated the claims it depends on — a bounded row, a cut cell, and a column whose position is the same
on every row including the header — as a property over generated names (D-213). That moved the
scoped run from 70 survivors to 67. What remains is everything those claims do not reach: the
shrink order in `_column_widths` when several columns compete, `_ellipsize` at width 1 and 2,
`wrap`'s break behaviour, `field_block`'s continuation column, `status_bar`'s hint dropping and
`pane_budget`'s floors. Any later slice that depends on one of those must state it first.
The ordering and grouping functions added by step 5 (`separate`, `action_prompt`,
`is_action_prompt`) are held; the survivors remaining in them are exact `ValueError` message texts,
which is `make mutants` noise rather than a finding (D-134).

## B-108 — The real macOS Keychain E2E is order-dependent in the integration suite

Found: CP-19 step 15 full verification (2026-09-09) · Severity: high · Status: intermittent,
retained after green CP-20 closing gates

Two independent `make integration` runs completed 380 of 381 E2E tests and failed while
`mcp_stdio_e2e_test` asked `/usr/bin/security create-keychain` to create a unique temporary
Keychain. Security.framework returned `errSecParam` (`-50`, process status 206): `One or more
parameters passed to a function were not valid.` The same test passed alone in 2.151 seconds and
the identical E2E was green twice inside the successful final `make quality` run.

The failure is not a leaked process environment or working directory: a diagnostic prefix run
reproduced it after 274 earlier E2Es with no changes to `os.environ`, the repository working
directory or `tempfile.tempdir`. An immediate retry with the same valid unique path also failed.
Smaller module combinations can pass, while the full integration ordering reproduces the failure.
Do not hide it with a platform skip or claim the separate gate is green. Resolve the Keychain test
isolation, then rerun `make integration`; the product assertions and CP-19 focused tests are not
implicated.

CP-20 closing evidence no longer reproduces the failure: the real Keychain E2E passed in both
3,677-test `make quality` executions and the immediately following standalone 381-test
`make integration`. No Keychain test was skipped or weakened. Because the earlier order-dependent
failure had no identified cause, one green closing sequence is evidence that the release gate is
currently clear, not proof that the intermittent condition can never recur; retain this item for a
future recurrence with the exact order and Security.framework diagnostics.

**Recurred at CP-23 task 15 (2026-09-15, `085d5df`).** The standalone `make integration` ran 393
tests in 246.8 seconds and failed once, in the same test:
`mcp_stdio_e2e_test.InstalledMcpServerTest.test_the_real_keychain_delivers_the_secret_to_the_launched_server`.
`/usr/bin/security create-keychain` returned status 206 for a unique temporary Keychain. The same
test passed inside the green 4,273-test `make quality` run just before. It was not retried or
skipped. The condition is therefore still live, and the standalone integration gate is not green for
CP-23.

## B-109 — `Diagnostic` accepts a message that is not a string

Found while reading `make mutants` survivors for CP-21 step 9 (`aart_cli/domain/publication.py`,
`application/registry_publication.py`, `io/registry_publication.py`). A recurring survivor class
replaces a refusal's `message` with `None`, and nothing notices: `Diagnostic.__post_init__` sorts
and freezes `remediation`, `details` and `interactive`, but never checks that `code` is a
`DiagnosticCode`, that `severity` is a `Severity`, or that `message` is a non-empty single-line
string. A `None` message survives construction and reaches a renderer, where it prints as `None`.

This is not specific to publication — it is every refusal in the repository, and it is why that
survivor class appears in any module `make mutants` is pointed at. Adding the three checks to
`Diagnostic` would kill the class everywhere at once. It is not on the critical path: no product
behaviour currently constructs such a diagnostic, and every call site passes a literal.

Not blocking. Do it in a slice that already touches `aart_cli/domain/diagnostics.py`, and
expect a wide but mechanical test fallout from fixtures that pass loose values.

## B-110 — `make mutants` reuses a stale working copy when `ONLY` changes

Reproduced three times during CP-21 step 9. Pointing `make mutants ONLY=<a.py>` at one module and
then at a different one makes the second run stop with:

```
Stopping early, because we could not find any test case for any mutant.
It seems that the selected tests do not cover any code that we mutated.
```

which reads as a test-selection mistake and is not one. `mutants/` still holds the previous run's
working copy, whose `mutmut-stats.json` reports `0 files mutated, 255 ignored, 1 unmodified`, so the
newly scoped module is never mutated. `rm -rf mutants` before the run fixes it every time, and the
run then completes normally.

`scripts/mutants.py` already writes and restores the `[mutmut]` scope in `setup.cfg`; it could
clear `mutants/` whenever the scope it is about to write differs from the one already recorded
there, which would make the tool honest about what it is measuring. The advisory nature of the gate
is why this is backlog rather than critical: the misleading message costs a run, not a wrong answer.

CP-21 `QA-076` reproduced the stale-copy condition again. Its runs moved each generated `mutants/`
tree to a unique temporary directory before changing scope; no generated mutation checkout remains
in the repository worktree.

CP-23 task 01 reproduced the same condition when switching from `application/consumer_ui.py` to
`io/consumer_actions.py`. Moving the generated UI checkout under `.git/` before rerunning the
new module restored mutation discovery. No runner or product gate was weakened.

## B-111 — `make mutants` aborts when a Hypothesis property test is in `TESTS`

Found: 2026-09-10, during CP-21 step 5.

`make mutants ONLY=aart_cli/tui_consumer.py TESTS="… tests/workspace_context_line_test.py"`
exits 2 with every mutant reported `not checked`, and the cause is buried far above the summary:

```
hypothesis.errors.FailedHealthCheck: The method
WorkspaceContextLineTest.test_a_shown_path_is_bounded_and_keeps_its_final_segment was called from
multiple different executors.
```

mutmut runs the suite from several executors; Hypothesis treats that as a source of flaky,
non-replayable results and refuses. The whole run is lost, not just the property test, and the exit
message says nothing about Hypothesis.

Workaround: leave property-test files out of `TESTS` and mutate against the example-based ones.
That is what step 5 did, and it costs nothing there because the property in question is about
`abbreviate_path` rather than about the mutated module. It will cost something the first time a
slice's only coverage of a claim is a property.

Worth fixing properly in `scripts/mutants.py` -- either by suppressing that health check for the
mutation run, or by naming the cause in the failure so the next agent does not spend the run
finding it. Related to `B-110`, which is the other way this command fails with a misleading message.

CP-23 task 01 reproduced this with `consumer_ui_state_test.py` during the clean-test phase.
The successful advisory retry used the example/E2E Source suites; the generated cursor property
remained enabled in ordinary tests and the deliberate mutation proof. No health check was disabled.

CP-23 task 15 is the case this item warned about. With `configuration_edit_test`,
`frame_matrix_test` and the other property-bearing files left out, 49 survivors inside task 14's
own functions looked unheld, and several of them were only held by the excluded files. A cheap way
to tell the two apart without disabling anything: after a run, execute
`MUTANT_UNDER_TEST=<module>.<mutant> python -m unittest <modules>` inside the kept `mutants/`
copy. The trampoline switches to that mutant under plain `unittest`, Hypothesis included.

## B-112 — `make mutants` mutates no class methods in `consumer_views.py`

Found: 2026-09-10, during CP-21 step 6.

A scoped run over `aart_cli/application/consumer_views.py` generated 4329 mutants and not one
of them touched a method: `ConsumerSession.navigate`, `ConsumerSession.back` and their neighbours
appear in `mutants/…/consumer_views.py` verbatim. Only module-level functions were mutated. mutmut
is capable of mutating methods — a run over `tui_consumer.py` produced
`xǁCanonicalScreenSourceǁ_list__mutmut_17` — so this is specific to that module, most likely to its
`@dataclass(frozen=True, slots=True)` shape.

Why it matters: a clean mutation run over that module says nothing about the code that holds the
session, the settings and the drafts, which is where its behaviour actually lives. An agent reading
"no survivors" could reasonably conclude the opposite of the truth. Step 6's own claims are held —
the targeted mutations covered `navigate` by hand and both were killed — but that was hand work
that the advisory tool did not and will not report on.

Worth pinning down which shape mutmut is skipping, and either recording it in `DECISIONS.md` as a
known blind spot the targeted mutation must cover, or configuring around it. Related to `B-110` and
`B-111`, the other two ways this command misleads.

## B-113 — `artifact_placement`'s refusals and its hook path are held only by their branching

Found: 2026-09-11, during CP-21 step 11.

The scoped run over `aart_cli/io/artifact_placement.py` generated 390 mutants and left 99
alive. Step 11 read them and fixed everything inside CP-21's claims: the declaration narrowing, the
skip that must not become a stop, and the request/capability asymmetry are held now, by tests whose
names say so. The re-run leaves 77, and they fall into three groups.

**Refusal wording (about sixty).** Each changes only the *text* of a refusal: a message replaced by
`None`, a remediation dropped, a literal uppercased or wrapped in mutmut's `XX` markers. They cover
`placement_for`'s guards on its own arguments, on a missing object and on a missing `harness_root`;
the three "registers with / merges into / is read by none of these harnesses" refusals; and
`_deliveries` and `_merges` on an undeliverable kind, a delivery-shape mismatch and a region of
somebody else's file. Every one of those branches has a test that reaches it and asserts `Err` plus,
at most, a code — enough to hold the branching and nothing about what the operator reads. `D-238`
makes a remediation a sorted set of remedies rather than prose, so it is assertable directly, and
`QA-078`'s test now does exactly that.

**Arguments on paths these three test files never walk (about ten).** The `_settings` call for a
hook, and the optional `sources` and `preferred_installer` passed through to `ArtifactPlacement`,
survive dropping their arguments because no fixture in the mutation scope installs a hook or supplies
either. Those claims may well be held elsewhere; the scope, not the suite, is what is silent here.

**Three that are genuinely behavioural, and are not held anywhere in this scope:**

- `placement_for`'s first guard, `not isinstance(artifact, …) or not isinstance(scope, …)`, survives
  becoming `and`. A bad artifact with a good scope would then fall through to fail somewhere less
  legible.
- `_deliveries` and `_merges` both build `ArtifactEnvironment(str(identity), root)` and survive
  `str(None)`. Either the identity does not reach the payload path, in which case the argument is
  misleading, or it does and nothing checks it.
- `_merges` builds its destination as `os.path.join(harness_root, target.destination)` and survives
  losing the second half, which would merge into the harness root itself rather than into the file
  the table names. The merge tests assert which harnesses were reached, never where.

Not critical: no invariant depends on the refusal wording, the sentences are currently correct, and
the three behavioural gaps are all on paths the end-to-end gate exercises for real. Worth doing the
next time a slice touches these branches for a product reason rather than as a sweep — asserting
sixty sentences nobody has read at a terminal would freeze wording that the manual runs keep
improving. The third group deserves a test whenever `_merges` is next opened. Related to `B-110`,
`B-111` and `B-112`.

## The Registry initialization stage report on screen 46 (`QA-098`)

2026-09-14 disposition (D-248): remains noncritical backlog after operator closure of CP-22.
CP-23 implements the new concrete screen reports, not this separate durable stage-history feature.
The unfinished fragment of the earlier QA-098 message is not an active clarification or blocker.

The operator asked Registry Maintainer to show the run that produced the current snapshot: `init`,
`lock`, `build`, `validate`, `audit`, `commit`, ending in `committed <sha> locally; not pushed and
not merged`. CP-22 step 17 built everything else in that finding — the registry as a row, and its
lifecycle as the cursor's description (`D-247`) — and left this out for a reason worth writing down.

`RegistryBootstrapStage` already models exactly those stages, but nothing keeps them. A bootstrap
run reports its stages to whoever asked for it and they are gone when that screen is left; screen 46
is drawn from durable observation, and there is no durable record to draw from. Showing the stages
would therefore mean either re-running the bootstrap to draw a frame, which CP-22 forbids outright,
or inventing stages from the checkout's current state, which would be the screen reporting a run
that never happened.

The work is to record the last bootstrap run as a receipt beside the registry — what ran, whether it
passed, what it said, and the commit it ended on — and project that. Not critical: the lifecycle the
screen now carries already answers the question the finding opens with (where has this registry got
to), and the stage report is the history behind it. Worth doing when a slice next opens
`io/registry_bootstrap.py` for a product reason.

## B-114 — Source-onboarding mutation scope leaves unrelated UI/action claims unmeasured

Found: 2026-09-14, CP-23 task 01. Advisory runs intentionally used Source addition/onboarding and
navigation examples, rather than claiming adequacy for both large modules as a whole.

- `application/consumer_ui.py`: 1,961 mutants; 550 killed, 1,345 survived, 66 had no selected test.
  `_set_rows` has no survivor. Reviewed `_back_focus` survivors concern the pre-existing general
  workflow predicate, unrelated-screen fallback and Candidate validation-row unwrapping. The
  Source-specific reverse edges are held by the two targeted mutations and composed workflow.
  Other survivors cover unrelated bindings/forms, event guards, promotion/publication completion
  and generic completion selection/pending-state clearing. They are not evidence those areas lack
  tests in the full repository: those suites were outside this advisory selection.
- `io/consumer_actions.py`: final fresh run has 2,170 mutants; 246 killed, 278 survived, 1,646 had
  no selected test. Six newly added notice/text survivors were within this task's claims and were
  closed by checking the three actual rendered statements separately. The sole remaining
  `_execute_source_addition` survivor removes refreshing `offers` from the reread context. Both
  real and fake Source-add fixtures keep the approved offers unchanged, as this operation should;
  a separately changed approved-offer observation would need its own refresh scenario. The other
  survivors/no-test cases concern existing review identity/diagnostic variants, shared host/screen
  composition and non-onboarding installation, maintenance, promotion and credential actions.

Noncritical: no survivor remains in the new cursor fallback or new Source success notice. Broaden
the appropriate scope when the later CP-23 tasks touch those existing contracts, especially
Candidate transitions (tasks 04/09) and publication/completion (tasks 05/06). Do not treat these
scoped figures as full-module mutation adequacy. B-110/B-111 record the runner limitations met
before successful runs; neither was resolved by changing product tests or weakening a gate.

## B-115 — Validation Details' `source.detail` branch is shadowed by its Enter binding

Found 2026-09-14 during CP-23 task 04's targeted mutation. On screen 39 the `Enter → Policy`
screen binding decides what the real Enter key does, so `CanonicalScreenSource.detail`'s
`VALIDATION_DETAILS → POLICY_REVIEW` branch is never reached by a key press. Pointing that branch
at Promotion Review turned only `test_enter_on_validation_details_continues_to_policy` red (it
calls `detail` directly). The key-path walk stayed green. Pointing the binding there turned five
tests red, including both E2E walks. Noncritical: both routes currently agree. Pick one owner for
Enter on screen 39 when task 14 audits advertised keys against dispatch.

## B-116 — `registry_remote_default_branch` has no production caller after D-255

Found 2026-09-14 during CP-23 task 05. The TUI's publication preparation was the only production
caller of `io/registry_publication.registry_remote_default_branch`; `aart-cli registry push` resolves
the default branch through `_configured_registry_branch` instead. The function and its IO test
still pass. Noncritical: it is harmless, and deleting it is a CLI-module cleanup rather than part of
removing the TUI capability. Decide whether the CLI should use it (the remote's actual default)
or whether it should be removed.

## B-117 — No reviewed installation Undo exists to offer from Success

Found 2026-09-14 during CP-23 task 06. Product Specification §167 allows Success to offer Undo
when the recorded effects support safe reversal, as a separately reviewed operation. The consumer
surface has no such operation: `UndoAvailability` is projected from receipts, but the only undo
command (`aart receipt undo`) reverses setup records. Success and Receipt Details therefore
explain that no reviewed undo is offered (D-256). Noncritical: withholding an unreviewed reversal
satisfies INV-009/INV-192. Adding one needs an owned-effect reversal plan, a review screen and
receipt semantics; it is not a relabelled Uninstall.

## B-118 — Source counts and the Status filter still read stored Candidate state

Found 2026-09-14 during CP-23 task 09. After a local promotion, the Candidates row reads
`Promoted locally` (D-259). `MaintainerSourceView.candidate_states` (Dashboard/Sources counts) and
screen 53's Status facet still count the stored state, so they say `ready=1` until Source Sync runs
after Registry Sync. Noncritical: nothing there is actionable, and no promotion is offered from
those counts. Fixing it means projecting the record into the Source view and adding a Status facet
value for it.

## B-119 — Updates keep recorded harnesses and do not offer target reselection

Found 2026-09-14 during CP-23 task 10. Explicit harness choice applies to a new installation.
The update path continues to build `previous` from installed receipts and keeps the harness
components that installation recorded; it does not expose screen 05's target picker. This is the
smallest conservative choice under INV-179: changing configuration is not reinstall, and an update
must not silently add or remove harness delivery. A future supported harness-migration workflow
needs its own explicit reconciliation intent, review, effects and receipt rather than overloading
artifact update. Noncritical: current updates retain the installed targets and task 10 changes no
update behavior.

## B-120 — Credential actions do not reach Activity

Found 2026-09-14 during CP-23 task 12 (D-262). Verify, Replace and Delete on screen 24 run through
the credential lifecycle and report on the landing screen, but they record no receipt. Activity
receipts are per-artifact `LifecycleExecutionOutcome`s, while a credential action is about a
reference that may serve several artifacts or none. INV-173 asks credential rotation to share the
receipt machinery. The likely shape is a credential-rotation lifecycle receipt per dependant, plus a
subject-less record for an unused reference. Two other items were noticed and left as they are:

- Screen 23 still prints `Actions: verify, replace.` above `[Enter] Open` (task 14's audit).
- 24a's trail reads "Review Credential Action" even when it shows Verify's answer.

Both were fixed by CP-23 task 14.6 (D-272); the receipt gap remains.

Noncritical: no receipt is claimed, the outcome is stated where the action lands, and no value is
involved.


## B-121 — Cross-installation credential merging causes a second-owner pre-check failure

Status: ABSORBED INTO CP-26.19 / B-144 (D-333, 2026-09-19); correction pending.

Found 2026-09-14 during CP-23 task 13 (D-263). The old composer gives two MCP artifacts declaring
the same input id one provider reference and asks once. The first store changes the observation
reviewed for the second owner, so the transaction ends Partial. Under Product Specification §169,
the merged reference and single prompt are themselves invalid.

The old proposed repair by shared-effect ownership/reference counting is withdrawn. CP-26.19 must
collect values separately and allocate separate provider items before review, preserving independent
preconditions and receipts. Reuse this failure as characterization of the old defect and prove
that independent owners complete without changing each other's credential state. Do not implement
a sharing route to fix it. Closure requires CP-26.19 evidence, not this planning update.

## B-122 — Advisory mutation survivors outside CP-23's claims in the TUI modules

Found 2026-09-15 by CP-23 task 15's scoped `mutmut` runs, whose working copies are kept under
`/private/tmp/cp23-task15-*`.

| module | mutants | killed | survived | no test | timeout |
|---|---:|---:|---:|---:|---:|
| `tui_consumer.py` | 3,957 | 1,912 | 1,892 | 151 | 2 |
| `tui_maintainer.py` | 1,501 | 624 | 782 | 95 | 0 |
| `application/consumer_ui.py` | 2,292 | 1,111 | 1,166 | 15 | 0 |

The survivors CP-23 owned became tests or were shown equivalent (slice, task 15). The rest cluster
in large, older surfaces:

- **`tui_consumer`:**
  - `CanonicalScreenSource._body` (418), `description` (130) and `detail` (61);
  - `_remediation_change`, `_review_facts`, `render_lifecycle_plan`, `render_credential_review`,
    `render_marketplace_artifact` and `render_lifecycle_outcome`.
- **`tui_maintainer`:** `render_maintainer_candidate_diff`, `render_maintainer_candidate`,
  `maintainer_workspace_detail`, `render_maintainer_registry`, the version-conflict, promotion-review
  and provenance renderers.
- **`consumer_ui`:** `key_event` (454), `reduce_consumer_ui` (269) and `key_bindings` (148).

Many are string-case and `XX…XX` wording mutations on prose that tests check with `assertIn`
fragments. Some would be killed by the property files that B-111 keeps out of `TESTS`. A few are
type-guard messages. None is known to break a Product Specification invariant, because the frame,
key and `v` laws are held over all 74 screens by `frame_matrix_test` (D-274).

The useful follow-up is per renderer: exact expected lines for the facts a screen promises, and a
B-111 fix so the property files can join the selection. Do not chase the figure itself (D-134).

Named claims in `consumer_ui` that are still unheld:
- a result arriving while a quit confirmation is pending clears it (`quit_pending=False` in
  `_action_prepared`, `_action_recorded`, `_action_failed` and `_declined_preparation`);
- a recorded promotion on Registry Commit clears the selection and sets `registry_commit_applied`
  with a `LOAD_SCREEN` of that screen (`_action_recorded` mutants 2–24);
- a declined preparation hides Help and clears search.

## B-123 — `maintainer_registry_rebuild_test.py` leaves file reads unclosed

Found 2026-09-15 in CP-23 task 15's `make quality` output. Two `ResourceWarning: unclosed file`
warnings come from reads in `tests/maintainer_registry_rebuild_test.py`. They do not fail the gate,
and no product code is implicated. The fix is `pathlib.Path.read_text` or a `with` block.


## B-124 — The Release Please pull request starts no `pr-check` run

Found 2026-09-15 while preparing PR #1 for its first release. Severity: medium, and a gap against a
MUST: INV-096 says a generated release PR must satisfy the normal quality contract before it becomes
a release. `release-please.yml` authenticates with `GITHUB_TOKEN`, and GitHub raises no workflow
event for a pull request that token opens or updates, so `pr-check` never runs on the release PR.
`main` has no branch protection either, so nothing stops the merge.

The usual fixes are a GitHub App token or a fine-grained PAT for the release-please step, or a
`workflow_dispatch`/`pull_request_target` route that runs the gates on the release branch. Each
touches repository secrets or settings the owner holds, which is why this is not done inline.

Not reclassified as critical yet: the release PR changes only the version literals and
`CHANGELOG.md`, and the tree it sits on passed `pr-check` when it reached `main`.

Evidence/links: INV-096; `.github/workflows/release-please.yml`; D-275.

## B-125 — Open findings carried over from the deleted residue register

Recorded 2026-09-15 by D-276. `docs/testing/residue-register.md` is deleted; its open and deferred
rows are summarized here so they are not lost. **None has been re-verified against the current
tree.** Most were measured on predecessor-project wheels in August 2026, and some may already be
fixed. Check each against the code before acting on it. Git history keeps the full rows.

Rows about the deleted documents themselves are not carried over.

Setup and receipts:
- A Docker tag rebound by a setup run cannot be restored by undo, because the earlier image id is
  never captured.
- A docker build's image differs from a hand build (file modes, per-build mtimes, buildx defaults).
- `custom.install@1` scripts get no `HOME`, so tools that read dotfiles misbehave; the verify probe's
  environment differs from the adapters it checks.
- A long failing `RUN` instruction is reduced to a fragment in the failure detail.
- A completed undo reports `skipped`, which reads as "setup never ran".
- `receipt verify`'s record-wide claims render as their own opposite.
- A setup recipe can collect a secret that an MCP descriptor cannot reference, so every stage can
  report success on a server that was never authenticated.
- A truncated Keychain secret passes every check setup performs.
- `help_urls` are parsed and validated but rendered nowhere.
- Recovery-note paths are folded mid-word and are not home-relative.
- Every declared input is prompted before the run finds the item needs nothing.
- `usage report projection failed` names nothing actionable.
- A retry is offered for a JSON path collision the same command cannot fix.
- Outside a terminal, the `START` rule continues the previous prompt's line.
- The token-containment test's "walked structurally" claim holds for channel 2 but not channel 4.
- Recipe format: no `_comment` field; no shell-rc module by that name; the package root refuses any
  extra top-level file.

Sources, store and lifecycle:
- `source add` refuses `file://` locations, and local-source symlink refusals are worded differently
  on the two channels.
- Removing a source does not remove its content; a review that says it changes nothing writes to the
  durable store.
- The object store's garbage collector has no caller; several `application/` functions are
  unreachable, and `fp.py` duplicates `domain/result.py`.
- `aart_cli/io/cache.py` is imported by nothing.
- Reclaiming a merge file depends on uninstall order; an emptied harness directory outlives its file.
- `uninstall` with no coordinate advises `marketplace list`, which refuses when no source is
  configured.
- The ownership gate warns for one of the two effects an artifact can use.
- A project profile override replaces the whole profile, silently dropping absent sections.
- An unexplained write to a real data root was observed during a sandboxed session (high).

Registry, security and release:
- `registry scaffold` cannot scaffold a setup-bearing artifact.
- `revendor` cannot narrow a vendored subtree.
- `registry init` and `registry validate` disagree about a workspace holding only `aart-source.json`.
- The registry group renders failure two ways; `reporting` and `upgrade` have no `--json`.
- `security scan` needs an object envelope no command emits; `security analyzers` lists analyzers it
  cannot run.
- The SPDX allowlist rule in `registry_publication.py` is not applied by any gate.
- `wheel-digest` builds the working tree while stamping `HEAD`; `make wheel` dirties a tracked file.
- Two curses helpers keep a flag-dependent return type.
- The index-version boundary for setup-bearing artifacts is not enforced.

## B-126 — `registry push` refuses every branch when `origin/HEAD` is not set

Found 2026-09-15 while writing `docs/ci/github-enterprise-rollout.md`. Severity: medium.
`_configured_registry_branch` in `aart_cli/commands/registry.py` resolves the consumer branch
from `refs/remotes/<remote>/HEAD` and otherwise falls back to the current branch. A repository that
was `git init`ed and pushed, or cloned while empty, has no `origin/HEAD`, so every checked-out branch
is treated as the consumer branch and refused. The rollout manual tells the reader to run
`git remote set-head origin --auto`. A fix would read the remote's default branch with
`git ls-remote --symref` or refuse with that command as the remediation.

## B-127 — `scripts/vendor_scan.py` still says `registry vendor` cannot take a single file

Found 2026-09-15 during the D-276 comment sweep. The vendoring tutorials say a lone file vendors
cleanly and is re-rooted under its basename, but `vendor_scan.py`'s docstrings and its `adopt`
output still say a single file cannot be vendored. Verify the current behaviour, then either route
`adopt` through `registry vendor` or correct the text.

## B-128 — Decide whether to keep the `agent-artifacts` command alias

Recorded 2026-09-15 by D-276. The wheel still installs `agent-artifacts` beside `aart`, and the
package is still `aart_cli`. Both are names from the predecessor project. Dropping the alias
is a breaking change for anyone who scripted it, so it waits for an explicit decision.

## B-129 — RESOLVED: the manual lab raced git's background repack

Found 2026-09-15 in `pr-check`, once on Python 3.14 (release PR #2) and once on 3.10 (PR #3).
Reclassified as critical because it turns required checks red at random, including a release PR's.
- `manual_test_lab_test.test_setup_builds_a_fresh_ecosystem_with_a_credential_mcp` failed in two ways:
  - `reset_lab` hit `Directory not empty` on `repositories/registry/.git`;
  - `git clone --bare` hit `hardlink different from source` on `objects/pack/tmp_idx_*`.
- Cause: the runner's git 2.55 runs automatic maintenance in a detached process after a commit.
  The lab copies and deletes a repository straight after committing to it, so a repack still
  writing there raced both operations.
- Fix: `scripts/manual_test.py:_run` sets `maintenance.auto=false` and `gc.auto=0` through
  `GIT_CONFIG_COUNT`, which also reaches the CLI's own git. Test:
  `test_no_git_the_lab_starts_repacks_in_the_background`. Targeted mutation:
  `maintenance.auto=true` turns it red.
- Other test helpers that commit and then copy or delete a repository could race the same way;
  none has been seen failing.

## B-130 — Nothing holds which registries a Source view names

Found by scoped mutants over `aart_cli/application/maintainer_views.py` during CP-24.01.
Replacing the union of the Candidate and collection target registries with an intersection kills no
test: `MaintainerSourceView.target_registries` is asserted nowhere with a Source scanned for two
registries. Not critical to CP-24; a test with one Candidate per registry would hold it.

## B-131 — A Source view's last successful sync time is unheld

Same run: replacing `published_at_epoch_seconds` with `None` survives. The field is rendered in the
Source detail, so a rendering assertion over a known publication time would hold it.

## B-132 — SCHEDULED AS CP-25.11: a review offers no way to choose the Python backend

CP-24.04 (D-283) reduced a dependency contract to one offer, naming the backend that will run, which
is what issue #7 asked for. A reader who wants the other usable backend still has only policy
(`allowed_python_installers`) to say so, and policy is not where a one-off choice belongs. If that
demand appears, it is one choice with one selected — never two changes to approve — and the selection
rule (`chosen_installer`) already takes a preference, so the work is carrying the reader's answer to
it. The owner requested that choice in issue #11 and moved every open issue into CP-25 on
2026-09-17. D-291 schedules it as CP-25.11; the backend that runs must remain the one the review
names.

## B-133 — A Python dependency specification's serialized shape is unheld

Found by scoped mutants over `aart_cli/domain/python_runtime.py` during CP-24.04: every
mutant of `dependency_spec_to_data` survives (16 of them), as do the `artifact_environment_to_data`
mutants, which the scoped test set does not reach at all. Both functions are the canonical shape a
plan and a receipt carry, so a key renamed or a value dropped is a compatibility change nothing
notices. Not critical to CP-24; one round-trip assertion per function would hold them.

## B-134 — SCHEDULED AS CP-25.06: the registry's Pages escape hatch does not escape anything

Found while removing `actions/setup-python` (CP-24.10). The same trap the tool's own workflows had
sits in the registry template `registry init` writes: `actions/upload-pages-artifact@v3` and
`actions/deploy-pages@v4` are referenced from a job that always runs, with `AART_PAGES` read at step
level. An action is resolved during "Set up job", before any step condition is read, so an instance
that does not carry those actions fails the usage-dashboard workflow even with `AART_PAGES=false` —
the escape hatch the rollout page documents. The fix is the same shape as CP-24.10's: move the
condition to job level, so the publishing job is skipped rather than its steps. Out of scope for
CP-24, which is about the tool's own release; the registry template is a separate contract and
`plan_registry_init` refuses a registry whose managed file has drifted, so changing it is a
migration rather than an edit.

## B-135 — PROMOTED TO CP-25.15: validate the pull request title before expensive quality work

Status: PROMOTED
Discovered in: CP-25 follow-up / Enterprise fork CI smoke test (2026-09-17)
Why useful: A smoke PR titled `test` ran the quality gates before
`scripts/conventional_title.py` rejected its title. The existing check is the last step of
`.github/actions/quality/action.yml`, so an invalid release-semantic input wastes the full gate run
on every matrix interpreter before giving the operator an actionable error.
Why noncritical when discovered: The title was already refused by the required `pr-check`; this
changed feedback latency, not merge safety or release classification. The owner explicitly added it
to CP-25 as task 15 after the first fourteen tasks were complete (D-300).
Potential approach: Move the existing title-validation step to the very beginning of the composite
action, before workspace trust, release-PR scope checking, pip-index setup, developer-tool
installation and `scripts/quality.py`. Keep the same `pull_request` guard, `PR_TITLE` binding and
validator. Do not add a second workflow or change branch protection. First add a workflow-shape test
that fails on the present ordering; then move the step and run the relevant gates. A targeted
ordering mutation must turn the new test red.
Invariants touched: INV-090 and INV-092 (the title remains the release-semantic input); INV-103
(feedback latency). No product or release-policy semantics change.
Evidence/links: `.github/actions/quality/action.yml`, `scripts/conventional_title.py`,
`tests/release_workflow_test.py`; owner's CI smoke report: `pull request title is not a conventional
commit: 'test'` after the full gate run.
Acceptance: An invalid title reaches the validator as the action's first step and fails before any
tool installation or quality gate; `test: verify fork CI` continues to the unchanged full gate set.
Changing a PR title alone still does not retrigger the current workflow; that separate event-policy
question is out of scope.
Promotion condition: Met by the owner's explicit CP-25.15 instruction on 2026-09-17 (D-300).
The task is implemented; see the slice's acceptance evidence.

## B-136 — Publish a per-release checksum for wheel download verification

Status: OPEN
Discovered in: CP-25 post-review Enterprise installation discussion (2026-09-17)
Why useful: A checksum distributed with each wheel would let an operator verify downloaded bytes
before `pipx` or `uv tool` installs them, including when a release URL returned unexpected content.
Why noncritical now: The release action already verifies the wheel against the tag before attaching
it, and the owner asked for a simple README command without checksum for now. A downloaded wheel's
archive shape is checked before the documented install, but that is not an authenticity check.
Potential approach: Publish a checksum as a distinct release asset or an explicitly supported
release-metadata field, then document a fail-closed verify-before-install command for public and
Enterprise releases. Decide how the expected digest is authenticated, not just where it is copied.
Invariants touched: INV-098, INV-099; release artifact integrity and supply-chain provenance.
Evidence/links: `README.md` installation section and `.github/actions/release/action.yml`.
Promotion condition: Owner requests a verifiable download contract or a release acceptance test
requires client-side digest comparison.

## B-137 — `doctor` crashes when a source's local alias differs from its registry's own alias

Status: OPEN
Discovered in: CP-25 follow-up / running the released `aart-cli doctor` against a real machine
(2026-09-17)
Why useful: `aart-cli doctor` exits with an unhandled `ValueError: offline source readiness is
inconsistent` and a Python traceback. The failing clause is
`aart_cli/application/offline_readiness.py:56`,
`any(item.coordinate.source != self.alias for item in self.artifacts)`. A configured source's alias
is a *local* name for a remote origin, but the coordinates published inside that registry carry the
registry's own alias. The invariant assumes the two are equal, which is false for any source added
under a name the registry does not itself use. Reproduced on a real configuration: alias
`ci-registry` (kind `registry-git`, ref `qa/publish-v1`) serving
`aart-test-registry/skill/verification-before-completion@1.0.0`. Reproduced on the CP-25 branch as
well as on the released 0.1.2, so it is not a regression introduced by this slice.
Why noncritical when discovered: CP-25 was complete and its pull request already green; this is
neither caused by nor required for any of its fourteen tasks, so recording it is correct rather than
expanding the slice. It is, however, the most user-visible failure shape there is — the diagnostic
command itself crashing — and the owner may reasonably want it fixed before 0.2.0 ships.
Potential approach: Decide first which value is authoritative. Either the invariant is wrong and
should compare against the coordinate's source alias rather than the local one (probably by dropping
that clause and keeping the grouping key explicit), or the io layer is wrong to group a registry's
foreign-aliased coordinates under the local alias, in which case
`aart_cli/io/offline_readiness.py:93` should partition by `coordinate.source`. Whichever is
chosen, `read_offline_readiness` must return an `Err` diagnostic rather than letting a domain
`ValueError` escape to the CLI: INV-175 is that AART says when it cannot do something. A regression
test should construct a source whose configured alias differs from its published coordinates.
Promotion condition: Promote if the owner wants `doctor` dependable for 0.2.0, or as soon as any
user configures a source under an alias of their own choosing — which the `source add` interface
invites.

## B-138 — The remaining bash-only CI scripts are untested against a shell that is not bash

**Evidence.** D-304 fixed the one step that declares no `shell:` and runs inside the
organisation's container image. Five scripts still open with `set -euo pipefail` and declare
`shell: bash`: `.github/actions/aart/action.yml` (which also writes a `/usr/bin/env bash` shim),
`.github/actions/mutants/action.yml`, `.github/actions/pip-index/action.yml`,
`.github/actions/release/action.yml` (twice), `.github/workflows/pr-check.yml`, and the aggregate
gate step in `aart_cli/registry_commands/templates.py`.

**Why it is not critical.** Each declares `shell: bash` explicitly, so on an image without bash it
fails at step setup with a clear refusal rather than the misleading `Illegal option` the registry
step gave. All of them run on the runner rather than in `AART_CI_IMAGE`, and this repository's own
Enterprise fork has released through them.

**What would make it critical.** An operator pointing `AART_RUNNER` at a self-hosted runner whose
image lacks bash. Then `pr-check` and `release` stop working on that instance and the refusal is
not actionable without reading this entry.

**Shape of the work.** Reuse `TheStepRunsOnAnImageWithoutBashTest`'s harness: extract each `run:`
block and execute it under `dash`. `.github/actions/aart` is the one worth converting first — it
is the tool-provisioning step's sibling and carries the same shim.

## B-139 — A fix to the generated registry workflow cannot reach a registry that already exists

**Evidence.** D-304 corrects `.github/workflows/aart-registry.yml` as `registry init` writes it. A
registry initialised before that carries the broken copy in its own history, and there is no
command that refreshes it: `registry init` answers
`error: registry init refuses an existing registry workspace`, and the top-level `upgrade` replaces
the AART executable, not a registry's managed files. Verified against a scratch registry whose
workflow was rolled back to the pre-fix shape.

**Why this bites more than it looks.** `.aart-cli-version` pins which AART the gates run, so a registry
does track tool versions — but the workflow that *fetches* that AART is outside the pin, which is
the one file the pin cannot govern. Every defect in the provisioning step is therefore permanent
for every registry already created, and `plan_registry_init` refuses a hand-edited template, so
editing it by hand puts the registry out of step with the command that manages it.

**Shape of the work.** A `registry upgrade` (or `init --refresh`) that rewrites only the managed
paths, reviewed like any other mutation, reporting the diff and refusing when an unmanaged edit
would be lost.

**Verified workaround, until it exists.** `init` refuses on two separate conditions, so both have
to be cleared: the four identity files it checks for (`planning.py:501`), and *any* template path
that already exists (`registry init refuses to overwrite an existing template`). Deleting all eight
managed paths and re-running `init` with the same `--source-id` and `--display-name` regenerates
them, leaves `artifacts/` untouched, and `publish --yes` then commits only what actually changed --
one file, in the case that motivated this. The registry keeps its repository, and so keeps the
variables and secrets already configured on it, which is the whole reason the workaround matters.
Two values are re-derived rather than preserved: `requires_aart.min_inclusive` comes from the
version of AART running `init` (pass `--minimum-version` to hold the old one), and `README.md` and
`.gitignore` come back as templates, losing any local edit.

**Not on a promoted registry.** On a registry carrying `registry/versions/`, `publish` writes
the legacy `aart.lock.json` / `aart.index.json` pair that B-142 then cannot clear; recompile with
`build --yes` instead. On an authored registry the `publish --yes` below is required.

**The `publish --yes` is not optional, and on a registry holding artifacts it is not one file.**
`init` rewrites `aart-registry.json` and `aart-source.json`, and both feed the deterministic inputs
digest the lock records, so the reset invalidates the lock on its own — no artifact has to change.
A registry pushed after the reset but before the recompile fails its own `validate --strict
--frozen` with `registry lock does not match deterministic registry inputs`, plus one
`compiled index disagrees with owned package <kind>/<name>` for every artifact it holds. Confirmed
against a scratch registry: `publish --yes` clears all of it, after which `lock --check` and
`build --check` both report `unchanged`. A real Enterprise registry hit exactly this.

## B-140 — A registry pushed straight after `init` fails its own generated CI

**Evidence.** `registry init` writes six paths and ends with
`next: validate`, `next: lock`, `next: build`, `next: audit`. Following them in that order fails at
the first one: `validate --strict --frozen` answers
`error: compiled registry requires lock and index`, and so do `lock --check`, `build --check` and
both `registry test` runs. The generated workflow runs the gates in that same order, so a registry
committed as `init` leaves it is red on its first push — with five failures whose remediation text
names a command the maintainer was never told to run before pushing.

**What does work.** `registry publish --yes` prepares the lock and index, validates and audits that
exact snapshot, and commits all eight paths in one reviewed mutation. That is the correct first
move after `init`, and it is the one command the `next:` hints do not mention.

**Shape of the work.** Make `init`'s closing hint `next: aart-cli registry publish --yes`, or have
`init` write the lock and index itself so the six paths it emits are internally consistent. Either
removes the state in which a registry exists but cannot pass its own gates. Prefer the hint: `init`
writing generated files would make it a mutation of content it did not author.

**Not a blocker for D-304.** Verified on `M1F1/aart-registry-smoke`, created for that decision's
end-to-end check.

## B-141 — Three of the four fetch arms cannot authenticate, so a private instance has one route

**Evidence.** With D-304 in place the step runs to completion under `sh` on a real Enterprise
runner and then fails in the git arm:

```
fatal: could not read Username for 'https://<instance>': No such device or address
Error: Process completed with exit code 128
```

The clone carries no credential. Neither does the wheel arm, whose `urllib` fetch of a release
asset on a private instance returns a sign-in page rather than a wheel. `AART_TOOL_PATH` needs
control of the CI image. So on an instance where the AART copy is private — the normal case inside
a company — exactly one of the four arms can authenticate: `AART_PACKAGE`, through
`AART_PIP_INDEX_CREDENTIALS_SECRET`.

**Why the shipped default makes this worse.** Git is the arm reached when nothing is set, and it is
the only arm carrying a default. An organisation that configures nothing lands on the one arm that
cannot work for it, with an error naming a username prompt rather than the missing capability.

**Shape of the work.** Give the git arm the credential story the index arm already has: an
`AART_GIT_CREDENTIALS_SECRET` naming a secret that holds `user:token`, assembled into the clone URL
in the step and re-masked in halves exactly as `INDEX_CREDENTIALS` is, never written to `how` or any
log line. The wheel arm wants the same treatment as an `Authorization` header on the `urllib`
request. Both are the same shape as the code already in this step, which is why they belong
together.

**Workaround until then.** Publish the wheel to the internal index (`scripts/publish_to_index.py`
is wired into the release action) and set `AART_PACKAGE=aart-cli=={version}` with
`AART_PIP_INDEX_URL`. The instance that raised this already has
`AART_PIP_INDEX_CREDENTIALS_SECRET` set and `AART_PIP_INDEX_URL` unset, so it is one variable and
one publish away from the supported route.

## B-142 — `publish` on a registry carrying both representations enters a gate it cannot pass

**Critical.** A real registry met this and could not be unblocked by any command the tool offered.
It is the operator-facing half of B-057, which was reclassified critical on 2026-09-09 and is still
open.

**What happens.** `_prepare_publish` (`curation/runtime.py:1327`) branches on
`is_promoted_registry`, which is true when *any* path under `registry/versions/` exists, and skips
the lock step entirely — `test_publish_gates_the_approved_representation_without_locking_it` states
that as intended. But `validate_registry_workspace` still checks `aart.lock.json` and
`aart.index.json` when they are present. A checkout carrying both — which
`is_promoted_registry`'s own docstring calls "the migration's real shape" — therefore fails publish
with a set of errors publish structurally cannot fix:

```
error: registry publish gate failed: compiled index artifact identities are incomplete;
compiled index disagrees with owned package <kind>/<name>; compiled index does not match
registry inputs; registry lock does not match deterministic registry inputs
```

The printed remediation, `aart-cli registry lock --yes, then aart-cli registry build --yes`, is wrong for
this shape: `lock` dispatches to `_prepare_promoted_lock` and leaves the legacy pair untouched.
Nothing the operator can run clears it, and nothing says why.

**How a registry gets there.** `init` writes no lock or index; one `publish --yes` on the
still-empty registry writes both; a later `promote` adds the approved representation beside them.
Reproduced end to end that way, matching the reported failure line for line.

**Verified remedy, until the migration closes.** Delete `aart.lock.json` and `aart.index.json`.
All six generated gates then pass and `registry/index.json` is unchanged, so no consumer sees a
difference — *provided* the registry owns no authored artifacts. Confirmed both ways: with an
authored artifact present, deleting the pair drops it out of the consumer index while leaving it on
disk, which is a silent content loss rather than a fix. Going the other way is not available at
all: deleting `registry/` leaves promotion's versioned `artifacts/<kind>/<name>/<version>/` tree,
which the authored shape cannot read (`required file is missing: artifact.json`, B-057).

**Shape of the work.** Smallest honest fix: publish refuses a both-shapes checkout by name, says
which representation it is going to keep, and names the files to remove. Real fix: close B-057 so
the two shapes cannot coexist. Either way `validate` and `publish` must agree on which files are
live, because today one refuses to repair what the other insists on checking.

## B-143 — PROMOTED TO CP-26.20: Add Registry cannot synchronize a canonical Registry from a local Git checkout

Status: PROMOTED TO CRITICAL PATH (2026-09-18)

**Reported.** GitHub issue #23, 2026-09-18. A maintainer has synchronized an external Source,
promoted its Candidate into the local canonical Registry and committed it. The Candidate correctly
reads `Promoted locally`, but Add Registry cannot connect that local Registry checkout so its
canonical packages can be exercised through the normal Marketplace and installation path.

**Current behaviour.** Add Registry in the TUI has `alias`, `url`, `ref` and `default`; no local
path or location kind. The configuration model has `registry-git`, `source-git` and `source-local`,
but no local Registry kind. Both an absolute path and `file://` are rejected for `registry-git` as
not being a safe Git URL. `source-local` is an authoring Source and compiles author manifests; it
does not read canonical Registry packages. The approved Marketplace aggregation also deliberately
filters out `PublicationStage.PROMOTED_LOCAL`. `aart-cli registry test` checks Registry/AART version
compatibility; it does not install an artifact through Marketplace. Product Specification §165.23's
Candidate `Test Install`/`aart dev install` surface is not implemented either.

The only partial workaround is to push a review branch, add the same remote at that ref under a
second alias, synchronize it, and select the qualified alias in Marketplace. Configuration permits
one Git origin at different refs, and Marketplace already refuses ambiguous unqualified artifacts.
That workaround is not local, requires publishing bytes before testing them, and the configured
Registry reader treats content carried by the synchronized branch as published. It therefore does
not honestly represent a pre-publication test.

**Correct contract.** This is not a weaker preview trust class. Local checkout and remote Git are
two acquisition adapters for the same configured canonical Registry abstraction:

```
remote: URL + ref       -> acquire exact commit -> validate -> save snapshot -> Marketplace
local:  path + branch   -> read exact commit     -> validate -> save snapshot -> Marketplace
```

Once admitted, both are equally valid Registry connections and use the same Marketplace,
resolution, policy and installation paths. The local adapter performs no clone or fetch. Add reads
and validates the configured branch's exact commit before configuration is committed; Sync resolves
that same branch, validates the successor and atomically advances the cached snapshot. A failed local read or invalid
successor leaves the last known valid snapshot active, exactly like a failed remote Sync.

**Owner clarification, 2026-09-19 (D-350).** Save the selected local branch with the path and alias;
read committed content independently of checked-out HEAD and dirty worktree edits. Do not switch
branches or fall back if the configured branch is missing. The intended flow is committed artifact
on a local Registry branch → Add Registry for that repo/branch → ordinary install → MCP smoke
tests. No separate Candidate Test Install process is introduced or required by CP-26.20/20a.

**Alias and collision rule.** A remote and local connection to the same Registry may coexist only
under different configured aliases, for example `company` and `company-local`; alias uniqueness is
already a configuration invariant. The alias remains part of the Marketplace coordinate, so the
same canonical package is addressable as `company/skill/foo@1.0.0` and
`company-local/skill/foo@1.0.0`. An unqualified request matching both remains explicitly ambiguous
and requires choosing the alias. Local never silently shadows remote and neither is silently
deduplicated out of provenance.

The alias must also namespace every consumer-owned value beneath the selected artifact. The state
key is one stable installation target (Registry alias + kind + name + normalized scope and
project/user destination + harness/profile), followed by the declared input id. For example,
`company/mcp/foo` and `company-local/mcp/foo` must be able to hold two different `endpoint` values
and two different `token` provider references. So must `company/mcp/foo` installed into project A,
project B and a user-level harness. Matching canonical bytes, artifact names, input ids or target
types never merge them. D-333 also forbids explicitly binding one external credential item to
several targets. Each installation requires separate value entry and its own provider item; matching
input names do not supply values for another owner. Update may preserve compatible state only within the
same exact target owner, and uninstall/reconfigure of one owner must leave every other target
untouched.

The general collision defect and its transport-independent repair are tracked by B-144. B-143
depends on that contract but does not own it: a Registry synchronized from a remote URL must obey
the identical state-key rule before `registry-local` exists.

**Shape of the work.** Implement it as a vertical capability, not as a `file://` exception:

- add a `registry-local` configuration kind and a Remote Git / Local checkout choice to Add
  Registry; CLI accepts the same normalized absolute path and selected local branch;
- require the path to resolve to the root of a Git worktree carrying a valid canonical Registry;
  bind each synchronized snapshot to its configured branch, exact commit, content digest and alias;
- route both adapters into one Registry validation/admission service and one source-store snapshot
  representation, so later Marketplace and installation code does not branch on transport;
- include canonical versions carried by the local snapshot through the same Marketplace projection
  and trust rules as the remote Registry; a recorded `Promoted locally` version stays named that
  way but is fully selectable through the local alias, and transport alone neither downgrades nor
  upgrades trust;
- retain alias, snapshot digest, resolved commit and local/remote origin in receipts and status;
- make local Sync read-only with respect to the checkout, network-free, and subject to the same
  last-known-good rule and actionable diagnostics as remote Sync;
- key persisted/reused configuration, credential bindings, setup state and lifecycle ownership by
  alias-qualified installation-target identity, including normalized project/user destination and
  harness/profile, by using B-144's general consumer-state contract; keep secret values inside their
  provider and store only the target-specific provider reference;
- test coexistence with the remote Registry, alias-qualified selection, unqualified ambiguity,
  dependency closure, install/update/status and an invalid local successor; install the same MCP
  from local and remote aliases with different config and secret references, and install one alias
  into two project roots plus user scope with independent values. Then prove update, reconfigure,
  credential rotation and uninstall of any target cannot affect another. Under D-333, attempts to
  select one provider item for distinct installations are refused; no explicit sharing route exists.
  Assert alias-qualified runtime paths and distinct harness entry keys even for byte-identical
  local/remote packages (Product Specification §169.3).

This is distinct from §165.23 Candidate Test Install. Candidate Test Install exercises the compiled
candidate before promotion; a configured local Registry exercises the exact canonical
representation, dependency closure and collections after promotion using the normal consumer path.
It is complementary to CP-26 step 18: Push readiness answers whether a Registry commit may leave
the machine, while this capability makes that Registry a normal local Marketplace input before it
does. The owner promoted it to CP-26.20 on 2026-09-18, after B-144 establishes safe target-qualified
consumer state in step 19.

## B-144 — PROMOTED TO CP-26.19: Configuration and credential bindings are not keyed by installation target

Status: PROMOTED TO CRITICAL PATH (2026-09-18)

Discovered in: issue #23 design review / `application/installation_inputs.py` /
`io/consumer_actions.py`

**Why useful.** Configuration and secret bindings are general consumer state, independent of how a
Registry is acquired. Their complete logical owner is:

```text
Registry alias + artifact kind/name + scope + normalized target root + harness/profile + input_id
```

Each distinct key must hold an independent ordinary value or credential provider reference. For
macOS Keychain, it must resolve to a unique generic-password `service`/`account` pair. The encoding
may hash or otherwise hide the raw target path, but two distinct logical keys may not alias.
D-333 (2026-09-19) withdraws the earlier explicit-sharing allowance: no two installations may bind
the same provider item. Each new installation requires separately entered configuration/secrets,
including four input sets when four harnesses are selected. No global value pool or copy UI exists.

**Current defect.** Input composition groups declarations globally by `InputId` and one supplied
source is returned to every owner declaring it. The TUI's automatic Keychain reference uses one
service derived from user home and an account equal to `input_id`; it omits Registry alias,
artifact, project/user target and harness/profile. Ordinary files are physically per artifact root
and harness, but initial composition still projects one value into every matching target, while
receipt credentials are not target-qualified. These collisions affect remote URL Registries today;
local Registry support would only make them easier to encounter.

**Why critical now.** The owner added B-143 and B-144 to CP-26 on 2026-09-18. This item is step 19
and precedes local Registry acquisition in step 20 because the collision already affects remote
Registries and local aliases would compound it. It does not block the current scaffold removal;
the current next task is recorded at the top of NEXT.md (14 at the 2026-09-19 audit).

**Potential approach.** Introduce one nominal `InstallationTargetId`/input-binding key at the domain
boundary rather than concatenating strings in adapters. Carry it through input composition,
persisted configuration lookup, provider-reference generation, receipts, setup and lifecycle
dependency edges. Derive the macOS Keychain item identity from a canonical structured encoding;
include an opaque digest of normalized roots instead of their plaintext. Keep version outside the
stable owner so compatible updates at the same target can retain values.

**Acceptance evidence.** Install the same artifact from one remote Registry into two projects and
user scope, and from two aliases into the same target. Give every instance different configuration
and Keychain references; reopen, update, reconfigure, rotate and uninstall each independently.
Property-test that distinct valid complete keys never produce the same provider item identity.
Reject attempts to bind distinct installations to one provider item. Exercise four selected
harnesses with separate fields/prompts/items and a headless missing-target refusal. Prove runtime,
receipt and lifecycle independence as well as input isolation. Run scoped mutation over the new
identity module and input-composition change. Product Specification §169 and D-332/D-333 supersede
the earlier sharing acceptance; CP-26.18a establishes names/home/path policy first.

Invariants touched: INV-051–059, INV-179–180, INV-190, INV-196, INV-231–232, INV-243.

Evidence/links: Product Specification §§38–39, §96, §161.7, §169; D-332–D-335 (supersede D-313 sharing); B-143.

Promotion condition: satisfied by the owner's 2026-09-18 instruction; implement as CP-26.19 before
CP-26.20 local Registry consumption.

## B-145 — Generated Registry workflow helpers have broad surviving string mutants

Status: OPEN, NONCRITICAL

Discovered in: CP-26.02 scoped mutation of `registry_commands/templates.py`, 2026-09-18

The task-2 run used `tests/registry_init_scaffold_test.py` and generated 46 mutants: 16 killed and
30 survived. The two survivors in `render_registry_readme` change the codec spelling from `utf-8`
to `UTF-8` and are equivalent. The other 28 are in the pre-existing `_job` and `_aggregate`
workflow generators. They are outside CP-26.02's claim, which is that generated maintainer guidance
no longer advertises withdrawn `registry scaffold` and instead names `scan`/`promote`; the new
README assertions kill mutations of that guidance.

Read the `_job`/`_aggregate` survivors when generated workflow behavior is next changed. Classify
equivalent formatting/string mutations separately from changes to shell selection, gate order,
matrix shape, credentials, image selection and aggregate status. Add behavioral assertions for any
survivor that changes one of those contracts; never weaken a test to move the count.

Evidence/links: CP-26.02; `aart_cli/registry_commands/templates.py`;
`tests/registry_init_scaffold_test.py`; D-134; D-317.

## B-146 — Canonical promoted-package extraction has ten surviving scoped mutants

Status: OPEN, NONCRITICAL

Discovered in: CP-26.03 scoped mutation of `registry_maintenance/promoted.py`, 2026-09-18

The fresh scoped run generated 89 mutants and killed 79. Every mutant in the new retired-path
classifier and empty/canonical/mixed shape decision was killed. The ten survivors are in the
pre-existing `_package_entries` and `promoted_registry_artifacts` package extraction/projection,
outside step 3's dispatch claim.

When canonical promoted-package projection is next changed, inspect those ten survivors and add
load-bearing assertions for path re-rooting, vendored-only selection, identity and object-digest
projection. Do not broaden CP-26.03 merely to improve the count.

Evidence/links: CP-26.03; `aart_cli/registry_maintenance/promoted.py`;
`tests/promoted_registry_maintenance_e2e_test.py`; D-134; D-317.

## B-147 — Committed registry attestations have no producer and a misleading field name

Status: OPEN, NONCRITICAL

Discovered in: CP-26.04, while removing the consumer's retired-representation branch, 2026-09-18

Two findings, both pre-existing and neither blocking step 4.

First, no shipped command writes a `security/index.json` for a canonical Registry. `aart-cli security
scan` takes an operator-supplied `--registry-index` file and emits one attestation; assembling the
index and committing it is undocumented and unautomated. The consumer reads the file honestly when
it is there, which is why this never surfaced as a failure.

Second, `SecurityIndex.registry_inputs_digest` and `AttestationTrustContext.registry_inputs_digest`
now carry the canonical registry *state* digest (D-319), because the inputs digest they were named
for lived in the retired `aart.index.json`. The name should follow the value.

Do both together: name the field for what it binds, and give the Registry CI generator a step that
produces and commits the attestation set, so registry-reviewed trust is something a Registry can
actually earn rather than something a hand-built fixture demonstrates.

Evidence/links: CP-26.04; D-319; `aart_cli/consumer/runtime.py::_registry_security_evidence`;
`aart_cli/commands/security.py::_scan`; `aart_cli/security/attestations.py`;
`tests/consumer_runtime_test.py::test_verified_registry_security_index_is_bound_to_exact_marketplace_coordinates`.

## B-148 — Native-source projection keeps four surviving scoped mutants

Status: OPEN, NONCRITICAL

Discovered in: CP-26.04 scoped mutation of `aart_cli/consumer/runtime.py`, 2026-09-18

The scoped run generated 592 mutants and killed 464. Inside step 4's claim, `_project_graph_source`
keeps three survivors: one pre-existing mutant that drops `native.value.collections` from the
authoring-source branch, and two string-spelling mutants whose wrapped text still contains the
substring the refusal tests assert. The remaining survivors are in `load_local_consumer_service`
composition, `_merged_security_evidence` and `load_read_only_marketplace`, which step 4 did not
change.

When the native-source projection is next touched, assert the collections a native source
contributes. Do not broaden CP-26.04 to improve the count, and do not loosen a refusal assertion to
catch a spelling mutant.

Evidence/links: CP-26.04; `aart_cli/consumer/runtime.py`; `tests/consumer_runtime_test.py`;
D-134; D-317.

## B-149 — `aart-cli registry vendor` writes the retired unversioned package layout

Status: CLOSED, **CRITICAL when found** — repaired before CP-26.6 under D-326, 2026-09-18

Discovered in: CP-26.05, while resolving the inherited red set D-318 assigned to this step

`plan_artifact_vendor` writes its package at `<artifact_root>/<kind>/<name>/`, with no version
segment. `registry_maintenance/promoted.py::legacy_registry_paths` classifies exactly that shape as
the retired authoring workspace, so from CP-26.01 onward `_canonical_current` and
`_canonical_snapshot` refuse a checkout that has been vendored into. The sequence
`aart-cli registry init` → `aart-cli registry vendor` → `aart-cli registry validate` therefore ends in a refusal
naming the file the previous command just wrote.

**Why this is critical rather than a cleanup.** Vendoring is a Product Specification capability, and
the reclassification rule in `CLAUDE.md` is met exactly: without this, a mandatory capability cannot
be exercised at all on a canonical Registry, so CP-26 cannot be declared complete at task 21.

**Why CP-26.05 did not fix it.** Step 5's scope is the lock/index schema, the tree constants, the
planning halves and the fixtures. The vendor layout is orthogonal — it is about `artifacts/` shape,
not about `aart.lock.json` — and the correct fix is not a path change: a versioned package needs a
`registry/versions/<kind>/<name>/<version>.json` approval and the two catalogs recomputed, which
means routing `vendor` through the promotion projection the way `scan` + `promote` already are
(`application/promotion.py::project_promotion`). That is a slice, not an edit.

**Consequence held open deliberately.** `tests/registry_vendor_license_test.py` keeps its 20 tests
and 12 of them stay red. D-318 said the inherited red set describes the removed representation and
should be deleted with its fixtures; that premise holds for the lock/index tests and is wrong for
these, which characterize `--license` discovery, copy integrity, upstream drift and QA-015/LAF-45
reporting — all behaviour nothing in CP-26 removed. Deleting them would delete the only coverage of
that behaviour and hide this defect. D-323 records the correction.

Evidence/links: CP-26.05; D-318; D-323; `aart_cli/registry_commands/planning.py::plan_artifact_vendor`;
`aart_cli/registry_maintenance/promoted.py::legacy_registry_paths`;
`aart_cli/curation/runtime.py::_canonical_current`; `tests/registry_vendor_license_test.py`.

**Resolution.** Vendoring now stages authored wrapper bytes in the version directory, projects one
immutable approved package through `plan_bulk_promotion`, and writes its version record, promotion
record and catalogs atomically. Re-vendoring writes another version while retaining the previous
copy. `validate_registry_graph` accepts distinct approved versions and checks collection selectors
per version. The retained vendoring tests and canonical CLI gates pass; CP-26.21 still owns broad
verification.

## B-150 — An installation's identity is the harness *and* the scope it was installed into

Status: PROMOTED TO CRITICAL PATH — CP-26.19 (2026-09-19, D-332/D-333); implementation pending

Raised by the owner, 2026-09-18, while CP-26.05 was in flight.

The principle: **no artifact shares global state with any other artifact.** The entity that AART
records as "installed" is not the artifact — it is the artifact *placed into one target*, and the
target is what the installation path already encodes:

1. Which harness it was installed for (Claude Code, another agent runtime, …), and
2. which scope of that harness — user-level versus project-level — because the same harness at two
   scopes is two installations, with two configurations and two credential bindings, not one
   installation seen twice.

Mandatory CP-26.19 acceptance, now specified in Product Specification §169:

- Installed is keyed by (Registry alias, artifact, harness/profile, scope, concrete root), so the same artifact legitimately
  appears more than once and each row is independently verifiable, upgradable and removable.
- Keychain entries and configuration bindings are keyed by that same alias-qualified target, which
  is what CP-26 task 19 already names; this states *why* the key has that shape and adds the
  user/project scope to it.
- Uninstalling one row must not disturb another row of the same artifact, and nothing may be
  reference-counted across targets, because that would be shared global state by another name.
- Whatever AART writes into a harness has to be attributable to exactly one installation entity, or
  the no-shared-state rule cannot be checked.

On 2026-09-19 the owner made this mandatory: private runtime/projection under the harness,
central canonical objects and receipt metadata under `~/.aart-cli`, and separate configuration and
secret entry for every installation. Product Specification §§38–39, 84–85, 96, 169 now contain the
contract. CP-26.18a establishes portable paths and the `aart-cli` namespace; 19 implements isolation.
Four harnesses mean four input sets and four provider items per secret, with no explicit or implicit
sharing. This is required for INV-243–247 and therefore promoted from noncritical discussion input
to critical-path acceptance. Immutable package deduplication and Collection reasons for the same
complete installation do not permit cross-target mutable state sharing.

Evidence/links: CP-26 task 19; B-150 raised by the owner; `docs/product-specification/PRODUCT_SPECIFICATION.md`.

## B-151 — Seven shipped documents still describe `aart.lock.json` and `aart.index.json` as files AART writes

Status: OPEN, NONCRITICAL for CP-26.05 — becomes critical for CP-26.21

Found while executing CP-26.05, 2026-09-18.

CP-26 steps 1–5 removed the retired authoring-workspace representation from the product: nothing
parses, compiles or writes `aart.lock.json`, `aart.index.json` or `entries/`, and a checkout
carrying them is refused by name. The reader-facing documentation has not moved with it. Still
describing the removed files as part of normal maintenance:

- `docs/protocol/registry-v1.md`
- `docs/registry/maintainer-commands-v1.md`
- `docs/registry/maintenance-planning-v1.md`
- `docs/security/attestations-v1.md`
- `docs/ci/github-enterprise-rollout.md`
- `docs/testing/manual-acceptance.md`
- `docs/tutorials/company-registry-tabnine-v1.md`
- `README.md` (the "Registry layout" prose, not the command tree, which CP-26.05 corrected under
  D-324 because `tests/adoption_first_contact_test.py` gates it)

Why it is not step 5's: step 5's contract is the schema, the tree constants, the planning halves and
the fixtures. `make docs-check` validates fences and links, not whether prose matches the product, so
no gate fails today and repairing eight documents inside the deletion slice would hide what the
deletion changed. Steps 13–16 rewrite the README against the consumer-first contract (D-316) and are
the natural place for the registry documents to be reconciled with them.

Why it becomes critical for CP-26.21: task 21 is the slice's verification, and CP-26 cannot be
declared verified while shipped documentation instructs a maintainer to produce files that make
their Registry refuse every gate. Treat this as a precondition of task 21, not as optional polish.

Evidence/links: D-318, D-321, D-322, D-324; CP-26 tasks 13–16 and 21;
`aart_cli/registry_maintenance/promoted.py::legacy_registry_paths`.

## B-152 — Four registry diagnostic codes have had no user since CP-26.05

Status: OPEN, NONCRITICAL for CP-26.08

Found while executing CP-26.06, 2026-09-19.

`aart_cli/protocol/codes.py` still defines `REGISTRY_LOCK_INVALID`,
`REGISTRY_LOCK_STALE`, `REGISTRY_TREE_INVALID` and `REGISTRY_SELF_REFERENCE`. Step 5 deleted the
only code that raised them along with the retired representation's schema and planning halves;
nothing in `aart_cli` references any of the four today.

Why it is not a step's: a diagnostic code is a stable identifier and removing one is a
compatibility statement about what AART may emit, not a cleanup. It belongs with the step that
settles the shipped diagnostic vocabulary rather than inside an authoring slice. Nothing breaks
while they exist; what they cost is a reader who searches for `registry-lock-stale`, finds a
definition, and concludes AART still checks a lock.

## B-153 — `ruff format .` rewrites the Product Specification's code blocks

Status: OPEN, NONCRITICAL for CP-26.08

Found while executing CP-26.08, 2026-09-19.

The `format-check` and `lint` gates scope ruff to `aart_cli`, `tests` and `scripts`
(`scripts/quality.py`). Run from the repository root without those paths, this build's ruff also
formats the Python fenced blocks inside Markdown: `ruff format .` reflowed eleven code blocks in
`docs/product-specification/PRODUCT_SPECIFICATION.md`, plus blocks in two slice documents. The
Product Specification is the sole source of product truth and a formatter is not allowed to be an
author of it.

No gate is wrong — the gate is correctly scoped and the damage came from a hand-run command — so
this is not a defect in the quality suite. What is missing is a statement in the repository that
ruff is scoped on purpose, and, if this build's ruff supports it, an exclusion that makes the
unscoped invocation safe as well. Worth doing before more agents run formatters by hand.

## B-154 — `aart-cli author check` does not check Collection manifests

**Found:** 2026-09-19, CP-26.11.

`check` reports a Collection manifest as `skip`: discovered, not an artifact, not judged. That is
honest -- `registry scan` passes over one too -- but an author writing a Collection gets no verdict
at all, and `parse_author_collection_manifest` is right there. The obstacle is that
`compile_author_collections` refuses the whole tree rather than the one manifest, so attributing a
Collection refusal to its path needs either a per-manifest variant or attribution by
`Diagnostic.path`.

**Noncritical.** No Product Specification invariant, acceptance test or security boundary depends
on it, and no CP-26 slice needs it. It becomes critical only if a mandatory acceptance test
requires a Collection verdict from `author check`.

## B-155 — 274 mutants survive in `authoring/skeleton.py`, almost all in template text

**Found:** 2026-09-19, CP-26.12.

`make mutants ONLY=aart_cli/authoring/skeleton.py TESTS="tests/author_skeleton_test.py"`
kills 771 of 1045. Of the 274 survivors, 245 are in the blueprint, payload and guidance builders --
case flips and `"XX...XX"` wrappers on the prose a skeleton carries, plus the placeholder harness
and platform names in `compatibility`. The repository does not pin generated prose in a test, so
these are noise by design.

The remaining 29 are in `_anchored`, `author_skeleton`, `_disabled` and `_live_document`, and are
about **where** a disabled block is placed rather than whether it is correct: the anti-drift and
uncommenting oracles compare parsed documents, and `JsonObject` sorts its entries, so a block that
moves from above the next live key to the end of its mapping produces the same document. Several
are equivalent mutants outright (`>` to `>=` against a key that is by construction absent from the
live set; `continue` to `break` on a branch no current blueprint reaches).

Two survivors *were* real and are already closed as tests rather than left here: nothing asserted
`AuthorSkeleton.kind`/`.name`, and the ungenerated-kind refusal could stop naming the kinds it does
generate.

**Noncritical.** Closing the rest would mean asserting generated prose, which the repository
deliberately does not do. It becomes critical only if the *placement* of a disabled block becomes a
contract -- for instance if a shipped example were diffed against a generated one byte for byte.

## B-156 — every generated registry's CI has failed its validation gate since 0.0.1

**Found:** 2026-09-19, CP-26.18. **Fixed in the same change**; recorded here for the lesson.

The generated workflow ran `aart-cli registry validate --source . --strict --frozen`. Neither flag has
ever existed on the CLI, so the step died with `unrecognized arguments` in every registry `registry
init` has ever produced. `docs/refactor/slices/cp-26-authoring-and-legacy-removal.md` step 18 still
describes the gate set as "strict/frozen validation", which is where the flags came from.

`EveryVisibleCommandMentionTest` exists to catch exactly this: it parses every `aart …` string the
package names with the shipped parser. It could not see this one, because the command lived inside
a `bytes` template literal that the guard's `ast` walk reads as a `bytes` constant rather than a
visible string. CP-26.18 moved the gate list into `registry_commands/publication.py` as ordinary
`str`s, and the guard failed on the first run.

**Noncritical as a backlog item, because the defect is closed.** What is open is the class: any
other operator-facing command still living in a `bytes` template is invisible to the guard. Making
`_visible_strings` decode `bytes` constants would close it, and would need the false positives
measured first -- most `bytes` literals in the package are file content, not advice.

## B-157 — Enterprise index release customization is deferred

**Owner decision, 2026-09-19; issue #24; D-349.** Revisit configurable distribution/release naming
when the owner starts the actual Enterprise package-index release. Do not add this work to CP-26
installation naming or local smoke verification. Preserve the accepted `aart-cli` executable,
`aart_cli` import and application-home contract; any eventual distribution customization needs its
own scoped acceptance and release evidence. This deferral does not remove CP-26.21's existing
verification obligations. **Open, noncritical; explicitly deferred.**

## B-158 — mutmut cannot scope a large module to the changed callable

**Found:** 2026-09-19, CP-26.19.

`make mutants ONLY=aart_cli/application/consumer_ui.py
TESTS="tests/install_time_config_form_test.py"` generated 2502 mutants across every consumer screen,
although the slice changed only the installation-config draft and row handling. The runner writes
mutmut's file-only `only_mutate` setting and cannot select a class or callable. The run was stopped
after 253 mutants as disproportionate; the slice's owner-key claim is instead held by a recorded
targeted mutation and its focused E2E.

**Noncritical.** Add callable or line-level scoping to `scripts/mutants.py`, or extract cohesive
screen models when that is architecturally justified. This does not block CP-26.19 because the
required semantic mutation went red and the complete unit suite is green; it becomes critical only
if a future slice changes this broad module and has no practical mutation-adequacy signal.

## B-159 — the launcher's harness argument and per-harness config filename are now redundant

**Found:** 2026-09-20, CP-26.19 (D-360).

An installation is one harness's now, so its tree holds exactly one configuration file and its
launcher is started by exactly one harness. The launcher still takes the harness as an argument and
still resolves its configuration file by that harness's name (`config/<harness>.conf`), which is
correct but says something the tree already knows. Both date from the shape where one launcher
served several harnesses (D-264, D-355).

**Noncritical.** Nothing is wrong or unsafe: the argument is passed, the file is found, and the
value read is the right one. Simplifying it is a rename of a path and a signature, and doing it
during the split would have mixed a cosmetic change into a commit whose failures need to stay
readable. It becomes critical only if a future slice needs the launcher to be startable without an
argument.

## B-160 — `propose_installation` supersession is still keyed by coordinate

**Found:** 2026-09-20, CP-26.19 (D-360).

`previous` / `superseded` in `application/installation_proposal.py` is resolved by unversioned
coordinate. With several installations of one artifact, a multi-harness **update** can therefore
pair a member with another harness's previous state and forget the wrong record.
`record_installation_transaction` already forwards `superseded.owner` to
`forget_installation`, so the store does the right thing once the proposal names the right
installation.

**Reclassified critical and closed, 2026-09-20 (D-361).** It did not fall out of the view slice.
Measured rather than predicted: `marketplace update` on a Skill installed into claude and opencode
was refused outright with `installation-proposal-invalid: an artifact was superseded twice`,
because `dict(previous)` collapsed the two entries that name one coordinate. Nothing was paired
with the wrong state and nothing was forgotten -- the whole update stopped. That is §169.3's update
acceptance failing, so it moved into CP-26.19. The key is now the installation owner the previous
state already carries, and `tests/configured_update_command_e2e_test.py` converges both trees.

## B-161 — an authored artifact cannot declare a dependency, so `requires` is unreachable in practice

**Found:** 2026-09-20, while writing CP-26.20's dependency-closure evidence (D-362).

`requires` exists on the published native artifact manifest, is validated by
`protocol/registry_index.validate_registry_graph` (a dependency the registry does not publish is
refused, and the refusal explains that `requires` resolves inside one registry), is carried into
the Marketplace graph by `compiler/graph.py`, and becomes an install-time `ArtifactRequest` in
`io/configured_selection._dependency`. None of that can be reached from the authoring surface: the
author manifest's field set in `protocol/authoring.py` does not include `requires`, and
`compile_author_snapshot` emits `artifact.json` with `requires=()` every time. So the whole
dependency mechanism is exercised only by tests that construct a `NativeArtifactPackage` directly
(`tests/registry_index_test.py`, `tests/registry_dependency_scope_test.py`), and no end-to-end path
-- promote, publish, resolve, install a closure -- exists to hold it.

**Why it is not critical.** No Product Specification invariant on CP-26's critical path requires an
authored dependency, and nothing regressed: this is a capability that was never wired to its own
front door, not a break. CP-26.20's claim is the re-addressing itself, which
`tests/configured_registry_alias_test.py` holds against the real reader.

**What closing it needs.** Either add `requires` to the authoring manifest surface (schema, parser,
`author init` skeleton, `author check`, and the emitted `artifact.json`) and then one acceptance
test that installs a closure end to end, or decide deliberately that dependencies are a
registry-maintenance concept only and delete the unreachable half. The decision belongs with the
authoring-surface owner, not with this slice.
