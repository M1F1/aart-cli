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
Status: OPEN — attempted and reverted on 2026-08-31 (D-062)
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
Status: PROMOTED TO CP-13 CRITICAL PATH (2026-08-31)
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
Evidence/links: D-052, D-059, D-063; `tests/consumer_ui_actions_test.py`;
`tests/consumer_action_shell_test.py`.
Unblock condition: aggregate execution, durable recording and screen projections are verified for
single and multi-artifact Selection, including partial execution and compensation evidence.
