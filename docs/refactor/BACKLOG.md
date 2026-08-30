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
