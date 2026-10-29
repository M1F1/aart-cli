# aart-cli Product Specification

> **STATUS: CANONICAL — SOLE PRODUCT SOURCE OF TRUTH**
>
> **2026-09-19 accepted revision:** §169 defines the `aart-cli` namespace, one portable
> `~/.aart-cli` home, harness-owned installations and independently entered inputs for every
> installation. Implementation is pending in CP-26.18a and CP-26.19; accepted examples are the
> target contract, not a claim that the current binary already implements these names or paths.
> **2026-09-19 accepted addition, revised 2026-10-14 (D-378):** §170 defines local MCP smoke
> verification in two direct stages, installation configuration and MCP startup and protocol,
> through `aart-cli mcp test` and an optional test offered after installation. CP-28 step 3
> implements the revision; this acceptance is not evidence that it is already implemented.
>
> **2026-10-15 accepted addition (D-406):** §171 adds the OpenCode plugin artifact kind: reviewed,
> vendored code that opencode loads into its own process, registered by path and reviewed as
> high-risk execution. CP-29 steps 4–5 implement it.
>
> **Target repository:** `M1F1/aart-cli`
>
> This document is the canonical product specification for the aart-cli refactor. It defines the
> accepted product behavior, architecture, UX, TUI contracts, domain model, registry/source/
> candidate/marketplace boundaries, lifecycle, reconciliation model, policies, security rules,
> credential handling, testing expectations, maintainer workflows, consumer workflows, edge cases,
> migration invariants, and release direction.
>
> If any other document, README prose, issue, comment, legacy implementation, or older aart-cli
> repository conflicts with this document, **this Product Specification wins**.
>
> Older repositories including `M1F1/aart`, `agent-artifacts`, `Agent Artifacts`, old registry
> experiments, and other predecessor repositories are **reference material only**. They may be read
> for behavior, fixtures, provenance, or implementation ideas, but they are not refactor targets and
> never override this specification.
>
> Execution plans, migration notes, backlog entries, and implementation decisions may refine *how*
> this specification is implemented, but may not weaken or silently change *what* it requires.
>
> The intended execution mode includes long unattended agent runs. Critical-path requirements are
> mandatory. Non-blocking discoveries belong in `docs/refactor/BACKLOG.md` instead of expanding the
> active slice.

---

# aart-cli Enterprise Architecture v3 — Cumulative Design
## Algebraic model for artifacts, requirements, remediations, effects, policies, MCP runtimes, and TUI-driven configuration

> **Status:** cumulative architecture draft v3  
> **Primary goal:** design aart-cli as an open-source, enterprise-ready package manager and marketplace for agent artifacts.\
> **Primary human interface:** TUI.  
> **Automation interface:** deterministic CLI / JSON suitable for CI/CD.  
> **Out of scope for now:** an autonomous agent itself as an aart-cli artifact type.

---

# 1. Product direction

aart-cli should not be only a marketplace for Agent Skills.

It should become:

> **An enterprise package manager, registry client, policy engine, installation planner, configuration assistant, and human review interface for heterogeneous AI-agent artifacts.**

Initial artifact families:

```text
Skill
MCP
Guideline / Rule
Hook
Memory
```

Potential future families:

```text
Prompt
Command
Workflow
Bundle / Collection
Agent
```

The architecture should preserve interoperability with external standards instead of inventing replacements for them.

---

# 2. Public aart-cli vs private enterprise configuration

A critical invariant is:

```text
PUBLIC TOOLING != PRIVATE ENTERPRISE CONTENT
```

The public `aart-cli` repository should contain:

```text
domain model
artifact algebra
requirement algebra
remediation algebra
effect algebra
policy algebra / policy schema
planner
policy evaluator
importers
harness adapters
interpreters
TUI
CLI / JSON
receipts
validation
provenance
```

The private enterprise repository should contain:

```text
concrete artifact definitions
enterprise policies
profiles
collections
credential references
internal endpoints
internal registry mappings
organization-specific metadata
```

Conceptually:

```text
                     PUBLIC
               ┌──────────────┐
               │   aart-cli   │
               │              │
               │ schemas      │
               │ ADTs         │
               │ planner      │
               │ policies     │
               │ interpreters │
               │ TUI          │
               └──────┬───────┘
                      │
                      ▼
                    PRIVATE
          ┌────────────────────────┐
          │ enterprise-aart-cli-registry│
          │                        │
          │ artifacts/             │
          │ policies/              │
          │ profiles/              │
          │ collections/           │
          │ provenance/            │
          └────────────┬───────────┘
                       │
                       ▼
                  CI validation
                       │
                       ▼
                immutable snapshot
                       │
                       ▼
                 Nexus / Artifactory
```

Nexus or Artifactory should be treated as a **distribution/storage layer**, not as the semantic definition of the aart-cli registry.

---

# 3. Avoid mandatory enterprise forks where possible

A company may fork aart-cli, but the architecture should minimize that need.

Preferred model:

```text
public aart-cli
       ↓
company-approved build
       ↓
internal PyPI/Nexus
```

plus:

```text
private enterprise registry
+
private enterprise policies
+
private enterprise profiles
```

A fork remains possible when the organization needs:

```text
custom interpreters
custom authentication
custom compliance behavior
custom proprietary harness integrations
```

but should not be required for ordinary configuration.

---

# 4. Core algebraic model

The original three-algebra model evolves naturally into five related domains:

```text
                       aart-cli DOMAIN
                            │
       ┌────────────┬───────┼────────┬────────────┐
       │            │       │        │            │
       ▼            ▼       ▼        ▼            ▼
    Artifact    Requirement Effect Remediation   Policy
    Algebra      Algebra   Algebra  Algebra      Algebra
```

Their responsibilities are distinct.

## Artifact

Describes **what the package/capability is**.

## Requirement

Describes **what must be true before the artifact can work**.

## Effect

Describes **what mutation aart-cli can perform**.

## Remediation

Describes **how an unsatisfied requirement may be resolved**.

## Policy

Describes **which artifacts, requirements, remediations, and effects are permitted in a target environment**.

---

# 5. Artifact algebra

Conceptually:

```python
type Artifact = SkillArtifact | McpArtifact | GuidelineArtifact | HookArtifact | MemoryArtifact
```

Keep semantic kind separate from concrete format and protocol:

```text
kind=skill
format=agent-skills/v1

kind=rule
format=cursor/mdc

kind=mcp
format=mcp-server-json/v1
protocol=mcp/<version>
```

Common envelope:

```text
ArtifactPackage
├── coordinate
├── version
├── kind
├── format
├── metadata
├── provenance
├── requirements
├── compatibility
├── capabilities
└── payload
```

Example coordinates:

```text
company/skill/python-testing
company/mcp/github
company/hook/pre-commit
```

Potential URI:

```text
aart-cli://company/mcp/github@1.4.0
```

---

# 6. MCP should be the first serious vertical slice

MCP proves that an artifact cannot be modeled as only files.

A local MCP may be:

```text
Harness
  │
  │ launches process
  ▼
launcher.sh
  │
  ├── resolves credentials
  ├── optionally transforms them
  ├── prepares environment
  └── execs server.py
           │
           ▼
      official MCP Python SDK
           │
           ▼
          stdio
```

This matches a realistic enterprise pattern well.

MCP itself should not imply:

```text
Docker
npm
PyPI
Python
shell script
```

MCP is the protocol.

Distribution/runtime strategy remains separate.

---

# 7. MCP domain model

Suggested decomposition:

```python
type McpTransport = StdioTransport | StreamableHttpTransport

type McpDistribution = (
    SourceTreeDistribution
    | BinaryDistribution
    | PythonPackageDistribution
    | NpmPackageDistribution
    | OciDistribution
    | RemoteDistribution
)
```

Conceptually:

```python
McpArtifact(
    identity=...,
    version=...,
    transport=StdioTransport(...),
    distribution=SourceTreeDistribution(...),
    runtime_requirements=(...),
    credential_requirements=(...),
    network_requirements=(...),
    capabilities=(...),
    provenance=...,
)
```

Harness-specific config does not belong here.

Do not add:

```text
ClaudeConfig
CursorConfig
CodexConfig
```

to `McpArtifact`.

Those belong in adapters.

---

# 8. Current enterprise MCP pattern: source tree + launcher + Python + stdio

For the current practical enterprise pattern:

```text
artifact payload
├── server.py
├── launcher.sh
└── supporting modules
```

the aart-cli model can start conservatively.

Example:

```yaml
kind: mcp
format: aart-cli-mcp-v2

transport:
  type: stdio

distribution:
  type: source-tree

runtime:
  type: python
  min_version: "3.11"

launch:
  type: script
  path: launcher.sh

credentials:
  - id: github-token
    provider: macos-keychain
    inject_as:
      env: GITHUB_TOKEN
```

This represents the current working reality without prematurely replacing shell launchers.

---

# 9. Evolution path for launcher scripts

Do not remove working `launcher.sh` scripts immediately.

Use an incremental maturity model.

## V1 — managed script

```text
private artifact contains launcher.sh
aart-cli installs and registers it
```

## V2 — declarative launcher

```text
private artifact declares:
runtime
credentials
transformations
entrypoint
environment
```

aart-cli generates a launcher deterministically.

## V3 — native aart-cli runtime adapter

```text
aart-cli runtime adapter:
Keychain
  ↓
transform
  ↓
environment
  ↓
exec server.py
```

At V3 no shell script may be necessary.

The architecture should support all three.

---

# 10. Requirements are not effects

Example credential requirement:

```python
CredentialRequirement(
    id="github-token",
    provider="keychain",
    required=True,
)
```

This describes a condition.

It does not mean aart-cli has already read or stored the credential.

Other possible requirements:

```python
type Requirement = (
    CredentialRequirement
    | RuntimeRequirement
    | ExecutableRequirement
    | NetworkRequirement
    | FilesystemRequirement
    | HarnessRequirement
)
```

Examples:

```text
Python >= 3.11 exists
macOS Keychain is available
credential github-token exists
github.company.com is reachable
Claude harness is installed
```

---

# 11. Requirements have states

The environment inspection stage evaluates requirements.

```text
Requirement
   ↓
Inspector
   ↓
Satisfied | Unsatisfied | Unknown
```

For example:

```text
CredentialRequirement("github-token")
        ↓
Keychain inspector
        ↓
Unsatisfied
```

The planner should not blindly fail immediately.

Instead it can expose possible remediations.

---

# 12. Remediation algebra

A remediation describes a safe, understandable way of making a requirement true.

```python
type Remediation = (
    ConfigureCredential
    | InstallRuntime
    | InstallExecutable
    | ConfigureNetwork
    | ConfigureHarness
    | SelectAlternativeProvider
)
```

Example:

```text
UnsatisfiedRequirement
    requirement:
        CredentialRequirement("github-token")

    remediations:
        StoreInKeychain
        UseEnvironmentVariable
        UseEnterpriseSecretManager
```

This creates a powerful TUI workflow.

---

# 13. Available remediations are filtered

The user should not see every theoretically possible remediation.

The actual choices are:

```text
Possible Remediations
        ∩
Platform Capabilities
        ∩
Enterprise Policy
        ↓
Allowed Remediations
```

For example:

```text
macOS Keychain        ✓ available
environment variable  ✓ available
Vault                 ✗ unavailable
```

Policy may further reduce this:

```text
macOS Keychain        ✓ allowed
environment variable  ✗ forbidden
```

The TUI therefore displays only compliant options.

---

# 14. Credential lifecycle must be first-class

Credential management should not be a one-time special case.

aart-cli should explicitly support:

```text
create
verify
replace
rotate
delete
reconfigure provider
```

Potential credential mutations:

```python
type CredentialEffect = (
    StoreCredential | ReplaceCredential | DeleteCredential | VerifyCredentialAvailability
)
```

A replacement must be explicit.

Example:

```text
Existing credential detected:
github-token

Choose:

> Keep existing credential
  Verify existing credential
  Replace credential
  Delete and configure again
  Cancel
```

---

# 15. Yes — overwriting Keychain credentials is necessary

A user may:

```text
paste the wrong token
use an expired token
use a token for the wrong account
need to rotate credentials
change permissions/scopes
change environments
```

Therefore:

```text
StoreCredential
```

alone is insufficient.

A better model includes:

```text
CreateCredential
ReplaceCredential
DeleteCredential
VerifyCredential
```

or one algebraic operation:

```python
CredentialMutation(mode=Create | Replace | Delete)
```

The explicit ADT variants are likely clearer.

---

# 16. Credential replacement UX

Suggested TUI flow:

```text
GitHub MCP credential
─────────────────────────────

Credential:
  github-token

Provider:
  macOS Keychain

Status:
  ✓ value exists

Actions:

> Verify credential
  Replace credential
  Change provider
  Delete credential
  Back
```

If the user chooses `Replace credential`:

```text
A credential already exists.

Replacing it affects this installation:
  company/mcp/github · Claude · user · <user-home>

Continue?
```

Then:

```text
Enter new token:
[••••••••••••••••••]

> Test before replacing
  Replace without test
  Cancel
```

Preferred path:

```text
new secret
   ↓
validate
   ↓
atomic replace
   ↓
verify
   ↓
continue
```

---

# 17. Credential replacement should ideally be atomic

Where the provider supports it, replacement should behave conceptually like:

```text
receive new value
      ↓
validate new value
      ↓
write new value
      ↓
verify
      ↓
success
```

Avoid:

```text
delete old
   ↓
attempt write new
   ↓
failure
   ↓
credential lost
```

The exact semantics depend on the credential provider interpreter.

aart-cli's abstract effect should express intent; the provider-specific interpreter handles the safest implementation.

---

# 18. Never expose the old credential

aart-cli should never offer:

```text
Show current token
```

as normal product behavior.

For existing credentials the user should see:

```text
exists
provider
reference
last validation status
possibly metadata
```

but not the value.

Example:

```text
github-token
Provider: macOS Keychain
Status: present
Last verified: valid
```

Not:

```text
ghp_abc123...
```

---

# 19. Secret-safety invariants

These should be architectural invariants.

```text
Secret values must never appear in:

InstallPlan
Receipt
registry snapshot
provenance
logs
telemetry
JSON CLI output
error messages
TUI history
```

The secret may temporarily exist in:

```text
interactive input buffer
credential interpreter call
provider-specific secure channel
```

and should be discarded as soon as practical.

Another strong invariant:

```text
aart-cli plan does not require reading secret values
```

Planning should operate on:

```text
credential exists?
provider available?
credential reference?
policy allows provider?
```

not on the actual token.

---

# 20. Install-time vs runtime secret handling

For MCP, this distinction is especially useful.

Install time:

```text
verify that a credential reference exists
optionally configure/replace it interactively
write runtime reference
```

Runtime:

```text
launcher/runtime adapter
      ↓
secure provider
      ↓
resolve secret
      ↓
optional transform
      ↓
inject environment
      ↓
exec server
```

aart-cli does not need to persist the actual secret.

---

# 21. Credential transformations

Some launchers transform retrieved secrets.

Avoid making arbitrary shell transformation the only model.

Possible future ADT:

```python
type CredentialTransform = Identity | Prefix | JsonField | Base64Decode | Template
```

For example:

```text
retrieve JSON secret
      ↓
JsonField("token")
      ↓
Prefix("Bearer ")
      ↓
inject
```

Initially, aart-cli may continue supporting script-based launchers.

Later, common transformations can become declarative.

---

# 22. Effects should remain explicit

Suggested high-level effect families:

```python
type Effect = (
    FilesystemEffect
    | PackageEffect
    | RuntimeEffect
    | CredentialEffect
    | HarnessEffect
    | VerificationEffect
)
```

Candidate primitive effects:

```text
CopyTree
WriteFile
MergeJson
ManagedBlock
CreateDirectory
CreateSymlink
EnsureExecutable
EnsurePackage
EnsureContainerImage
VerifyDigest
ConfigureHarness
StoreCredential
ReplaceCredential
DeleteCredential
```

Some of these may be semantic effects that compile further into provider-specific operations.

---

# 23. Effect risk classes

Not all effects deserve the same approval model.

Suggested risk categories:

```text
ReadOnly
LocalMutation
ConfigurationMutation
CredentialMutation
ExecutableInstall
NetworkMutation
HighRiskExecution
```

Examples:

```text
InspectCredentialReference
→ ReadOnly

MergeHarnessConfig
→ ConfigurationMutation

ReplaceCredential
→ CredentialMutation

InstallPythonRuntime
→ ExecutableInstall

RunArbitraryShellCommand
→ HighRiskExecution
```

Policy and UI can react differently to each class.

---

# 24. Arbitrary shell execution should not be the universal effect

Avoid:

```text
RunShell("whatever")
```

as the central abstraction.

It is impossible to statically reason about:

```text
filesystem mutations
network usage
credential access
side effects
rollback
security impact
```

A script-based launcher can still be supported as an artifact runtime strategy, but should remain visible as such.

For example:

```text
runtime:
    launch_mode: external-script
```

Policy may allow or deny this.

---

# 25. Install effects vs runtime requirements

For MCP this separation is fundamental.

Example current Python/stdio setup.

## Install effects

```text
CopyTree
EnsureExecutable(launcher.sh)
ConfigureHarness
WriteReceipt
```

## Runtime requirements

```text
Python runtime
Keychain provider
Credential github-token
launcher.sh executable
possibly network access
```

Runtime requirement does not automatically imply that aart-cli must install the missing dependency.

It may instead provide a remediation.

---

# 26. Minimal dependencies should be a policy preference

Enterprise environments generally prefer fewer dependencies.

aart-cli should not assume:

```text
Docker
Node
npm
uv
Python
```

are globally available.

Instead the planner evaluates actual artifact needs.

For current enterprise MCPs:

```text
Python
shell
Keychain
stdio
```

may already be enough.

A policy can explicitly say:

```yaml
runtime:
  preferred:
    - system-python

  forbidden:
    - docker
    - npm
```

or in another company:

```yaml
runtime:
  preferred:
    - oci

  forbidden:
    - source-tree
```

The artifact model remains unchanged.

---

# 27. Docker is optional, not part of MCP semantics

Docker can be one distribution/runtime option:

```text
MCP Artifact
    ↓
OCI Distribution
    ↓
EnsureContainerImage
    ↓
RegisterStdioServer
```

but should not become a required dependency of aart-cli.

If current enterprise MCPs already work with:

```text
server.py
launcher.sh
Keychain
stdio
```

aart-cli should support that path with zero Docker dependency.

---

# 28. Policy algebra

Public aart-cli defines policy primitives.

Examples:

```text
AllowTransport
ForbidRuntime
RequireDigest
AllowRegistry
AllowNetworkHost
RequireCredentialProvider
ForbidArbitraryLauncher
RequireApprovedArtifact
```

The enterprise repository composes concrete policy expressions.

Example private structure:

```text
policies/
├── base.yaml
├── security.yaml
├── workstation.yaml
├── production.yaml
└── ml-team.yaml
```

---

# 29. Policy composition belongs to the enterprise layer

Public aart-cli owns:

```text
policy language
policy parser
composition algorithm
conflict detection
policy evaluator
```

Private enterprise repo owns:

```text
which policies are selected
which values are configured
how environments compose them
```

Conceptually:

```text
PolicyExpr
  +
PolicyExpr
  +
PolicyExpr
      ↓
compose()
      ↓
EffectivePolicy
```

Example:

```text
enterprise-base
      ∧
security
      ∧
developer-workstation
      ∧
team-policy
      ↓
EffectivePolicy
```

---

# 30. Restrictive policy composition invariant

For security-sensitive constraints:

```text
child policy must not silently broaden parent policy
```

For example:

```text
organization:
    allowed_registries = [internal]

project:
    allowed_registries = [internal, public]
```

should not automatically produce:

```text
[internal, public]
```

The effective result should remain constrained by the parent.

Think:

```text
effective allowed set = intersection
```

for allow-lists.

Different policy fields may need different algebraic composition rules.

Examples:

```text
allowed hosts      → intersection
forbidden runtime  → union
required checks    → union
risk ceiling       → minimum
```

These rules should be explicit and testable.

---

# 31. Requirement remediation + policy

The whole flow becomes:

```text
Artifact
   ↓
Requirements
   ↓
Inspect Environment
   ↓
Satisfied?
   │
   ├── yes ──────────────────────┐
   │                             │
   └── no                        │
       ↓                         │
Generate Remediations            │
       ↓                         │
Policy Filter                    │
       ↓                         │
Allowed Remediations             │
       ↓                         │
TUI Wizard                       │
       ↓                         │
Effects                          │
       ↓                         │
Re-inspect Requirements ─────────┘
       ↓
Installation Plan
       ↓
Review
       ↓
Execute
       ↓
Receipt
```

This is a powerful general mechanism beyond credentials.

---

# 32. TUI as configuration assistant

The user should ideally be able to complete the full lifecycle without leaving aart-cli:

```text
search
  ↓
inspect
  ↓
install
  ↓
detect missing requirements
  ↓
configure credentials/runtime
  ↓
verify
  ↓
configure harness
  ↓
finish
```

Example wizard:

```text
Install company/mcp/github
────────────────────────────────

✓ Python 3.11 detected
✓ launcher.sh supported
✗ Credential github-token missing

Configure now?

> Yes
  No
  Cancel installation
```

Then:

```text
Choose credential provider:

> macOS Keychain
  Environment variable
```

Policy may remove disallowed options.

---

# 33. TUI and CI must use the same domain model

Architecture:

```text
TUI ──────┐
          │
CLI ──────┼──► Application API
          │
JSON API ─┘
                │
                ▼
              Domain
```

The TUI must not implement Keychain logic directly.

Bad:

```text
TUI
  ↓
security add-generic-password
```

Good:

```text
TUI
  ↓
Application Service
  ↓
CredentialEffect
  ↓
CredentialInterpreter
  ↓
macOS Keychain
```

---

# 34. Non-interactive CI behavior

Interactive remediation should be configurable.

Example CI policy:

```yaml
interactive_remediation: false
```

Then:

```text
MissingCredential
      ↓
FAIL
```

not:

```text
open wizard
```

CI can instead receive credentials from an approved environment/provider.

The same `Requirement` and `Policy` model still applies.

---

# 35. InstallPlan should never contain secret values

Example safe plan:

```yaml
effects:
  - type: configure-harness
    artifact: company/mcp/github

requirements:
  - type: credential
    id: github-token
    provider: macos-keychain
    status: satisfied
```

Unsafe:

```yaml
token: ghp_xxxxxxxxxx
```

The plan should remain safely serializable to JSON and suitable for audit.

---

# 36. TUI as effect review surface

The TUI can render the planned mutations before execution.

```text
┌──────────────────────────────────────────────┐
│ Install company/mcp/github@1.4.0             │
│                                              │
│ Runtime                                      │
│ ✓ Python 3.11                                │
│ ✓ stdio MCP                                  │
│                                              │
│ Files                                        │
│ + MCP source tree                            │
│ + launcher.sh                                │
│                                              │
│ Credentials                                  │
│ ✓ github-token                               │
│   provider: macOS Keychain                   │
│                                              │
│ Harness                                      │
│ ~ Claude MCP configuration                   │
│                                              │
│ Risk                                         │
│ LocalMutation                                │
│ ConfigurationMutation                        │
│                                              │
│ Trust                                        │
│ ✓ approved registry                         │
│ ✓ provenance verified                        │
│                                              │
│          [ Install ]       [ Cancel ]        │
└──────────────────────────────────────────────┘
```

Credential replacement gets its own review because it is a `CredentialMutation`.

---

# 37. Credential management should be accessible outside installation

A user should not need to reinstall an artifact to rotate credentials.

Potential commands:

```text
aart-cli credentials list
aart-cli credentials inspect github-token
aart-cli credentials verify github-token
aart-cli credentials configure github-token
aart-cli credentials replace github-token
aart-cli credentials delete github-token
```

These command sketches abbreviate the target. `github-token` alone is not a global identifier:
inspection and mutation must resolve the complete installation owner (§38/169) explicitly, and an
ambiguous input id must never select a target silently. Listing may aggregate metadata.

Equivalent actions should exist in the TUI.

This makes credential lifecycle a first-class application feature.

---

# 38. Credentials belong to one installation

Each concrete installation owns its own credential bindings and provider items. There is no
cross-installation credential selection, sharing, copying or "use for all targets" action in the
current product. Ordinary configuration follows the same boundary (§96).

An installation is identified by Registry alias, artifact kind/name, scope, normalized concrete
project/user target root and harness/profile. Input identifiers are local to this owner. Version
is excluded from the stable identity so a compatible update can retain that installation's inputs.

Installing one MCP into four harnesses creates four installations. The user enters each required
secret separately for each installation; with one secret per installation this means four secure
entries and four distinct provider items, even when the user types identical secret text. aart-cli
neither compares secret values nor requires the upstream service to issue four different tokens.

Replacement, verification and deletion address exactly one installation's credential. The UI shows
its artifact, harness, scope and target root before mutation. Uninstall deletes the removed
installation's credentials with it (§208); a credential never becomes a globally selectable
credential for another installation.
Compatible inputs may be retained during update or repair only within the same complete identity.

Non-interactive execution supplies separate target-qualified input bindings through an approved
provider (§34); a missing binding fails with the affected target rather than opening a prompt or
borrowing another installation's input.

---

# 39. Credential identity vs secret value

Important distinction:

```text
CredentialReference
```

is stable metadata.

```text
CredentialValue
```

is ephemeral secret material.

Example:

```python
CredentialReference(
    input_id="github-token",
    provider="macos-keychain",
    service="aart-cli.<installation-target-id>",
    account="github-token",
)
```

The logical `installation-target-id` is derived deterministically and collision-resistently from:

```text
Registry alias
+ artifact kind and name
+ project/user scope
+ normalized concrete project/user target root
+ harness/profile
```

The complete credential-binding key is therefore:

```text
Registry alias + artifact + scope + concrete target root + harness/profile + input_id
```

For macOS Keychain, every distinct complete key creates or selects a distinct generic-password item
(a distinct `service`/`account` pair). The provider-facing encoding should be opaque and must not
expose a raw filesystem path, but it must preserve this uniqueness. The rule applies equally to a
Registry synchronized from a remote URL and one synchronized from a local checkout. Equal package
bytes, artifact names or input ids do not collapse entries. A provider item cannot be bound to a
second installation, including through an explicit UI, CLI or automation action.

The actual token is never part of this domain object.

This enables:

```text
receipts
dependency graph
policy
TUI
audit
```

without handling secret values.

---

# 40. Interpreters

Effects execute through interpreters.

Examples:

```text
FilesystemInterpreter
GitInterpreter
CredentialInterpreter
PythonRuntimeInterpreter
ContainerInterpreter
PackageInterpreter
HarnessInterpreter
NetworkInspector
```

Concrete credential interpreters might be:

```text
MacOSKeychainInterpreter
EnvironmentCredentialInterpreter
EnterpriseVaultInterpreter
LinuxSecretServiceInterpreter
```

Only interpreters touch external mutable systems.

---

# 41. Planner should remain mostly pure

Desired shape:

```python
def plan_install(
    artifact: Artifact,
    target: Target,
    policy: EffectivePolicy,
    platform: PlatformFacts,
    requirement_status: RequirementStatusSet,
) -> Result[InstallPlan, PlanningError]: ...
```

Environment inspection may be effectful.

Planning after inspection should remain deterministic.

---

# 42. Algebraic errors

Suggested planning errors:

```python
type PlanningError = (
    UnsupportedPlatform
    | UnsupportedHarness
    | PolicyViolation
    | MissingRequirement
    | NoAllowedRemediation
    | DependencyConflict
    | UntrustedSource
    | DigestMismatch
)
```

Policy violations:

```python
type PolicyViolation = (
    ForbiddenRegistry
    | ForbiddenRuntime
    | ForbiddenCredentialProvider
    | ForbiddenNetworkHost
    | ForbiddenTransport
    | ForbiddenEffect
    | UnapprovedArtifact
)
```

Credential failures:

```python
type CredentialError = (
    CredentialMissing
    | CredentialInvalid
    | CredentialProviderUnavailable
    | CredentialWriteFailed
    | CredentialReplaceFailed
    | CredentialDeleteFailed
)
```

Structured errors are renderable both in TUI and JSON.

---

# 43. Source, Registry, Marketplace

Maintain this separation:

```text
SOURCE != REGISTRY != MARKETPLACE
```

## Source

```text
GitHub
GitLab
internal Git
HTTP
OCI
PyPI
npm
local
```

## Registry

```text
identity
version
digest
source
compatibility
dependencies
provenance
requirements
security metadata
```

## Marketplace

```text
search
categories
usage
documentation
trust
compatibility
collections
```

---

# 44. Enterprise repository layout

Potential private repository:

```text
enterprise-aart-cli-registry/
│
├── artifacts/
│   ├── mcp/
│   │   ├── github/
│   │   │   ├── artifact.json
│   │   │   └── payload/
│   │   │       ├── server.py
│   │   │       └── launcher.sh
│   │   ├── jira/
│   │   └── postgres/
│   │
│   ├── skills/
│   ├── hooks/
│   ├── guidelines/
│   └── memory/
│
├── policies/
│   ├── base.yaml
│   ├── security.yaml
│   ├── workstation.yaml
│   └── production.yaml
│
├── profiles/
│   ├── claude.yaml
│   ├── codex.yaml
│   └── cursor.yaml
│
└── collections/
    ├── python-engineer.yaml
    └── data-engineer.yaml
```

---

# 45. Registry CI/CD

Suggested flow:

```text
PR
 ↓
aart-cli registry validate
 ↓
aart-cli registry policy-check
 ↓
aart-cli registry audit
 ↓
aart-cli registry build
 ↓
immutable snapshot
 ↓
sign / attest
 ↓
publish to Nexus
```

The developer consumes only approved immutable snapshots.

---

# 46. Importers

Foreign ecosystem formats should be normalized before consumer installation.

```text
foreign source
     ↓
 importer
     ↓
canonical aart-cli artifact
     ↓
validation
     ↓
enterprise policy
     ↓
approved registry snapshot
```

Initial candidates:

```text
AgentSkillsImporter
McpServerJsonImporter
McpRegistryImporter
AGENTSmdImporter
CursorRuleImporter
ClaudeArtifactImporter
```

Possible interface:

```python
class ArtifactImporter(Protocol):
    def probe(self, source: SourceSnapshot) -> ProbeResult: ...

    def discover(
        self,
        source: SourceSnapshot,
    ) -> tuple[ForeignArtifact, ...]: ...

    def compile(
        self,
        artifact: ForeignArtifact,
    ) -> CanonicalArtifact: ...
```

---

# 47. Harness adapters

Canonical artifact intent remains independent from harness config format.

```text
Canonical Artifact
       │
       ▼
Installation Planner
       │
 ┌─────┼─────┐
 ▼     ▼     ▼
Claude Codex Cursor
Adapter Adapter Adapter
```

For the current MCP pattern, an adapter may generate:

```text
command = launcher.sh
transport = stdio
```

Another harness might require a completely different config structure.

---

# 48. Relationship to `skills.sh`

Useful design ideas to preserve:

```text
simple source syntax
good discovery UX
interactive installation
project/global scopes
lock/reproducibility concepts
marketplace separate from source ownership
```

aart-cli generalizes:

```text
Source
  ↓
Skill
  ↓
copy/symlink
```

into:

```text
Source
  ↓
Importer
  ↓
Artifact
  ↓
Requirements
  ↓
Environment Inspection
  ↓
Remediations
  ↓
Policy
  ↓
InstallPlan
  ↓
TUI / JSON Review
  ↓
Effects
  ↓
Interpreters
  ↓
Receipt
```

---

# 49. Core architecture principle

> **Artifact describes intent. Requirements describe what must be true. Remediations describe how missing requirements may be satisfied. Policy decides what is permitted. Planner produces an explicit plan. TUI/CLI reviews or approves it. Interpreters perform mutations. Receipts record what happened.**

Compactly:

```text
Artifact
   ↓
Requirements
   ↓
Inspect
   ↓
Remediate
   ↓
Policy
   ↓
Plan
   ↓
Review
   ↓
Effects
   ↓
Receipt
```

---

# 50. Strong invariants

These should drive the implementation and property-based tests.

```text
planning never mutates the environment

secret values never appear in:
plans, receipts, registry, provenance, logs, telemetry, JSON output

planning does not require reading secret values

credential replacement never requires exposing the old value

forbidden effects never reach interpreters

more restrictive policy cannot produce a more permissive effective policy

same artifact + target + effective policy + environment facts
produces the same plan

private enterprise configuration is not embedded into public aart-cli source

harness-specific configuration never leaks into canonical artifact semantics

MCP does not imply Docker

distribution is independent from transport

runtime requirements are independent from install effects

consumer installation does not crawl arbitrary foreign repository layouts

receipts record only effects actually performed

credential deletion/replacement identifies and warns about its sole installation owner

interactive remediation can be disabled for CI
```

---

# 51. Property-based tests worth adding

Hypothesis is particularly useful for:

```text
policy composition monotonicity

allow-list intersection

deny-list union

secret-redaction invariants

planner determinism

requirement/remediation completeness

unsupported remediation filtering

credential replacement ownership and isolation

receipt round-tripping

undo ownership boundaries

artifact identity stability

MCP transport/distribution independence
```

Example property:

```text
Given policies P and restrictive overlay R:

permissions(compose(P, R))
    ⊆
permissions(P)
```

---

# 52. Recommended implementation sequence

## Phase 1 — domain definitions

- [ ] ADR for five algebras.
- [ ] Frozen artifact ADTs.
- [ ] Requirement ADTs.
- [ ] Remediation ADTs.
- [ ] Effect ADTs.
- [ ] Policy expression model.
- [ ] Structured errors.
- [ ] Credential reference/value separation.

## Phase 2 — current MCP vertical slice

- [ ] Model `stdio`.
- [ ] Model source-tree distribution.
- [ ] Model Python runtime requirement.
- [ ] Model script launch strategy.
- [ ] Model Keychain credential requirement.
- [ ] Install existing `server.py + launcher.sh`.
- [ ] Register with one harness.
- [ ] Verify MCP startup.
- [ ] Record receipt.

## Phase 3 — interactive remediation

- [ ] Requirement inspection.
- [ ] Detect missing Keychain credential.
- [ ] TUI credential wizard.
- [ ] Store credential.
- [ ] Verify credential.
- [ ] Replace credential.
- [ ] Delete credential.
- [ ] Installation owner shown before credential mutation.
- [ ] Re-run requirement check.

## Phase 4 — policy composition

- [ ] Parse PolicyExpr.
- [ ] Compose enterprise policies.
- [ ] Build EffectivePolicy.
- [ ] Add monotonic composition rules.
- [ ] Filter remediations by policy.
- [ ] Filter effects by policy.

## Phase 5 — TUI effect review

- [ ] Render artifact metadata.
- [ ] Render requirements.
- [ ] Render remediations.
- [ ] Render planned effects.
- [ ] Render risk classes.
- [ ] Explicit approval for credential mutation.
- [ ] Reuse same plan for JSON mode.

## Phase 6 — runtime abstraction

- [ ] Declarative credential transformations.
- [ ] Generated launcher option.
- [ ] Native runtime adapter option.
- [ ] Remote MCP.
- [ ] OCI MCP.
- [ ] Additional harness adapters.

---

# 53. Recommended first production-quality MCP model

Do not begin with Docker.

Start with the actual enterprise pattern already proven in practice:

```text
MCP
├── source-tree distribution
├── stdio transport
├── Python runtime
├── launcher.sh
├── server.py
├── Keychain credential reference
└── harness registration
```

aart-cli then adds:

```text
validation
requirements
interactive remediation
credential lifecycle
policy filtering
TUI review
receipts
auditability
```

This minimizes dependencies while immediately testing the full architecture.

---

# 54. Final target experience

A developer runs:

```text
aart-cli
```

Searches for:

```text
company/mcp/github
```

aart-cli shows:

```text
MCP GitHub
──────────

Transport:
  stdio

Runtime:
  Python 3.11+

Credential:
  github-token via macOS Keychain

Status:
  ✓ runtime available
  ✗ credential missing
```

The user chooses install.

aart-cli says:

```text
One requirement is missing.

Configure github-token now?
```

The user pastes the token.

aart-cli:

```text
✓ credential validated
✓ credential stored securely
✓ requirement satisfied
```

Then:

```text
Planned changes:

+ install MCP files
+ make launcher executable
~ configure Claude MCP entry
+ create installation receipt

[ Install ] [ Cancel ]
```

Later, when the token expires:

```text
aart-cli
→ Credentials
→ github-token
→ Replace
```

aart-cli:

```text
This credential belongs to company/mcp/github · Claude · user · <user-home>.

Enter replacement token.
```

Then:

```text
✓ new credential validated
✓ credential replaced
✓ this installation remains configured
```

The developer never needs to manually:

```text
open Keychain
edit JSON
export environment variables
leave the TUI
```

unless enterprise policy explicitly requires an external step.

That is the intended aart-cli experience.
---

# 55. Author repository vs aart-cli installation contract

aart-cli must not require an MCP author to redesign the internal implementation of an existing server merely to participate in the marketplace.

An author repository may remain completely usable on its own:

```text
example-mcp-servers/
└── github/
    ├── server.py
    ├── launcher.sh
    ├── src/
    ├── tests/
    └── aart-cli.yaml
```

The author may continue using:

```text
launcher.sh
custom development scripts
manual debugging flows
repository-specific conventions
```

aart-cli introduces a separate contract:

> **You own the MCP implementation. aart-cli owns the installation contract.**

The `aart-cli.yaml` / `aart-cli.json` manifest is that contract.

---

# 56. `aart-cli.yaml` is a package manifest, not a launcher

The closest analogy is:

```text
pyproject.toml
package.json
Cargo.toml
```

not:

```text
install.sh
launcher.sh
```

The manifest describes:

```text
artifact identity
artifact boundary
payload files
transport
runtime
entrypoint
requirements
credential bindings
compatibility
installation intent
```

It does not need to contain imperative shell commands.

Example:

```yaml
schema: aart-cli.dev/mcp/v1

artifact:
  name: github-mcp
  kind: mcp
  version: 1.4.0

payload:
  include:
    - server.py
    - src/**
    - requirements.txt

  exclude:
    - tests/**
    - .venv/**
    - "**/__pycache__/**"

transport:
  type: stdio

runtime:
  type: python
  version: ">=3.11"

launch:
  type: python
  entrypoint: server.py

credentials:
  - id: github-token
    provider: macos-keychain
    inject:
      env: GITHUB_TOKEN

compatibility:
  harnesses:
    - claude
    - codex
```

---

# 57. Manifest discovery defines artifact boundaries

aart-cli should not crawl arbitrary repository layouts and guess what constitutes an artifact.

Instead:

```text
repository
   ↓
discover known aart-cli manifests
   ↓
each manifest defines one artifact boundary
```

For example:

```text
example-mcp-servers/
│
├── github/
│   ├── server.py
│   ├── launcher.sh
│   └── aart-cli.yaml
│
├── jira/
│   ├── server.py
│   └── aart-cli.yaml
│
└── confluence/
    ├── server.py
    └── aart-cli.yaml
```

produces three candidate artifacts.

The discovery contract should be explicit, for example:

```text
**/aart-cli.yaml
**/aart-cli.json
```

rather than heuristic detection of `server.py`, `launcher.sh`, or README contents.

---

# 58. Repository content is not artifact payload

A core invariant should be:

```text
Git repository != artifact payload
```

The manifest selects the files that belong to the published artifact.

Example:

```yaml
payload:
  include:
    - server.py
    - src/**
    - config/defaults.json

  exclude:
    - tests/**
    - docs/**
    - .venv/**
    - local/**
```

A stronger safe default is:

> **Canonical artifact payload contains only files selected by the manifest.**

This reduces accidental publication of:

```text
.env files
developer credentials
test fixtures
local caches
unrelated repository files
```

and makes artifact identity and hashing deterministic.

---

# 59. Authoring format and canonical registry format should differ

Do not require the convenient developer-facing manifest to be identical to canonical registry representation.

Recommended split:

```text
aart-cli.yaml
```

is the **authoring format**.

```text
artifact.json + payload/
```

is the **canonical registry package**.

Conceptually:

```text
aart-cli.yaml
   ↓
Manifest Parser
   ↓
Artifact Compiler
   ↓
CanonicalArtifact
   ├── artifact.json
   └── payload/
```

This resembles:

```text
pyproject.toml
   ↓
build
   ↓
wheel metadata + package payload
```

The authoring format can prioritize ergonomics.

The canonical representation can prioritize:

```text
determinism
validation
immutable identity
machine readability
registry compatibility
signing
provenance
```

---

# 60. Promotion into the marketplace

An MCP can exist perfectly well outside aart-cli.

Example lifecycle:

```text
author builds MCP
      ↓
server.py + launcher.sh work internally
      ↓
repository becomes useful/popular
      ↓
team wants marketplace distribution
      ↓
author adds aart-cli.yaml
      ↓
aart-cli validation
      ↓
enterprise review/policy
      ↓
canonical artifact build
      ↓
registry
      ↓
marketplace
```

This makes adoption incremental instead of requiring every internal project to use aart-cli from day one.

---

# 61. aart-cli takes responsibility after publication

Once an artifact is published through the aart-cli-native path:

```text
aart-cli owns:
    installation planning
    requirement checking
    remediation
    credential configuration
    harness configuration
    effect execution
    verification
    receipts
    uninstall/undo boundaries
```

The author's repository remains responsible for:

```text
MCP implementation
business capability
tests
development workflow
protocol behavior
```

The author should not need to duplicate enterprise installation logic in bespoke shell scripts.

---

# 62. Declarative installation should be the marketplace standard

Avoid making this the primary marketplace API:

```yaml
install:
  command: ./install-whatever.sh
```

because arbitrary commands destroy most of the benefits of:

```text
static validation
policy evaluation
effect review
risk classification
rollback
cross-platform interpretation
deterministic planning
```

Prefer declarative intent:

```yaml
runtime:
  type: python

launch:
  type: python
  entrypoint: server.py

credentials:
  - id: github-token
    provider: macos-keychain
    inject:
      env: GITHUB_TOKEN
```

which compiles into known aart-cli domain objects and effects.

---

# 63. Escape hatch for existing launchers

Existing `launcher.sh` scripts remain useful as a compatibility mechanism.

Example:

```yaml
launch:
  type: external-script
  path: launcher.sh
```

aart-cli should model this explicitly as arbitrary executable behavior rather than pretending it understands the script.

For example:

```text
ExternalScriptLaunch
    risk = HighRiskExecution
```

Enterprise policy can then decide:

```yaml
launch:
  external_scripts:
    allowed: false
```

or temporarily allow them during migration.

This supports gradual standardization.

---

# 64. Marketplace compliance levels

A useful migration model could expose artifact compliance levels.

For example:

```text
aart-cli Native
aart-cli Compatible
Legacy
```

Possible semantics:

## aart-cli Native

```text
declarative manifest
known requirements
known credential bindings
known launch model
known effects
no arbitrary installation scripts
```

## aart-cli Compatible

```text
valid aart-cli manifest
but uses an escape hatch such as external launcher
```

## Legacy

```text
no aart-cli installation contract
manual/internal use only
not eligible for normal marketplace installation
```

Enterprise policy can require:

```yaml
marketplace:
  minimum_compliance: aart-cli-native
```

for sensitive environments.

---

# 65. Manifest compilation pipeline

The complete publication path becomes:

```text
              AUTHOR REPOSITORY

 github/
 ├── server.py
 ├── launcher.sh
 ├── src/
 └── aart-cli.yaml
        │
        │ aart-cli build
        ▼
 ┌───────────────────────┐
 │ Manifest Compiler     │
 └──────────┬────────────┘
            │
            ▼
      CanonicalArtifact
      ├── artifact.json
      └── payload/
            │
            │ CI
            ▼
       Policy Validation
            │
            ▼
       Provenance / Audit
            │
            ▼
        aart-cli Registry
            │
            ▼
         Marketplace
            │
            ▼
        aart-cli install
            │
            ▼
    Requirement Inspection
            │
            ▼
        Remediations
            │
            ▼
          Policy
            │
            ▼
       InstallPlan
            │
            ▼
       Effect Engine
            │
            ▼
 Filesystem / Keychain / Harness
```

---

# 66. Scanner vs importer vs compiler

These responsibilities should remain distinct.

## Scanner

Finds explicitly supported manifests.

```text
repo
 ↓
**/aart-cli.yaml
**/aart-cli.json
```

It should not infer artifact semantics from arbitrary repository contents.

## Manifest parser

Validates syntax and produces an authoring-domain representation.

## Compiler

Converts the authoring representation into the canonical aart-cli artifact model.

## Importer

Converts a foreign standard into the canonical model.

Examples:

```text
Agent Skills
MCP Registry server.json
Cursor rules
AGENTS.md
```

This yields:

```text
aart-cli manifest ───────► compiler ──┐
                                  │
Foreign format ──────► importer ──┼──► CanonicalArtifact
                                  │
Native registry pkg ──────────────┘
```

---

# 67. aart-cli effect engine is predefined and finite

The manifest should select from capabilities understood by aart-cli.

It should not define new effect implementations.

Conceptually:

```text
aart-cli.yaml
    ↓
declarations
    ↓
aart-cli compiler
    ↓
predefined ADTs
    ↓
planner
    ↓
predefined effects
    ↓
interpreters
```

For example:

```python
type InstallEffect = (
    CopyTree
    | WriteFile
    | MergeStructuredConfig
    | CreateSymlink
    | EnsureExecutable
    | ConfigureHarness
    | RegisterStdioServer
    | StoreCredential
    | ReplaceCredential
    | DeleteCredential
)
```

New effect types are introduced by new aart-cli versions, reviewed as public tool behavior, rather than injected by artifact manifests.

This is essential for enterprise auditability.

---

# 68. Manifest declares intent; aart-cli chooses implementation

A manifest might say:

```yaml
credentials:
  - id: github-token
    provider: keychain
    inject:
      env: GITHUB_TOKEN
```

It should not say:

```yaml
commands:
  - security find-generic-password ...
  - export GITHUB_TOKEN=...
```

aart-cli lowers the declaration using platform-specific interpreters.

For example:

```text
CredentialBinding
      │
      ├── macOS
      │     ↓
      │ MacOSKeychainInterpreter
      │
      ├── Linux
      │     ↓
      │ SecretServiceInterpreter
      │
      └── Enterprise
            ↓
        VaultInterpreter
```

This is the core portability mechanism.

---

# 69. Revised target architecture

The cumulative architecture is now:

```text
                        SOURCE REPOSITORY
                              │
                       Manifest Discovery
                              │
                              ▼
                         aart-cli.yaml
                              │
                              ▼
                     Manifest Compiler
                              │
                              ▼
                       Artifact Algebra
                              │
                              ▼
                     Canonical Artifact
                              │
                              ▼
                       aart-cli Registry
                              │
                              ▼
                        Marketplace
                              │
                              ▼
                         aart-cli install
                              │
                              ▼
                    Requirement Algebra
                              │
                              ▼
                    Environment Inspection
                              │
                              ▼
                     Remediation Algebra
                              │
                              ▼
                        Policy Algebra
                              │
                              ▼
                        InstallPlan
                              │
                              ▼
                      TUI / JSON Review
                              │
                              ▼
                         Effect Algebra
                              │
                              ▼
                         Interpreters
                              │
          ┌───────────────────┼──────────────────┐
          ▼                   ▼                  ▼
      Filesystem          Keychain            Harness
                              │
                              ▼
                           Receipt
```

The five algebraic domains remain:

```text
Artifact
Requirement
Remediation
Policy
Effect
```

while the authoring manifest becomes the controlled entry point into that model.

---

# 70. Revised implementation priority

The first vertical slice should now explicitly include manifest authoring and compilation.

## Slice A — author repository

Create a real MCP example:

```text
github/
├── server.py
├── launcher.sh
└── aart-cli.yaml
```

## Slice B — manifest compiler

Implement:

```text
discover manifest
parse
validate
select payload
compile CanonicalArtifact
calculate digest
```

## Slice C — registry promotion

Implement:

```text
validate
policy-check
build
publish immutable snapshot
```

## Slice D — installation

Implement:

```text
resolve artifact
inspect requirements
offer remediations
compose/evaluate policy
produce InstallPlan
review in TUI
execute effects
write receipt
```

## Slice E — credential UX

Implement:

```text
detect missing credential
configure in Keychain
verify
replace
delete
installation-qualified credential actions
```

## Slice F — launcher migration

Support initially:

```text
ExternalScriptLaunch
```

Then add:

```text
PythonLaunch
CredentialBinding
CredentialTransform
```

and migrate popular marketplace MCPs toward `aart-cli Native`.

---

# 71. Final publication contract

The marketplace contract should be simple enough to explain to an internal MCP author:

> Your MCP may be implemented and developed however you want.  
> If you want it distributed through the aart-cli marketplace, add an aart-cli manifest next to the artifact entry point.\
> The manifest declares which files form the artifact, what runtime and credentials it needs, how it is launched, and what compatibility it has.  
> aart-cli validates that declaration, builds a canonical immutable artifact, evaluates enterprise policy, and takes responsibility for installation and configuration.

This preserves developer freedom while standardizing enterprise distribution.

The concise principle is:

```text
Author owns implementation.
Manifest owns declaration.
Registry owns approved identity.
Policy owns permission.
aart-cli owns installation.
```

---

# 72. Registry synchronization model

aart-cli should distinguish two completely different synchronization workflows:

```text
Registry-maintainer synchronization
!=
Consumer registry synchronization
```

They may both involve the word "sync" at an implementation level, but they have different actors, trust boundaries, inputs, and effects.

## 72.1 Registry-maintainer synchronization

Registry maintainers configure a set of source repositories that are eligible for discovery.

Example:

```yaml
sources:
  - id: example-mcp-servers
    repo: git.company/example-mcp-servers
    discovery:
      manifests:
        - "**/aart-cli.yaml"
        - "**/aart-cli.json"

  - id: platform-ai
    repo: git.company/platform-ai
    discovery:
      manifests:
        - "**/aart-cli.yaml"
        - "**/aart-cli.json"
```

A scheduled or manually triggered CI workflow scans those repositories:

```text
configured source repositories
            ↓
checkout source at a concrete commit
            ↓
discover known aart-cli manifests only
            ↓
parse manifests
            ↓
compile CandidateArtifacts
            ↓
compute artifact input digests
            ↓
compare against current registry state
            ↓
prepare registry changes
```

The scanner must not infer artifact boundaries from arbitrary files such as `server.py`, `README.md`, or `launcher.sh`.

The author explicitly opts into aart-cli distribution by adding a supported manifest.

The invariant remains:

```text
No manifest
=
No aart-cli artifact candidate
```

---

# 73. Automated registry update PRs

Discovery of an upstream change must not automatically modify the approved registry.

Instead, registry CI produces an update proposal, preferably as a pull request.

Example:

```text
Registry sync: example-mcp-servers

Added
+ company/mcp/foo@1.0.0

Updated upstream
~ company/mcp/github
  source commit: abc123 -> def456
  artifact digest: aaa... -> bbb...

Unavailable upstream
! company/mcp/legacy
```

The registry PR is the review boundary.

Before it can be merged, CI may run:

```text
manifest validation
canonical artifact compilation
payload boundary validation
digest verification
enterprise policy checks
tests
security checks
compatibility checks
provenance validation
```

The lifecycle is:

```text
UPSTREAM CHANGE
      ↓
AUTOMATED DISCOVERY
      ↓
CANDIDATE ARTIFACT
      ↓
AUTOMATED REGISTRY PR
      ↓
VALIDATION + POLICY + CI
      ↓
HUMAN REVIEW
      ↓
MERGE
      ↓
APPROVED REGISTRY STATE
```

The key invariant is:

```text
Upstream update
!=
Registry approval
```

A new artifact version becomes trusted by that registry only after the registry change has passed the configured approval process.

This creates a clean enterprise trust boundary.

---

# 74. Human approval as promotion

Merging the registry PR should be treated semantically as promotion.

The human reviewer is not merely approving a Git diff.

The merge means:

```text
"We approve this exact artifact snapshot as part of this trust domain."
```

Therefore the registry commit should contain or deterministically identify:

```text
artifact coordinate
artifact version
canonical manifest
canonical payload
artifact digest
source repository
source commit
source manifest path
compiler/importer identity
policy/validation metadata where appropriate
```

This makes Git history itself an auditable record of registry evolution.

---

# 75. Vendored canonical artifact as the default approved form

For approved enterprise registries, aart-cli should default to materializing the complete installable artifact into the registry rather than leaving the registry entry as only a link to an upstream repository.

Example upstream:

```text
example-mcp-servers/
└── github/
    ├── aart-cli.yaml
    ├── server.py
    └── src/
```

Manifest:

```yaml
payload:
  include:
    - server.py
    - src/**
```

Approved registry representation:

```text
registry/
└── artifacts/
    └── mcp/
        └── github/
            └── 1.5.0/
                ├── artifact.json
                └── payload/
                    ├── server.py
                    └── src/
```

The registry does not need to vendor the entire source repository.

It vendors only the deterministic artifact boundary declared by the manifest.

Strong invariant:

```text
If an approved artifact version exists in an aart-cli Registry,
that registry contains everything required to install that artifact version.
```

The final consumer must therefore not depend on the continued availability of the author's repository.

---

# 76. Why approved registries should not be link-only indexes

A link-only registry would produce:

```text
RegistryEntry
    ↓
repo + commit + path
    ↓
consumer install
    ↓
fetch upstream repository
```

This creates undesirable failure modes if the upstream repository is later:

```text
deleted
archived
renamed
moved
made inaccessible
permission-restricted
history-rewritten
partially corrupted
abandoned
```

An artifact could still appear in the marketplace while being impossible to install.

That violates the semantics users naturally expect from an approved registry.

By retaining the canonical payload, an artifact can remain installable even if upstream disappears.

Example:

```text
Upstream status: unavailable
Registry snapshot: healthy
Artifact: company/mcp/foo@1.0.0
Installability: preserved
```

The organization can then deliberately choose whether to:

```text
keep
deprecate
transfer ownership
fork
replace
remove in a later registry revision
```

without immediately breaking existing consumers.

---

# 77. Upstream synchronization and abandoned repositories

Registry scanning should explicitly track upstream health independently from registry artifact health.

Conceptually:

```python
class UpstreamStatus:
    AVAILABLE
    MOVED
    UNAUTHORIZED
    MISSING
    INVALID_MANIFEST
    UNKNOWN
```

This is metadata about the source relationship, not about whether the already-promoted registry artifact is installable.

For example:

```text
company/mcp/legacy@2.1.0

Registry artifact:
  healthy

Upstream:
  missing

Last successful source sync:
  2026-07-14

Action:
  review ownership
```

This distinction is important for maintainability at enterprise scale.

---

# 78. Artifact digest instead of repository commit churn

A source repository commit changing does not necessarily mean an aart-cli artifact changed.

Especially in monorepositories, unrelated files may change constantly.

Therefore registry scanning should compute an `ArtifactInputDigest` from only the inputs that semantically define the artifact.

Conceptually:

```text
aart-cli manifest
+
selected payload files
+
relevant declarative metadata
        ↓
ArtifactInputDigest
```

If:

```text
source commit changed
BUT
ArtifactInputDigest unchanged
```

then the scanner should produce no artifact update.

This prevents noisy registry PRs caused by:

```text
README changes
test-only changes outside the artifact boundary
documentation
another MCP in the same repository
CI configuration
unrelated application code
```

This becomes particularly important when aart-cli scans hundreds of repositories or large monorepositories.

---

# 79. Registry CI at scale

The final developer running `aart-cli` should never be responsible for scanning hundreds of enterprise source repositories.

Source discovery belongs to registry maintenance infrastructure.

A private enterprise registry repository may look like:

```text
enterprise-aart-cli-registry/
├── sources.yaml
├── artifacts/
├── policies/
├── profiles/
└── collections/
```

CI can run:

```text
scheduled trigger
manual trigger
optional repository webhook/event
        ↓
aart-cli registry scan
        ↓
discover candidate changes
        ↓
generate deterministic diff
        ↓
open/update pull request
```

This is a GitOps-oriented operating model.

It scales organizationally because:

- source teams own implementation repositories,
- artifact authors own `aart-cli.yaml`,
- registry automation owns discovery and compilation,
- reviewers own promotion decisions,
- consumers see only approved registry state.

---

# 80. Optional pinned-reference content mode

aart-cli may still support a lighter pinned-reference content mode (§173.9, D-376):

```python
type RegistryContentMode = SelfContained | PinnedReference
```

`PinnedReference` means the registry stores a pinned source reference rather than a durable canonical payload.

This can be useful for:

```text
development registries
experimental artifacts
personal registries
temporary integrations
very large or externally managed artifacts
```

However, `SelfContained` should be the default for approved enterprise marketplaces.

The marketplace can surface the distinction:

```text
company/mcp/github
✓ Self-contained
✓ Reproducible
✓ Upstream-independent
```

versus:

```text
experimental/mcp/foo
⚠ Pinned reference to upstream
⚠ Availability depends on source
```

Policy can restrict the mode:

```yaml
production:
  allowed_content_modes:
    - self-contained
```

The finite policy algebra therefore may include primitives such as:

```text
AllowRegistryContentMode(SelfContained)
ForbidRegistryContentMode(PinnedReference)
```

---

# 81. Registry is not a disposable cache

Vendoring approved artifacts should not be modeled as a cache.

A cache is disposable.

An approved registry snapshot is part of the trust and availability contract.

The conceptual transition is:

```text
external source artifact
        ↓
review / policy / promotion
        ↓
organization-approved immutable snapshot
```

Therefore:

```text
Registry artifact snapshot
!=
download cache
```

It represents an ownership boundary.

---

# 82. Consumer-side registry synchronization

The end-user `aart-cli` has a completely different synchronization responsibility.

The user subscribes to one or more approved registries.

Example:

```yaml
registries:
  - company-core
  - data-platform
  - team-ai
```

Consumer synchronization means:

```text
configured registries
        ↓
fetch latest approved registry snapshots/indexes
        ↓
validate registry identity/digests
        ↓
update local marketplace index
        ↓
compare registry state with local installation state
```

It does not mean:

```text
scan author repositories
discover manifests
compile foreign artifacts
approve upstream changes
```

Those responsibilities remain entirely on the maintainer side.

The architecture therefore has two trust directions:

```text
AUTHOR REPOSITORIES
        ↓
Registry maintenance CI
        ↓
APPROVED REGISTRY
        ↓
consumer registry sync
        ↓
aart-cli CLI
```

A consumer may not even need permission to access the original author repository.

---

# 83. Consumer marketplace and available updates

After consumer registry synchronization, aart-cli compares installed artifact receipts/locks against the approved versions now available in subscribed registries.

Example:

```text
Installed locally:
company/mcp/github@1.4.0

Approved registry:
company/mcp/github@1.5.0
```

Marketplace/TUI can render:

```text
Updates available

PROJECT
company/mcp/github
1.4.0 -> 1.5.0

GLOBAL
company/skill/python-testing
up to date
```

The user can choose:

```text
inspect
update
ignore
pin
defer
```

Strong invariant:

```text
Registry update
!=
Automatic local update
```

Registry synchronization discovers approved availability.

Artifact update is a separate explicit operation.

---

# 84. Project and user installation scopes

Project and user are explicit installation scopes. A user installation is still specific to one
selected harness/profile and concrete user target root; it is not a runtime shared by all harnesses.
A project installation is specific to one project root and one selected harness/profile.

For the same `company/mcp/github` package:

| Target | Installed files | Harness registration |
|---|---|---|
| Tabnine / project | `<project>/.tabnine/agent/aart-cli/mcp/company/github/` | `<project>/.tabnine/agent/settings.json` |
| Claude / user | `<user-home>/.claude/aart-cli/mcp/company/github/` | `<user-home>/.claude.json` |

Each tree contains its own payload, runtime, launcher and ordinary configuration. Its receipt and
exact installed version/digest are recorded under `~/.aart-cli/state/installations/`. No runtime
or ordinary input values live in that central state, and no project-local state mirror is created.
Canonical packages and Registry snapshots are kept under `~/.aart-cli` (§169).

Both installations have independent lifecycle and health. A missing runtime means an existing
recorded installation needs repair; package availability in the object store alone never means it
is installed. Harness configuration targets remain adapter-defined and must match the actual
harness contract; an unsupported target is refused before writing.

# 85. Install target as a first-class domain value

The stable installation owner is:

```text
Registry alias + artifact kind/name + scope + normalized concrete target root + harness/profile
```

For project scope the context identifies the project. For user scope it identifies the selected
user/harness home, including an explicitly configured alternate harness home. Distinct homes or
profiles must not collapse to one installation. Version and package digest belong to the receipt
but do not create a different owner during update.

The planner expands every selected artifact and harness/scope target into an installation before
collecting inputs. Duplicate selection of the same complete owner is deduplicated; a second
harness, project, scope, profile or Registry alias creates a different owner. Four selected harnesses
therefore require four independent configuration sets and four credential sets.

The application lowers each target into owned file effects, one harness registration fragment and
its central receipt. Target selection and identity have the same meaning in TUI, CLI and headless
execution. Scope resolution belongs in the domain/application model, with external harness paths
resolved by the adapter.

---

# 86. End-to-end operating model

The cumulative architecture now has two clearly separated sides.

```text
                         MAINTAINER SIDE

 Source Repo A ─┐
 Source Repo B ─┼─────────────┐
 Source Repo C ─┘             │
                              ▼
                     Registry Scanner
                              │
                     discover manifests
                              │
                              ▼
                      CandidateArtifacts
                              │
                     ArtifactInputDigest
                              │
                       compare state
                              │
                    ┌─────────┴──────────┐
                    │                    │
                unchanged             changed
                    │                    │
                   skip                 ▼
                                 Registry Update PR
                                         │
                         validation / tests / policy
                                         │
                                         ▼
                                    Human Review
                                         │
                                        merge
                                         │
                                         ▼
                              APPROVED REGISTRY
                                         │
─────────────────────────────────────────┼────────────────────────────
                                         │
                                     CONSUMER SIDE
                                         │
                                         ▼
                              aart-cli registry/source sync
                                         │
                                         ▼
                                Local Marketplace View
                                         │
                              compare with local receipts
                                         │
                              ┌──────────┴───────────┐
                              ▼                      ▼
                         new artifact          update available
                              │                      │
                              ▼                      ▼
                           install                 update
                              │                      │
                              └──────────┬───────────┘
                                         ▼
                                  Requirements
                                         ↓
                                   Remediation
                                         ↓
                                      Policy
                                         ↓
                                   InstallPlan
                                         ↓
                                  Review / TUI
                                         ↓
                                      Effects
                                         ↓
                                     Receipts
```

---

# 87. Naming of the two synchronization operations

Because the two workflows are materially different, the CLI should avoid presenting them as one ambiguous `sync`.

Possible maintainer-side vocabulary:

```text
aart-cli registry scan
aart-cli registry discover
aart-cli registry refresh-upstreams
```

Preferred semantic meaning:

```text
registry scan
=
inspect configured source repositories and produce candidate registry changes
```

Possible consumer-side vocabulary:

```text
aart-cli source sync
```

or:

```text
aart-cli registry sync
```

Preferred semantic meaning:

```text
consumer sync
=
retrieve the latest approved state from subscribed registries
```

The exact command names can be finalized later, but the domain distinction must remain explicit.

---

# 88. Revised trust model

The complete trust chain is now:

```text
Artifact Author
    owns implementation
        ↓
aart-cli Manifest
    declares artifact boundary and requirements
        ↓
Registry Scanner
    discovers and compiles candidate
        ↓
Registry CI
    validates candidate
        ↓
Enterprise Policy
    evaluates admissibility
        ↓
Human Reviewer
    approves promotion
        ↓
Registry
    owns approved immutable snapshot
        ↓
Marketplace
    exposes approved catalog
        ↓
Consumer aart-cli
    syncs approved registry state
        ↓
Install Planner
    applies target/user policy
        ↓
User
    approves local mutation
```

This gives two independent approval boundaries:

1. **Registry approval** — should this artifact/version be available in this trust domain?
2. **Consumer approval** — should this artifact/version mutate this particular local environment?

Neither upstream source changes nor registry synchronization bypass either boundary.

---

# 89. Core invariants added by the synchronization design

The following invariants should become explicit architecture and testing targets:

```text
1. Source repository changes never directly mutate an approved registry.

2. Registry discovery is deterministic for:
   source commit + manifest + selected payload.

3. Unrelated monorepo changes do not produce artifact updates.

4. Registry promotion is explicit and auditable.

5. An approved vendored artifact remains installable if its upstream disappears.

6. Consumer installation does not require access to the author repository.

7. Consumer registry sync never scans author repositories.

8. Registry sync never automatically updates locally installed artifacts.

9. Project and global installation states are independent.

10. Every local mutation is represented by an InstallPlan and Receipt.

11. The registry contains only files declared as belonging to the artifact.

12. A referenced artifact is visibly weaker than a vendored artifact
    and may be rejected by policy.

13. Upstream availability and registry artifact health are separate concepts.

14. Human approval of a registry PR is a promotion event, not merely a Git merge.
```

These are strong candidates for property-based and integration testing.

---

# 90. Recommended default operating mode

For the enterprise aart-cli use case, the recommended default is now:

```text
Author repository
    ↓
aart-cli.yaml
    ↓
automated registry discovery
    ↓
candidate compilation
    ↓
automated PR
    ↓
human review + policy checks
    ↓
merge
    ↓
vendored canonical immutable registry artifact
    ↓
consumer registry sync
    ↓
marketplace
    ↓
explicit project/global install or update
```

Referenced artifacts remain an optional escape hatch.

The concise principle is:

```text
Authors publish candidates.
Registry automation discovers.
Humans promote.
Registry preserves.
Consumers synchronize.
Users install and update explicitly.
```

---

# 91. Artifact runtime inputs: secrets vs non-secret configuration

aart-cli must explicitly distinguish confidential runtime inputs from ordinary runtime configuration.

This distinction must exist in the domain model and manifest schema, not only in the TUI.

The artifact author declares:

```text
WHAT input is required
+
HOW the executable accepts it
```

The artifact must not declare where an enterprise credential value physically comes from.

The enterprise/user environment declares:

```text
WHERE a secret comes from
+
WHAT non-secret configuration value should be used
```

aart-cli connects those two sides during installation.

The core rule is:

```text
Artifact declares contract.
Environment declares binding.
aart-cli builds the installation projection.
```

---

# 92. Runtime input algebra

aart-cli should model runtime inputs as at least two separate classes:

```python
type RuntimeInput = SecretInput | ConfigInput
```

## 92.1 SecretInput

Examples:

```text
GitHub token
Jira API token
OAuth client secret
private key password
database password
```

Secrets must never be persisted in:

```text
artifact manifest
canonical registry package
registry metadata
InstallPlan
Receipt
generated launcher source
harness settings
logs
telemetry
CLI JSON output
```

Only a stable secret reference/provider configuration may be persisted.

## 92.2 ConfigInput

Examples:

```text
GitHub URL
Jira URL
username
organization name
project name
tenant ID when non-secret
API base URL
feature flag
region
```

These values are ordinary configuration.

They may be collected interactively during setup and persisted as part of the local aart-cli installation state or generated runtime projection.

They may also be written directly into a generated launcher when policy permits.

---

# 93. The executable contract remains independent from providers

For an MCP whose executable contract is CLI-based:

```text
server.py
  --github-token <secret>
  --github-host <config>
  --username <config>
```

the artifact manifest should describe those process bindings without coupling them to Keychain, Vault, environment variables, or aart-cli itself.

Example authoring manifest:

```yaml
schema: aart-cli.dev/mcp/v1

artifact:
  name: github
  kind: mcp
  version: 1.2.0

transport:
  type: stdio

runtime:
  type: python
  version: ">=3.11"

launch:
  type: python
  entrypoint: server.py

inputs:
  - id: github-token
    kind: secret
    required: true
    inject:
      type: cli-argument
      argument: --github-token

  - id: github-host
    kind: config
    required: true
    inject:
      type: cli-argument
      argument: --github-host

  - id: username
    kind: config
    required: true
    inject:
      type: cli-argument
      argument: --username
```

This manifest says nothing about:

```text
macOS Keychain
1Password
Vault
environment variables
aart-cli credential storage implementation
```

Those belong to deployment/user configuration.

---

# 94. Value source and process binding are separate concepts

aart-cli should not conflate:

```text
where a value comes from
```

with:

```text
how the executable receives the value
```

These are separate axes.

Conceptually:

```python
type InputValueSource = (
    SecretProviderReference | PersistedConfigValue | PromptedValue | PolicyProvidedValue
)

type ProcessBinding = CliArgumentBinding | EnvironmentBinding | FileBinding | StdinBinding
```

Example:

```text
macOS Keychain
      ↓
SecretProviderReference
      ↓
value
      ↓
CliArgumentBinding("--github-token")
      ↓
server.py
```

versus:

```text
persisted local config
      ↓
"https://github.company"
      ↓
CliArgumentBinding("--github-host")
      ↓
server.py
```

This separation is central to keeping artifacts portable.

---

# 95. Setup flow should visibly distinguish secrets from configuration

Interactive setup should present secrets and non-secret configuration as different steps and with different handling guarantees.

Example:

```text
Configure company/mcp/github

Configuration
─────────────
GitHub URL:
> https://github.company

Username:
> michal.filek

Secrets
───────
GitHub token:
Credential provider:
  [x] macOS Keychain
  [ ] Environment
  [ ] Enterprise secret manager
```

The TUI may explain that ordinary configuration can be persisted locally, while secrets are stored only through an approved credential provider.

The two categories should not share the same generic "variables" abstraction in the user interface.

---

# 96. Persisting non-secret configuration

Ordinary configuration belongs inside the owning installation's tree in the harness directory.
It is never stored as a global value in `~/.aart-cli`, Registry metadata or a shared input pool.
Its complete binding key is:

```text
Registry alias + artifact + scope + concrete target root + harness/profile + input_id
```

Example for Tabnine in one project:

```text
<project>/.tabnine/agent/aart-cli/mcp/company/github/
├── payload/
├── runtime/.venv/
├── launch.sh
└── config/
    └── tabnine.conf
```

The ordinary configuration file uses literal `input-id=value` lines, for example:

```text
github-host=https://<instance>
organisation=<org>
```

It contains no secrets. The central receipt records ownership, the file path and digest, and secret
provider references only; it does not duplicate ordinary input values. Configuration remains in
this installation's tree through supported update/repair, and is removed with that installation.

Each new target holds every required value independently. Within one installing operation, one
answer per artifact is copied to each of that artifact's new targets (§172.4, D-413); otherwise
there is no copy-answers action, shared configuration option or cross-target prefill. Remote
and local Registry acquisition use the same rule. A user may enter equal text separately; equality
does not create shared state. Compatible values may survive an update or repair only inside the
same complete installation identity.

---

# 97. Generated launcher may embed non-secret values

When producing a runtime projection, aart-cli may materialize non-secret configuration values directly into the generated launcher.

Example:

```bash
#!/bin/sh
set -eu

GITHUB_TOKEN="$(
  /usr/bin/security find-generic-password \
    -s "company.github" \
    -a "mcp" \
    -w
)"

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

exec python3 \
  "$SCRIPT_DIR/server.py" \
  --github-token "$GITHUB_TOKEN" \
  --github-host "https://github.company" \
  --username "michal.filek"
```

The distinction is deliberate:

```text
GitHub token
→ resolved at runtime from secret provider

GitHub URL
username
→ ordinary values materialized during installation
```

This keeps runtime independent from aart-cli while preventing secrets from being written into generated files.

---

# 98. Generated launcher is an installation projection, not artifact source

The generated launcher is not part of the canonical artifact authored upstream.

It is derived from:

```text
CanonicalArtifact
+
InstallTarget
+
Runtime input bindings
+
Platform
+
Harness
+
EffectivePolicy
```

Conceptually:

```text
Canonical Artifact
       ↓
semantic launch contract
       +
local configuration
       +
credential references
       +
platform lowering
       ↓
Generated Runtime Projection
```

This projection may contain:

```text
payload files
generated launcher
non-secret configured values
harness registration
references to secret providers
```

but never secret values themselves.

---

# 99. Recommended Tabnine projection for stdio MCP

For a project-local Tabnine installation:

```text
project/
└── .tabnine/
    └── agent/
        ├── settings.json
        └── aart-cli/
            └── mcp/
                └── company/
                    └── github/
                        ├── payload/
                        ├── runtime/.venv/
                        ├── config/tabnine.conf
                        └── launch.sh
```

Tabnine settings point to the absolute launcher path and an alias-qualified key. Here `/workspace/project`
is the concrete example project root. The adapter must encode the key unambiguously using the
harness's supported key characters; this example key is illustrative of its ownership:

```json
{
  "mcpServers": {
    "company--github": {
      "command": "/workspace/project/.tabnine/agent/aart-cli/mcp/company/github/launch.sh"
    }
  }
}
```

The runtime chain is:

```text
Tabnine
   ↓ stdio
launch.sh
   ├── resolve secret provider references
   ├── apply credential transforms if needed
   ├── use persisted non-secret configuration
   └── exec server.py with its declared CLI contract
        ↓
MCP stdio
```

aart-cli is not required at runtime.

---

# 100. Runtime independence invariant

A successful aart-cli installation must not require the aart-cli executable during artifact runtime unless the artifact explicitly declares aart-cli itself as a runtime dependency.

Strong invariant:

```text
Successful installation
MUST NOT require `aart-cli` at runtime.
```

Therefore:

```text
aart-cli = installer / compiler / planner / configurator

aart-cli != implicit artifact runtime
```

This invariant applies equally to:

```text
skills
MCP servers
hooks
guidelines
memory
future artifact kinds
```

---

# 101. Secret storage invariant

Secret material must have a stricter lifecycle than ordinary configuration.

The required invariant is:

```text
SecretValue
exists only transiently in:
- interactive secure input
- secret-provider interpreter calls
- process invocation preparation
```

It must not cross into persistent artifact state.

By contrast:

```text
ConfigValue
```

may be persisted and materialized if permitted by policy.

This distinction should be encoded in types so accidental persistence of a `SecretValue` is difficult or impossible.

Possible type sketch:

```python
@dataclass(frozen=True)
class SecretReference:
    input_id: str
    provider: CredentialProviderRef


@dataclass(frozen=True)
class ConfigValue:
    input_id: str
    value: str
```

There should be no persistent domain type such as:

```python
PersistedSecretValue
```

in the normal installation model.

---

# 102. Policy over runtime inputs

Enterprise policy should be able to constrain both classes independently.

Examples:

```text
RequireSecretProvider("macos-keychain")
ForbidSecretProvider("plaintext-file")
ForbidSecretInEnvironment
AllowSecretCliBinding
ForbidSecretCliBinding
RequireSecretStdinBinding

AllowPersistedConfig
ForbidPersistedConfig("username")
RequireConfigValue("github-host", allowed_hosts=[...])
```

This becomes especially useful when the artifact executable contract cannot immediately be changed.

For example, an existing MCP may require:

```text
--github-token SECRET
```

while a stricter future policy may require migration to:

```text
stdin
inherited file descriptor
OS-specific secure channel
```

without changing the abstract `SecretInput` concept.

---

# 103. Security note on secrets passed through CLI

aart-cli may support secret delivery through CLI arguments when that is the executable's existing public contract.

However, this binding has a weaker security profile because command-line arguments can be observable through process inspection on some systems.

Therefore:

```text
SecretInput
+
CliArgumentBinding
```

should be representable but should carry explicit security semantics/risk metadata.

Policy can then allow it temporarily or reject it in stricter environments.

The architecture must not force existing MCP implementations to migrate immediately, but it should leave room for safer bindings later.

---

# 104. Final runtime-input responsibility split

The finalized responsibility boundary is:

```text
ARTIFACT AUTHOR
───────────────
declares:
- required input identifiers
- secret vs non-secret classification
- executable binding
- runtime/entrypoint
- transport


ENTERPRISE / USER CONFIGURATION
───────────────────────────────
declares:
- secret provider/reference
- non-secret values
- policy restrictions
- target harness/scope


aart-cli
────
performs:
- requirement inspection
- interactive setup
- secret-provider configuration
- persistence of non-secret config
- semantic planning
- platform/harness lowering
- launcher generation
- harness configuration
- receipt generation


HARNESS
───────
performs:
- launches generated projection
- communicates via stdio


MCP SERVER
──────────
knows only:
- its executable interface
- its MCP protocol behavior
```

Concise architectural rule:

```text
Artifact declares WHAT it needs
and HOW its executable accepts it.

Environment declares WHERE values come from.

Secrets remain indirect.
Configuration may be materialized.

aart-cli connects the two at install time
and disappears from the runtime path.
```


---

# 105. Python MCP dependency environments

Python-based MCP artifacts should use isolated artifact-owned Python environments by default.

Strong invariant:

```text
1 installed Python MCP
=
1 isolated Python environment
```

An artifact installation must not mutate the user's global Python environment unless the user explicitly requests such behavior and policy permits it.

The installed projection may look like:

```text
.tabnine/agent/aart-cli/mcp/company/github/
├── payload/
│   ├── server.py
│   ├── requirements.txt
│   └── src/
├── runtime/
│   └── .venv/
└── launch.sh
```

This isolates dependency versions between MCP servers and makes update, rollback, uninstall, verification, and ownership significantly simpler.

Runtime environments are private to one installation. Cross-target environment sharing is outside
the current product contract; only immutable canonical package storage may be deduplicated.

---

# 106. Environment creation and dependency installation are installation effects

Creation of an isolated Python environment and installation of its dependencies are installation-time mutations and therefore belong to the Effect Algebra.

The semantic effects should remain implementation-independent:

```python
CreatePythonEnvironment(...)
InstallPythonDependencies(...)
```

rather than leaking package-manager commands into the domain model:

```text
RunPip
RunUv
RunPoetry
```

A typical installation plan may contain:

```text
CopyArtifactPayload
CreatePythonEnvironment
InstallPythonDependencies
ConfigureCredentialReferences
PersistConfigInputs
GenerateRuntimeProjection
ConfigureHarness
WriteReceipt
```

Planning remains pure. The interpreter performs the actual filesystem/process mutations only after review and policy approval.

---

# 107. Runtime requirements, package requirements, and runtime inputs are distinct

The architecture must not collapse all runtime concerns into one generic `requirements` bucket.

For a Python MCP, these are separate concepts:

```text
Python >= 3.11       -> RuntimeRequirement
mcp                  -> PythonPackageRequirement
websockets           -> PythonPackageRequirement
GitHub token         -> SecretInput
GitHub URL            -> ConfigInput
```

Conceptually:

```text
ArtifactRequirements
├── RuntimeRequirements
│   └── Python >= 3.11
├── PackageRequirements
│   ├── mcp
│   └── websockets
├── SecretInputs
│   └── github-token
└── ConfigInputs
    ├── github-url
    └── username
```

Each category has different inspection, remediation, persistence, security, and lowering rules.

---

# 108. Reuse Python ecosystem dependency descriptors

aart-cli should not invent a replacement Python dependency language.

An artifact should point to an existing Python dependency descriptor such as:

```text
requirements.txt
pyproject.toml
poetry.lock
uv.lock
```

For example:

```yaml
runtime:
  type: python
  version: ">=3.11"

python:
  dependencies:
    type: requirements
    path: requirements.txt
```

or:

```yaml
python:
  dependencies:
    type: poetry
    pyproject: pyproject.toml
    lock: poetry.lock
```

or:

```yaml
python:
  dependencies:
    type: uv
    pyproject: pyproject.toml
    lock: uv.lock
```

The relevant descriptor and lock files must be included in the canonical artifact payload so the approved artifact remains installable independently of the source repository.

---

# 109. Dependency specification is not the dependency installer

aart-cli must explicitly separate:

```text
dependency specification
!=
dependency installer
```

For example, `requirements.txt` describes dependency input. It does not require aart-cli to use `pip`; a compatible backend such as `uv` may install the same requirements.

Conceptually:

```python
type PythonDependencySpec = RequirementsFile | PyProjectSpec | PoetryProjectSpec | UvProjectSpec

type PythonDependencyInstaller = PipInstaller | UvInstaller | PoetryInstaller
```

The artifact declares the dependency specification. The aart-cli environment/platform/profile/policy selects a compatible installer.

This keeps artifact metadata portable and prevents package-manager implementation details from leaking into the artifact contract.

---

# 110. Initial Python dependency support

The recommended initial implementation should optimize for simplicity and broad compatibility.

Recommended V1 dependency specifications:

```text
requirements.txt
pyproject.toml
```

Recommended V1 installation backends:

```text
pip
uv
```

Poetry support can be added as an additional dependency specification/backend where artifacts already use `pyproject.toml + poetry.lock`.

aart-cli should not require every artifact to provide multiple equivalent formats such as:

```text
requirements.txt
poetry.lock
uv.lock
```

An artifact chooses one supported dependency contract. aart-cli adapts to that contract.

---

# 111. Package manager availability and remediation

Package-manager availability is an environment capability, not an assumption of the artifact.

For example, an enterprise profile may prefer:

```yaml
python:
  preferred_installer: uv
```

The planner can inspect:

```text
compatible Python available?
uv available?
pip available?
```

If `uv` is preferred but unavailable, available remediations may include:

```text
Install uv
Use pip instead
Cancel
```

The final choices are filtered through platform capabilities and effective policy.

aart-cli itself can retain zero Python runtime dependencies by invoking available system tooling through its effect interpreters rather than importing package-manager libraries.

---

# 112. Dependency resolution and approved registry state

Loose author requirements and an enterprise-approved resolved environment are different concepts.

Example author intent:

```text
mcp>=1.2,<2
websockets>=12,<16
```

A registry promotion process may resolve these to an approved concrete set:

```text
mcp==1.8.0
websockets==15.0.1
...
```

Conceptually:

```text
Author dependency intent
        ↓
Registry candidate build
        ↓
Dependency resolution
        ↓
Validation / policy / security review
        ↓
Approved resolved dependency state
```

Where reproducibility requirements justify it, registry CI should retain lock/resolution metadata with the promoted artifact.

A registry update PR can therefore surface dependency changes such as:

```text
github-mcp 1.4.0 -> 1.5.0

Dependency changes:
~ mcp 1.7.2 -> 1.8.0
~ websockets 14.2 -> 15.0.1
+ new transitive dependency xyz
```

This allows reviewers to understand not only source changes but also runtime dependency changes before promotion.

---

# 113. Generated launcher uses the artifact-owned environment

The generated runtime projection must invoke the Python interpreter belonging to the artifact-owned environment rather than relying on a globally active environment.

For example:

```bash
#!/bin/sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

TOKEN="$(
  /usr/bin/security find-generic-password \
    -s "company.github" \
    -a "mcp" \
    -w
)"

exec "$ROOT/runtime/.venv/bin/python" \
  "$ROOT/payload/server.py" \
  --github-token "$TOKEN" \
  --github-url "https://github.company"
```

This combines the previously established runtime-input rules with isolated dependency management:

```text
runtime/.venv
    -> executable/runtime dependencies

secret provider
    -> confidential runtime inputs

generated launcher constants/local config
    -> non-secret runtime inputs

payload/server.py
    -> artifact executable contract
```

aart-cli is not present in the runtime path after successful installation.

---

# 114. Python MCP installation lifecycle

The resulting Python MCP installation flow is:

```text
CanonicalArtifact
        ↓
Inspect Python runtime requirement
        ↓
Choose compatible Python
        ↓
Copy artifact payload
        ↓
Create artifact-owned isolated environment
        ↓
Select compatible dependency installer
        ↓
Install dependencies from artifact descriptor/lock
        ↓
Configure secret provider references
        ↓
Persist non-secret runtime configuration
        ↓
Generate launcher/runtime projection
        ↓
Configure harness
        ↓
Verify installation
        ↓
Write receipt
```

For the Tabnine stdio case:

```text
Tabnine settings.json
        ↓
launch.sh
        ↓
runtime/.venv/bin/python
        ↓
payload/server.py + CLI inputs
        ↓
MCP stdio
```

---

# 115. Python environment ownership invariant

The ownership rule is per complete installation identity (§85/169). Canonical immutable package
storage may deduplicate content; each target's installed payload copy and runtime are private.

```text
Each installed Python MCP owns:
- its installed payload copy
- its isolated Python environment
- its resolved dependency installation
- its generated runtime projection
- its aart-cli-owned harness configuration fragment
```

Therefore aart-cli can reason precisely about:

```text
install
verify
repair
update
rollback
uninstall
```

without depending on or mutating unrelated global Python state.

Strong invariant:

```text
aart-cli installs artifact dependencies into an artifact-owned isolated runtime by default.
It MUST NOT mutate the user's global language environment unless explicitly requested and permitted by policy.
```

---

# 116. TUI evolution strategy: reuse behavior, refactor boundaries

The existing aart-cli TUI should be evolved rather than rewritten from zero.

The guiding rule is:

```text
reuse behavior and tested interaction patterns
refactor structure and domain boundaries aggressively when the new architecture demands it
```

Reuse is not a commitment to preserve old abstractions. Existing behavior is valuable when it already satisfies the new architecture, especially:

```text
immutable wizard/session state
pure state transitions
one core / two skins
review-before-mutation
headless testability
curses frontend
plain-text fallback
shared application services between CLI and TUI
project/user scopes
source and marketplace workflows
receipts
```

However, old types and modules may be replaced or split when they obscure the new algebraic model. In particular, `WizardStage`, `Request`, marketplace projections, setup flows, credential flows, requirements flows, and the large TUI orchestration module are not compatibility boundaries and may be refactored.

The project should optimize for semantic clarity and composability rather than source-level preservation of the current TUI implementation.

---

# 117. Primary FP/ADT design criterion

The most important design criterion for aart-cli, including the TUI, is:

```text
Can this part be expressed as:
data + pure transformation + explicit effect boundary?
```

If the answer is yes, the implementation should prefer that structure.

Conceptually:

```text
Data
  +
Pure transformation
  +
Explicit effect boundary
  =
Preferred aart-cli design
```

Examples:

```text
Artifact + EnvironmentFacts + EffectivePolicy
    -> pure planning
    -> InstallPlan
    -> effect interpreter

AppState + UiEvent
    -> pure transition
    -> AppState
    -> renderer

RequirementAssessment + Policy
    -> pure remediation selection
    -> RemediationViewModel
    -> TUI
```

This criterion is more important than preserving a current class hierarchy, callback structure, screen implementation, or module boundary.

---

# 118. TUI as an algebraic state machine

The TUI should increasingly model screens and workflows as algebraic data types rather than branching callback trees.

Conceptually:

```python
type Screen = (
    MarketplaceScreen
    | InstalledScreen
    | UpdatesScreen
    | RegistriesScreen
    | CredentialsScreen
    | InstallWizardScreen
    | MaintainerScreen
)
```

An install operation can similarly be represented as:

```python
type InstallStage = (
    SelectTarget
    | InspectRequirements
    | ConfigureInputs
    | ConfigureSecrets
    | SelectRemediations
    | ReviewPlan
    | ApplyPlan
)
```

The preferred transition shape is:

```python
def transition(state: AppState, event: UiEvent) -> AppState: ...
```

or, where commands/effects must be emitted:

```python
def transition(state: AppState, event: UiEvent) -> tuple[AppState, tuple[UiCommand, ...]]: ...
```

The transition itself should remain pure. Commands are interpreted at the edge.

The conceptual model is:

```text
State + Event
    ↓
pure transition
    ↓
New State + Commands
    ↓
explicit interpreters
```

not:

```text
UI callback
  -> filesystem
  -> conditional
  -> keychain
  -> subprocess
  -> mutate screen
```

---

# 119. TUI information architecture: dashboard plus operation wizards

The existing wizard model should remain useful for mutating operations, but the top-level TUI should evolve toward a dashboard plus focused operation wizards.

Recommended top-level areas:

```text
Marketplace
Installed
Updates
Registries
Credentials
Settings
Maintainer
```

Browsing and inspection should not require entering a mutation wizard.

A wizard starts when the user selects an operation such as:

```text
Install
Update
Configure
Repair
Replace credential
Uninstall
Promote
```

A Python MCP install flow can be projected as:

```text
Artifact
  ↓
Target
  ↓
Environment inspection
  ↓
Requirements
  ↓
Configuration
  ↓
Credentials
  ↓
Remediations
  ↓
Plan
  ↓
Review
  ↓
Apply
```

This is a UI projection of the domain pipeline, not a separate business workflow.

---

# 120. TUI must render domain decisions, not invent them

The TUI must not contain requirement, remediation, policy, credential, or installation decision logic.

For example, avoid:

```python
if not python_available:
    choices = ["Install Python", "Use another Python"]
```

inside TUI code.

Instead:

```text
Requirement Algebra
      ↓
Environment inspection
      ↓
Remediation Algebra
      ↓
Effective Policy
      ↓
AvailableRemediations
      ↓
TUI projection
```

The same applies to credentials:

```text
SecretInput
    +
CredentialProviderCapabilities
    +
EffectivePolicy
      ↓
CredentialSetupModel
      ↓
TUI / CLI / JSON
```

This makes the interaction layer replaceable and keeps domain behavior identical across human and machine interfaces.

---

# 121. Shared view models across interaction surfaces

The application layer should expose structured immutable outcomes/view models that can be projected by multiple frontends.

Examples:

```text
RequirementAssessment
RemediationOptions
CredentialSetupModel
MarketplaceArtifactView
InstallPlan
PolicyDecision
ReceiptVerification
```

These should be usable by:

```text
curses TUI
plain-text TUI
flag CLI
JSON CLI
future web/GUI frontend
```

The TUI is therefore a projection of application/domain state, not the owner of that state.

---

# 122. TUI modularization

The current TUI implementation should be split as new capabilities are introduced rather than allowing one orchestration module to absorb the entire product.

A possible direction is:

```text
aart_cli/
└── tui/
    ├── app.py
    ├── state.py
    ├── navigation.py
    │
    ├── marketplace.py
    ├── installed.py
    ├── updates.py
    ├── registries.py
    ├── credentials.py
    ├── settings.py
    │
    ├── install/
    │   ├── target.py
    │   ├── requirements.py
    │   ├── configuration.py
    │   ├── credentials.py
    │   ├── remediation.py
    │   └── review.py
    │
    ├── maintainer/
    │   ├── sources.py
    │   ├── candidates.py
    │   ├── promote.py
    │   └── registry.py
    │
    └── rendering/
        ├── layout.py
        ├── controls.py
        └── theme.py
```

This directory layout is illustrative, not normative. The important boundary is:

```text
TUI feature modules
        ↓
Application services / immutable view models
        ↓
Domain
        ↓
explicit effect interpreters
```

TUI modules must not directly become filesystem, subprocess, Git, package-manager, or credential-provider adapters.

---

# 123. Zero-dependency TUI remains the default

aart-cli should retain the value of a zero-runtime-dependency CLI/TUI unless a strong product reason appears to change it.

The existing stdlib/curses approach provides useful enterprise properties:

```text
small trusted runtime surface
simple internal distribution
fewer supply-chain dependencies
offline-friendly installation
predictable bootstrap
```

Libraries such as Textual, Rich, prompt-toolkit, or questionary should not become mandatory merely for presentation improvements.

If a richer frontend is introduced later, it should preferably remain an optional skin over the same application/domain core.

---

# 124. Canonical Project Invariant Catalog

This section is the **single canonical quick-reference list of aart-cli architectural invariants**.

Earlier sections may explain or motivate individual invariants, but this catalog is the authoritative place to review the complete set. When a new invariant is introduced, it should be added here in the same change.

## A. Core architectural invariants

**INV-001 — Public/private boundary**

```text
PUBLIC TOOLING != PRIVATE ENTERPRISE CONTENT
```

Public aart-cli contains reusable mechanisms, schemas, algebras, planners, adapters, interpreters, CLI/TUI, and policy machinery. Enterprise-specific artifact definitions, policy values, profiles, internal endpoints, credential references, and trust decisions live outside the public tool.

**INV-002 — Preferred FP decomposition**

```text
If a component can be expressed as
Data + Pure Transformation + Explicit Effect Boundary,
it should prefer that structure.
```

**INV-003 — Explicit effects**

Environment mutation occurs only through explicit modeled effects interpreted at system boundaries.

**INV-004 — Planning purity**

```text
Planning never mutates the environment.
```

**INV-005 — Planner determinism**

For the same canonical artifact, target, effective policy, and environment facts, planning produces the same semantic plan.

**INV-006 — Forbidden effects do not execute**

Any effect rejected by policy must never reach an effect interpreter.

**INV-007 — Review before mutation**

Mutating human workflows expose the exact semantic plan/review before finalization unless an explicit approved non-interactive policy says otherwise.

**INV-008 — Receipts describe reality**

Receipts record only effects actually performed and sufficient ownership/state information to verify or safely undo them.

**INV-009 — Undo respects ownership**

Undo may reverse only state owned or explicitly captured by the corresponding aart-cli operation; it must not blindly restore unrelated external state.

## B. Artifact and package invariants

**INV-010 — Semantic kind is separate from format/protocol**

Artifact kind, concrete package format, and runtime protocol are separate dimensions.

**INV-011 — Repository is not artifact payload**

```text
Git repository != artifact payload
```

The declared artifact boundary determines canonical payload membership.

**INV-012 — No manifest, no native candidate**

For aart-cli-native repository discovery:

```text
No supported aart-cli manifest = No aart-cli artifact candidate
```

The scanner does not infer native artifacts from `server.py`, README files, launcher names, or other heuristics.

**INV-013 — Canonical payload contains only declared files**

Registry materialization must not accidentally include undeclared repository files such as local secrets, caches, `.env`, unrelated tests, or worktree state.

**INV-014 — Artifact identity is content/provenance stable**

Pinned canonical inputs and deterministic compilation yield stable artifact identity/digest independent of unrelated repository changes.

**INV-015 — Unrelated monorepo changes do not update an artifact**

Artifact update detection is based on the manifest and selected artifact inputs, not every source-repository commit change.

## C. Registry, source, marketplace, and trust invariants

**INV-016 — Upstream update is not registry approval**

```text
Upstream update != Registry approval
```

Source changes create candidates; they do not mutate approved registry state.

**INV-017 — Promotion is explicit and auditable**

Human/authorized approval of a registry change is a semantic promotion event into that trust domain.

**INV-018 — Discovery is deterministic**

For a pinned source commit, manifest, compiler/importer version, and selected payload, registry discovery/compilation is deterministic.

**INV-019 — Approved vendored artifacts are self-contained**

```text
If an approved vendored artifact version exists in an aart-cli Registry,
that registry contains everything required to install that version.
```

**INV-020 — Approved vendored artifacts survive upstream loss**

Deleting, archiving, moving, permission-changing, or rewriting the author repository must not make an already approved vendored artifact uninstallable/installable only via upstream access.

**INV-021 — Consumer installation does not require author-repository access**

Installing an approved vendored registry artifact uses the registry snapshot, not the author repository.

**INV-022 — Consumer registry sync never scans author repositories**

Consumer synchronization fetches approved registry state only.

**INV-023 — Registry sync is not local artifact update**

```text
Registry update != Automatic local update
```

Synchronization discovers approved availability; install/update is a separate operation.

**INV-024 — Registry health and upstream availability are separate**

An upstream may be unavailable while an approved vendored registry artifact remains healthy and installable.

**INV-025 — Referenced mode has weaker trust/availability semantics**

Referenced artifacts must be visibly distinguishable from vendored artifacts and may be rejected by policy.

**INV-026 — Marketplace aggregates; registry approves**

A marketplace is a human-facing projection over configured registries; it does not silently redefine registry trust decisions.

**INV-027 — Ambiguous coordinates are not silently shadowed**

When multiple registries expose conflicting coordinates/versions in an enterprise context, aart-cli should surface ambiguity or require explicit selection rather than silently choosing an unreviewed source.

## D. Policy invariants

**INV-028 — Restrictive policy composition is monotonic**

```text
Adding a more restrictive policy overlay cannot produce a more permissive effective policy.
```

**INV-029 — Allow-lists narrow by intersection**

Security-sensitive allowed sets compose restrictively unless a policy primitive explicitly defines otherwise.

**INV-030 — Deny-lists widen by union**

Security-sensitive forbidden sets accumulate restrictively.

**INV-031 — Required checks accumulate**

Adding policy overlays does not silently drop existing mandatory checks/requirements.

**INV-032 — Policy is evaluated before effects execute**

Semantic intent and, where applicable, lowered primitive effects are policy-checkable before mutation.

## E. Requirements, remediation, and runtime invariants

**INV-033 — Requirements are not effects**

```text
RuntimeRequirement != InstallEffect
```

A requirement states what must be true; an effect states what aart-cli may do to make/change something.

**INV-034 — Requirements and remediations are separate**

An unsatisfied requirement may have zero, one, or many possible remediations. The artifact does not directly dictate arbitrary mutations.

**INV-035 — Remediation choices are capability/policy filtered**

```text
AvailableRemediations
=
PossibleRemediations
∩ PlatformCapabilities
∩ EffectivePolicy
```

**INV-036 — Interactive remediation is optional**

CI/non-interactive mode can disable interactive remediation and fail deterministically on unresolved requirements.

**INV-037 — Distribution and transport are independent**

For MCP and future executable artifacts:

```text
Distribution != Transport
```

For example, stdio does not imply Docker, Python, npm, or any specific package manager.

**INV-038 — MCP does not imply Docker**

Docker/OCI is one optional distribution/runtime mechanism, not an MCP architectural requirement.

**INV-039 — aart-cli is not an implicit runtime**

```text
Successful installation MUST NOT require `aart-cli` at artifact runtime
unless the artifact explicitly declares aart-cli as a runtime dependency.
```

**INV-040 — Harness semantics do not leak into canonical artifact semantics**

Harness-specific paths/configuration are generated projections from canonical artifact semantics plus target context.

## F. Python dependency/runtime invariants

**INV-041 — Python runtime and package dependencies are different requirements**

```text
Python runtime requirement
!= Python package dependency requirement
```

**INV-042 — Dependency specification and installer backend are separate**

```text
requirements.txt / pyproject.toml / lock metadata
!=
pip / uv / Poetry execution strategy
```

**INV-043 — Artifact selects a dependency contract, not every equivalent format**

An MCP need not provide requirements.txt, Poetry lock, and uv lock simultaneously. It provides one supported dependency contract.

**INV-044 — Every Python MCP installation owns its isolated environment**

```text
1 installed Python MCP = 1 artifact-owned isolated Python environment
```

The owner is the complete installation identity (§85/169). No cross-installation runtime sharing
is part of the accepted product.

**INV-045 — No implicit global language mutation**

aart-cli must not mutate the user's global Python/language environment unless explicitly requested and allowed by policy.

**INV-046 — Generated launchers use the artifact-owned runtime**

The runtime projection invokes the interpreter/environment belonging to the installed artifact rather than relying on whichever global environment happens to be active.

**INV-047 — Author dependency intent may differ from approved resolution**

Loose source requirements and registry-approved resolved/locked dependency state are distinct concepts and may be reviewed separately.

## G. Runtime input and credential invariants

**INV-048 — Runtime input kind is explicit**

```text
SecretInput != ConfigInput
```

Confidential and non-confidential runtime inputs have different lifecycle and persistence rules.

**INV-049 — Value source and process binding are independent**

```text
Where a value comes from
!=
How the process receives the value
```

A secret may come from Keychain/Vault and still be bound as a CLI argument, stdin, environment, file, or future secure channel according to the executable contract and policy.

**INV-050 — Executables know their interface, not credential storage**

`server.py` should know its CLI/runtime input contract, not macOS Keychain, aart-cli, Tabnine, or enterprise secret-manager implementation details.

**INV-051 — Secret values never enter persistent aart-cli state**

Secret material must never be persisted in normal aart-cli artifact/configuration state.

**INV-052 — Secret values never appear in plans or observability outputs**

Secret values must never appear in:

```text
InstallPlan
Receipt
registry snapshot
provenance
logs
telemetry
JSON CLI output
error messages
TUI history
```

**INV-053 — Planning does not read secret values**

Planning operates on secret references, provider availability, existence/verification state, and policy—not on the token/password value itself.

**INV-054 — Secret values are transient only**

Secret values may exist only as briefly as needed in secure interactive input, credential-provider calls, or runtime invocation preparation and should be discarded promptly.

**INV-055 — Config values persist locally to their installation under policy**

Non-secret configuration may be stored/materialized within its harness-owned installation tree
when policy permits. Central metadata stores only its path/digest, not the values. This permission
does not extend to secret material, which remains with that owner's provider item.

**INV-056 — Credential replacement does not expose the old secret**

Replacing/rotating a credential must not require reading or displaying the previous value.

**INV-057 — Credential mutations identify their sole installation owner**

Deleting/replacing/rebinding a credential identifies its artifact, harness, scope and concrete
target root. Binding a provider item to a second installation is refused.

## H. Scope and ownership invariants

**INV-058 — Installation scope is explicit**

Project, user/global, and harness-specific targets are explicit installation boundaries rather than inferred side effects.

**INV-059 — Project and global installation states are independent**

Mutating one scope must not silently mutate another.

**INV-060 — Installed artifact ownership is explicit**

An installed Python MCP normally owns its payload, isolated runtime, resolved dependency installation, generated runtime projection, and aart-cli-owned harness configuration fragment.

## I. TUI / interaction invariants

**INV-061 — One core, multiple skins**

CLI, TUI, JSON, and future frontends invoke the same application/domain operations rather than reimplementing business logic.

**INV-062 — TUI is a projection, not a domain owner**

The TUI renders immutable domain/application state and emits user intent. It does not decide requirement satisfaction, remediation availability, policy permission, credential semantics, or filesystem mutations.

**INV-063 — TUI state transitions are pure by default**

```text
AppState + UiEvent -> New AppState (+ explicit commands)
```

should be modeled without hidden I/O.

**INV-064 — TUI does not call effectful infrastructure directly**

TUI feature code must not directly become a filesystem, subprocess, Git, package-manager, network, or secret-provider implementation.

**INV-065 — Browsing is separate from mutation workflows**

Marketplace/installed/update inspection can be navigated without starting an install/update wizard. Wizards represent explicit operations.

**INV-066 — Requirements/remediations shown by TUI come from the core**

The TUI does not synthesize choices such as “install Python” or “use Keychain” from ad-hoc platform conditionals; it displays choices produced by requirement/remediation/capability/policy evaluation.

**INV-067 — Secret and config UX are visibly distinct**

The UI must not collapse secret inputs and non-secret configuration into one generic “variables” concept.

**INV-068 — TUI remains headlessly testable**

Core interaction/state behavior must be testable without a real terminal or live infrastructure.

**INV-069 — Reuse is subordinate to architecture**

Existing TUI behavior and tests should be reused where valuable, but no current class/module/screen structure is protected from refactoring if it conflicts with ADT/FP composability or explicit effect boundaries.

**INV-070 — Zero-runtime-dependency frontend remains the default**

The baseline aart-cli CLI/TUI should not gain mandatory presentation dependencies without a demonstrated product/security/maintenance benefit. Richer frontends may be optional skins.

**INV-071 — Development verification tooling never leaks into runtime**

Property-testing, test, mutation-testing, linting, typing, coverage, and build verification tools such as Hypothesis, pytest, mutmut, ruff, mypy, and coverage MUST remain outside the production/runtime dependency graph. They belong to development and CI only.

**INV-072 — Enterprise forks customize environment, not quality semantics**

Enterprise configuration may replace runners, container images, package indexes, mirrors, publishing endpoints, tool locations, and credential references. It must not silently weaken the semantic quality contract (tests, invariant checks, packaging checks, policy checks) merely by changing repository variables.

**INV-073 — Non-secret CI configuration uses variables; secret values use secrets**

Repository/organization variables may contain endpoints, labels, feature switches, tool paths, matrix values, and the *names* of secrets. Secret values themselves MUST live only in the CI secret store and must never be duplicated into plain variables or committed workflow files.

**INV-074 — Public defaults are self-contained and safe**

An unconfigured public checkout/fork should execute with safe public defaults. Enterprise-only endpoints or assumptions MUST NOT be hardcoded as defaults when they would make an isolated enterprise fork fail or accidentally contact public infrastructure.

**INV-075 — CI configuration is explicit and auditable**

All supported enterprise overrides must be documented as a finite CI configuration contract. Hidden environment-variable conventions, undeclared runner assumptions, or fork-only YAML edits are not part of the supported operating model.

**INV-076 — Workflow orchestration stays thin**

GitHub workflow YAML should primarily select triggers, permissions, environment/profile inputs, and reusable actions/scripts. Quality logic, release validation, and deterministic build logic should live in repository-owned scripts or reusable action boundaries that are runnable/testable outside GitHub Actions when practical.

**INV-077 — One stable required gate represents variable matrices**

Branch protection should depend on one stable aggregate gate name rather than matrix-specific or environment-specific job names. The aggregate gate MUST fail when no valid gate arm ran or when any selected arm failed.

**INV-078 — Enterprise CI must support no-public-egress operation**

The supported enterprise profile must be capable of running without github.com/PyPI/public registry access when equivalent internal mirrors, source mirrors, or prebuilt runner/container capabilities are configured.

**INV-079 — CI backend choices do not redefine project semantics**

Choosing a self-hosted runner, custom image, internal package index, Poetry path, pip mirror, or release transport changes execution infrastructure only. The same source tree and declared project policy should produce the same logical quality/release verdict, modulo explicitly documented platform-specific checks.

**INV-080 — Optional enterprise capabilities fail visibly, never masquerade as passed**

If an enterprise-specific check is intentionally unavailable or disabled, the result must be represented as `skipped`/`not configured` with visible evidence. It MUST NOT be reported as passed.

---

# 125. Invariant testing strategy

The invariant catalog should drive example-based, property-based, integration, and end-to-end tests.

High-value Hypothesis properties include:

```text
INV-004  planning purity
INV-005  planner determinism
INV-006  forbidden effects never reach interpreters
INV-014  artifact identity stability
INV-015  unrelated monorepo changes do not update artifact input digest
INV-018  deterministic registry discovery
INV-028  policy monotonicity
INV-029  allow-list intersection
INV-030  deny-list union
INV-034  requirement/remediation completeness
INV-035  unsupported remediation filtering
INV-045  no accidental global Python mutation
INV-052  secret redaction
INV-053  planning never requires secret values
INV-057  installation-qualified credential mutation
INV-059  project/global scope independence
INV-063  pure TUI state transitions
INV-066  TUI remediation projection matches core output
```

A useful review rule is:

```text
Every architectural change asks:
1. Does it violate an existing INV-*?
2. Does it introduce a new invariant?
3. If yes, was the canonical catalog updated?
4. Can the invariant be encoded as a property/integration test?
```

The invariant catalog should therefore function as both an architectural constitution and a test-design index.


# 126. CI/CD architecture for public and enterprise forks

aart-cli should continue the strong idea already present in the current repository: the public repository contains one canonical workflow implementation, while an enterprise fork adapts execution through GitHub repository/organization settings rather than rewriting workflow YAML.

The governing principle is:

```text
PUBLIC CI SEMANTICS
        +
ENTERPRISE EXECUTION PROFILE
        =
SAME QUALITY CONTRACT IN A DIFFERENT ENVIRONMENT
```

Enterprise forks should therefore parameterize infrastructure, not redefine correctness.

## 126.1 What the current aart-cli CI already gets right

The existing workflow model is a strong base and should be reused conceptually:

- pull-request-only quality gates;
- release work separated from source-quality work;
- repository variables for runner, image, Python matrix, internal package index, Poetry path, reference registry, and publication endpoints;
- variables holding secret *names* while values remain in GitHub Secrets;
- duplicated public/private-image job shells only where GitHub Actions syntax makes a conditional `container.credentials` block impossible;
- reusable local composite actions under `.github/actions/*`;
- a single stable `pr-check` aggregate job suitable for branch protection;
- enterprise documentation describing how a fork should be configured without editing YAML;
- no-public-egress operation via self-hosted runners/custom images/internal indexes/mirrored sources.

These are worth retaining.

## 126.2 What should be improved as aart-cli grows

As the architecture gains registries, policy, artifact compilation, dependency resolution, TUI tests, credential abstractions, and property tests, a flat list of unrelated `AART_CLI_*` variables will become harder to reason about. The solution is not to make GitHub Actions itself more clever. The solution is to define an explicit **CI Profile Contract**.

Conceptually:

```python
@dataclass(frozen=True)
class CiProfile:
    runner: RunnerSpec
    python: PythonCiSpec
    container: ContainerSpec | None
    package_index: PackageIndexSpec
    release: ReleaseDestinationSpec
    reference_registry: RegistryReference | None
    capabilities: CiCapabilities
```

GitHub repository/organization variables are one interpreter for that profile. They are not the domain model.

This mirrors the wider aart-cli architecture:

```text
GitHub vars/secrets
       ↓
CI profile loader
       ↓
validated CiProfile
       ↓
workflow/action/script execution
```

The advantage is that malformed combinations can be rejected deliberately rather than producing mysterious GitHub Actions behavior.

## 126.3 Variables versus secrets

Use variables for visible, non-confidential configuration:

```text
AART_CLI_RUNNER
AART_CLI_CI_IMAGE
AART_CLI_PYTHON
AART_CLI_PYTHON_VERSIONS
AART_CLI_PIP_INDEX_URL
AART_CLI_RELEASE_PYTHON_VERSION
AART_CLI_POETRY
AART_CLI_REFERENCE_REGISTRY_URL
AART_CLI_INDEX_PUBLISH_URL
```

Use variables to point to secret names where dynamic lookup is required:

```text
AART_CLI_IMAGE_USERNAME_SECRET_NAME
AART_CLI_IMAGE_PASSWORD_SECRET_NAME
AART_CLI_PIP_INDEX_CREDENTIALS_SECRET_NAME
AART_CLI_INDEX_PUBLISH_CREDENTIALS_SECRET_NAME
```

The actual credential values remain only in GitHub Secrets.

This is the CI equivalent of aart-cli's runtime rule:

```text
CredentialReference != CredentialValue
```

## 126.4 Parameterize environment, not gates

Good enterprise parameters:

```text
runner labels
container image
Python executable
Python versions
internal package index URL
source mirror URL
release/publish endpoint
reference registry
path to preinstalled tooling
feature capability: pages available / unavailable
secret references
```

Bad parameters:

```text
AART_CLI_SKIP_TESTS=true
AART_CLI_DISABLE_PROPERTY_TESTS=true
AART_CLI_IGNORE_POLICY_FAILURES=true
AART_CLI_MIN_COVERAGE=0
AART_CLI_SKIP_PACKAGING_CHECK=true
```

An enterprise fork may need different infrastructure, but it should not get a repository-variable escape hatch that quietly changes what 'green' means. If an organization genuinely wants a different quality policy, that belongs in an explicit reviewed policy/configuration layer committed to its fork, not a hidden mutable Actions setting.

## 126.5 GitHub Actions should be an orchestration adapter

The project should avoid encoding important build/quality semantics only in YAML. Prefer:

```text
.github/workflows/pr-check.yml
        ↓
.github/actions/quality/action.yml
        ↓
python scripts/quality.py
        ↓
pure/checkable project logic
```

Likewise:

```text
release.yml
   ↓
release composite action
   ↓
scripts/release.py
```

This gives:

- local reproducibility;
- easier testing;
- portability to GitHub Enterprise;
- future portability to another CI system;
- fewer YAML-specific branches;
- a natural explicit-effect boundary.

The same FP criterion applies here:

> Can the CI decision be expressed as data + pure transformation + explicit effect boundary?

For example, release validation should ideally produce a structured result first and only then perform upload/tag/release effects.

## 126.6 Recommended workflow topology

```text
Pull Request
   ↓
quality matrix
   ├─ unit tests
   ├─ integration tests
   ├─ property tests (Hypothesis)
   ├─ static checks
   ├─ mutation-testing budget / scheduled deep gate
   ├─ packaging/build reproducibility checks
   └─ architecture/invariant checks
   ↓
stable aggregate job: pr-check
   ↓
branch protection

main
   ↓
release tag / release event
   ↓
release-specific validation
   ↓
deterministic wheel build
   ↓
artifact publication
   ├─ GitHub release asset
   └─ optional enterprise package index
```

Not every expensive verification must run on every PR. Mutation testing is a good example of a development/CI-only tool that may belong in a scheduled or explicitly triggered deep-quality workflow rather than the fast PR critical path. This does not change the runtime dependency invariant.

## 126.7 CI profile validation

Introduce a small repository-owned validation script, for example:

```text
python scripts/ci_profile.py validate
```

It can check combinations such as:

```text
AART_CLI_CI_IMAGE set
  -> Python setup download must not be required

private image credentials selected
  -> both referenced secrets must resolve

AART_CLI_PYTHON_VERSIONS with a fixed one-Python image
  -> reject misleading multi-version matrix

internal publish URL configured
  -> publishing credential reference required when policy says authenticated

reference registry absent
  -> reconciliation result is explicitly SKIPPED
```

The important point is that validation produces a structured decision before effects run.

## 126.8 Repository variables versus committed enterprise policy

Not everything should be a GitHub variable.

Use repository/organization settings for **deployment/environment facts** that differ between GitHub instances or organizations.

Use committed files for **semantic policy** that deserves code review and history.

For example:

```text
GitHub variable:
  AART_CLI_RUNNER=["self-hosted","linux"]

Committed enterprise policy:
  minimum supported Python = 3.11
  property tests mandatory
  approved release destinations
  arbitrary launcher forbidden
```

This distinction prevents an administrator changing a repository variable from silently changing architectural/security semantics without review.

## 126.9 Organization-level defaults

For enterprise use, prefer organization variables/secrets for the common execution profile:

```text
organization
├── AART_CLI_RUNNER
├── AART_CLI_CI_IMAGE
├── AART_CLI_PIP_INDEX_URL
├── secret references
└── internal publishing endpoints

repository
└── overrides only when genuinely repository-specific
```

This makes a newly created aart-cli registry or enterprise fork work with minimal setup and reduces configuration drift across many registries.

## 126.10 Reusable workflows versus local composite actions

The existing local composite actions are a good choice for sharing implementation between public/private-image job shells. Keep them for step composition.

Reusable workflows can be useful later for organization-wide policy, but aart-cli should not require a central enterprise workflow repository to function. A fork must remain self-contained.

Preferred layering:

```text
workflow YAML              orchestration / permissions / matrix
local composite actions    reusable GitHub-specific step adapter
Python scripts             deterministic build/validation logic
aart-cli domain/application    reusable semantic logic where applicable
```

## 126.11 Fork portability invariant

The desired enterprise experience remains:

```text
1. fork/mirror aart-cli
2. configure organization/repository variables + secrets
3. run the same workflows
4. no source edits required for infrastructure differences
```

Only intentional semantic customization should require committed source/policy changes.

## 126.12 Development tooling boundary

Hypothesis, pytest, mutmut, ruff, mypy, coverage, and similar tools are CI/development dependencies only. Their presence in CI is encouraged; their presence in the installed aart-cli runtime is forbidden by INV-071.

---

# 116. Automated Semantic Versioning and Release Automation

aart-cli release versioning MUST be automatic, driven from reviewed change semantics, and MUST NOT depend on hand-maintained version consistency tests between source files, tags, release metadata, or package metadata.

The release model is based on Semantic Versioning plus Conventional Commits:

```text
fix:        -> PATCH
feat:       -> MINOR
<type>!:    -> MAJOR
BREAKING CHANGE: -> MAJOR
```

The version is a derived release artifact, not a value developers manually keep synchronized across files.

## 116.1 Release automation tool

For aart-cli, the preferred default is **Release Please** rather than Python Semantic Release.

Reasons:

1. aart-cli already uses GitHub Actions as the public CI orchestration layer.
2. Release Please creates and continuously updates a release PR from Conventional Commits.
3. The release PR makes the generated CHANGELOG and proposed SemVer bump reviewable before release.
4. Merging the release PR creates the tag and GitHub Release.
5. Package publication remains a separate explicit release effect, which fits aart-cli's existing CI architecture and enterprise-fork model.
6. Release Please supports Python packages but does not become a runtime dependency of aart-cli.
7. Release automation runs in CI only and therefore does not violate the zero-runtime-dependency invariant.

Python Semantic Release is a good Python-native alternative, but it couples version calculation, source version stamping, changelog generation, tagging, and publication more tightly. aart-cli prefers release orchestration where version decision/release metadata and package publication remain separable effects.

`setuptools-scm` is NOT the primary release automation mechanism. It derives package versions from Git tags and repository state but does not by itself provide Conventional-Commit-driven patch/minor/major release decisions plus release-PR changelog workflow.

## 116.2 Release lifecycle

```text
PR
  |
  | reviewed title / squash commit
  v
Conventional Commit on main
  |
  v
Release Please
  |
  +--> calculate next SemVer
  +--> update CHANGELOG.md
  +--> update package version metadata where required
  +--> maintain Release PR
            |
            | merge
            v
         Git tag
            +
       GitHub Release
            |
            v
      Build exact wheel
            |
            v
       Publish artifact
```

For example:

```text
fix: handle missing registry snapshot
```

from `1.4.2` produces `1.4.3`.

```text
feat: add MCP Python environment installer
```

produces `1.5.0`.

```text
feat!: replace legacy MCP manifest schema
```

or a commit containing a `BREAKING CHANGE:` footer produces `2.0.0`.

## 116.3 Squash merge as the preferred Git model

aart-cli SHOULD use squash merge for normal feature PRs.

The PR title becomes the canonical Conventional Commit entering `main`:

```text
fix(mcp): preserve config values during update
feat(tui): add credential remediation flow
feat(registry)!: replace legacy source identity model
```

This means individual development commits inside a PR do not need to be perfectly curated for release automation. The reviewed PR title is the release-semantic boundary.

CI SHOULD validate PR titles against the Conventional Commits subset accepted by the release model. This is not a version-number consistency test; it validates the semantic input used by release automation.

## 116.4 Version authority

There MUST be one effective version authority.

The next version is derived from:

```text
last released version
+
reviewed Conventional Commits since that release
```

Developers MUST NOT manually bump versions in ordinary feature/fix PRs.

Version metadata files generated or updated by release automation are outputs of the release process, not independent authorities.

The old model:

```text
pyproject version
<-> package __version__
<-> tag
<-> release
<-> tests verifying they all match
```

is rejected as unnecessary synchronization state.

The desired model is:

```text
reviewed change semantics
       +
last release
       |
       v
next SemVer
       |
       +--> release metadata
       +--> package metadata
       +--> tag
       +--> changelog
```

## 116.5 Changelog

`CHANGELOG.md` MUST be generated by release automation from reviewed change semantics.

Developers SHOULD NOT manually maintain normal release entries.

The changelog should primarily expose user-relevant categories such as:

```text
Features
Bug Fixes
Performance
Breaking Changes
```

Pure CI, test, formatting, and internal maintenance changes MAY be excluded from user-facing release notes according to committed release configuration.

Release-note classification is committed project policy and MUST NOT be mutable through GitHub repository variables.

## 116.6 Package publication is separate from release decision

Release automation decides:

```text
what version is next
what changed
when the release is materialized
```

Publication decides:

```text
where the built wheel is sent
```

Therefore enterprise configuration may parameterize publication destinations and credentials without changing SemVer semantics:

```text
public fork       -> GitHub Release / configured public package destination
enterprise fork   -> internal package destination / GitHub Enterprise Release
```

Both use the same versioning algorithm.

## 116.7 Enterprise-fork compatibility

Enterprise forks MUST be able to reuse the same release semantics without editing application code.

Environment-specific release facts may be supplied by repository/org variables and secrets:

```text
runner
container image
package publish endpoint
credential secret references
GitHub Enterprise environment
```

But these MUST NOT redefine:

```text
fix -> PATCH
feat -> MINOR
breaking -> MAJOR
```

or silently disable changelog/release-history generation.

If a company chooses to mirror Release Please or use an approved equivalent tool internally, the replacement MUST preserve the same release contract.

## 116.8 Tooling is CI-only

Release Please, Conventional Commit validators, changelog tooling, or any equivalent release automation tooling are development/CI dependencies only.

They MUST NOT become aart-cli runtime dependencies.

This extends the development-tool isolation invariant already covering Hypothesis, pytest, mutmut, ruff, mypy, and coverage.

## 116.9 Release tests that should disappear

aart-cli SHOULD remove tests whose only purpose is keeping manually duplicated version values synchronized, for example tests asserting that:

```text
source version == tag
source version == hard-coded release value
multiple manually maintained version files agree
```

Release automation itself owns that projection.

Still-valid release verification includes tests/checks that prove actual artifacts are correct, for example:

```text
wheel can be imported
wheel contains expected files only
runtime dependency graph remains valid
release artifact digest is stable where promised
release publication completed successfully
Git tag/release was produced by the release automation flow
```

The distinction is:

```text
DO NOT test duplicated release bookkeeping.
DO test properties of the artifact that was actually produced.
```

# 117. Canonical invariant catalog additions — Release and Versioning

The following invariants are part of the canonical project invariant catalog and should be merged into the single catalog section during the next catalog normalization pass.

### INV-081 — Automatic semantic versioning

Release versions MUST be derived automatically from the last released version and reviewed change semantics.

### INV-082 — Conventional change semantics

aart-cli's default release semantics are `fix -> PATCH`, `feat -> MINOR`, and breaking changes -> `MAJOR`.

### INV-083 — No manual routine version bumps

Normal feature, fix, refactor, test, documentation, or CI PRs MUST NOT manually bump the package version.

### INV-084 — Generated changelog

Normal changelog release entries MUST be generated from reviewed release semantics rather than maintained manually.

### INV-085 — One effective version authority

The project MUST NOT require multiple independently maintained version values plus tests whose only purpose is synchronizing them.

### INV-086 — Release semantics are committed policy

The mapping from reviewed change semantics to SemVer and changelog classification MUST be committed/reviewable configuration, not mutable GitHub Settings state.

### INV-087 — Publication destination does not affect version semantics

Changing from public to enterprise publication infrastructure MUST NOT change the calculated SemVer result for the same release history.

### INV-088 — Release tooling remains outside runtime

Semantic-release/changelog/commit-validation tooling MUST NOT enter aart-cli's runtime dependency graph.

### INV-089 — Release artifact verification targets outputs, not bookkeeping

Release checks SHOULD verify properties of the produced artifact and publication result, not manually duplicated version bookkeeping.

### INV-090 — Reviewed merge boundary drives release semantics

Under the preferred squash-merge workflow, the reviewed PR title/squash commit is the canonical Conventional Commit used by release automation.


## 116.10 Hands-off release mode

aart-cli distinguishes automatic version calculation from release approval.

The default recommended mode is reviewable automation: Release Please maintains the release PR automatically; merging that PR materializes the release.

If the project requires literal hands-off releases, the release PR MAY be auto-merged once the stable required CI gate succeeds and repository policy permits it. In that mode no developer manually edits a version or changelog and no separate release command/button is required.

The trade-off MUST remain explicit: automatic merging increases release frequency and removes the final human batching/release boundary. Therefore hands-off auto-merge is a repository release-policy choice, while SemVer calculation itself remains identical in both modes.

### INV-091 — Version calculation is never manual

Whether release materialization is reviewable or hands-off, the next SemVer and changelog MUST be calculated automatically from reviewed change semantics.


# Release lifecycle architecture

## Canonical release flow

aart-cli uses Conventional Commits semantics, Semantic Versioning, and Release Please to automate version calculation and changelog generation while retaining an explicit release boundary.

```text
feature/fix PR
   ↓
Conventional Commit-compatible PR title
   ↓
PR quality gates
   ↓
mandatory/preferred squash merge to main
   ↓
Release Please updates one release PR
   ↓
release PR passes the same quality contract
   ↓
human merges release PR
   ↓
SemVer tag + GitHub Release + generated CHANGELOG
   ↓
tag triggers artifact release pipeline
   ↓
build wheel
   ↓
verify release artifact
   ↓
clean-environment smoke test
   ↓
publish
```

The release PR is the explicit release boundary. Version calculation and changelog maintenance are automatic; the merge determines when accumulated releasable changes are actually published.

## Normal pull requests

Developers do not manually edit package versions, CHANGELOG entries, tags, or release metadata. The squash commit produced from a PR must carry Conventional Commit semantics, normally through the PR title.

Examples:

```text
fix(tui): preserve selected artifact after refresh
feat(mcp): add isolated Python runtime
feat(registry)!: replace legacy source schema
```

The PR pipeline validates that the title is a valid release-engine input. This is validation of semantic change metadata, not a version synchronization test.

## Main branch history

Squash merging keeps `main` as a clean stream of semantic changes. Release Please interprets this history to determine the next SemVer version.

```text
fix(...)      -> PATCH
feat(...)     -> MINOR
!... / BREAKING CHANGE -> MAJOR
```

`main` is expected to remain releasable. The release PR decides when to publish, not what version number a human wants.

## Release Please ownership

Release Please owns automatic release bookkeeping:

- calculate the next SemVer version;
- maintain a single release PR;
- generate/update CHANGELOG;
- prepare release metadata;
- create the release tag and GitHub Release after the release PR is merged.

A new change merged to `main` updates the existing release PR rather than creating an unrelated manual version-bump workflow.

## Release PR quality gates

The generated release PR passes the normal project quality contract. aart-cli does not introduce a second large release-specific source test suite merely to repeat tests already proven on ordinary pull requests.

The release PR remains reviewable committed state and provides a clear auditable publication boundary.

## Tag-triggered artifact pipeline

The tag created by the release automation triggers a release pipeline whose subject is the distributable artifact rather than the source tree's bookkeeping.

```text
released tag
   ↓
checkout exact release
   ↓
build wheel
   ↓
inspect artifact metadata
   ↓
install into clean environment
   ↓
verify zero runtime dependencies
   ↓
smoke-test CLI
   ↓
publish immutable artifact
```

Useful artifact checks include:

- the wheel can be built successfully;
- wheel metadata describes the intended released version;
- the wheel installs in a clean supported Python environment;
- runtime dependency metadata remains empty unless the architecture explicitly changes;
- `aart-cli --version` works;
- `aart-cli --help` works;
- package contents and integrity are valid.

These tests validate the artifact being published. They do not exist to reconcile several manually maintained copies of a version number.

## Version authority

The desired conceptual model is:

```text
Release Please = decides next SemVer
Git tag         = canonical released version
Python build    = consumes released version
```

There must not be several independently maintained version authorities followed by tests whose only purpose is to prove that the duplicated values happen to agree.

Dynamic packaging/version derivation may be used where it cleanly supports this model, but a second tool must not independently calculate a competing release version.

## Removed legacy release concepts

The target architecture removes the need for:

- routine manual version bumps;
- manual CHANGELOG editing;
- a dedicated `cut-release` workflow;
- routine manual tag creation;
- tests comparing a source version to a tag solely for synchronization;
- tests comparing multiple manually maintained version files;
- release checklists whose purpose is version bookkeeping;
- rerunning the complete source quality suite after tagging the exact tree already proven by PR gates.

Release-specific CI concentrates on the actual release artifact and publication effects.

## CI responsibility split

```text
PR / release PR gates
---------------------
lint
static typing
unit tests
property tests
integration tests
architecture invariant tests
selected E2E tests
Conventional Commit / PR-title validation
policy checks

Tag/release pipeline
--------------------
build wheel
inspect wheel metadata
clean-environment install
zero-runtime-dependency verification
CLI smoke tests
package integrity
publication
```

Mutation testing and unusually expensive property/E2E suites should normally run as scheduled or explicit deep-quality workflows rather than lengthening every pull-request feedback loop.

## Enterprise release portability

Enterprise forks retain the same release semantics while changing execution environment and publication destinations.

```text
PUBLIC
release semantics
   ↓
GitHub-hosted execution
   ↓
GitHub Release / configured public publication

ENTERPRISE
same release semantics
   ↓
enterprise runner / image / mirrors
   ↓
GitHub Enterprise Release / internal package publication
```

Enterprise configuration may change WHERE release work runs, WHERE artifacts are published, and HOW authentication is supplied. It must not silently redefine `fix -> patch`, `feat -> minor`, or `breaking -> major`.

An optional future fully automatic mode may auto-merge a green Release Please PR. This is a release policy choice, not the initial default. The initial default retains the generated release PR as the explicit human-controlled publication boundary.

# Canonical Project Invariant Catalog — v10 additions

The following invariants extend the canonical catalog. They are normative and should be considered together with all earlier `INV-*` entries.

- **INV-092 — Conventional semantic input:** Every change merged into the release history MUST expose machine-readable Conventional Commit semantics sufficient for deterministic release classification.
- **INV-093 — Squash release history:** The normal merge strategy MUST produce a clean semantic change entry on `main`; implementation/WIP commit noise MUST NOT become release classification input by accident.
- **INV-094 — Explicit release boundary:** Automatic version calculation and changelog generation MUST NOT remove the explicit release boundary. By default, merging the generated release PR is that boundary.
- **INV-095 — Single maintained release PR:** Accumulated unreleased changes SHOULD update one generated release PR rather than require routine manual version-bump PRs.
- **INV-096 — Release PR is gated on what it changes:** A generated release PR MUST pass a required quality gate before it can become a release. That gate MUST prove every property the release PR itself can break — the release identity it writes into the tree, the artifact that identity produces, and the documents it rewrites — and MUST NOT repeat the complete source test suite for a tree that has already passed it (INV-097, INV-102). Narrowing the gate is conditional on the release PR changing nothing but release bookkeeping: a release PR that touches anything else MUST be gated as an ordinary change.
- **INV-097 — Tag triggers artifact verification:** Post-release-tag CI MUST primarily verify and publish the distributable artifact rather than repeat the complete source test suite for the same proven tree.
- **INV-098 — Artifact tests test artifacts:** Release checks MUST validate properties of the built artifact (buildability, metadata, clean installation, dependency metadata, smoke execution, integrity) and MUST NOT exist merely to reconcile duplicated manually maintained version values.
- **INV-099 — Release tag is canonical released identity:** Once published, the release tag is the canonical identity of that released source state. Packaging MUST consume that release identity rather than independently inventing a competing version.
- **INV-100 — No competing version engines:** Multiple tools MAY participate in release/build mechanics, but only one release engine may decide the next semantic version for a release.
- **INV-101 — No routine manual release bookkeeping:** Normal development MUST NOT require manual version bumps, manual changelog entries, manual release tags, or a manual cut-release procedure.
- **INV-102 — Release CI has a distinct subject:** PR CI proves source/change quality; release CI proves the built distribution and publication process. The two MAY share primitives but MUST NOT be conflated into redundant pipelines.
- **INV-103 — Expensive verification preserves feedback speed:** Mutation tests and unusually expensive property/integration/E2E suites SHOULD be separated from mandatory fast PR feedback unless evidence shows they fit the required latency budget.
- **INV-104 — Enterprise release semantics are invariant:** Enterprise forks MAY parameterize runners, images, mirrors, endpoints and secret references, but MUST NOT silently change the project's SemVer classification semantics.
- **INV-105 — Fully automatic publication is policy:** Auto-merging a generated release PR MAY be enabled as explicit release policy, but MUST NOT be an accidental consequence of version automation.

---

# 141. Migration strategy: evolve the existing aart-cli repository

The preferred implementation strategy is to refactor the existing aart-cli repository rather than
create a greenfield replacement. This is a controlled architectural migration, not incremental
feature accumulation.

```text
Preserve valuable behaviour.
Reuse tested interaction patterns.
Replace abstractions whose boundaries are wrong.
Do not preserve structure merely because it already exists.
```

The migration follows vertical slices:

```text
existing architecture
→ introduce new domain core
→ route one complete use case through it
→ prove behaviour
→ migrate the next use case
→ remove the superseded legacy path
```

A new repository is justified only if the current implementation proves too coupled to introduce a
clean domain core. The current repository does not presently justify that cost.

## 141.1 Primary refactoring criterion

The primary criterion remains:

```text
Can this part be expressed as:

Data
+
Pure Transformation
+
Explicit Effect Boundary
?
```

Reuse is subordinate to architecture. Reuse behaviour when valuable, reuse code when its boundaries
remain correct, refactor when the new algebra exposes a better boundary, and delete obsolete
abstractions after migration.

## 141.2 Clean domain zone

Conceptually:

```text
aart_cli/
├── domain/
│   ├── artifacts.py
│   ├── requirements.py
│   ├── remediations.py
│   ├── policies.py
│   ├── effects.py
│   ├── plans.py
│   └── receipts.py
├── application/
├── infrastructure/
├── adapters/
└── tui/
```

The exact modules may evolve. The dependency direction may not:

```text
TUI / CLI / JSON
→ Application Services
→ Domain
→ semantic commands/effects
→ Infrastructure interpreters
```

The domain contains immutable values, ADTs, validation and pure transformations. It does not perform
filesystem mutation, subprocess execution, credential-provider access, terminal rendering or
network I/O.

## 141.3 First migration vertical slice

The preferred first serious vertical slice is MCP installation:

```text
aart-cli.yaml
→ Manifest Parser
→ CanonicalArtifact
→ Requirements
→ Environment Inspection
→ Remediations
→ Policy
→ InstallPlan
→ Review
→ Effects
→ Receipt
```

The first concrete scenario should exercise Python MCP + stdio + artifact-owned isolated venv +
standard Python dependency descriptor + ConfigInput + SecretInput + macOS Keychain + generated
launcher + one real harness adapter.

A likely migration sequence is:

```text
MCP → skills → guidelines/rules → memory → hooks
    → registry promotion → marketplace aggregation
```

---

# 142. Live acceptance ecosystem

aart-cli has a verification layer above unit, property, integration and deterministic E2E tests:
a **Git-backed live acceptance ecosystem**.

It models the topology in which aart-cli actually operates:

```text
aart-cli
  │
  ├── artifact source repo A
  │     ├── mcp/github/
  │     │     ├── server.py
  │     │     ├── dependency descriptor
  │     │     └── aart-cli.yaml
  │     └── other artifacts + manifests
  │
  ├── artifact source repo B
  │     └── artifacts + manifests
  │
  ├── synthetic aart-cli registry repo
  │     ├── artifacts/
  │     ├── policies/
  │     ├── profiles/
  │     └── sources.yaml
  │
  └── consumer project repo
        ├── harness configuration
        ├── harness-owned installation trees (receipts under ~/.aart-cli/state)
        └── normal project files
```

The source repositories are ordinary artifact-development repositories. Artifacts can exist and run
without aart-cli; aart-cli integration begins with their manifests.

## 142.1 Live acceptance complements deterministic tests

```text
unit
→ property / Hypothesis
→ integration
→ deterministic E2E
→ Git-backed live acceptance
```

Live acceptance does not replace faster deterministic layers. It catches problems simplified
fixtures often miss: real Git refs/history, repository-relative paths, manifest discovery,
provenance, vendored payloads, registry checkout behaviour, consumer sync, real process execution,
harness projection and state surviving between commands.

## 142.2 Live acceptance lifecycle

Critical cross-repository workflows should be proven through realistic flows:

```text
source repo change
→ registry scan
→ candidate discovery
→ validation / policy
→ promotion boundary
→ canonical artifact materialization
→ approved registry state
→ consumer registry sync
→ marketplace discovery
→ install
→ runtime projection
→ artifact actually starts
→ receipt
→ update
→ verify / rollback / uninstall
```

Not every PR needs every permutation, but every critical cross-repository contract needs realistic
acceptance proof.

## 142.3 Characterization harness for refactoring

Live acceptance also protects the migration:

```text
capture externally observable behaviour
→ encode acceptance scenario
→ refactor/replace internals
→ execute same scenario
→ prove external contract
```

This allows aggressive internal refactoring without treating current implementation structure as a
contract. Intentional public-contract changes update acceptance scenarios together with the reviewed
architecture/product decision.

## 142.4 Test public contracts, not private implementation

Live acceptance should use supported public surfaces:

```text
CLI
manifest schemas
registry schemas
contractual filesystem outputs
receipts
harness projections
runtime/process behaviour
Git-visible registry state
```

It must not depend on private Python functions, incidental module layout or internal ADT
representation merely for convenience.

## 142.5 Repository topology

The exact repository count is not fixed. One possible topology is:

```text
aart-cli
aart-cli-live-source-mcp
aart-cli-live-source-skills
aart-cli-live-registry
aart-cli-live-consumer-tabnine
aart-cli-live-consumer-generic
```

A consolidated live-fixtures repository is also valid if it preserves real Git-backed,
cross-repository semantics. Existing live-acceptance repositories should be reused where their
contracts remain valuable and refactored where the new architecture requires it.

## 142.6 CI placement

Recommended split:

```text
Pull Request
├── unit
├── property
├── integration
├── deterministic E2E
└── selected live-acceptance smoke scenarios

scheduled / deep-quality / release-candidate verification
└── broader live-acceptance matrix
```

The fast feedback path and realistic proof must coexist.

---

# 143. Verification tooling versus runtime

Hypothesis and other verification tooling remain development/CI dependencies only:

```text
pytest
Hypothesis
mutmut
ruff
mypy
coverage
live-acceptance orchestration tooling
```

None of these dependencies may leak into the production runtime dependency graph of `aart-cli`.

---

# 144. Canonical Project Invariant Catalog — additions

These extend the single canonical invariant catalog.

## Migration and architecture

**INV-106 — Behaviour reuse does not imply structural preservation.** Existing behaviour and tested
interaction patterns should be reused when valuable, but abstractions must not be preserved solely
because they already exist.

**INV-107 — Primary functional architecture criterion.** For every substantial subsystem, prefer
`Data + Pure Transformation + Explicit Effect Boundary` whenever the problem can reasonably be
expressed that way.

**INV-108 — Domain independence.** Domain code must not directly perform filesystem mutation,
subprocess execution, credential-provider access, network I/O, terminal rendering or
GitHub-specific operations.

**INV-109 — Explicit effect boundaries.** Externally observable mutations must cross an explicit
effect/interpreter boundary rather than hide inside domain transformations or UI callbacks.

**INV-110 — Vertical-slice migration.** New architecture should be introduced through complete
externally useful flows; migration must not require a flag-day rewrite.

**INV-111 — Legacy structure is deletable.** Once a legacy path is replaced and its required
external behaviour is protected, obsolete implementation should be removed rather than retained as
permanent parallel architecture.

## Live acceptance

**INV-112 — Realistic cross-repository proof.** Every critical workflow spanning artifact sources,
registry state and consumer installation must receive at least one realistic Git-backed acceptance
proof, not solely in-memory or temporary-directory fixtures.

**INV-113 — Live acceptance complements deterministic testing.** Live acceptance must not replace
unit, property, integration or deterministic E2E testing.

**INV-114 — Acceptance protects public contracts.** Live acceptance must primarily depend on
supported public contracts and observable behaviour, not private implementation structure.

**INV-115 — Acceptance fixtures model repositories.** Live source and registry fixtures should
behave as real Git repositories with realistic commits, paths and state transitions rather than
mocks of internal aart-cli functions.

**INV-116 — Characterize before replacement.** Existing critical behaviour should receive
acceptance characterization before its implementation path is replaced, unless that behaviour is
intentionally changing.

**INV-117 — Intentional contract changes are explicit.** When public behaviour intentionally
changes, the acceptance contract must change as part of the reviewed architecture/product change.

**INV-118 — Promotion proves the trust boundary.** Acceptance covering promotion must distinguish
upstream source mutation from approved registry state.

**INV-119 — Consumers use approved registry state.** Consumer live acceptance should install and
update from the synthetic approved registry rather than bypassing it for author repositories,
except for tests explicitly dedicated to referenced/development modes.

**INV-120 — Executable artifacts receive runtime proof.** For executable artifacts such as MCP
servers, at least one relevant live acceptance scenario must prove that the generated runtime
projection actually starts the artifact and satisfies its declared transport contract.

**INV-121 — Verification dependencies never become runtime dependencies.** Unit/property/mutation/
acceptance/lint/type/coverage/CI tooling must not leak into aart-cli's production runtime dependency
graph.

**INV-122 — Acceptance topology is implementation-independent.** Repositories may be split or
consolidated over time; correctness depends on modeled contracts and realistic topology, not fixed
repository names or count.

**INV-123 — Fast feedback and realistic proof coexist.** Mandatory PR verification should retain a
fast feedback path with selected live smoke scenarios; broader expensive acceptance matrices may
run in deep-quality, scheduled or release-candidate workflows.

---

# 145. Multi-artifact installation, Collections and TUI Selection

aart-cli installation is modeled as:

```text
Selection → Resolution → Requirements → Configuration/Credentials
→ Policy → ONE InstallPlan → ONE Review → Effects → Receipt
```

`Selection` may contain one artifact, many directly selected artifacts, one or more Collections, or
a mixture of Collections and direct selections. Single and bulk installation therefore use the
same application/domain pipeline.

A conceptual domain type is:

```python
@dataclass(frozen=True)
class ArtifactSelection:
    artifacts: tuple[ArtifactCoordinate, ...]
    collections: tuple[CollectionCoordinate, ...]
```

The exact representation may evolve; the explicit separation between selection and resolution may
not.

## 145.1 Collections are declarative

A Collection is a versioned set of artifact selectors/constraints, not an imperative installer:

```yaml
name: data-engineer
version: 2.1.0
artifacts:
  - company/mcp/github@^2
  - company/mcp/jira@^3
  - company/skill/code-review@^1
  - company/rule/python@^4
```

Resolution produces exact approved versions and deduplicates identical complete installation
owners while retaining why each is present. Direct selection and multiple Collections may require
the same owner. Different Registry aliases or harness targets remain separate installations.

An exact Collection installation is distinct from using a Collection as a selection template. If a
member is removed before installation, the resulting state is a custom selection derived from the
Collection, not a false claim that the exact Collection is installed.

Ownership provenance must survive installation so removing one Collection never removes an artifact
still required by another Collection or direct installation intent.

## 145.2 One transaction wizard

Bulk installation must not create N independent wizards. Requirements are aggregated across the
resolved set, with equivalent host prerequisites deduplicated while preserving dependants.
Artifact configuration and credential requirements retain their complete installation identity.

Configuration and secrets remain separate stages. Target-qualified input fields and secure prompts
are never deduplicated across installations: one MCP on four harnesses needs four independent
sets of answers. Shared guidance and one review do not imply shared values. One final InstallPlan
describes all artifact
versions, isolated runtimes, configuration, credential mutations, harness projections and file
effects.

Execution should be transactional to the maximum extent supported by the effects. Where perfect
atomicity is impossible, compensation and the final partial state must be explicit and auditable in
the receipt.

# 146. TUI Marketplace multi-selection

Marketplace uses first-class Selection state. `Space` toggles an item; selection persists
predictably while browsing/searching until explicitly cleared, completed or cancelled.

Reference view:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ aart-cli / Marketplace                                      scope: PROJECT       │
├───────────────────┬──────────────────────────────────────────────────────────┤
│ Marketplace       │ Search: _                                                │
│                   │                                                          │
│ › All             │     TYPE         ARTIFACT               VERSION          │
│   MCP             │ [ ] MCP          github-mcp             1.5.0            │
│   Skills          │ [x] MCP          jira-mcp               2.3.0            │
│   Rules           │ [x] Skill        code-review            1.4.2            │
│   Hooks           │ [ ] Rule         python-engineering     3.1.0            │
│   Collections     │                                                          │
│                   │──────────────────────────────────────────────────────────│
│ Registries        │ jira-mcp                                                 │
│ ✓ company-core    │ Jira MCP server                                          │
│ ✓ platform-ai     │ Runtime Python >=3.11 · Transport stdio                  │
│                   │ Status Not installed                                     │
│                   │                                                          │
│                   │ 2 selected                          [ Install (2) ]       │
├───────────────────┴──────────────────────────────────────────────────────────┤
│ ↑↓ navigate  Space select  Enter details  / search  i install  Esc back      │
└──────────────────────────────────────────────────────────────────────────────┘
```

The UX term is **Selection**, not Cart.

A review screen separates user intent from resolution:

```text
Selected for installation

Direct
─────────────────────────────────────
× github-mcp
× jira-mcp
× another-skill

From Python Developer Toolkit
─────────────────────────────────────
  code-review
  python-rules
  testing-skill
  git-hooks

7 unique artifacts

Conflicts:          0
Already installed:  2
Updates:            1
New:                4

                         [ Resolve & Continue ]
```

# 147. Collections in Marketplace and Installed

Collections primarily live under Marketplace:

```text
Marketplace
 ├ All
 ├ MCP
 ├ Skills
 ├ Rules
 ├ Hooks
 └ Collections
```

Reference Collection detail:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ← Marketplace / collections/data-engineer                       v2.1.0       │
├──────────────────────────────────────────────────────────────────────────────┤
│ Data Engineer Toolkit                                                       │
│ Standard tooling for Data Engineering projects                              │
│                                                                              │
│ Includes                                                                     │
│ ✓ github-mcp              MCP          ^2                                    │
│ ✓ jira-mcp                MCP          ^3                                    │
│ ✓ code-review             Skill        ^1                                    │
│ ✓ python-engineering      Rule         ^4                                    │
│                                                                              │
│ Resolved                                                                     │
│ github-mcp                2.4.1                                              │
│ jira-mcp                  3.2.0                                              │
│ code-review               1.7.0                                              │
│ python-engineering        4.1.3                                              │
│                                                                              │
│ 4 artifacts · 2 MCP · 1 Skill · 1 Rule                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ i Install Collection ]    [ Space Select Items ]               Esc Back    │
└──────────────────────────────────────────────────────────────────────────────┘
```

Installed views preserve Collection ownership and show all reasons retaining the same complete
installation. This does not merge different targets or their mutable state.

# 148. Bulk Install Plan reference

In this example, an existing Jira credential belongs to the same already installed target being
reconciled. It is never borrowed from another installation.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Install Plan                                                     PROJECT     │
├──────────────────────────────────────────────────────────────────────────────┤
│ Artifacts                                                                    │
│ + github-mcp              1.5.0                                              │
│ + jira-mcp                2.3.0                                              │
│ + code-review             1.4.2                                              │
│                                                                              │
│ Runtime                                                                      │
│ + github-mcp/.venv                                                           │
│ + jira-mcp/.venv                                                             │
│                                                                              │
│ Credentials                                                                  │
│ + github-token → macOS Keychain                                              │
│ = jira-token   → existing Keychain entry                                     │
│                                                                              │
│ Harness                                                                      │
│ ~ .tabnine/agent/settings.json                                               │
│     + github-mcp                                                             │
│     + jira-mcp                                                               │
│                                                                              │
│ Files                                                                        │
│ + .tabnine/agent/aart-cli/mcp/company/github/**                                          │
│ + .tabnine/agent/aart-cli/mcp/company/jira/**                                            │
│ + .agents/skills/code-review/**                                              │
│                                                                              │
│ 3 artifacts · 17 effects · 2 configs · 1 credential mutation                │
├──────────────────────────────────────────────────────────────────────────────┤
│                    [ Cancel ]             [ Apply 17 effects ]                │
└──────────────────────────────────────────────────────────────────────────────┘
```

# 149. Canonical Project Invariant Catalog — additions

**INV-124 — Single and bulk installation share one model.** Single-artifact, bulk and Collection
install use the same selection/resolution/planning pipeline.

**INV-125 — Collections are declarative.** Collections contain selectors and metadata, not hidden
imperative installation logic.

**INV-126 — Selection differs from resolution.** User intent is represented independently from the
exact resolved artifact set.

**INV-127 — Resolution retains membership provenance.** Deduplication cannot discard why an
artifact is present.

**INV-128 — Exact Collection identity requires exact membership.** Removing Collection members
produces a Collection-derived custom selection.

**INV-129 — Multiple reasons may retain one complete installation.** Direct selection and multiple
Collections may require the same complete installation owner. Removing one reason cannot remove
that installation while another reason remains. Different artifacts, Registry aliases, harnesses,
profiles, scopes or concrete roots never share mutable installation state.

**INV-130 — Bulk installation produces one coherent plan.** A multi-artifact operation has one
InstallPlan and one review boundary.

**INV-131 — Common prerequisites may aggregate; installation inputs do not.** Equivalent host
prerequisites (such as availability of a Python interpreter) may be checked once with dependants
retained. Configuration and credential requirements remain keyed by complete installation identity
plus input id; equal declarations never merge their values, prompts or provider items.

**INV-132 — Config and secrets remain distinct during bulk setup.** Aggregation cannot collapse
ConfigInput and SecretInput into an untyped prompt flow, or collapse inputs across installation
owners. Each selected harness/scope/root has its own answers and provider items.

**INV-133 — Partial execution is explicit and recoverable.** Receipts expose successful, failed and
compensated effects and preserve enough state for safe recovery.

**INV-134 — Marketplace Selection is first-class UI state.** Multi-selection belongs to the TUI
state machine, not imperative widget-local state.

**INV-135 — Selection survives navigation predictably.** Search/filter/detail navigation cannot
silently discard selected intent.

**INV-136 — Collection uninstall respects the ownership graph.** Removal planning computes remaining
ownership before proposing deletion of members.

**INV-137 — Collection resolution obeys registry trust and policy.** Collections cannot bypass
registry approval, provenance, resolution or policy checks.

**INV-138 — One receipt explains the transaction.** A bulk receipt explains selection provenance,
resolved artifacts, effects and final ownership relationships.

---

# 150. Durable refactoring progress and agent handoff

The aart-cli migration will span multiple sessions and may be implemented by different coding agents.
Progress MUST therefore be durable repository state and MUST NOT depend on chat history or one
agent's memory.

The repository should contain one obvious migration entry point, conceptually:

```text
docs/migration/
├── README.md
├── status.md
├── decisions.md
├── next.md
└── slices/
    ├── 001-domain-core.md
    ├── 002-mcp-manifest.md
    ├── 003-mcp-python-runtime.md
    └── ...
```

The exact filenames may evolve.

## 150.1 Canonical status

The status should record: current phase, completed slices, work in progress, active legacy paths,
authoritative new paths, temporary compatibility layers, known failures/deferred tests,
architectural risks and last verified live-acceptance state.

Useful states:

```text
NOT STARTED → IN PROGRESS → IMPLEMENTED → VERIFIED → MIGRATED → LEGACY REMOVED
                         ↘ BLOCKED
```

`MIGRATED` means the supported path is actually routed through the new architecture and required
verification passes; existence of new code alone is insufficient.

## 150.2 Slice records

Each substantial vertical slice should record:

```text
Goal
Relevant architecture sections / INV-* invariants
Legacy path
Target path
Public behaviour to preserve
Intentional behaviour changes
Implementation steps
Required tests
Live acceptance scenarios
Completed work
Remaining work
Temporary compromises
Legacy removal criteria
```

These records do not duplicate architecture. The master document remains architectural truth; slice
records track implementation progress against it.

## 150.3 Agent handoff protocol

At the end of meaningful implementation work, the agent updates durable handoff state so another
agent can determine:

```text
What was the goal?
What changed?
What works now?
What remains?
What should be done next?
What must not be undone?
Which invariants apply?
Which tests prove the state?
What is known to fail?
Where is legacy code still authoritative?
```

Example:

```text
Slice: MCP Python Runtime
State: IN PROGRESS

Completed:
- PythonRuntimeRequirement
- CreatePythonEnvironment effect
- pip interpreter
- unit/property tests

Verified:
- isolated-venv integration test

Remaining:
- uv backend
- generated launcher integration
- live acceptance

Do not remove:
- LegacyMcpInstaller; one harness still uses it

Next:
- route that harness through the new planner

Relevant invariants:
INV-039, INV-044, INV-045, INV-046, INV-107, INV-109, INV-112
```

## 150.4 `next.md` is optimized for resumption

One intentionally short document should identify the safest next bounded unit of work, its
preconditions, steps, prohibitions and definition of done.

This is operational migration state, not permanent architecture.

## 150.5 Four complementary sources of truth

```text
Master architecture
    = why and what must remain true

Migration status / slice records
    = where the transformation currently is

Git commits / PRs
    = exactly what changed

Tests + live acceptance
    = what is actually proven
```

Progress documentation complements Git and tests rather than replacing them.

When implementation materially changes migration state, the progress record should be updated in
the same change series. Tracking exists to make continuation reliable for humans and agents, not to
create fragile bookkeeping bureaucracy.

# 151. Canonical Project Invariant Catalog — handoff additions

**INV-139 — Migration state is durable repository state.** Progress cannot depend on conversation
history, one agent's memory or undocumented local knowledge.

**INV-140 — One obvious resumption entry point.** A new agent must have a canonical location from
which current migration state and next work can be reconstructed.

**INV-141 — Progress reflects repository reality.** A slice cannot be marked migrated merely because
target code exists; the authoritative path and required verification must match the declared state.

**INV-142 — Architecture and progress remain separate.** The master architecture defines
constraints; migration records track progress and reference rather than duplicate those decisions.

**INV-143 — Substantial slices are handoff-capable.** Each substantial slice records enough goal,
state, remaining work, risks, verification and legacy information for another agent to continue.

**INV-144 — Handoffs expose protected constraints.** Applicable invariants and temporary
compatibility constraints must be discoverable by successor agents.

**INV-145 — Implementation and progress advance together.** Material migration-state changes should
update durable progress in the same change series.

**INV-146 — Git, progress and tests have distinct roles.** Git records exact changes, progress
records migration position, architecture records intended constraints, and tests/live acceptance
record verified behaviour.

**INV-147 — Progress tracking cannot weaken quality semantics.** Tracking mechanisms must not become
mutable shortcuts around architecture, quality gates or required verification.

**INV-148 — Next work is explicit.** Active migration should identify the safest next bounded work
unit, its preconditions, completion criteria and important prohibitions.

---

# 152. Progressive disclosure: Fast and Verbose installation UX

aart-cli serves users with different levels of infrastructure knowledge. The installation workflow must
therefore support **progressive disclosure** without creating different installation semantics.

The same domain pipeline and the same InstallPlan are rendered at different levels of detail:

```text
Artifact Selection
       ↓
Resolution
       ↓
Requirements
       ↓
Remediation
       ↓
Policy
       ↓
InstallPlan
       ↓
┌──────────────────────┐
│ Presentation Profile │
├──────────────────────┤
│ Fast / Minimal       │
│ Verbose / Detailed   │
└──────────────────────┘
```

The presentation profile changes **what is shown and when**, never what the planner, policy engine or
effect interpreter is allowed to do.

## 152.1 Fast / Minimal mode

Fast mode is the default candidate for ordinary consumer installation, especially for users such as
Data Scientists who want an artifact to work and do not need infrastructure-level explanation.

The design goal is:

> Ask only for decisions or values that aart-cli cannot safely derive.

Fast mode should hide satisfied requirements, routine dependency-resolution details, low-risk
derived effects and implementation mechanics unless they require user attention.

Example:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Install github-mcp                                                          │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ GitHub URL                                                                   │
│ [ https://github.company                                                   ] │
│                                                                              │
│ GitHub token                                                                 │
│ [ •••••••••••••••••••••••••••                                            ] │
│                                                                              │
│ aart-cli will securely store the token in macOS Keychain.                       │
│                                                                              │
│ ✓ Ready to install                                                          │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ [ Cancel ]                                               [ Install ]          │
└──────────────────────────────────────────────────────────────────────────────┘
```

The user does not need to see, by default:

```text
Python >=3.11 satisfied
resolver selected requirements.txt
pip/uv backend details
CreatePythonEnvironment
MergeStructuredConfig
GenerateLauncher
17 primitive effects
artifact digest
source commit
policy evaluation trace
```

unless one of those facts becomes actionable, risky or fails.

Fast mode may summarize a Collection or bulk install as:

```text
Install Data Engineer Toolkit

4 artifacts
✓ System requirements ready

Needs your input:
- GitHub URL
- GitHub token
- Jira URL

                              [ Continue ]
```

and finally:

```text
Ready to install

4 artifacts
2 MCP servers
1 Skill
1 Rule

Changes:
- configures 2 MCP servers for Tabnine
- creates isolated Python environments
- stores 1 new credential securely

                              [ Install ]
```

This remains review-first. The review is concise rather than absent.

## 152.2 Verbose / Detailed mode

Verbose mode exposes the technical reasoning and generated plan for users who want to understand,
debug or audit the installation.

It may show:

```text
resolved artifact versions
registry provenance
dependency resolution
runtime requirements
requirement assessments
chosen remediations
credential providers and references
policy decisions
runtime/environment backend
generated harness projection
files and configuration mutations
semantic effects
lowered primitive effects
risk classes
receipt/rollback expectations
```

Reference:

```text
Install Plan

Artifacts
+ github-mcp@1.5.0

Resolution
registry: company-core
digest: sha256:91ab...
source commit: 81f3...

Requirements
✓ Python >=3.11
✓ macOS Keychain
! github-token → remediation: StoreInKeychain
? github-host  → prompt

Runtime
+ isolated .venv
+ install dependencies from requirements.txt

Harness
~ .tabnine/agent/settings.json
+ generated launcher

Effects
17 total
12 LocalMutation
 3 ConfigurationMutation
 1 CredentialMutation
 1 ExecutableInstall

                           [ Apply 17 effects ]
```

Verbose mode is especially useful for developers, platform engineers, security review,
troubleshooting and architecture verification.

## 152.3 One workflow, not two products

Fast and Verbose MUST NOT become separate planners or installation implementations.

Conceptually:

```python
plan = plan_installation(selection, environment, policy)

render(plan, presentation=FAST)
render(plan, presentation=VERBOSE)
```

Both views refer to the same immutable plan.

A user may switch from Fast to Verbose before applying without restarting resolution or changing the
meaning of the operation.

For example:

```text
Ready to install

4 artifacts
1 credential will be stored

[ Show details ]                         [ Install ]
```

`Show details` reveals the detailed plan; it does not create another plan.

## 152.4 Attention overrides minimalism

Fast mode is not permission to hide material risk.

aart-cli must surface information when user action or informed approval is required, including:

```text
missing required input
credential creation/replacement/deletion
credential owner and lifecycle impact
policy warning
approval requirement
high-risk execution
arbitrary/external launcher
unexpected network access
conflict
partial-failure recovery
destructive uninstall
ambiguous registry coordinate
unsupported requirement
```

Progressive disclosure hides routine detail, not meaningful risk.

A useful rendering rule is:

```text
Fast view =
required user inputs
+ unresolved problems
+ material risk/approval
+ concise mutation summary
```

Everything else is available through details/Verbose mode.

## 152.5 Technical language adapts to the presentation level

Fast mode should prefer outcome-oriented language:

```text
"Creates an isolated Python environment"
```

rather than:

```text
"Lowering CreatePythonEnvironment through StdlibVenvPip interpreter"
```

and:

```text
"Stores your GitHub token securely in macOS Keychain"
```

rather than exposing internal credential ADT terminology.

Verbose mode may expose precise architecture terminology because its purpose includes explanation
and diagnostics.

This is presentation adaptation, not semantic simplification of the underlying model.

## 152.6 Remembered preference and explicit override

The TUI may remember the user's preferred presentation profile:

```text
Installation detail
● Fast
○ Verbose
```

A command invocation may also explicitly request detail level, conceptually:

```text
aart-cli marketplace install ...
aart-cli marketplace install ... --verbose
```

Exact CLI flags remain an implementation decision.

CI/JSON interfaces are not governed by human-oriented minimal presentation. Machine-readable output
should remain complete, stable and structured while still respecting secret-redaction invariants.

---

# 153. Canonical Project Invariant Catalog — progressive-disclosure additions

**INV-149 — Fast and Verbose share installation semantics.** Presentation detail must not select a
different planner, policy path, resolver or effect semantics.

**INV-150 — Minimal mode asks only necessary questions.** Fast installation should request only
values/decisions aart-cli cannot safely derive plus approvals required by risk or policy.

**INV-151 — Minimalism cannot hide material risk.** Credential mutation, destructive changes,
high-risk execution, policy warnings, conflicts and other meaningful approval information must
remain visible regardless of presentation mode.

**INV-152 — Verbose is a projection of the same plan.** Detailed mode exposes resolution,
requirements, policy and effects from the same immutable InstallPlan used by Fast mode.

**INV-153 — Detail switching does not mutate intent.** Switching between Fast and Verbose before
apply must not silently change selection, resolution or planned effects.

**INV-154 — Routine satisfied detail is progressively disclosed.** Fast mode may hide satisfied
requirements, routine dependency mechanics and low-risk derived effects while retaining an explicit
path to inspect them.

**INV-155 — Fast review remains review-first.** Minimal installation may compress the final review
but cannot eliminate the review boundary required before mutation.

**INV-156 — User-facing language matches audience without weakening types.** Fast-mode copy may use
outcome-oriented terminology while the domain retains precise typed concepts.

**INV-157 — Machine output remains structured and complete.** Human presentation profiles must not
degrade deterministic JSON/CI representations of plans and results, subject to secret-redaction
rules.

**INV-158 — Presentation preference is not policy.** A user's Fast/Verbose preference cannot weaken
enterprise policy, approval requirements, risk thresholds or security constraints.

---

# 154. Registry-provided input guidance and examples

Runtime inputs should be able to carry **human-facing guidance metadata** so users know what value is
expected and where to obtain it.

This is especially important in Fast mode, where the goal is to help a less technical user complete
installation without understanding aart-cli internals.

The registry/canonical artifact metadata may expose guidance such as:

```yaml
inputs:
  - id: github-host
    kind: config
    required: true
    help:
      label: GitHub URL
      example: https://github.company
      description: Base URL of your company GitHub instance.

  - id: github-token
    kind: secret
    required: true
    help:
      label: GitHub token
      description: Personal access token used to authenticate to GitHub.
      obtain_from:
        label: Create a GitHub token
        url: https://github.company/settings/tokens
      format_hint: ghp_...
```

The exact schema may evolve, but guidance metadata should remain separate from runtime semantics.

## 154.1 Fast-mode rendering

Fast mode may render compact hints inline:

```text
GitHub URL
[ ______________________________ ]
  (example: https://github.company)

GitHub token
[ ••••••••••••••••••••••••••• ]
  (create one in GitHub → Settings → Developer settings → Tokens)
```

or, when terminal hyperlink support exists:

```text
GitHub token
[ ••••••••••••••••••••••••••• ]
  (Create token: github.company/settings/tokens)
```

The purpose is to remove the need for the user to leave aart-cli and guess what is required.

## 154.2 Structured format guidance

For non-trivial configuration values, input metadata may describe the expected shape:

```yaml
help:
  label: Azure scope
  description: Resource identifier used by the MCP server.
  example: /subscriptions/<subscription-id>/resourceGroups/<resource-group>
```

Fast mode may render:

```text
Azure scope
[ ______________________________________________ ]

(example:
/subscriptions/<subscription-id>/resourceGroups/<resource-group>)
```

For structured values, guidance may include a short schema-like hint:

```text
Expected format:
<scheme>://<host>[:port]
```

or:

```text
Expected structure:
organization/project
```

This is guidance only. Actual validation belongs to typed input validation/domain logic.

## 154.3 Guidance source and trust boundary

Guidance should come from approved artifact/registry metadata, not from arbitrary runtime network
content fetched during installation.

For enterprise registries, maintainers may enrich or override upstream author guidance during
promotion, for example:

```text
Author:
"Provide a GitHub token"

Enterprise registry:
"Create a Fine-grained PAT at <internal URL>; required permissions: Metadata read,
Pull requests read/write."
```

This allows organizations to provide company-specific onboarding without modifying the executable
artifact.

The resulting guidance becomes part of the reviewed canonical registry state.

## 154.4 Secret safety

Help metadata must never contain actual secret values.

Allowed:

```text
example pattern: ghp_...
token creation URL
required scopes
provider recommendation
```

Forbidden:

```text
real token
credential value from any installation
example copied from a live environment
embedded password
```

A secret `example` should normally be represented as a format/pattern hint rather than a plausible
working credential.

## 154.5 Optional validation guidance

Input metadata may also describe user-facing validation expectations:

```yaml
validation:
  type: url
  allowed_hosts:
    - github.company
```

or:

```yaml
validation:
  pattern: "^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$"
  message: "Use organization/project format."
```

Domain validation remains authoritative. The help text merely explains the rule before the user
fails it.

## 154.6 Collection aggregation

When a Collection requires inputs from several artifacts, Fast mode should aggregate the guidance:

```text
What you will need

GitHub
• URL (example: https://github.company)
• Token (Create token → GitHub settings)

Jira
• URL (example: https://jira.company)
• Token (Create token → Jira profile settings)
```

If multiple artifacts have equivalent input guidance, aart-cli may avoid repeating the explanatory
copy where safe to do so. This presentation deduplication must not merge their values or credential
bindings or their entry fields. Reuse across installations is not offered; even identical input
declarations require separately supplied values for each installation.

---

# 155. Canonical Project Invariant Catalog — input guidance additions

**INV-159 — Input guidance is metadata, not runtime semantics.** Labels, examples, descriptions and
documentation links must not determine how an artifact actually receives a value.

**INV-160 — Guidance is registry-reviewable.** Enterprise-specific help may be enriched during
promotion and becomes part of approved canonical registry state.

**INV-161 — Secret guidance never contains secret values.** Secret help metadata may include format
hints, creation locations and permission requirements, but never usable credentials.

**INV-162 — Validation and explanation are separate.** Help text explains expected input shape;
typed/domain validation remains authoritative.

**INV-163 — Fast mode surfaces actionable input help.** When input guidance exists, minimal
installation should expose enough of it to let a user obtain or construct the required value without
guesswork.

**INV-164 — Collection guidance may aggregate without merging inputs.** Equivalent explanatory
help may be displayed once with each installation owner identified. Every owner's value fields,
secure prompts and provider bindings remain separate; help-text grouping is presentation only.

**INV-165 — Guidance cannot bypass trust policy.** Runtime-fetched or unreviewed remote content must
not silently replace approved registry guidance during installation.

---

# 156. Concrete example values for non-secret inputs

Registry-provided input guidance should support **concrete example values** for ordinary
configuration inputs.

Examples:

```yaml
inputs:
  - id: user-id
    kind: config
    required: true
    help:
      label: User ID
      example: pl847362
      description: Your company user identifier.

  - id: github-host
    kind: config
    required: true
    help:
      label: GitHub URL
      example: https://github.company

  - id: project-key
    kind: config
    required: true
    help:
      label: Jira project key
      example: DATA
```

Fast TUI should prefer compact rendering such as:

```text
User ID
[ ______________________________ ]
  (e.g. pl847362)

GitHub URL
[ ______________________________ ]
  (e.g. https://github.company)

Jira project key
[ ______________________________ ]
  (e.g. DATA)
```

For simple inputs, `e.g.` is preferred over a verbose explanation when an example communicates the
expected value clearly.

The registry may combine:

```text
label
description
example
format hint
obtain-from link
validation hint
```

and the TUI chooses the smallest useful subset according to Fast/Verbose presentation mode.

## 156.1 Secret examples remain different

Secret inputs must not use realistic example values that could be mistaken for credentials.

Preferred:

```text
GitHub token
[ ••••••••••••••••••••••••••• ]
  (format: ghp_…)
  (Create token → GitHub settings)
```

Not preferred:

```text
(e.g. ghp_abcd1234...)
```

because such examples train users to think of secret values as ordinary copyable configuration and
increase the risk of accidental leakage.

---

# 157. Canonical Project Invariant Catalog — concrete-example additions

**INV-166 — Non-secret inputs may expose concrete examples.** Registry guidance may provide realistic
example values such as `pl847362`, `DATA` or `https://github.company` for ordinary configuration.

**INV-167 — Fast mode prefers compact examples where sufficient.** For simple values, concise
`(e.g. ...)` guidance is preferred over unnecessary explanatory text.

**INV-168 — Secret inputs do not use realistic example credentials.** Secret guidance should use
format hints and obtain-from locations rather than plausible credential values.

---

# 158. Desired-state reconciliation and minimal repair

aart-cli is not only an installer. For installed artifacts it acts as a declarative desired-state
manager capable of reconciling the smallest independently repairable part of an installation.

The fundamental model is:

```text
Canonical Artifact
       +
Installation State
       +
Local Configuration
       +
Credential References
       +
Effective Policy
       ↓
DESIRED STATE
       │
       │ compare
       ↓
CURRENT STATE
       │
       ↓
DIFF
       │
       ↓
Minimal MutationPlan
       ↓
Policy
       ↓
Review
       ↓
Effects
       ↓
Re-inspect
       ↓
Receipt
```

Installation is therefore not an indivisible sequential script that must be replayed from the
beginning whenever one component is wrong.

## 158.1 Component-level inspection

An installed artifact can conceptually expose independently inspectable state such as:

```text
Artifact Desired State
│
├── Payload
├── Runtime
│   ├── Python environment
│   └── Dependencies
├── Configuration
│   ├── github-host
│   └── user-id
├── Credentials
│   └── github-token
├── Generated launcher
└── Harness projection
```

Inspection may produce:

```text
                 CURRENT     DESIRED

Payload          ✓           ✓
Python env       ✓           ✓
Dependencies     ✓           ✓
github-host      ✓           ✓
github-token     ✕           ✓
Launcher         ✓           ✓
Tabnine config   ✓           ✓
```

The planner should then propose only the required repair.

## 158.2 Credential-only repair

If the only invalid component is a credential:

```text
github-mcp                              ⚠ Attention

Configuration
──────────────────────────────────────────
✓ GitHub URL       https://github.company
✓ User ID          pl847362
✕ GitHub token     Authentication failed

Runtime
──────────────────────────────────────────
✓ Python environment
✓ Dependencies

Integration
──────────────────────────────────────────
✓ Tabnine configuration

                         [ Repair token ]
```

the user should not re-enter unrelated configuration or repeat installation.

Fast repair:

```text
GitHub token

Current credential is not working.

New token
[ ••••••••••••••••••••••••••• ]

Create token → GitHub settings

[ Cancel ]                  [ Replace ]
```

The resulting plan may contain only:

```text
ReplaceCredential
VerifyCredential
```

followed by re-inspection.

## 158.3 Configuration-only repair

Changing:

```text
github-host = https://github.com
```

to:

```text
github-host = https://github.company
```

must not imply reinstalling the artifact.

A minimal plan might be:

```text
UpdateConfigValue
RegenerateLauncher
```

while leaving payload, Python environment, dependencies and credentials untouched.

## 158.4 Runtime-only repair

If an isolated environment disappears or is corrupted:

```text
github-mcp                          ⚠ Needs repair

✓ Configuration
✓ Credentials
✕ Python environment
✓ Tabnine configuration
```

aart-cli may propose:

```text
CreatePythonEnvironment
InstallPythonDependencies
```

without prompting again for already valid inputs.

## 158.5 Harness-only repair

If the artifact runtime is valid but the harness projection has drifted:

```text
✓ Runtime
✓ Configuration
✓ Credentials
✕ Tabnine integration
```

the repair may lower to only:

```text
ConfigureHarness
```

No unrelated component should be mutated merely because the original installation contained more
effects.

## 158.6 Intents share reconciliation machinery

Conceptually:

```text
Install
Update
Configure
Repair
Credential rotation
Harness reconfiguration
Uninstall
```

are different intents over the same reconciliation architecture:

```text
Intent
   +
Current State
   +
Desired State
      ↓
   Planner
      ↓
Minimal Plan
      ↓
Policy
      ↓
Review
      ↓
Effects
      ↓
New State
      ↓
Receipt
```

The exact desired-state calculation differs by intent, but the project should avoid implementing
each lifecycle operation as an unrelated imperative workflow.

## 158.7 Effect repair capabilities

Not every effect is equally inspectable, idempotent, reversible or independently repairable.

Conceptually, effect/interpreter capabilities may include:

```python
EffectCapabilities(
    inspectable=True,
    idempotent=True,
    reversible=True,
    independently_repairable=True,
)
```

The exact representation may differ, but these properties must be explicit enough for the planner
to avoid pretending that arbitrary operations have safe reconciliation semantics.

Typical examples:

```text
Copy/write owned file       highly inspectable
Create isolated venv        inspectable/re-creatable
Install dependencies        inspectable/re-creatable
Merge harness config        inspectable with ownership metadata
Replace credential          inspectable indirectly; security-sensitive
External script             weak guarantees / potentially non-reversible
Remote mutation             backend-dependent guarantees
```

## 158.8 Repair algorithm

Repair follows the same explicit architecture as installation:

```text
inspect
   ↓
compare current vs desired
   ↓
identify drift
   ↓
determine independently repairable components
   ↓
construct minimal plan
   ↓
policy
   ↓
Fast / Verbose review
   ↓
apply
   ↓
re-inspect
   ↓
receipt
```

A repair is successful only after the relevant state is re-inspected where verification is
supported.

## 158.9 Fast UX consequence

Fast mode should expose the smallest user problem, not the historical installation procedure.

If only a token is wrong:

```text
GitHub token is not working.
[ Repair token ]
```

not:

```text
Reinstall github-mcp
```

If only the harness configuration drifted:

```text
Tabnine configuration changed.
[ Restore configuration ]
```

If only the runtime disappeared:

```text
Python environment is missing.
[ Repair ]
```

This is a major usability requirement for non-platform users.

## 158.10 Verbose reconciliation view

Verbose mode may expose the exact state comparison and minimal plan:

```text
Reconciliation: github-mcp@1.5.0

Component              Current        Desired       Action
────────────────────────────────────────────────────────────
Payload                OK             OK            none
Python environment     OK             OK            none
Dependencies           OK             OK            none
github-host            OK             OK            none
github-token           INVALID        VALID         replace
Launcher               OK             OK            none
Tabnine projection     OK             OK            none

Planned effects:
1. ReplaceCredential(github-token)
2. VerifyCredential(github-token)
```

This makes repair auditable without burdening Fast users.

---

# 159. Installed lifecycle TUI reference decisions

The Installed lifecycle uses health-oriented Fast statuses:

```text
✓ Ready
↑ Update
⚠ Attention
✕ Broken
```

Technical states remain available in Verbose mode.

Installed Artifact Details expose outcome-oriented configuration state, for example:

```text
Configuration
────────────────────────────────
✓ GitHub URL      https://github.company
✓ User ID         pl847362
✓ GitHub token    Configured securely
```

Secret values are never displayed.

`Configure`, `Verify`, `Repair`, `Update` and `Uninstall` are lifecycle intents that reuse the
planning/policy/effect/receipt architecture rather than bypassing it.

Collections aggregate member health. Update supports multi-selection and reuses the same Required
Inputs UX when a new version introduces new inputs.

Failed updates should restore the previous working state where effect capabilities make that
possible, and report the actual result clearly.

Uninstall planning must respect the ownership graph. Removing a Collection removes only members no
longer required by any reason for that exact installation owner. Retained installations carry a
user-facing explanation; other targets remain independent.

**Amended 2026-10-28 by D-496 (§208):** removing an installation deletes its own credential
items with it. An installation that a Collection removal narrows, rather than removes, keeps them.
No other installation can adopt an item.

---

# 160. Canonical Project Invariant Catalog — reconciliation additions

**INV-169 — Installation is not an indivisible script.** An installed artifact must not require
replaying its entire original installation workflow merely to repair one independently repairable
component.

**INV-170 — Current and desired state are explicit concepts.** Lifecycle planning should compare
observable current state with intended state rather than infer repair solely from historical
commands.

**INV-171 — Repair plans are minimal.** A repair should mutate only components required to reconcile
identified drift, subject to dependencies, policy and safety constraints.

**INV-172 — Valid components are preserved.** Repairing one component must not unnecessarily
recreate or reprompt for unrelated valid configuration, credentials, runtimes or payload.

**INV-173 — Lifecycle intents share reconciliation architecture.** Install, update, configure,
repair, credential rotation, harness reconfiguration and uninstall should reuse common
planning/policy/effect/receipt machinery rather than become unrelated imperative systems.

**INV-174 — Repairability is explicit.** The architecture must not assume every effect is
inspectable, idempotent, reversible or independently repairable.

**INV-175 — Unsupported repair semantics are surfaced.** When aart-cli cannot safely inspect or repair a
component independently, it must say so rather than fabricate a minimal-repair guarantee.

**INV-176 — Repair is re-verified when possible.** Successful effect execution alone is not enough
when the relevant component supports post-mutation inspection.

**INV-177 — Fast repair presents the smallest actionable problem.** Minimal UX should ask the user
to repair the failing component rather than force them through the historical installation flow.

**INV-178 — Verbose repair explains the reconciliation diff.** Detailed UX should expose current
state, desired state and planned component-level actions without changing plan semantics.

**INV-179 — Configuration change is not reinstall by default.** Updating ConfigInput should produce
only the dependent mutations required by the new value.

**INV-180 — Credential rotation is independently planable.** Replacing a credential must not
implicitly reinstall unrelated artifact components.

**INV-181 — Runtime repair preserves valid inputs.** Rebuilding an isolated runtime must not require
re-entering valid configuration or credentials unless the executable contract itself changed.

**INV-182 — Harness drift is independently repairable where supported.** Owned harness projections
should be inspectable and restorable without reinstalling the artifact runtime.

**INV-183 — Installed Fast status is outcome-oriented.** Consumer-facing status communicates
Ready/Update/Attention/Broken while detailed technical assessment remains progressively disclosed.

**INV-184 — Failed update prefers restoration of known-good state.** Where effects are reversible or
compensatable, update failure should attempt to restore the previous verified working state and
report whether restoration succeeded.

**INV-185 — Credential cleanup is explicit.** *Amended by §208 (D-496).* An uninstall review
names every credential it deletes. It deletes exactly the items of the installations it removes,
and no other.

**INV-186 — Collection health derives from member state.** Collection status must reflect relevant
member health without hiding which member requires attention.


---

# 161. Accepted Consumer TUI Screen Catalog

Status: **ACCEPTED**. This catalog is the canonical consumer-side product/interaction contract. Exact terminal spacing may evolve, but information hierarchy, safety behavior and navigation semantics must remain intact unless explicitly superseded.

## 161.1 01 Dashboard — ACCEPTED

Persistent application with left navigation and Fast UX by default. Overview emphasizes installed count, updates, attention and recent activity. Global keys include arrows, Enter, Esc, `/`, `?`, `q`. Contextual shortcuts appear only where relevant.

Registry Maintainer Mode is hidden by default and enabled in Settings. With it disabled, maintainer navigation does not appear.

## 161.2 02 Marketplace — ACCEPTED

Marketplace aggregates configured registries. Fast browse avoids runtime/backend/digest/effect jargon. `Space` multi-selects artifacts and Collections; selection count and install action are visible. Filters include Type, Registry and Installation state. Collection preview summarizes contents. `v` switches Fast/Verbose projection without changing selection or semantics.

Reference interaction:

```text
Marketplace
  All / MCP / Skills / Rules / Hooks / Collections

[ ] MCP          github-mcp             1.5.0
[x] MCP          jira-mcp               2.3.0
[x] Skill        code-review            1.4.2
[ ] Collection   Data Scientist Kit     2.0.0

2 selected                                      [ Install (2) ]
```

## 161.3 03 Artifact Details — ACCEPTED

Fast details explain what the artifact does, approval/status and what the user will need. Registry-provided help may include concrete non-secret examples and obtain-from guidance:

```text
github-mcp                                      ✓ Approved
GitHub integration

What it needs
✓ Your system is ready

During installation you will be asked for:
• GitHub URL (e.g. https://github.company)
• User ID (e.g. pl847362)
• GitHub token (Create token → GitHub settings)

[ Select ]  [ Install ]  [ Verbose ]
```

Verbose may expose registry, transport, runtime, compliance, requirements, source/digest, bindings and dependencies.

## 161.4 04 Collection Details / 04A Contents — ACCEPTED

Fast Collection details summarize artifact counts and aggregated prerequisites rather than dumping all members immediately.

```text
Data Scientist Kit                              ✓ Approved

Includes
8 artifacts
3 MCP servers
3 Skills
2 Rules

What you will need
• GitHub URL (e.g. https://github.company)
• User ID (e.g. pl847362)
• GitHub token (Create token → GitHub settings)
• Jira URL (e.g. https://jira.company)
• Jira token (Create token → Jira profile)

[ Install Collection ] [ View Contents ] [ Verbose ]
```

Contents support member selection. Deselecting a member visibly changes the semantic intent:

```text
7 / 8 selected
⚠ Custom selection
This will not install the complete Data Scientist Kit collection.
```

## 161.5 05–11 Fast Installation Flow — ACCEPTED

**Superseded in part by §172 (D-413).** §172 defines screens 05 to 07b: harnesses per artifact,
configuration once per artifact, scope per artifact and harness, and credentials settled before
installation. Where this section disagrees with §172 about those screens, §172 wins. 08 to 11 stand
as written.

Canonical flow before D-413:

```text
Marketplace
   ↓
Review Selection
   ↓
automatic resolution / inspection
   ↓
Required Inputs       [only if needed]
   ↓
Ready to Install      [lists the material changes it agrees to]
   ↓
Installing
   ↓
Success
```

Routine satisfied requirements never become mandatory click-through screens.

### 05 Review Selection

Shows direct selection, Collection-derived selection, unique resolved artifact count, conflicts/new/update summary. Deduplicated artifacts retain ownership/reason information. Verbose may expose version resolution and registry origin.

### 06 Automatic inspection

Resolution, requirements and inspection run without separate confirmation screens when there is no user decision.

### 07 Required Inputs

Fast uses one compact form and registry guidance:

```text
A few things are needed before installation

GitHub
User ID
[ __________________ ]
  (e.g. pl847362)

GitHub URL
[ https://github.company ]
  (e.g. https://github.company)

GitHub token
[ ••••••••••••••••• ]
  Create token → GitHub settings
```

Known valid config is pre-filled only for an existing identical installation owner. Existing
secrets for that owner are shown only as `Configured securely`. New targets have separate fields
and secure prompts, including four separate input sets when four harnesses are selected. No
"same for all" control or cross-installation credential picker is provided. D-413 changes this
for one operation: §172.3 and §172.5 ask once per artifact and write a separate copy for each of
its new installations.

### 08 Remediation — folded into 09

There is no separate Remediation screen. The material changes aart-cli will make to satisfy the
plan's requirements are listed on Ready to Install, the one final review, because confirming it is
what agrees to them. Routine derived changes, such as configuring the chosen harness, are not
listed there in Fast. Example of the list on 09:

```text
AART will make these changes when you confirm:

  - install the python >=3.11 runtime it runs on

  - store the credential it needs securely in macos keychain
```

### 09 Ready to Install

Concise final review summarizes outcomes such as configured MCP servers, isolated environments,
installed skills/rules and securely stored credentials. In every mode it lists each material change
aart-cli will make once confirmed, as an outcome naming its subject (08). A material risk that no
listed change already names is still said in plain words (INV-151). `[v]` (More info) exposes the
same InstallPlan in Verbose mode.

### 10 Installing

Fast shows meaningful progress, not raw logs. Detailed effects remain available on demand.

### 11 Success

Outcome-oriented completion with `View installed`, `View receipt`, `Done`.

## 161.6 12–20 Installed Lifecycle — ACCEPTED

Installed is health-oriented:

```text
✓ Ready
↑ Update
⚠ Attention
✕ Broken
```

### 12 Installed

Lists installation instances with Registry-qualified artifact, version, harness/profile, scope,
concrete target root and health. The same package in Tabnine/project and Claude/user produces two
independently actionable entries; four harness targets produce four entries. Collections may group
entries without collapsing their installation identities.

### 13 Installed Artifact Details

```text
github-mcp                                      ✓ Ready
Version 1.5.0

Used by
• Data Scientist Kit
• Developer Toolkit

Configuration
✓ GitHub URL      https://github.company
✓ User ID         pl847362
✓ GitHub token    Configured securely

[ Configure ] [ Verify ] [ Uninstall ]
```

Configure is reconciliation, not reinstall.

### 14 Installed Collection Details

Collection health aggregates member health and identifies members requiring attention.

### 15–17 Updates

Updates support multi-selection. Major updates receive extra attention. New inputs reuse the same Required Inputs UX. Update review states what changes and what is preserved. Where capabilities allow, failed updates restore previous known-good state.

### 18–19 Uninstall

Uninstall respects ownership. Collection removal deletes only artifacts no longer required/owned elsewhere and explains what is retained and why. An uninstall deletes the removed installations' own credentials, and its review says so (§208).

### 20 Verify / Repair

Verify compares current vs desired state. Repair targets only drifted independently repairable components. Example: a missing Python environment can be rebuilt without re-entering valid config or credentials.

## 161.7 21 Registries — ACCEPTED

Fast registry UI explains availability rather than Git internals:

```text
Registries determine which artifacts are available in Marketplace.

✓ company-core       Connected
  48 artifacts

✓ platform-ai        Connected
  21 artifacts

  community          Not connected

[ Sync ]
```

Registry Details summarize counts and last update. Verbose may expose protocol/source/snapshot/trust metadata.

Add Registry accepts two transports for the same canonical Registry contract:

- **Remote Git** — a credential-free Git URL plus a branch or tag;
- **Local Git checkout** — a normalized absolute repository path plus an explicitly selected local
  branch containing a canonical Registry. Persist that branch with the connection's alias.

Transport does not change Registry authority. Before either connection is saved, aart-cli snapshots the
exact revision, runs the same Registry validation and records the same stable snapshot identity.
Sync repeats that acquisition and validation; a local connection performs no network operation and
resolves the configured local branch to its exact commit, independently of the currently checked-out
branch. Read committed content from that revision, without switching branches, modifying the
worktree, including uncommitted edits or falling back to `HEAD`/the default branch. A missing branch
or invalid successor never replaces the last known valid snapshot.
Both transports contribute equally to Marketplace, resolution and installation.

The local testing flow is ordinary Registry consumption: commit the candidate's canonical package
to a branch in a local Registry repo → Add Registry with alias, local path and branch → synchronize
and install through Marketplace or the normal CLI → run MCP smoke tests on that installation.
This requires neither pushing/merging the branch nor a separate Candidate Test Install process.
CP-26.20/20a do not introduce or require a new direct-from-Source installation workflow (D-350).

Making a local Registry available to that explicitly configured Marketplace does not claim that its
commit was merged into a remote consumer-visible branch. Versions retain their recorded lifecycle,
including `Promoted locally`, while remaining fully selectable through the local Registry alias.
Review evidence and policy determine trust; the local transport alone neither downgrades nor
upgrades it.

A local and remote connection to the same Registry may coexist only under distinct configured
aliases, for example `company` and `company-local`. The alias remains part of every Marketplace
coordinate, receipt and installation identity. If both connections expose the same unqualified
artifact name/version, Marketplace reports ambiguity and requires the alias-qualified coordinate;
neither connection silently shadows the other.

That alias boundary applies to all consumer-owned state, not only Marketplace rows. Runtime input
bindings are namespaced by a stable installation-target identity: Registry alias + artifact kind +
artifact name + normalized destination context (scope and project/user root) + harness/profile,
then by input identifier. Thus `company/mcp/foo` and `company-local/mcp/foo` may hold different
ordinary configuration values and different secret provider references even when the canonical
manifests and input identifiers are identical. The same artifact installed into project A, project
B and a user-level harness likewise owns three independent sets of values and references. An update
within one exact installation target may preserve compatible inputs, but changing the Registry
alias, project/user destination or harness target creates a different owner and never imports them
implicitly. Removing, updating or reconfiguring one owner cannot mutate another owner's values,
references or files. Neither explicit nor implicit sharing of configuration values or credential
provider items is supported. Every new installation receives separately entered inputs (§169).

**Registry sync is not artifact update.** Sync may discover `github-mcp 1.6`; installed `1.5` remains untouched until an explicit update plan is accepted.

## 161.8 22–24 Credentials — ACCEPTED

Credentials is a view of installation-owned provider references and their lifecycle. It never
exposes secret values and never offers a global credential pool or a cross-installation selector.
The global navigation entry may list metadata from several installations, with each owner visible:

```text
GitHub token    Ready      company/mcp/github · Tabnine · project · <project>
GitHub token    Ready      company/mcp/github · Claude  · user    · <user-home>
Jira token     Attention  company/mcp/jira   · Claude  · user    · <user-home>
```

Details identify the one installation and show provider, health and actions:

```text
GitHub token — company/mcp/github
Claude · user · <user-home>
Stored securely: macOS Keychain
Status: Ready

[ Verify ] [ Replace ] [ Delete ]
```

Each action is scoped to that owner. A retained item after uninstall is shown with its former owner
and may be explicitly deleted; it cannot be adopted by another installation. Reference metadata may
be indexed centrally, but neither secret values nor ordinary configuration values become global
state. UI grouping never changes credential ownership.

---

## 161.9 25–27 Activity / Receipts — ACCEPTED

Fast UX calls this area **Activity**. `Receipt` is the technical/audit concept available in details/Verbose.

```text
Today
✓ 14:32  Installed Data Scientist Kit
✓ 12:18  Replaced GitHub token
✓ 10:41  Updated github-mcp  1.5.0 → 1.6.0

Yesterday
↶ 16:02  Restored jira-mcp  2.2.0
```

Receipt details may expose intent, plan digest, registry snapshot, effects and compensation data.

Receipt does **not** imply guaranteed Undo. Rollback/compensation exists only when actual effect semantics and safely retained state support it. Old secret values must not be retained merely to manufacture credential undo.

## 161.10 28 Settings — ACCEPTED

```text
Experience
Detail level
● Fast
○ Verbose

Installation
Default scope
● Project
○ User

Updates
[✓] Show available updates

Advanced
[ ] Registry Maintainer Mode
```

Registry Maintainer Mode OFF hides Sources, Candidates, Promotion, Registry Diff, Validation and Publish from consumer navigation.

## 161.11 29 Doctor / Check System — ACCEPTED

Doctor performs environment-wide inspection and reconciliation:

```text
aart-cli / Check system

✓ github-mcp
✓ database-mcp
⚠ jira-mcp
  Jira token authentication failed.
✓ notebook-review
✓ python-engineering

11 ready
1 needs attention

[ Repair issues ]
```

CLI equivalent:

```text
aart-cli doctor
```

Doctor never means reinstall-all. It inspects installed artifacts, computes drift and constructs minimal repair plans through the same reconciliation engine.

---

# 162. Accepted Consumer Navigation Map

```text
Dashboard
│
├── Marketplace
│   ├── Artifact Details
│   ├── Collection Details
│   │   └── Collection Contents
│   └── Selection
│       └── Install Flow
│           ├── Review Selection
│           ├── Required Inputs       [conditional]
│           ├── Ready to Install
│           ├── Installing
│           └── Success
│
├── Installed
│   ├── Artifact Details
│   │   ├── Configure
│   │   ├── Verify
│   │   ├── Repair
│   │   └── Uninstall
│   └── Collection Details
│       └── Uninstall Collection
│
├── Updates
│   ├── Review Updates
│   └── Update Result
│
├── Registries
│   └── Registry Details
│
├── Credentials
│   └── Credential Details
│       ├── Verify
│       ├── Replace
│       └── Delete
│
├── Activity
│   └── Activity / Receipt Details
│
├── Check system / Doctor
│   └── Repair Issues
│
└── Settings
    └── Registry Maintainer Mode toggle
```

Maintainer navigation is added as a separate advanced area only when Registry Maintainer Mode is enabled.

---

# 163. Canonical Project Invariant Catalog — Consumer TUI additions

**INV-187 — Accepted TUI behavior is a product contract.** Refactoring terminal components must preserve accepted information hierarchy, safety behavior and navigation semantics unless explicitly superseded.

**INV-188 — Registry sync never implies artifact update.** Learning about a newer registry snapshot must not silently mutate installed artifacts.

**INV-189 — Credentials UI is reference-oriented, not value-oriented.** Consumer views may expose provider, health, usage and lifecycle actions but never secret values.

**INV-190 — Each credential reference has one installation owner.** Provider items and bindings
cannot be shared across installations. Credential lifecycle actions identify and affect that owner
only; metadata aggregation in the Credentials view does not permit sharing.

**INV-191 — Fast audit UX is Activity.** Receipt remains the complete technical/audit record while the default consumer projection describes meaningful user actions.

**INV-192 — Receipt does not promise universal undo.** Undo, rollback and compensation are offered only when supported by actual effect semantics and retained safe state.

**INV-193 — Maintainer navigation is opt-in.** Maintainer-only concepts remain hidden until Registry Maintainer Mode is enabled.

**INV-194 — Doctor uses reconciliation, not reinstall-all.** Environment-wide health checking identifies drift and constructs minimal repairs rather than replaying all installation workflows.

**INV-195 — Consumer screens progressively disclose implementation detail.** Fast describes outcomes and required decisions; Verbose exposes technical resolution, provenance, requirements, effects and receipts without changing semantics.

**INV-196 — Known valid inputs are retained only within their owner.** Update, configuration and
repair may retain compatible values already belonging to the same complete installation identity.
Every new installation collects its own inputs, including each target in a bulk install.

**INV-197 — Conditional steps stay conditional.** The Required Inputs screen exists only when the current plan actually requires user input. Remediation is never a stop of its own: its material changes are listed on Ready to Install, which confirms them (§161.5 08).

**INV-198 — Collection UI preserves semantic identity.** Exact Collection installation and custom member selection remain visibly distinct.

---

# 164. Accepted Maintainer TUI Screen Catalog

This section records the canonical Registry Maintainer Mode screens accepted during the screen-by-screen
review. Status: **ACCEPTED**.

Registry Maintainer Mode is explicitly enabled from Settings and is intentionally more technical than the
default consumer experience.

The primary workflow is:

```text
Source Repository
      ↓
Manifest Discovery
      ↓
Candidate
      ↓
Canonicalization
      ↓
Validation
      ↓
Policy
      ↓
Promotion Plan
      ↓
Vendoring / Referencing
      ↓
Registry Diff
      ↓
Registry Validation
      ↓
Commit
      ↓
Canonical Registry Branch
      ↓
Marketplace
```

The TUI must preserve the distinction:

```text
Source ≠ Candidate ≠ Registry ≠ Marketplace
```

## 164.1 Screen 30 — Registry Maintainer Dashboard — ACCEPTED

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ aart-cli / Registry Maintainer                                     Verbose       │
├───────────────────┬──────────────────────────────────────────────────────────┤
│ Dashboard         │ Maintainer overview                                      │
│ Marketplace       │                                                          │
│ Installed         │ Sources                         4                          │
│ Updates           │ Candidates                      7                          │
│ Registries        │ Validation failures             1                          │
│ Credentials       │ Ready for promotion             3                          │
│ Activity          │                                                          │
│ Settings          │ Recent maintainer activity                                  │
│                   │ ✓ Synced example-mcp-servers                              │
│ Maintainer        │ ⚠ github-mcp candidate has validation warning             │
│ › Overview        │ ✓ Promoted jira-mcp 2.3.0                                │
│   Sources         │                                                          │
│   Candidates      │                                                          │
│   Registry        │                                                          │
├───────────────────┴──────────────────────────────────────────────────────────┤
│ Enter open   s sync sources   / search   Esc back                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 164.2 Screens 31–34 — Sources — ACCEPTED

A Source is an authoring/discovery location. It is not itself an approved registry.

Discovery is explicit and manifest-driven:

```text
**/aart-cli.yaml
**/aart-cli.json
```

aart-cli must not discover artifacts by guessing from arbitrary README files, `server.py`, `pyproject`
or repository layout.

Source list:

```text
✓ example-mcp-servers                                          Synced
  git@github.company:ai/example-mcp-servers.git
  branch: main
  12 manifests

✓ data-science-agent-tools                                   Synced
  git@github.company:data/ds-agent-tools.git
  8 manifests

⚠ legacy-agent-tools                                         Attention
  3 manifests · 1 invalid
```

Source Detail includes URL, branch, last successful revision, manifest count and candidate summary.

Source Sync performs fetch/discovery/diff and creates or updates candidates. It never performs
promotion.

## 164.3 Screen 35 — Candidates — ACCEPTED

```text
STATUS        ARTIFACT              VERSION      SOURCE

Ready         github-mcp            1.6.0        example-mcp-servers
Ready         jira-mcp              2.3.0        example-mcp-servers
Changed       database-mcp          1.4.0        data-science-agent-tools
Warning       notebook-review       2.0.0        ds-agent-tools
Invalid       legacy-search-mcp     0.9.0        legacy-agent-tools
```

Candidate lifecycle states include:

```text
New
Changed
Ready
Warning
Invalid
Promoted
Superseded
Rejected
Source Removed
```

## 164.4 Screen 36 — Candidate Details — ACCEPTED

Candidate Detail exposes full technical authoring information: identity, version, kind, source,
manifest path, source revision, artifact input digest, runtime, transport, inputs, dependency
descriptor and validation state.

Example guidance remains visible:

```text
CONFIG user-id
  example: pl847362

SECRET github-token
  obtain from: GitHub Settings → Tokens
```

## 164.5 Screen 37 — Candidate Diff — ACCEPTED

Maintainer review is **semantic diff first, file diff second**.

Example:

```text
github-mcp

Registry      1.5.0
Candidate     1.6.0

Changes
────────────────────────────────────────

~ artifact version
  1.5.0 → 1.6.0

~ requirements.txt
  mcp==1.12.0 → mcp==1.14.0

+ runtime input
  user-id
  CONFIG
  example: pl847362

~ payload/server.py
  modified

No credential semantics changed.

[ View Files ]   [ Validate ]
```

Large raw unified diffs are available on demand rather than being the primary review surface.

## 164.6 Screens 38–40 — Validation and Policy Review — ACCEPTED

Validation is presented as a pipeline of explicit checks, for example:

```text
✓ Manifest schema
✓ Payload boundaries
✓ No symlinks / special files
✓ Runtime descriptor
✓ Dependency descriptor
✓ Input definitions
✓ Secret metadata
✓ Policy
✓ Security checks
✓ Live acceptance
```

Failures include actionable paths and declared/expected values.

Warnings and errors are distinct. Policy determines whether warnings block promotion.

Policy-required manual approval is an explicit candidate state and cannot be hidden as an ordinary
warning.

## 164.7 Screens 41–46 — Promotion, Registry Commit and explicit Push — ACCEPTED

Promotion Review shows source revision, artifact coordinate/version, target registry, validation and
policy status.

Enterprise default promotion mode:

```text
● Vendor canonical payload
○ Reference source revision
```

Promotion creates canonical registry state and provenance but does not automatically push Git
changes.

Registry review remains semantic-first:

```text
+ artifacts/mcp/github-mcp/1.6.0/artifact.json
+ artifacts/mcp/github-mcp/1.6.0/payload/...
~ registry/index.json
~ registry/snapshot.json
```

Registry validation checks schema, identities, digests, provenance, dependency closure, collections,
policy and snapshot reproducibility.

Commit is explicit. aart-cli creates the local registry commit.

**Accepted revision, 2026-09-18: Registry Workspace owns explicit Push.** Push is an action on the
local Registry workspace row on screen 46, not the terminal step of initialization, rebuild or
promotion. Returning to Registry Workspace after any of those workflows — or reopening aart-cli later
— derives the same answer from the current checkout. A connected Registry snapshot row, Candidate
or Source never offers Push.

Registry Workspace presents three distinct facts rather than collapsing them into one status:

- the accepted consumer-visible snapshot and revision read from the Registry's default branch;
- the local workspace snapshot, branch and exact `HEAD` commit;
- publication readiness for that exact local commit.

A local snapshot differing from the accepted snapshot is expected unpublished work, not invalidity.
Push readiness instead requires a clean worktree and index, a named exact `HEAD`, generated Registry
outputs already matching their reproducible build, and every mandatory Registry publication gate
passing over those committed bytes. The readiness check uses the same application contract as
`registry publish`; it does not trust an in-memory wizard flag or a commit subject. It covers the
mandatory format, strict/frozen validation, canonical lock check, reproducible build check, audit
and required compatibility checks. A failed or not-yet-run gate makes Push unavailable and Registry
Maintainer lists the failed check and its actionable diagnostic. Preparation and execution recheck
the evidence so a change after drawing the screen is refused.

Choosing Push opens a separate review step with an explicit branch target. When aart-cli was launched
in an existing named Registry branch that is neither `main` nor the Registry default, that current
branch is the target; the action cannot redirect its commit to another existing branch. When the
checkout is on `main`, another default branch or in detached HEAD, the form instead accepts a new
branch name. It is prefilled from the action that most recently produced the local commit when that
context is available, and otherwise with `aart-cli/registry-update`. The configured Registry remote is
shown; `origin` is the fallback when no other remote is configured.

The push moves the exact recorded commit, never a later moving `HEAD`. A branch that does not exist
is created. An existing branch may advance only through an ordinary non-force push; divergence is
reported and never overwritten. The branch named `main` is always refused. The Registry's default,
consumer-visible branch is also refused by name and checked again against the remote's advertised
default. aart-cli does not merge or open a pull request. Before offering or executing the action, aart-cli
resolves the one Git worktree containing the launch workspace and proves that its root is the
Registry whose reviewed commit the result records.
If that worktree is a Source or any other repository, aart-cli refuses; it does not continue walking to
a parent checkout in search of a Registry. Registry Workspace keeps the local workspace row visible
but marks Push unavailable with that reason. Escape or leaving the review without confirming Push
keeps the operation local.

After a successful push, aart-cli explains the remaining steps: complete review/merge into the
consumer-visible branch where required, update the local checkout, and synchronize the Registry
subscription to observe the approved state. Pushing a review branch alone does not make its
artifacts available to consumers subscribed to the default branch. Source Sync discovers upstream
Candidates; Registry Sync reads approved Registry state. Neither operation implicitly pushes,
promotes or updates installed artifacts.

A consumer subscription reads the Registry's default branch. Local promotion and remote review
branches remain distinct from the approved snapshot that consumer synchronization can activate.
This TUI revision does not implicitly remove an independently supported CLI publication contract.

## 164.8 Screen 46 — Registry Workspace View — ACCEPTED

Maintainer Registry view exposes registry validity, artifact counts by kind, accepted and local
snapshot state, publication readiness with blocking diagnostics, current-branch publication and
recent promotions.

## 164.9 Screen 47 — Bulk Promotion — ACCEPTED

Multiple Ready candidates may be selected and promoted as one registry transaction:

```text
[x] github-mcp      1.6.0   Ready
[x] jira-mcp        2.3.0   Ready

2 selected

                         [ Promote (2) ]
```

Bulk promotion produces one coherent registry diff/validation/commit boundary.

## 164.10 Screens 48–53 — Lifecycle, provenance, conflicts, collections and filters — ACCEPTED

Candidate lifecycle:

```text
Discovered
    ↓
New / Changed
    ↓
Validation
    ├── Invalid
    ├── Warning
    └── Ready
          ↓
      Promotion
          ↓
       Promoted
          ↓
source changes again
          ↓
       Changed
```

Provenance exposes source URL, pinned revision, manifest path, artifact input digest, importer,
importer version, payload paths and warnings.

Published `coordinate@version` is immutable. A candidate with the same coordinate/version but a
different digest is blocked and must receive a new version.

Collections are candidates too. Collection validation resolves membership against registry state
and verifies that members are approved and compatible.

Candidate filters include status, kind, source and target registry.

Maintainer keyboard shortcuts are contextual:

```text
Space   select
Enter   details
s       sync
v       validate
p       promote
d       diff
r       provenance/report
/       search
f       filters
Esc     back
```

---

# 165. Accepted Registry and Lifecycle Edge Cases

Status: **ACCEPTED**.

## 165.1 Source deletion does not delete published artifacts

If an artifact disappears from its source repository, Source Sync records that fact but published
registry versions remain intact.

```text
github-mcp 1.6.0

Source status
⚠ Missing from source

Registry status
✓ Published in company-core

Installed users
unaffected
```

Vendored artifacts remain usable even if the entire upstream repository disappears or becomes
unavailable.

## 165.2 Published lifecycle: Published, Deprecated, Revoked

Normal lifecycle does not physically delete published versions.

```text
Published
Deprecated
Revoked
```

Deprecated means new use is discouraged while existing installations may continue subject to
policy.

Revoked means the version is unsafe or prohibited for new installation and existing installations
require policy-driven attention.

Revocation/deprecation metadata may evolve while the original canonical payload and artifact digest
remain immutable.

## 165.3 Consumer behavior for deprecated and revoked versions

Deprecated:

```text
github-mcp 1.5.0                     ⚠ Update recommended

This version is deprecated.
Recommended: 1.6.0
```

Revoked:

```text
github-mcp 1.5.0                     ✕ Action required

This version has been revoked.
Recommended version: 1.6.1
```

Effective policy determines whether continued execution is allowed, warned, blocked or requires
remediation.

Registry sync detecting revocation does not secretly mutate the installation. Any disabling,
updating or harness change is represented as a policy-driven remediation plan.

## 165.4 Dependency conflicts

Constraint conflicts fail explicitly.

```text
github-mcp

Data Scientist Kit
requires >=1.5,<2

Developer Toolkit
requires >=2,<3

No single version satisfies both.
```

aart-cli never silently chooses a conflicting version.

V1 has one active version per complete installation identity (§85): Registry alias + artifact +
harness/profile + scope + concrete target root. Different targets may independently run different
versions. Constraints from multiple Collections conflict only when they address the same complete
owner. Concurrent versions within one owner are outside this contract.

Update conflicts are surfaced before mutation. Exact Collections are not partially updated merely
to bypass a conflict.

## 165.5 Collection drift and custom selections

An exact Collection installation establishes desired membership.

If a member disappears locally:

```text
Data Scientist Kit 2.0                ⚠ Incomplete

7 / 8 artifacts present

Missing
notebook-review

[ Repair Collection ]
```

Repair restores the missing owned member.

A custom selection derived from a Collection is not an exact Collection and must not be reported as
an incomplete Collection:

```text
Custom selection
Based on Data Scientist Kit 2.0

7 artifacts
```

Collection version updates display membership changes semantically:

```text
+ database-mcp
- notebook-review
~ github-mcp 1.5 → 1.6
```

Removed members are physically removed only if no remaining ownership requires them.

## 165.6 Registry rollback and history

Registry rollback is represented as a new Git revert/repair commit rather than history deletion.

```text
commit A
commit B
commit C
commit D = revert C
```

aart-cli may provide `Prepare Revert`, but the resulting state remains auditable through ordinary Git
history.

Each consumer-visible registry snapshot has stable identity, including a digest and corresponding
Git revision where applicable. Receipts record the registry snapshot used for planning/install.

## 165.7 Invalid registry HEAD

A consumer must not replace a known-good local registry snapshot with an invalid newly fetched
snapshot.

```text
company-core

✕ Registry invalid

Current HEAD
a81bc...

Last known valid
8d21c...

Problems
• duplicate coordinate
• invalid artifact digest
```

The last known valid snapshot remains active until a valid successor is available.

## 165.8 Payload changed without version bump

If source content changes while the artifact retains an already-published version:

```text
✕ Version conflict

github-mcp 1.6.0 already exists.

Published digest
sha256:aaaa

Current source digest
sha256:bbbb

Published versions are immutable.

Increment the artifact version.
```

Promotion is blocked.

Moving or renaming an upstream source does not rewrite historical provenance. New versions may
reference the new source location.

## 165.9 Compromised artifacts and revocation

Maintainers may prepare security actions affecting one or more immutable versions:

```text
Security action

github-mcp 1.5.0
github-mcp 1.6.0

Reason
Credential exfiltration vulnerability

Action
Revoke versions
Recommend replacement 1.6.1

Consumer severity
Critical
```

Dependency health propagates revocation: an artifact depending on a revoked dependency becomes an
attention item even if its own payload is unchanged.

## 165.10 Physical purge is exceptional

Normal registry lifecycle uses deprecation, revocation and hiding from new installs rather than
physical deletion.

Physical purge is a high-risk exceptional operation for cases such as legal requirements, malware
or accidentally published secret material.

If a secret is discovered in canonical payload, aart-cli must clearly state that removing the current
payload does not guarantee removal from Git history and that repository-specific secret-removal and
credential-rotation procedures are still required.

## 165.11 Registry unavailable / offline state

When a registry is unavailable:

```text
company-core                       ⚠ Offline

Using last synced snapshot
2026-08-29 10:12
```

Marketplace may continue using the last known valid local snapshot.

Offline installability is decomposed into separate capabilities:

```text
metadata cached
canonical payload cached
runtime dependencies cached
```

A locally available artifact payload does not imply that package-manager dependencies can be
installed offline.

## 165.12 Install succeeded but verification failed

Successful effects followed by failed verification are not reported as clean success.

```text
⚠ Installation completed with a problem

github-mcp was installed,
but verification failed.

Authentication failed.

[ Repair token ]
[ View details ]
```

Receipt records applied effects, verification result and final health.

## 165.13 Partial multi-artifact failure

aart-cli does not claim transaction atomicity beyond actual effect guarantees.

If all applied effects are safely compensatable, the previous state may be restored.

Otherwise:

```text
⚠ Installation partially completed

5 artifacts ready
2 restored
1 needs attention

aart-cli could not fully restore:
database-mcp

[ Repair ]
[ View details ]
```

Partial outcomes are explicit and auditable.

## 165.14 Interrupted execution

An interrupted operation is never resumed by blindly continuing from the next imperative command.

```text
aart-cli found an interrupted operation.

Data Scientist Kit installation

Last completed
InstallPythonDependencies

Current state will be verified before continuing.

[ Resume safely ]
[ Inspect only ]
```

Resume performs re-inspection and reconciliation before constructing the remaining plan.

Receipt lifecycle may include:

```text
Interrupted
PartiallyApplied
Compensated
Completed
CompletedWithAttention
Failed
```

## 165.15 Concurrent mutation

Mutations are serialized per relevant scope/state store.

A second mutating process receives an explicit operation lock message while safe read-only
inspection remains available.

## 165.16 External manual modification

aart-cli detects drift in owned/generated state.

```text
⚠ github-mcp configuration changed outside aart-cli

[ Restore aart-cli version ]
[ Ignore temporarily ]
```

V1 does not adopt arbitrary manual modifications into desired state unless the artifact-specific
representation can be safely parsed, validated and intentionally supported.

## 165.17 Superseded candidates

If a newer candidate appears while an older candidate remains under review:

```text
github-mcp 1.6.0       Superseded
github-mcp 1.6.1       Ready
```

Superseded candidates remain auditable but are not the default promotion target.

## 165.18 Version downgrade

Downgrade is a normal reconciliation intent, not receipt undo.

It must evaluate compatibility, inputs, policy and dependent artifacts before planning the version
change.

## 165.19 Configuration and credential contract changes

Version updates may alter input contracts.

If aart-cli cannot safely map an old config field to a new one, it asks only for the newly required
value.

Authentication-model changes are explicit:

```text
github-mcp 2.0 requires a new authentication method.

Existing GitHub token cannot be reused.

You will need:
• Client ID
• Client secret
```

Old credentials retain their installation owner and follow explicit cleanup policy. A contract
change must not touch credentials owned by any other installation.

## 165.20 Collection update blocked by one member

An exact Collection update is blocked when any required member cannot satisfy requirements/policy.

```text
Data Scientist Kit 2.1

7 members ready
1 member blocked

database-mcp
requires Python >=3.12

Collection update cannot continue as an exact Collection.

[ Keep 2.0 ]
[ View blocker ]
```

aart-cli does not silently convert the exact Collection into a 7/8 custom selection.

## 165.21 Policy drift after installation

Health includes effective policy compliance.

An artifact that was previously allowed may later become non-compliant:

```text
⚠ github-mcp no longer complies with current policy.

Reason
External launch scripts are no longer allowed.

[ Review remediation ]
```

Policy drift creates an explicit remediation decision/plan rather than silently mutating installed
state.

## 165.22 Multi-registry collisions

When the same coordinate/version exists in multiple registries with different content, aart-cli
surfaces ambiguity rather than applying silent registry priority.

```text
⚠ Multiple approved sources

github-mcp 1.6.0

● company-core
○ platform-ai
```

Marketplace may group byte-identical packages visually only if every Registry alias remains
visible and individually selectable. An unqualified match across aliases requires a choice even
when digests match. Installed never merges those entries: each alias has its own target-qualified
path, receipt, runtime, input bindings and lifecycle (§169.3). Provenance retains the selected
Registry origin and snapshot.

Cross-registry dependency resolution is supported only when allowed by effective policy and remains
visible in Verbose resolution output.

Registry trust classifications such as Enterprise Approved, Community or Local/Unreviewed are
policy inputs and user guidance, not cryptographic proof of safety.

## 165.23 Development installs

Maintainers may test a candidate before registry promotion using an explicit development intent,
for example:

```text
aart-cli dev install ./mcp/github
```

or Candidate Detail → `Test Install`.

Development installations are clearly marked:

```text
⚠ Development artifact

Not installed from an approved registry.
```

Receipts record local/candidate source, no registry snapshot and development trust status. Doctor
continues to surface the development nature of the installation.

## 165.24 Promotion evidence and warnings

Effective policy may require evidence such as schema validation, tests, live acceptance or security
scanning.

Missing required evidence blocks promotion.

Warnings need not block promotion when policy allows them, but warnings are retained in candidate,
promotion and provenance records.

## 165.25 Explicit candidate rejection

Maintainers may reject a candidate with a reason.

A rejected candidate with the same artifact input digest should not continuously reappear as new on
every Source Sync.

If its input digest changes, it becomes reviewable again as a changed previously-rejected
candidate.

## 165.26 Promotion audit trail

Promotion records preserve sufficient evidence to reconstruct the decision:

```text
candidate digest
source revision
validation report digest
effective policy result
promotion mode
registry snapshot before
registry snapshot after
warnings
```

Identity of human approvers may be delegated to Git/PR systems. The architecture supports external
audit references rather than requiring aart-cli to implement its own enterprise RBAC system.

## 165.27 Git PR publication workflow

Recommended enterprise publication:

```text
aart-cli promote
   ↓
registry commit
   ↓
push branch
   ↓
PR
   ↓
CI
   ↓
human review
   ↓
merge
   ↓
consumer registry sync
```

aart-cli owns artifact/registry validation and preparation. Existing Git hosting owns branch protection,
review and merge authorization.

## 165.28 Promotion is not publication

A local promotion/commit is not yet globally Published.

Lifecycle:

```text
Candidate
→ Promoted locally
→ Registry commit
→ merged to canonical consumer-visible branch
→ Published
```

The consumer-visible canonical registry branch defines publication.

---

# 166. Canonical Project Invariant Catalog — Maintainer and Edge-Case Additions

**INV-199 — Source, Candidate, Registry and Marketplace are distinct domains.** UI and domain logic
must not collapse discovery state, review state, approved canonical state and consumer projection.

**INV-200 — Source Sync never promotes.** Discovery may create/update candidates but cannot silently
change approved registry contents.

**INV-201 — Manifest discovery is explicit.** Native source discovery uses declared aart-cli manifests
rather than heuristic repository crawling.

**INV-202 — Maintainer review is semantic-first.** Semantic artifact changes are the primary review
surface; raw file diffs remain available as deeper evidence.

**INV-203 — Published coordinate/version content is immutable.** Different content under an existing
published coordinate/version is a hard conflict requiring a new version.

**INV-204 — Enterprise promotion vendors by default.** Referenced promotion may exist as an explicit
weaker mode, but vendored canonical payload is the enterprise default.

**INV-205 — Promotion never implies push.** aart-cli may validate, materialize and commit registry
changes but must not silently push them to a remote repository.

**INV-206 — Bulk promotion has one registry transaction boundary.** Selected candidates are reviewed,
validated and represented in one coherent registry diff/commit operation.

**INV-207 — Source disappearance does not erase registry state.** Published vendored artifacts remain
available independently of upstream source availability.

**INV-208 — Deprecation and revocation are distinct.** Deprecation discourages use; revocation
signals unsafe/prohibited use and requires policy-driven attention.

**INV-209 — Lifecycle metadata may change without mutating immutable payload.** Status, replacement
and security metadata can evolve while canonical published content remains fixed.

**INV-210 — Registry revocation does not secretly mutate installations.** Registry changes may
trigger health/policy findings, but installation mutations still require explicit reconciliation
plans and applicable policy.

**INV-211 — Dependency conflicts fail explicitly.** Resolution never silently chooses a version that
violates another selected/installed requirement.

**INV-212 — V1 assumes one active version per complete installation identity.** Registry alias,
artifact, harness/profile, scope and concrete target root determine that identity. Multi-version activation
requires a future explicit namespacing design.

**INV-213 — Exact Collections preserve exactness.** Install/update/repair cannot silently degrade an
exact Collection into a partial custom selection.

**INV-214 — Custom selections are not incomplete Collections.** A deliberately partial selection
derived from a Collection has its own semantic identity.

**INV-215 — Ownership controls physical removal.** Collection membership removal does not delete an
artifact still owned directly, by another Collection or by another dependency relationship.

**INV-216 — Registry rollback preserves history.** Corrections are new commits/reverts rather than
history erasure.

**INV-217 — Registry snapshots have stable identity.** Consumer planning and receipts can identify
the exact approved snapshot used.

**INV-218 — Invalid fetched registry state cannot replace last-known-good state.** Validation gates
activation of newly synchronized registry snapshots.

**INV-219 — Historical provenance is not rewritten when upstream moves.** New versions may reference
new source locations; old provenance remains historical truth.

**INV-220 — Revoked dependency affects dependent health.** Health/policy evaluation propagates
relevant revocation through the resolved dependency graph.

**INV-221 — Physical purge is exceptional and high-risk.** Ordinary lifecycle uses
deprecated/revoked/hidden states; destructive purge requires explicit exceptional handling.

**INV-222 — aart-cli does not claim Git secret erasure.** Emergency payload purge cannot be represented
as proof that sensitive material disappeared from repository history.

**INV-223 — Offline capability is decomposed.** Cached metadata, payload and runtime dependencies are
separate capabilities and must not be conflated.

**INV-224 — Verification failure changes final health.** Applied effects followed by failed
verification are not reported as clean success.

**INV-225 — Transaction guarantees match effect guarantees.** aart-cli never claims atomicity,
reversibility or compensation that its effects/interpreters cannot provide.

**INV-226 — Interrupted operations re-inspect before resume.** Resume is reconciliation from observed
state, not continuation from an assumed imperative program counter.

**INV-227 — Conflicting mutations are serialized over owned effects.** Complete installation
identities are independent, but updates to a shared harness settings file must preserve all owned
fragments, including operations from different application homes. Conflicting mutating operations cannot
race over the same managed state.

**INV-228 — External drift is detected.** Owned/generated state changed outside aart-cli is surfaced
before repair; arbitrary drift is not silently adopted.

**INV-229 — Superseded candidates remain auditable.** New candidate revisions do not erase prior
review state.

**INV-230 — Downgrade is reconciliation, not receipt undo.** Version downgrade is planned against
current requirements, policy and compatibility.

**INV-231 — Input contract migrations are explicit.** aart-cli asks for or transforms changed inputs only
when the mapping is declared and safe; it does not invent semantic migrations.

**INV-232 — Credential contract changes preserve unrelated credential ownership.** Authentication
changes in one artifact/version do not delete credentials still used elsewhere.

**INV-233 — Policy drift contributes to health.** Installed artifact health includes current
effective-policy compliance in addition to local file/runtime state.

**INV-234 — Multi-registry ambiguity is explicit.** Different content for the same coordinate/version
across registries cannot be silently resolved by hidden priority.

**INV-235 — Cross-registry dependency resolution is policy-governed.** Registry boundaries remain
visible in detailed resolution and may be restricted by enterprise policy.

**INV-236 — Trust labels are policy metadata, not proof.** Registry classification informs decisions
but does not replace validation, provenance or security controls.

**INV-237 — Development installs are visibly distinct.** Local/candidate test installs cannot be
mistaken for approved registry installations.

**INV-238 — Required promotion evidence is policy-driven.** Validation/test/security evidence needed
for promotion is configurable through policy rather than hardcoded to one enterprise workflow.

**INV-239 — Rejected candidates are digest-aware.** An unchanged rejected candidate stays rejected;
material source change reopens review.

**INV-240 — Promotion decisions are auditable.** Promotion state retains source, validation, policy,
mode and before/after registry evidence.

**INV-241 — aart-cli does not replace Git review authorization.** Enterprise PR/CI/branch protection can
remain the authority for human approval and publication.

**INV-242 — Local promotion is not publication.** Published means present on the canonical
consumer-visible registry branch/snapshot, not merely prepared or committed locally.

**INV-243 — Runtime input state is Registry-, artifact- and target-qualified.** Configuration values
and credential bindings belong to one stable installation-target identity that includes the
configured Registry alias, artifact identity, project/user destination and harness/profile. Equal
artifact names or input identifiers across aliases, projects, user scope or harness targets never
permit value or provider-item sharing. Explicit sharing and copying are also excluded; every new
installation collects configuration and secrets independently.

---

# 167. Accepted TUI refinements from the 2026-09-14 manual run

Status: **ACCEPTED — implementation tracked in CP-23**. These explicit product-owner revisions
supersede earlier presentation choices where they differ. Acceptance is the intended contract,
not a claim that the existing implementation already satisfies it.

- **Source onboarding:** successful Add Source explains that Source Sync is needed to discover
  artifacts and create/refresh Candidates, including upstream version changes. Adding the Source
  alone does not discover them; discovery is distinct from promotion and consumer updates.
- **Candidates:** the status/artifact/version/source table and focused Candidate identity summary
  occupy separate frame blocks. The summary has no `Under the cursor:` heading and is shown under
  Verbose, collapsed in Fast, following the later all-screen clarification. A successfully promoted
  Candidate must no longer appear as New or remain eligible for
  duplicate promotion. Local promotion is visibly distinct from consumer-visible publication, and
  history remains auditable across refresh and restart.
- **Candidate Diff:** `v` switches between summary and bounded redacted file diffs as Fast/Verbose
  projections of the same Candidate. The `f` key and ineffective `d returns to summary` guidance
  are removed from this screen. The supplied `Press v to view bounded redacted file diffs` hint
  occupies its own block below the diff; navigation and review identity do not change on toggle.
- **Validation:** remove the redundant `p` Policy shortcut. Enter continues the existing review
  path through validation details and policy without bypassing either check.
- **Publication:** §164.7 gives Registry Workspace an explicit Push for a clean, gate-valid local
  Registry commit to a non-default review branch, and explains every reason it is unavailable plus
  any required review/merge before Registry Sync can discover the newly approved version.
- **Success:** View installed, View receipt, Done and any supported Undo are working controls,
  separate from outcome prose. View receipt targets this operation's exact record. Undo is a
  separately reviewed operation offered only when the actual effects support safe reversal.
- **Marketplace:** the row under the cursor has a description from approved artifact metadata in
  a separate block, shown under Verbose and collapsed in Fast with `v`, following the later
  all-screen clarification. No description is invented or fetched during rendering.
- **Remediation:** describe proposed aart-cli changes as actions aart-cli will perform after approval,
  not unexplained chores the user must perform. They are listed on Ready to Install rather than on a
  screen of their own, so confirming the final review is the one approval. Keep material changes and
  material risk visible; routine derived changes stay in Verbose.
- **Harness targets:** Skill installation always offers explicit choice among eligible harnesses,
  even when exactly one is eligible, and permits selecting multiple eligible targets. Eligibility
  follows artifact compatibility, platform, scope and policy; choosing a subset is user intent.
  Review, effects and receipts agree on that subset. Existing setup remains derived from actual
  delivery. This supersedes the earlier interpretation that deriving eligibility removes the
  need for a target picker; selecting targets is a meaningful decision under INV-150.
- **Artifact Details:** selection/install/detail controls must have working keys or selectable
  rows; a printed `Actions:` sentence alone is insufficient. Detected but unselected incompatible
  harnesses are not presented as missing requirements; explicitly selected incompatible targets
  remain refusals with guidance.
- **Credential Action:** permitted actions are navigable and executable through the same
  application services as other surfaces. Usage/replacement consequences remain outside action
  rows; in-use deletion restrictions, explicit mutation review and secret-value protection remain.
- **Every screen follows the shared frame:** the trail/applicable stepper, action rows, cursor
  description, view status, notices, workspace caption and key legend retain their shared order
  and separate blocks in both text and curses views. Empty blocks are omitted. Compliance must be
  checked over every declared screen and relevant conditional state, including populated forms,
  failures and completed operations, and enforced by tests when the catalog grows.
  There are no screen-specific skeleton exceptions for normal views remaining inside TUI,
  including credential/MCP forms, help and modal states. They all use the same frame composition;
  optional regions follow shared rules. Necessary external credential/MCP handoffs may use a
  fallback outside TUI, but returning restores the same frame and preserved session state.
- **One cursor-description rule:** `v` enables Verbose and shows the description for the current
  row; cursor movement updates it and returning to Fast hides it. This supersedes the earlier
  Fast-visible exceptions for Candidates and Marketplace. No stale detail remains on a screen
  without a describable row. Presentation changes do not mutate intent, execute actions or perform
  observation IO. Candidate Diff also discloses its file evidence through this same profile.
  Text-entry mode preserves literal text input. Required input help, material risks and blockers
  remain visible in Fast; they are essential form/review information, not optional cursor detail.
  These facts use the standard information block; their visibility is not a layout exception
  and does not allow mixing prose into selectable/input rows.
- **Explicit credential acquisition guidance:** the source author declares each credential's
  human name, purpose and how/where to obtain it in the native manifest's input guidance. Reuse
  §§154–157 and the existing help contract, including acquisition label/link and optional format
  or permissions guidance. Compilation and promotion preserve it in approved `artifact.json`;
  installation shows essential guidance at the point of secure entry in Fast and Verbose,
  including provider-owned prompts. Approved Registry enrichment may refine the guidance; the
  live Source or remote help is not fetched during installation/rendering. Manual issuance can
  be explained without inventing a self-service link. Missing guidance in older valid manifests
  receives author validation feedback and an honest consumer fallback rather than fabricated
  instructions or a silent new hard schema requirement. New examples demonstrate complete help.
  Descriptions/links contain no usable secret values and do not determine provider/binding policy.

These refine INV-062–068, INV-134–135, INV-149–168, INV-187–197, INV-202, INV-205 and INV-242;
they do not create a second planner, permit rendering IO or weaken the approved Registry baseline.

# 168. Accepted top-level README contract

Status: **ACCEPTED — implementation tracked in CP-26 steps 13–16**.

The repository README serves one primary audience: a normal user who wants to install an artifact
as quickly as possible. It is an adoption page and documentation index, not the full product,
authoring, Registry-maintenance, Enterprise, contributor, quality or release manual.

Its content order is contractual:

1. After the title and at most one outcome sentence, the fastest supported quick start installs
   aart-cli, connects and synchronizes a Registry, finds or selects an artifact in Marketplace,
   installs it into a selected harness and verifies the result. The TUI is the primary human route;
   a compact deterministic CLI equivalent may follow. Repository, Registry, artifact and harness
   values that cannot be universal remain explicit placeholders and never become organization-
   specific defaults.
2. A short explanation of what aart-cli is follows the working quick start. It may identify aart-cli as an
   agent-artifact package manager, Registry client, policy/review surface and installer, name the
   supported artifact families, and summarize Source → Candidate → Registry → Marketplace only far
   enough to orient a new user. Detailed architecture does not remain inline.
3. A compact categorized documentation index follows. It links to focused documents for ordinary
   lifecycle use, TUI/CLI, artifact authoring, Registry maintenance, Enterprise setup,
   security/protocol contracts, development/testing and releases. Every linked target exists.
   Author and maintainer workflows live in those documents rather than becoming a second README
   tutorial. Internal refactor records are not public getting-started documentation.
4. The existing MIT License section, legal wording and copyright/footer remain the final README
   content unless the owner separately changes that legal text.

Detailed material currently in README moves to focused documentation rather than being silently
discarded. The final documentation gate executes the advertised installation forms and checks the
section order, bounded product explanation, link targets and final License placement. A later task
that changes README or its install lines reruns that gate.

# 169. Accepted installation ownership, filesystem layout and product namespace

Status: **ACCEPTED 2026-09-19 — implementation pending in CP-26.18a and CP-26.19**.
This owner-approved contract supersedes the shared-runtime premise in D-071 and the explicit
cross-installation credential-sharing allowance in D-313. Earlier release records describe
historical behavior; this section defines the required result.

## 169.1 One product namespace

The package, executable, user-facing product name and tool-owned filesystem namespace are
`aart-cli`. The Python import package is `aart_cli`. Author manifests are `aart-cli.yaml` and
`aart-cli.json`; tool-owned schema/URI identifiers, generated files, block markers, branch
prefixes, environment variables and CI/release interfaces follow the same namespace, with
`AART_CLI_` for environment-variable identifiers. External harness filenames and formats remain
those required by each harness. Historical repository identities and legal attribution remain
literal historical facts.

Breaking changes are accepted throughout CP-26, not only for paths or names. The owner states that
the product is just starting and has no users requiring preservation of its old interfaces. Old
commands, names, files, schemas, formats, defaults and internal product rules may be replaced or
deleted directly to satisfy the accepted specification. Backward compatibility is not an
acceptance requirement. Do not add compatibility aliases, fallback readers, old-path probing,
dual-written state, migration commands or deprecation periods solely to preserve old behavior.
Update or remove obsolete behavior tests; retain tests of still-required behavior and ownership.
External harness contracts, secret protection and the new installation invariants still apply.

CP-26.18a inventories and changes every active producer, reader, packaged entry point, template,
example, test and public document. Implementation verification is proportional: focused tests or
smoke checks for changed behavior and the affected ownership boundaries, no old-version matrix,
no repetitive repository-wide runs. Existing relevant assertions should be reused; namespace-only
substitutions do not each need a new test or mutation. Required targeted semantic mutation/scoped
mutation evidence remains bounded to material behavior claims. CP-26.21 owns the final broad gates;
accepting breaking changes does not justify suppressing failures against the new contract.

## 169.2 One portable home for tool-owned user data

macOS and Linux resolve the same application home:

```text
explicit AART_CLI_HOME (normalized absolute path)
otherwise <user-home>/.aart-cli
```

`AART_CLI_HOME` is resolved once at the process boundary and passed through explicit path values;
domain code does not inspect environment variables or the filesystem. No platform-specific user
data/cache/config roots or XDG fallback are used. CI and isolated agent jobs can select a private
absolute directory without changing the OS user's home or the harness's home.

The managed layout is:

```text
~/.aart-cli/
├── config.json                     # Registry/Source connections and tool settings
├── objects/
│   ├── sha256/                      # immutable canonical package content by digest
│   └── quarantine/                  # rejected/corrupt object evidence
├── sources/                        # acquired Registry/Source snapshots and Candidate evidence
├── state/
│   ├── installations/              # one receipt per complete installation identity
│   ├── activity.sqlite3            # action records and artifact uses (§212), owner-only
│   ├── telemetry.sqlite3           # telemetry outbox and its state (§213), owner-only
│   ├── telemetry.lock              # held by the one telemetry sender (§213)
│   ├── setup/                      # target-qualified setup metadata
│   ├── object-references.json      # canonical object retention metadata
│   └── consumer-settings.json      # UI preferences
├── cache/                          # disposable derived data, including security assessments
├── locks/                          # concurrency control
└── tmp/                            # bounded staging and transient operation files
```

Configuration here means configuration of `aart-cli` itself. Artifact configuration values are
excluded from this home, including receipts, setup records, logs, recovery copies and temporary
global value stores. Receipts may contain target identity, version/digest, owned paths, file
digests and credential references. Secret values are excluded from all these files.

Identical canonical packages may share immutable object storage. They never share mutable runtime
trees, environments, launchers, configuration files or credential provider items. Deleting cache
does not remove installation receipts or required package evidence. Object pruning respects
recorded references. A central installation index is metadata, not shared configuration state.

Project installation receipts also live in this home, qualified by the concrete project root.
The tool creates no second `<project>/.aart-cli` receipt store or project-global runtime directory.
A bulk operation may additionally write one transaction/activity receipt linking the individual
installation receipts (INV-138); this is not a replacement for per-owner records. Multiple
Collections may retain one exact installation through ownership reasons (INV-129), without joining
different installations or inputs.
Author Sources and Registry checkouts remain in the locations explicitly selected by their owner;
this home stores acquired snapshots, not relocated author repositories.

## 169.3 Installed files belong to the selected harness

For a locally executed MCP, one installation owns a payload copy, an isolated runtime (a private
`runtime/.venv/` for Python), a launcher and a plain ordinary configuration file inside a
namespaced subtree of the selected harness. The namespace includes Registry alias, artifact kind
and name; the enclosing harness root and profile resolution distinguish targets. A profile or
alternate harness home must receive a distinct tree whenever it denotes a different installation.

Example on either supported platform (`~` means the selected user's home):

```text
<project>/.tabnine/agent/
├── settings.json                   # owns only this installation's MCP entry
└── aart-cli/mcp/company/github/
    ├── payload/
    ├── runtime/.venv/
    ├── config/tabnine.conf
    └── launch.sh

~/.claude/
└── aart-cli/mcp/company/github/
    ├── payload/
    ├── runtime/.venv/
    ├── config/claude.conf
    └── launch.sh

~/.claude.json                      # owns only this installation's MCP entry
```

Each registration uses the absolute path of its own launcher and a collision-resistant
alias-qualified entry key. Other entries and settings in the harness file are preserved. The
launcher resolves only that installation's provider references and starts its own runtime;
successful launch does not depend on `aart-cli` or on live reads from its canonical object store.
Files must not be linked back into a shared mutable runtime under the application home.

Registry connection identity is part of the path, even when two connections point to the same
upstream Registry or expose byte-identical packages. For example, connect the remote Registry as
`company` and its local checkout as `company-local`. Installing `mcp/github@1.5.0` from both into
Claude/user produces:

```text
~/.claude/aart-cli/mcp/company/github/
~/.claude/aart-cli/mcp/company-local/github/
```

Both have their own payload, runtime, launcher, config file and provider items. The two entries in
`~/.claude.json` use distinct keys derived from the alias-qualified identities and point to their
respective launchers. Two central receipts and two Installed rows retain `company/mcp/github` and
`company-local/mcp/github` as separate entities. Installing both into Tabnine/project as well adds:

```text
<project>/.tabnine/agent/aart-cli/mcp/company/github/
<project>/.tabnine/agent/aart-cli/mcp/company-local/github/
```

That is four installations, four independently collected input sets and four Installed rows.
Equality of package digest, version, upstream Registry id or original Source provenance never
merges those owners. Only their immutable canonical package object may be deduplicated by digest.
The configured Registry alias is a validated path component (or is safely encoded); it cannot
escape the managed root. Repointing a connection must not silently adopt another Registry's
existing installation; receipts retain Registry origin/snapshot provenance. A change of alias
creates a different installation namespace, not a credential/configuration transfer.

Skills, guidelines, hooks and memory continue to use the harness's documented discovery paths
and owned fragments; they do not gain a Python runtime merely to fit the MCP layout. Every emitted
file, tree or fragment has one installation owner. If two selected installations cannot coexist
under a harness's addressing rules, planning reports the conflict before writing. An adapter
without a safe supported destination refuses that target; it does not silently place the runtime
in the central application home. Registered stdio behavior and external filenames still require
harness-specific adapters.

An installation is recorded after its actual effects are applied, with its own verification result.
Presence in the canonical object store means available, not installed. Failed verification is
visible as unhealthy; partial execution records only actual effects. Installed shows independently
actionable rows for `company/mcp/github · Tabnine · project · <project>` and
`company/mcp/github · Claude · user · <user-home>`, each with its version and health. Grouping by
artifact or Collection must preserve those rows and their separate update/configure/repair/uninstall
actions. Removing one must not change the other's tree, receipt or credential item.

## 169.4 Every installation collects its own inputs

The complete key is:

```text
Registry alias + artifact kind/name + scope + normalized concrete target root + harness/profile
then input_id within that installation
```

Every new installation collects every required ordinary value and secret separately. Selecting
four eligible harnesses for one MCP is four installations, even in one wizard and one transaction.
With two ordinary variables and one secret, that operation has eight ordinary input fields and
four secure secret entries. It writes four ordinary configuration files and four independent
Keychain items for that secret on macOS. The provider creates the items; the user does not need to
create Keychain records manually. The user may type the same text independently for each target.
D-413 (§172) changes how the values are entered, not where they live: one operation asks once per
artifact, may leave inputs as placeholders, and still writes four files and four items.

There is no global input pool, automatic value propagation, cross-target prefill, copy-answers
button, shared credential picker or explicit sharing option. Input guidance may be displayed once,
but each target's fields and owner remain visible. A single bulk review preserves all four owners.
Compatible values may be retained during update/repair of an existing identical owner; that never
satisfies another installation's new-input requirements. Uninstall deletes only the
removed installation's own credentials (§208).

In non-interactive CI, each required binding must be supplied separately with its installation
identity through approved configuration input channels and secret providers. No secret enters the
serialized plan or receipt. A missing target's input yields a structured failure naming that
target; it never prompts, borrows another target's answer, or treats a generic input-id environment
variable as a value for all targets. Providers must keep distinct target-owned references/items;
one external provider item cannot be selected by two installations.

## 169.5 Platform boundaries that remain

The application home is portable. Harness discovery/configuration, Python executables and native
dependencies, permissions, process execution and secret providers retain their actual platform
contracts. A macOS environment is not copied into Linux CI merely because the path is identical.

macOS secrets live in Keychain; Linux/headless execution uses an approved available provider.
Provider implementation details and external provider files are outside the application home.
Machine policy remains administrator-controlled at
`/Library/Application Support/aart-cli/policy.json` on macOS and `/etc/aart-cli/policy.json` on
Linux. Relocating `AART_CLI_HOME` cannot disable or replace that policy. Trusted deployment/CI policy
provisioning must preserve the same authority boundary. Combining user data into one home does not
move administrator policy into a user-writable file.

## 169.6 Acceptance invariants

**INV-244 — One portable application home.** All tool-owned user configuration, immutable package
storage, snapshots, receipts, cache and transient state resolve beneath `~/.aart-cli` or the
explicit `AART_CLI_HOME` on macOS and Linux; project scope does not create another receipt store.

**INV-245 — Executable installation state belongs to one harness target.** Every installation has
its own harness-owned files/fragments, runtime and ordinary configuration. Immutable central
objects and metadata never imply a shared runtime or cross-target lifecycle mutation.

**INV-246 — New targets get separate input sets.** Four harnesses mean four independent
configuration and credential sets. Since D-413 one operation enters each value once per artifact
and writes a separate copy to each of its new installations (INV-259). TUI, CLI and CI neither implicitly nor explicitly share values
or provider items across installations; compatible reuse is confined to the same existing owner.

**INV-247 — The active namespace is aart-cli.** Distribution, executable, tool-owned filenames,
protocol identifiers, environment variables and generated/public guidance use the accepted
namespace, with no compatibility aliases or old-path fallback. Literal history and external
harness contracts remain identifiable as such.

## 169.7 Versionless installed names and credential addresses

Accepted 2026-09-19 (D-349), implemented by CP-26.19. Harness-visible installed names include
artifact name, Registry alias and scope (`project` or `user`), without the artifact version.
Version remains available in AART CLI/TUI and installation metadata; updating one owner preserves
its installed name, path and credential address. The full owner in §169.4 remains authoritative;
a readable name alone is not sufficient to identify a project root, harness/profile or input.

Adapters preserve the harness's supported discovery root, directory depth, filename and name
grammar. For a skill named `github` from alias `company`, the portable spelling is
`github-company-project` or `github-company-user`, not `github--company--project`. Examples:

```text
<project>/.tabnine/agent/skills/github-company-project/SKILL.md
~/.tabnine/agent/skills/github-company-user/SKILL.md
<project>/.opencode/skills/github-company-project/SKILL.md
~/.config/opencode/skills/github-company-user/SKILL.md
```

The installed skill's frontmatter `name` matches its directory where the harness requires this.
Canonical Source/Registry content retains its original name; only the private installed copy is
projected. Receipts distinguish canonical content from projected installed digests so verify and
repair recognize intentional transformations. Additional alias/scope directory levels must not
break discovery. Characterize supported installed harness versions, including Tabnine CLI user
scope, rather than treating an old adapter capability table as authority.

The [OpenCode skill contract](https://opencode.ai/docs/skills/#validate-names) and
[Agent Skills specification](https://agentskills.io/specification) require lowercase alphanumeric
names with single hyphen separators, 1–64 characters, and a matching parent directory. Follow
the [Tabnine CLI discovery contract](https://docs.tabnine.com/main/getting-started/tabnine-cli/features/agent-skills)
for its supported roots and depth. Validate composed names, lengths and collisions before writes,
including ambiguous joins of hyphenated names/aliases and conflicts with unmanaged entries. Never
silently truncate, overwrite or use encounter-order counters. If valid distinct names cannot be
represented by the adapter, refuse the conflicting target with an actionable explanation.

For MCPs the visible registration key follows this versionless artifact/alias/scope convention;
the private runtime tree in §169.3 may retain its structured kind/alias/artifact directories.
Guidelines, hooks and memory use supported keys or owned markers where an external contract fixes
the filename. Required harness filenames are not renamed to impose an invalid convention.

Keychain uses the same installation ownership model. Its deterministic, collision-resistant
`service`/`account` pair incorporates the complete §169.4 owner plus `input_id`, with opaque
identifiers for concrete roots and no artifact version. A readable label identifies artifact,
Registry alias, scope, harness/profile and input; a stable opaque owner discriminator distinguishes
otherwise identical labels from different roots. The implementation records its exact encoding
and checks collisions before any provider mutation. Neither labels nor identifiers contain secret
values or derive from secret material. Do not concatenate only the readable artifact/alias/scope
label as the provider lookup key, and do not put raw absolute roots in Keychain labels.

Separate roots, aliases, harnesses/profiles and input ids get distinct provider items even if the
user independently enters equal secret values. Same-owner compatible updates preserve references;
configure, rotation, retention and deletion operate only on that owner's item. Other providers
preserve equivalent ownership through their supported addressing contracts. No cross-target
credential copying or shared item is introduced by a naming convention.

**INV-253 — Installed names and credential addresses preserve complete ownership.** Installed
names expose artifact, Registry alias and scope within actual harness naming/discovery contracts;
version is metadata, not naming identity. Canonical content remains unchanged by installation
projection. Credential addresses additionally distinguish concrete root, harness/profile and
input id, with opaque roots and no secret material. Collisions fail before mutation; updates of
the same owner retain stable names/references and cannot affect another owner.

# 170. Local MCP smoke verification

Status: **ACCEPTED 2026-09-19, revised 2026-09-20 (D-365) and 2026-10-14 (D-378)**. D-378 narrows
verification to the two direct stages, removes result expectations and the harness route, and adds
the optional test offered after installation. It preserves §169's installation and credential
ownership boundaries.

## 170.1 Scope and selection

Provide one CLI command, `aart-cli mcp test`, exclusively for already installed MCP artifacts in
the local environment. The author testing route is an ordinary installation from a configured
local Registry repository and branch; consumers can also test installations from remote Registries.
Other already supported installation origins may be selected, but this command does not require
implementing Candidate Test Install or another direct-from-Source flow. Source files, uninstalled
Candidates and Registry packages alone are not runnable test targets.

The caller explicitly selects all installed MCPs in the chosen local target scope or particular
installed MCPs, and the harness installation target(s) to test. Local Source/Registry provenance
may narrow that selection; a Source or Registry path does not authorize launching uninstalled
content. Selection resolves to concrete existing installation owners and tested content identities
before any server or harness is started. Ambiguous selectors and an empty selection are explicit
non-success results. When testing a particular Candidate/Registry version, an older or changed
installation cannot silently supply its evidence. `--all` stays inside the selected local scope.

The command does not implicitly install, update, configure, promote, publish, rotate credentials
or repair. Missing local setup or bindings are `NOT CONFIGURED`. Source and Registry checkouts
remain unchanged. Local describes the setup and invocation: the declared call may contact that
installation's configured remote service. Internal enterprise
endpoints, proxy/CA settings and approved providers must work without assuming public egress.

There is no background monitor, scheduled CI job or production-wide scan. Besides the command, the
other surfaces are the optional test offered right after an installation (§170.4) and the test the
person asks for from Installed (§170.4). All give human-readable output, and the command also gives
a structured JSON report, for the same operation. Exact selector syntax follows the repository's existing origin/installation selection
conventions; the command must expose explicit all-versus-selected MCP and harness selection rather than infer them.

Author and maintainer documentation should recommend installing a new MCP locally, running this
command for the intended harnesses, reviewing both stages and fixing failures before publishing
that tested content to a public remote Registry. Document adding the local Registry repo and the
branch containing the committed canonical artifact, ordinary installation from that alias, then
smoke testing. No additional candidate-install process is required. This is a recommended
pre-publication workflow, not an
implicit publication gate or an automatic promotion. A changed artifact must be reinstalled or
updated and retested; old evidence does not cover its new content. Consumer guidance also shows
how to check several already installed MCPs without involving authoring or publication.

## 170.2 Two verification stages

Each selected installation receives two independently evidenced stage results:

| Stage | Claim |
| --- | --- |
| Installation configuration | The selected owner's registration, launcher/runtime, ordinary configuration and credential references are usable and identify the intended content |
| MCP startup and protocol | Its actual installed launcher responds using a supported MCP protocol, advertises the declared tool, and completes the declared call with a valid result |

The second stage depends on the first: when installation configuration does not pass, the protocol
stage is `NOT RUN` with the failed prerequisite named. A missing credential or an ordinary input
or credential still holding `AART_NOT_SET` makes installation configuration `NOT CONFIGURED`,
with the input-entry recovery named. A provider item existing is insufficient when the provider
reports that it is a placeholder; the comparison stays inside the provider (§172.3). This is a
verification result, not a refusal to install or launch the artifact (§172.3). Nothing else is verified. AART does not
claim that a passing protocol stage proves external-service access, authentication or permissions:
a server that turns an upstream failure into an ordinary successful result passes this stage, and
the report must not suggest otherwise. No keyword reading, result expectation or model assessment
supplements the two stages.

For a server somebody controls, author guidance recommends breaking its configuration once on
purpose and confirming that the protocol stage goes red. That shows the server reports upstream
failures as MCP errors, which makes a protocol pass meaningful for that server. This is guidance,
not a stage.

## 170.3 Predeclared read-only smoke operation

**Minimal declaration (D-351).** An MCP author manifest may contain this optional top-level block:

```yaml
smoke_test:
  tool: get_current_user
  read_only: true
```

The exact existing tool name and explicit `read_only: true` are required when the block is present.
Omitted `arguments` means the empty argument object; validate it against the discovered tool's
input schema, and fail before invocation if required arguments are missing. Optional `arguments`
contains fixed values or explicit references to this installation's non-secret configuration.
An optional bounded timeout overrides the default 15-second tool-call deadline; server startup has
its own bounded budget. The block takes `tool`, `read_only`, `arguments` and `timeout_seconds` and
nothing else: any other key, including the former `expect` and `reaches_service`, is refused as
unknown, and no reader tolerates it.

The default evaluator checks tool existence, valid arguments, completion before the deadline,
a valid MCP result without transport/JSON-RPC errors or `isError: true`, and conformance to the
tool's `outputSchema` when declared. An omitted `isError` follows MCP's non-error default; a
malformed flag or result is not a pass. Respect the negotiated MCP/schema contract. If a required
schema cannot be validated, report unsupported validation rather than silently skipping it.
Accept every supported MCP content type, including text, structured data, images and valid empty
results. Do not demand JSON, a nonempty payload, a dedicated health tool or `{"ok": true}` from
the MCP server. These checks concern the protocol envelope and declared schemas, not the arbitrary
business meaning of its content, which AART never guesses. See the
[MCP tools contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

The manifest/parser owns the contract; compilation, canonical packaging, validation and authoring
guidance preserve it. It belongs to the selected content version/digest, not an unrelated side file
or another installation. Secret values are never arguments or expected values in the contract.

A dedicated author-provided `check_connection` tool is suitable but is not a new standard MCP
method and is not mandatory. A reviewed existing read-only tool with explicit arguments is also
valid. For example, the server can use its normal API client and credentials to read its identity
or a known protected test resource. The probe must perform the declared read, not simply return
a constant healthy flag. It must not create, update, delete or perform create-then-delete cleanup
of service data. Any parameters that can select such modes are refused by the test contract.

Only the declared operation is eligible. The runner never guesses from names such as `get_*`,
chooses a tool with an LLM, invokes all tools, or treats MCP `readOnlyHint` alone as authorization.
An absent declaration makes the protocol stage `NOT CONFIGURED`; an unsafe or malformed declaration
is refused before invocation. The installation stage still runs. The client enforces the declared
tool and arguments: it sends that one call and no other, so an unexpected operation is blocked
rather than noticed afterwards.

Read-only is a reviewed implementation contract, not proof of arbitrary server behavior. Starting
a server also executes its code. AART must not promise that a flag makes unknown code harmless.
Service-side read-only privileges provide stronger enforcement where available, but the test
must not silently substitute different credentials and claim it verified the selected setup.
Existing trust and execution policies still govern launching local Candidate content.

## 170.4 The optional test after installation

When an installation transaction that installed at least one MCP has committed, the success view
offers to test the MCP installations it just made. Nothing runs unless the person chooses it. The
offer, before it is accepted, names the installations, the declared tool and arguments of each one,
and that the call reaches the configured service with that installation's credentials.

The test is the same operation as `aart-cli mcp test` over exactly those installations: the same
two stages, the same selection rules and the same evidence handling. It is an addition to the
installation, never part of it:

- the transaction is already committed and recorded before the offer appears, and the test never
  extends, reopens or rolls it back;
- any test outcome, including a failed or unstartable server, leaves the installation, its receipts
  and its reported success unchanged;
- declining or ignoring the offer is a complete, successful installation;
- an installation that declares no smoke operation is shown as `NOT CONFIGURED`, which is not a
  warning about the install.

A failed test explains which stage failed and why, and leaves repair or reconfiguration to the
person's own choice.

The same test can be asked for at any later time from Installed. On the Installed list the person
ticks one or more installations, or leaves the cursor on one, and asks for the test; Installed
Artifact Details asks for it for that one installation. The same review is drawn before anything
runs, naming each installation, its declared tool and arguments and that the call reaches the
configured service. The selection is installation-qualified exactly as on the command: each
selected row is one installation in one harness, a selected installation that is not an MCP is
refused by name rather than dropped, and an empty selection is refused. The test changes nothing,
and its answer returns to the screen it was asked from.

## 170.5 Results and evidence ownership

Reports name the installation owner, local origin/content identity, harness, stage, timestamp,
outcome and actionable reason. Outcomes are `PASS`, `FAIL`, `BLOCKED`, `NOT CONFIGURED`, `NOT RUN`
and `UNSUPPORTED`. A successful run and a zero exit mean both stages pass for every selected target.
Empty selections and failed prerequisites cannot pass.

Use only the selected installation's existing configuration and credential bindings. No cross-target
prefill, secret copying, shared provider-item binding or global artifact configuration pool is
introduced. Persistent output contains safe metadata and assertion outcomes, not secret values,
ordinary artifact configuration values or raw service responses.
`--show-response` is an explicit, default-off exception for inspecting the MCP response in the
current command output (human or JSON). Bound the displayed response to 64 KiB, indicate truncation,
escape terminal control characters, and never fetch linked resources. Keep it out of application
state, receipts and logs. Do not resolve credentials for display; redact known sensitive values where
available, without claiming arbitrary server content can be fully sanitized. Explain that the response
may contain confidential service data and that redirected output is retained by the caller.
Displaying a response never changes an outcome. Verification results are time- and content-qualified
observations, not permanent health promises.

## 170.6 Acceptance invariants

**INV-248 — Local smoke selection is explicit and installation-qualified.** Only already installed
MCPs may be selected, individually or in bulk within the chosen local scope, including Candidate
test installs and local/remote Registry-origin installations. Verification resolves their owners
and tested content, neither changes setup nor borrows another target's inputs.

**INV-249 — Smoke operations are predeclared read-only calls.** Only the declared tool and
arguments may execute; a missing or unsafe contract never triggers a heuristic fallback, and
declarations are not represented as a sandbox guarantee. The declaration has exactly the tool,
read-only, arguments and timeout fields.

**INV-250 — Verification is two honest stages.** Installation configuration and MCP startup and
protocol have separate evidence and honest non-success states, and a failed first stage leaves the
second `NOT RUN`. A protocol pass is never presented as proof of external-service access, and no
keyword reading, expectation or model assessment adds a verdict to it.

**INV-251 — The post-installation test is optional and additive.** It runs only when the person
chooses it after the transaction has committed, covers exactly the installations that transaction
made, and no outcome of it changes the installation, its receipts or its reported success.

**INV-252 — Smoke execution is bounded and does not expose installation values.** Explicit effect
boundaries preserve trust, secret isolation, zero runtime dependencies and bounded execution;
persistent reports retain only safe, installation-qualified evidence. Explicit `--show-response`
permits bounded current-output inspection under §170.5 without application persistence.

**INV-254 — The test from Installed is selected, reviewed and inert.** It runs only after the person
selects installed MCP installations on Installed or opens one, reviews the declared calls and
confirms. It covers exactly those installations, refuses a selected non-MCP installation by name,
and no outcome of it changes an installation, its receipts or its configuration.

# 171. OpenCode plugin artifacts

Status: **ACCEPTED 2026-10-15 (D-406)**. Adds one artifact kind. It preserves §169's ownership,
naming and layout rules and the security invariants that hold for every kind.

## 171.1 What a plugin is

A plugin is a JavaScript or TypeScript module that a harness loads into its own process and runs
for every session. OpenCode is the one harness this release measures. Its plugins can add tools,
change configuration and rewrite the messages a model sees. A plugin is therefore code execution
with the person's permissions, not content the harness reads. The kind is `plugin`, and its
manifest schema is `aart-cli.dev/plugin/v1`.

A plugin artifact is the plugin's reviewed tree: the module, and whatever else it reads beside
itself, such as the skills the superpowers plugin registers from its own directory. The manifest
names one entry module inside the payload. It must be a selected payload file ending in `.js`,
`.mjs` or `.ts`.

## 171.2 Vendored bytes, never a fetched spec

The harness never fetches a plugin. OpenCode can load an npm spec or a git URL at startup, and an
artifact registered that way would run whatever that spec resolves to on the day it resolves,
which is not what anyone reviewed. A plugin artifact is installed as the immutable, digest-pinned
payload a Registry approved. It is materialized into the installation's private tree under the
harness's own directory (§169.3), and the harness is told to load it from there by path.

AART does not install a plugin's dependencies. A payload whose root `package.json` declares
runtime `dependencies` or `optionalDependencies` is refused at compile time. It would install
cleanly, then fail inside the harness, or fetch packages the first time it ran. Development-only
declarations are not runtime dependencies.

## 171.3 Registration

Installing a plugin owns one entry of the harness's plugin list and nothing else in the file:
- OpenCode 1.x reads that list from the `plugin` key of `opencode.json` at the chosen scope's root:
  the project root for Project, the opencode config directory for User.
- The entry is the entry module's path relative to the directory holding that file, so a project's
  committed configuration names no machine-specific path.
- The installation's tree and therefore its entry follow the versionless installed-name rules of
  §169.7. An update keeps the same entry, and two Registries or two scopes never share one.

OpenCode 2.x reads a `plugins` key that accepts only the directory form. It is not measured in
this release. Supporting it is a new measured target, not a fallback written beside this one.

A harness that measures no plugin target refuses a plugin it was asked for by name and is left
out when it was not, exactly as for every other kind.

## 171.4 Review and risk

Registering a plugin is `high-risk-execution`. Fast never hides it (INV-151): Ready states in plain
words that the install runs code inside the harness. Verbose also names the entry module and the
file and key that register it. A policy whose risk ceiling is below high-risk execution refuses
the install before any mutation.

## 171.5 Lifecycle

- Uninstall removes exactly this installation's entry from the list, leaves the list and every other
  entry as found, and removes the installation's tree.
- Status and verification compare the payload against its recorded digest and the entry against
  the receipt. A missing or edited entry is drift and is never assumed away.
- Repair re-materializes the payload from the installation's own copy and re-registers the entry.

A plugin's internal names, such as the skills it registers or the tools it adds, are its own
content. AART neither rewrites nor namespaces them, and says so on Details.

## 171.6 Acceptance invariants

**INV-255 — A plugin is vendored and digest-pinned.** The harness loads a plugin only from the
installation's private copy of an approved payload, registered by a relative path. No install,
update or repair writes an npm spec, a git URL, or a path outside the installation's tree, and AART
never fetches a plugin's dependencies.

**INV-256 — A plugin is reviewed as high-risk execution.** Every plan that registers a plugin
carries `high-risk-execution`, and Fast states it in plain words. A policy ceiling below that
refuses the plan before mutation.

**INV-257 — A plugin owns one list entry and one tree.** Install, update, repair and uninstall
change only this installation's entry and tree. The rest of the configuration file and every other
entry in the list are left as they were found.

# 172. Per-artifact installation flow

Status: **ACCEPTED 2026-10-16 (D-413)**, on the owner's request. It replaces the 05–09 part of
§161.5 and narrows the input-entry rule of §169.4 and INV-246 for one installing operation. The
ownership, naming, layout and secret-handling rules of §169 are unchanged: every installation
keeps its own configuration file, its own credential item and its own lifecycle.

Every screen in this flow works on every artifact the operation installs together, whether that is
one artifact or several. Each screen shows the artifacts as groups. No screen forces a person to
go through the artifacts one at a time.

## 172.1 The flow

**Amended 2026-10-28 by D-497 (CP-46, §209):** 07a Scope comes before 07 Configuration.

```text
Marketplace
   ↓
05 Harnesses            one set of harnesses per artifact
   ↓
07a Scope               [only if a choice exists]  project or user per artifact and harness
   ↓
07 Configuration        [only if needed, optional]  one set of answers per artifact
   ↓
07b Credentials         [only if needed, optional]  entered once per artifact, or skipped
   ↓
09 Ready to Install
   ↓
10 Installing → 11 Success
```

A screen that has nothing to ask is not shown (§161.5). Back returns to the previous screen and
keeps every answer that is still valid. An answer becomes invalid when the thing it answers is no
longer chosen.

## 172.2 05 Harnesses

Each artifact lists the harnesses on this machine that can host it. A person ticks one or more
harnesses for each artifact independently. The same harness may be ticked for one artifact and not
for another. Each artifact must keep at least one harness. To leave an artifact out, a person goes
back and changes the selection; unticking every harness does not do it. An artifact with exactly
one eligible harness has it ticked already. Otherwise nothing is ticked until the person chooses.
Each ticked pair of artifact and harness is one installation (§169.4) once its scope is known.

## 172.3 Entering inputs during installation is optional, and nothing blocks

Installing a whole Collection of MCPs should not mean answering every input of every member
before anything installs. Nothing in this flow blocks: not the form, not the transaction, and not
the launcher.

07 and 07b never block. Every field may be left unanswered, and one action, `Set later`, skips
everything still unanswered on that screen. A skipped input becomes the placeholder `AART_NOT_SET` in each
installation it belongs to: in that installation's configuration file for an ordinary input, and
in its own provider item for a secret. Validation applies to an entered answer, never to the
placeholder.

The installation then completes like any other. The launcher starts and passes `AART_NOT_SET` on as the
value, as it would any value. A placeholder is something to set later, not a refusal. Credentials
and variables (§161.8) sets it one installation at a time, replacing that one installation's value
and nothing else.

Doctor, Installed and Credentials and variables warn about every value that is still the
placeholder: `Still the AART_NOT_SET placeholder — set it in Credentials and variables`.
- For an ordinary value the warning comes from comparing the text.
- For a secret it comes from comparing inside the provider's own processes, with only a match
  count returned. This process never reads the value.

A warning never stops an operation.

## 172.4 07 Configuration

The form asks each ordinary input once per artifact. An answer applies to every installation of
that artifact that this operation creates. Each of those installations is then written its own
configuration file holding its own copy of the answer. After the install, the copies are
independent. Credentials and variables shows and edits them per installation, and editing one
installation never changes another.

This is the only sharing there is. It happens while one operation creates the installations, and
it copies answers between installations of the same artifact. Nothing is pre-filled from another
artifact or from an existing installation that is a different owner. There is no global input pool,
and later operations never propagate a value. Defaults declared by the artifact are pre-filled as
before. An input left at its declared default is an answer, not a skip.

## 172.5 07a Scope

There is one row for each artifact and harness pair. The scopes offered for a pair are the ones
the artifact declares, minus Project when there is no project root. Each pair starts on the
default scope in Settings when it is offered, and on the only offered scope otherwise. A person
may change any pair. The screen is skipped when no pair has more than one scope.

One operation may therefore install into both scopes. It is still one reviewed transaction with
one review digest. It holds the mutation lease of every scope root it writes (acquired in a fixed
order), and each harness configuration is written under its own scope's root.

## 172.6 07b Credentials

**Amended 2026-10-28 by D-495 (CP-46, §207):** Enter on a credential lets the store's prompt ask
for it on 07b, at once, not while installing. The bullets below on marking and on prompting during
the transaction are superseded by §207.

**Amended 2026-10-26 by D-487 (CP-45, §201):** 07b no longer reads a credential. It decides which
credentials the credential store's own prompt asks for while installing, as `consume install` does.
A person who cannot find a credential leaves it, and the install still completes.

- The screen lists each secret input once per artifact. A secret already stored for the same
  existing owner shows `Configured securely` and asks nothing.
- Nothing is typed on 07b. Enter on a secret marks it `asked when installing`, and Enter again
  unmarks it. Set later unmarks every row. The UI state holds only which rows are marked. No
  value of a credential is held in the process, a frame, the plan, a receipt, a log or argv.
- While installing, the transaction lends the terminal to the store's own prompt for each marked
  credential, once per installation's own provider item, after the input's guidance. The person
  types into the store, and aart-cli never sees the value. Every unmarked secret is stored as the
  placeholder without prompting, over standard input on macOS. Both are removed again if the
  transaction rolls back.
- If the person cancels the store's prompt, the install finishes as partial, and the credential
  is set in Credentials and variables.
- Leaving before confirming on Ready forgets the marks.
- Ready lists, in every mode, which credentials the store will ask for, and which inputs are being
  left as the `AART_NOT_SET` placeholder.

## 172.7 Acceptance invariants

**INV-258 — Harness choice is per artifact.** Every installation an operation creates is a ticked
artifact and harness pair. No harness choice for one artifact adds, removes or narrows an
installation of another.

**INV-259 — One answer per artifact, then independent copies.** One operation asks each ordinary
input and each secret at most once per artifact. It writes a separate copy, or a separate
placeholder, into every installation of that artifact that it creates. After the operation, no
value is shared, and changing one installation changes nothing else.

**INV-260 — Scope is chosen per installation.** Each artifact and harness pair installs into the
scope chosen for it, which starts on the Settings default when that is offered. A transaction that
writes both scopes holds both leases and writes each harness configuration under its own root.

**INV-261 — Installation never waits or blocks on an input.** Every input is entered or skipped
before Ready, and the transaction stores each installation's values without prompting. A skipped
input is stored as the placeholder `AART_NOT_SET`. Nothing refuses it: the install completes and the
launcher starts. Doctor, Installed and Credentials and variables warn about it without reading a
secret value. No secret value reaches UI state, plan, receipt, log or argv.

# 173. Collections end to end, Registry-owned versions, install paths and views

Status: **ACCEPTED 2026-10-16 (D-422, D-423, D-424; §173.3 amended by D-430)**, on the owner's
request (B-067, #72–#75, #53, #54). It makes §145.1 reachable from a source repository to an installed harness, moves
versions from source manifests to the Registry, adds a default install path beside the §172 flow,
and removes the routes into a Registry that D-375 forbids. §145, §161.4, §165.5, §172 and §169
still hold where this section does not narrow them.

## 173.1 Source manifests carry no version

A source repository says *what* an artifact is. It never says which version it is.
- An artifact manifest (`aart-cli.yaml` / `aart-cli.json`) has no `artifact.version`. A manifest
  that still carries one is refused, and the refusal says to delete the field because the Registry
  assigns versions.
- A source repository defines no Collection (§173.3). A Collection manifest in a source is refused
  by `author check` and by Sync, and the refusal says a Collection is created in the Registry.
- Everything a Registry version is built from is the manifest plus the payload it selects. A
  dependency descriptor (`requirements.txt`, `pyproject.toml`, `uv.lock`) is part of that payload,
  so changing a pinned package is a change like any other.

## 173.2 The Registry assigns versions by counting approved changes

Sync compares each source manifest with the Registry's approved versions of the same artifact in
the target Registry. The comparison uses the digest of the manifest and its selected payload.
- If an approved version has the same digest, nothing changed; the Candidate is that version.
- Otherwise the Candidate is a change, and the Maintainer sees it in the Sync result and in
  Candidates as new or changed, with the version it will become.
- The version is the next one after the highest approved version (D-423). Patch counts up to 5,
  then minor counts up to 3, then major. `1.0.0`, `1.0.1` … `1.0.5`, `1.1.0` … `1.3.5`, `2.0.0`.
  The first approved version is `1.0.0`.
- Approval publishes exactly that version. If another approval took it first, the Candidate is
  refused as stale and the next Sync offers the following number. A published version is never
  rewritten (INV-207).

Version constraints keep their SemVer meaning: `^1` is every `1.x.y`, so it covers `1.0.0`–`1.3.5`.
A version says how much an artifact has changed, not whether a change is breaking.

## 173.3 A Collection belongs to the Registry

A Collection is curation: a Registry maintainer's statement that some approved artifacts go
together. It has no payload and is not authored in a source repository (D-430).
- **Creating and changing.** The Registry maintainer creates a Collection, or changes its summary
  or members, in the Maintainer TUI's Collections view and with `registry collection NAME
  --summary TEXT --include KIND/NAME …`. A member is an artifact this Registry has approved, from
  any of its sources. A member is named by kind and name. It carries no version constraint.
- **Reviewed like a promotion.** Each change is one Registry transaction, with the same
  validation, Registry diff and commit as a promotion (screens 43–45 in the TUI, `--yes` with the
  digest in the CLI). Nothing is written to the Registry before that review.
- **Versions pin exact members.** Each Collection version records the exact approved version of
  every member. The first version is `1.0.0`. Each later change takes the next version by D-423.
  A change that pins exactly what the current version pins publishes nothing.
- **Automatic bump.** When a promotion approves a new version of an artifact that is a member of
  a Collection, the same transaction publishes that Collection's next version. The new version
  pins the new member version and keeps every other member's pin. The Registry diff and the
  `registry promote` review show this bump beside the artifact. A Collection is therefore never
  behind the artifacts it names.
- The Registry reads each version back as a Collection, and refuses one whose bytes do not match
  its version record.

## 173.4 The Marketplace offers approved Collections

The configured Marketplace lists each approved Collection as one row, at its highest version. That
version's pinned members are what installing it installs (§145.1). A member may also be approved
and offered as an artifact of its own; installing it alone is an ordinary artifact install.

## 173.5 Installing a Collection treats it as one artifact

The §172 flow applies, with the Collection taking the place of one artifact (D-422).
- **05 Harnesses.** A harness is offered for the Collection only when it can host every member.
  A harness that cannot is shown as not offered, and the reason names the first member it cannot
  host. There is one choice per Collection and harness, and it applies to every member.
- **07a Scope.** A scope is offered for a Collection and harness only when every member has a
  target in it there. The chosen scope applies to every member.
- **07 Configuration / 07b Credentials.** Each member's inputs are asked once per member
  artifact, under that member's name, and `Set later` skips them (§172.3). Nothing blocks.
- Every member is installed into every chosen harness, or the Collection is not installed there.
  There is no partial Collection install (INV-213).

## 173.6 An installed Collection

Installed, Doctor and uninstall show an installed Collection as one row with its members under it.
Its health is its members' health and names the member that needs attention (INV-186). Uninstalling
it removes each member installation it owns, and keeps any member that is also owned directly or by
another Collection (INV-215).

## 173.7 Default path and custom path

After choosing in the Marketplace and pressing Install, a person chooses the path:
- **Default** takes the harnesses, scope and Python installer from Settings and goes straight to
  07/07b if anything needs entering, and to Ready otherwise. The harnesses are the Settings
  harnesses that are detected and can host the artifact; with none set in Settings, every detected
  harness that can host it. The scope is the Settings default scope when offered, else the only
  offered one.
- **Custom** is the §172 flow: 05, 07, 07a, 07b, Ready.

The choice is screen **05p Install Path**, between Install and 05, with Default first. It states
what Default will use. When a Settings value cannot be applied to the selection, Default does
not guess and does not narrow: it says which values do not fit and leaves the person on 05p to
choose Custom (§176, superseding D-435's fallback to 05).

Settings holds the default harnesses beside the default scope and Python installer: screen 28
draws one on/off row per detected harness, and with none on, Default uses every detected harness
that can host the artifact. The CLI has no path choice: `marketplace install` names its harnesses
with `--profile`.

## 173.8 Marketplace and Installed columns

Marketplace rows show, besides name, kind and version:
- installation status: not installed, installed, or update available;
- scope: `user`, `project`, or both, with the number of projects it is installed in;
- harnesses it is installed into;
- eligible harnesses: the detected harnesses that can host it;
- inputs still `AART_NOT_SET`, as a count.

Installed lists each installation as its own row (artifact, Registry alias, harness, scope and
project), with the same columns where they apply. Each installation keeps its own configuration
(§169.4). The details, such as which projects and which harnesses, are under More info, not in
the row.

## 173.9 Adoption by manifest is the only way in

A Registry is never where an artifact is defined (D-375). The `registry vendor`, `vendor-batch`,
`discover` and `revendor` commands, and every other route that writes canonical artifact content
without a source manifest, are removed. A Collection is not an artifact: §173.3's `registry
collection` writes only Registry curation over approved artifacts, through a reviewed transaction. What a Registry holds for an approved
version is its **content mode**: `RegistryContentMode = SelfContained | PinnedReference` (D-376),
and `promote --mode` takes `self-contained` or `pinned-reference`. INV-019, INV-020, INV-025,
INV-204 and INV-207 keep their meaning with these words.

## 173.10 Acceptance invariants

**INV-262 — Versions belong to the Registry.** No source manifest carries a version. The Registry
assigns every version by D-423 from the approved history, and an unchanged manifest and payload
never produce a new version.

**INV-263 — A Collection installs whole.** A Collection is offered for a harness and scope only
when every member can be installed there, and an install writes every member or none.

**INV-264 — A Collection is one choice in the flow.** One harness and one scope choice applies to
every member. Inputs are still asked once per member artifact and may be set later.

**INV-265 — The default path asks nothing Settings already answers.** It goes from Install to
the inputs, or to Ready, using the Settings harnesses, scope and Python installer.

**INV-266 — A Collection follows its members.** A Collection is defined only in its Registry, and
each version pins exact approved members. A transaction that approves a new version of a member
also publishes the next version of every Collection naming it. No Collection's current version
pins a member version older than that member's current approved version.

**INV-267 — Only manifests adopt.** Canonical Registry content is written only from a source
manifest.

# 174. An author's local checkout is read as Git would commit it

Status: **ACCEPTED 2026-10-17 (D-438)**, on the owner's request: AART works on an author's local
repository out of the box, without conditions on how the author keeps it.

A `source-local` Source, `aart-cli author check`, and `registry scan` / `registry promote
--checkout` read a directory the author works in. When that directory is inside a Git work tree,
the Source is the files Git would commit from it: the tracked files and the untracked ones its
ignore rules do not exclude, each read from the working tree. A virtual environment, cache or
editor directory the author ignores is not part of the Source, so its symlinks, special files and
size neither refuse nor bound it. A directory outside Git is read whole. Every file that is read is
still read without following links, and a symlink or special file Git would commit is still
refused. AART's own managed snapshots are read whole, as before.

**INV-268 — Ignored files are not the author's Source.** A path the author's Git ignore rules
exclude from a local checkout never enters a Source snapshot, and never makes reading it fail.

# 175. Three roles, three command families: consume, maintain, author

Status: **ACCEPTED 2026-10-17 (D-439)**, on the owner's decision. Supersedes the single `source`
command family and the `registry-*` / `source-*` source kinds wherever they meet a user.

## 175.1 The two kinds of repository

- An **Upstream repository** (short: *upstream*) is a repository its authors keep. A Registry
  maintainer connects it, synchronizes it and promotes its Candidates. A consumer never sees one.
- A **Registry** is a namespace of approved artifact versions taken from upstreams, plus the
  Collections its maintainer defines from them. A Registry authors no artifact of its own; a
  Collection is the only thing it creates. A consumer installs from Registries and from nothing
  else.

Artifacts flow one way: upstream → Candidate → Registry → consumer. "Source" is no longer a name
either role sees.

## 175.2 The command families

Every role-specific command lives under its role's verb; commands about the whole installation of
aart-cli stay at the top level.

```text
aart-cli consume registry add|list|sync|remove|resubscribe|health   --kind local|git
aart-cli consume list|search|install|update|uninstall|status|setup|receipt|health
aart-cli consume mcp test

aart-cli maintain upstream add|list|sync|remove|resubscribe|health|scan|adopt|check   --kind local|git
aart-cli maintain candidate list|promote
aart-cli maintain registry init|collection|format|validate|lock|build|audit|diff|test|publish|push

aart-cli author init|check

aart-cli doctor|upgrade|reset|security
```

- `consume registry sync` refreshes what a Registry offers and then points at `consume update`,
  whose review lists each installed artifact a newer approved version would replace (§82, §83).
  `sync` never changes installed artifacts; `update` never changes a Registry. Naming those
  artifacts in `sync`'s own output is B-201.
- `maintain upstream sync` discovers Candidates in connected upstreams; `scan` reports Candidates
  in one explicit checkout without changing anything; `adopt` and `check` are today's `registry
  adopt` and `registry check-upstream`. `maintain candidate promote` is today's `registry promote`.
- The kind is the family plus `local` or `git`; the four `registry-*` / `source-*` kinds go.
- `security` stays at the top level: consumers verify attestations and maintainers scan.
- `source`, `marketplace` and the top-level `registry` family are removed, without aliases.

## 175.3 Configuration and TUI

- Configuration keeps two lists, `registries` and `upstreams`. Consumer commands, screens and
  policy read only `registries`; the policy's direct-source switch goes, because a consumer can no
  longer connect an upstream at all.
- The consumer TUI's Registries screen lists Registries only. Registry Maintainer Mode has three
  areas named as the CLI is: **Upstream repositories** ("Author repositories this Registry takes
  artifacts from"), **Candidates**, and **Registry** (Collections, Validation, Publish).

## 175.4 A clean start that keeps the old state

AART keeps no migrators (§169), so a state written by another version, or one a person broke by
hand, must never leave aart-cli unusable. `aart-cli reset` therefore moves the AART-owned state out
of the application home instead of deleting it, and aart-cli starts as on a new machine:

- **Backup, not deletion.** Every target the factory reset plan names moves, by rename, into
  `<application home>-backups/<UTC timestamp>/` beside the home (`~/.aart-cli-backups/...`, or
  beside `AART_CLI_HOME`). The command prints that directory. Nothing is copied and nothing is
  removed; the backup holds no secret values, because the home holds none (§169).
- **One confirmation.** The step is reversible, so one typed `RESET AART` (or `--yes`) replaces
  the two confirmations a deletion needed.
- **Going back.** `aart-cli reset --restore DIR` moves the current state into a new backup first,
  then moves `DIR`'s contents back into the home. Restoring a state another version wrote is for
  running that version again; this version does not read it.
- **Out of the box.** When startup cannot load the local state (an invalid or foreign settings,
  history or configuration file), the error names `aart-cli reset` as the way to a clean start.
- Projects, harness files and organization policy are untouched, as before. Artifacts already
  installed into harnesses stay there; after a reset AART no longer records them.

## 175.5 Author Mode in the TUI

Authoring is a role in its own right, not a CLI-only corner. Like Registry Maintainer Mode, **Author
Mode** is hidden by default and enabled in Settings (`[ ] Author Mode`); with it on, the TUI adds an
Author area beside the consumer one, and with it off no author navigation appears.

- **Workspace.** The author picks the directory of their upstream repository once (a normalized
  absolute path, remembered in AART settings, never inside the application home's content). The
  area reads it exactly as `author check` does: as Git would commit it (§174).
- **Check.** Runs `author check` over the workspace and lists every manifest with ok or its
  diagnostics, the same result the CLI prints; selecting one shows its errors in full. Re-run is
  one key.
- **New artifact.** Chooses a kind and a name and writes the template `author init` writes, into
  the workspace or a chosen subdirectory; nothing existing is replaced, and the screen then shows
  that manifest's check.
- The area runs the same application code as `aart-cli author`, so a result never differs between
  the TUI and the CLI. It never connects the workspace as an upstream and never changes a Registry.

**INV-269 — A consumer reads only Registries.** No consumer command, screen or configuration entry
connects an upstream, and nothing a consumer installs comes from one.

**INV-270 — The first word names the role.** Every command specific to consuming, maintaining or
authoring is under `consume`, `maintain` or `author`; each noun means one thing within its family.

**INV-272 — Author Mode is the CLI's author family.** Every author action in the TUI is an
`aart-cli author` action with the same result; Author Mode is opt-in like Registry Maintainer Mode.

**INV-271 — A reset never destroys state.** `aart-cli reset` moves AART-owned state into a backup
it names and can restore; it removes nothing.


## 175.6 Marketplace holds artifact details and readable columns

Accepted 2026-10-17, on the owner's request (D-446). This narrows §161's standalone Artifact
Details screen and extends §173.8.

- **Details stay in Marketplace.** The separate Marketplace Artifact Details screen is removed.
  Every piece of information it provided is available for the artifact under the cursor through
  Marketplace's existing Verbose / More info control. This includes its existing provenance,
  security, harness compatibility, installation status, digest and declared input guidance fields. Browsing these details keeps the selection,
  search, cursor and install route in Marketplace. Install acts on marked offers, or on the
  offer under the cursor when nothing is marked, preserving the former single-artifact install
  without a preliminary tick. Collection preview and Installed details keep
  their own purposes.
- **Columns have headings.** Each Marketplace column has a visible heading identifying its
  meaning, including status, scope, harnesses and unset inputs (§173.8). Headings and cells use
  the same layout.
- **Narrow terminals keep the content.** A narrow Marketplace never ellipsizes or drops a
  heading or a cell value to make the columns fit. It wraps content into additional lines, or
  stacks labeled fields where columns would be unreadable. Row boundaries and the focused
  artifact remain clear; nothing requires opening another view to recover a truncated cell.
  When wrapping exceeds the terminal height, PgUp/PgDn scroll the content while headings and
  the navigation footer remain available; moving between offers keeps the focused row visible.
  §206 gives every other screen the same paging.

**INV-273 — Marketplace details stay with the offer.** Everything the retired Artifact Details
screen showed is available under More info on the focused Marketplace artifact, without losing
Marketplace state or introducing another details screen.

**INV-274 — Marketplace columns remain named and complete.** Every Marketplace field has a
visible heading or label, and narrowing the terminal never truncates its heading or value. (§196:
a value may be cut and marked `…` and a column left off and named, so that every offer stays one
line; a drawn heading is never cut, and a window wide enough shows every value whole.)

# 176. Default says which Settings values do not fit

Status: **ACCEPTED 2026-10-19 (D-452)**, on the owner's request (#82). This narrows §173.7.

Default means exactly what Settings says. When the person chooses Default on 05p, the install is
prepared from Settings as before (§173.7), and every Settings value is checked against what that
preparation measured for each selected artifact:
- **harness**: each Settings harness has to be detected and able to host the artifact. With no
  harness in Settings there is nothing to check, because Default uses every detected harness that
  can host it;
- **scope**: the Settings default scope has to be offered for the artifact;
- **Python installer**: when the selection declares Python dependencies, the Settings installer has
  to be one this machine and policy can use for it.

When any value does not fit, nothing is installed, narrowed or substituted, and no other screen
opens. 05p stays, with a block under "Default uses:" listing each mismatch once: the artifact (or
the whole selection, for a fact that holds for all of it), the Settings value and the reason, then
"Choose Custom". The cursor moves to Custom, and the Default row says it is not available with
these Settings. Choosing Default again checks again. Custom is the §172 flow, unchanged. When every
value fits, 05p and Default behave exactly as in §173.7.

A Collection is one artifact here, as on 05 (§173.5). The block carries artifact names, Settings
values and reasons only, never a configuration or secret value.

**INV-275 — Default never silently differs from Settings.** A Default install either applies every
Settings harness, the Settings scope and the Settings Python installer to every selected artifact,
or installs nothing and lists each value that does not fit.


# 177. The command reference is the parser

Status: **ACCEPTED 2026-10-19 (D-454)**, on the owner's request (#47).

The executable's parser is the only written command reference. `aart-cli docs` reads it when it
runs and prints it, so the reference always matches the installed version, works offline and adds
no runtime dependency:
- `aart-cli docs` lists every command with its one-line help;
- `aart-cli docs COMMAND…` prints that command's or group's description, usage, options and
  defaults, and the commands under a group; the words may also be given as one quoted argument;
- `--json` returns the same reference as one document: the program, its version, and for each
  command its path, help, description, usage and arguments (name, flags, metavar, help, default,
  choices, required, nargs);
- an unknown command is a usage error (exit `2`) that names it and points to `aart-cli docs`.

Every command and group carries a description, and every argument and option a help text. A
repository-root `llms.txt` written by hand tells an agent to run `aart-cli docs --json` and links
the few guides; it names no other command, so a rename never makes it stale. `make docs-check`
hands every `aart-cli …` (or `python -m aart_cli …`) line in a fenced block of the README and the
user-facing documents to the same parser and fails on one it rejects. `docs/refactor/` and this
specification are not held to it: they record history and the target.

**INV-276 — The documented command surface is the shipped one.** Every command, option and default
the reference prints is read from the parser the executable runs, and no user-facing document shows
a fenced command that parser rejects.


# 178. Marketplace lists a page of ten, one line per offer

Status: **ACCEPTED 2026-10-21 (D-456)**, on the owner's request (CP-34). This narrows §175.6.

- **Ten offers at a time.** Marketplace draws the page of ten offers that holds the cursor
  (1–10, 11–20, …) and, when there are more than ten, says which ones it shows and of how many.
  Moving the cursor past the page edge turns the page. Search, filters, selection and the install
  route still cover every offer, not only the page.
- **More info stays on screen.** Because the list is at most ten offers, the More info block for
  the offer under the cursor follows the list on the first screen instead of after every offer.
- **One line per offer.** Each column is as wide as its widest value. When the terminal has room,
  every offer is one line, directly under the headings, with no blank line between offers. Only a
  terminal too narrow for that wraps the widest columns first; INV-274 still forbids truncation,
  and the stacked layout keeps a blank line between offers because each one spans several lines.

**INV-277 — The focused offer's details fit beside the list.** Marketplace never draws more than
ten offers at once, the drawn ones always include the offer under the cursor, and in the grid
layout each offer is one line whenever the terminal is wide enough for every value.


# 179. A kind the harness only reads keeps no private copy

Status: **ACCEPTED 2026-10-21 (D-457)**, on the owner's request (CP-34). This narrows §169.3.

§169.3 gave every installation a private tree under its harness, and a Skill, guideline, hook or
memory got one too: its payload was copied into `<harness>/aart-cli/<kind>/<alias>/<name>/payload`
and copied again to where the harness reads it. The harness reads only the second copy, so a
project held every such artifact twice.

- **Delivered from the canonical object.** A Skill, guideline, hook or memory is delivered or merged
  straight from the payload of its canonical object in the application home
  (`objects/sha256/…/payload`). No `aart-cli/` subtree is written for it beside the harness.
- **The object is the installation's evidence.** The receipt records that payload path. Doctor
  measures it against the approved payload digest, and repair re-delivers from it. The installed
  object reference (§169.2) keeps it from collection while any installation records it.
- **Uninstall withdraws only what was placed.** Removing such an installation withdraws its
  deliveries, merged regions and settings entries and leaves the canonical object to the store.
- **Loaded kinds keep their tree.** An MCP server (payload, runtime, launcher, configuration) and a
  plugin (loaded by the harness from its tree) keep the private tree §169.3 describes.

**INV-278 — One copy where the harness reads.** Installing a Skill, guideline, hook or memory writes
nothing beside the harness except what the harness reads, and its delivery sources lie in the
canonical object its receipt records.



# 180. An adopted name belongs to its upstream

Status: **ACCEPTED 2026-10-21 (D-458)**, on the owner's request (CP-34). This narrows §173.2 for
repository adoption.

§173.2 compares a manifest with the approved versions "of the same artifact", and the artifact was
only its `kind/name`. Adopting `skill/brainstorming` from a second repository therefore made it the
next version of the first repository's `skill/brainstorming`: two authors' work under one name and
one version line, with nothing said.

- **One name, one upstream.** A `kind/name` this Registry adopted or promoted belongs to the
  upstream URL its versions record. Adopting it from that URL works as §173.2 says. Adopting it from
  another URL is refused before anything is written, and the refusal names both URLs.
- **The scan says so first.** A repository scan marks each artifact whose name the Registry already
  took from another upstream and names that upstream, on the CLI (`held_by`) and on screen 46d.
- **Another Registry name.** The Maintainer can adopt such an artifact under another name:
  `aart-cli maintain upstream adopt … --artifact KIND/NAME@VERSION --rename KIND/NAME=NEW-NAME`, or
  by typing it in the artifact's Registry name row on screen 46d. The copy is then its own artifact,
  starting at `1.0.0`, beside the first. Its input digest is still the author's, so its upstream
  check compares like with like and proposes later versions under the Registry name.
- **Source promotion is not covered.** A Source records the location its surface was given (a URL
  on the CLI, a configured location in the TUI), so it is not yet a stable upstream identity.

**INV-279 — An adopted name has one upstream.** Repository adoption never publishes a version of a
`kind/name` whose existing versions record a different upstream URL; it refuses, and the same
artifact can be adopted under a Registry name that is free or that the same upstream holds.


# 181. A Marketplace offer names its Registry and its upstream

Status: **ACCEPTED 2026-10-21 (D-459)**, on the owner's request (CP-34). This extends §173.8 and
§178.

The Artifact column read `alias/kind/name@version`. The Registry was buried in that coordinate, and
the row did not say where the work came from. Two Registries' copies of one name, or one Registry's
copies of two upstreams adopted under different names (§180), could not be told apart.

- **Columns.** A Marketplace offer's columns are, in order: Artifact, Registry, Upstream, Status,
  Scope, Harnesses, Unset. (§196: Artifact and Type are drawn by default, and the rest with `d`.)
- **Artifact column.** It is `kind/name@version`, and the Registry column is the alias that offers
  it. (§196: it is `name@version`, and the kind is the Type column.) A Collection's row shows the Collection in Artifact and its alias in Registry, and leaves
  Upstream empty.
- **Upstream column.** It is the last two path segments of the URL the version's provenance
  records, read as `owner/repository`. Scheme, host, port, credentials and a trailing `.git` are
  dropped, so the row never shows a secret. An offer with no recorded upstream leaves it empty.
- **More info.** It shows the whole upstream URL, with any credentials redacted (INV-052), as the
  `Upstream` field.
- **Rows still keyed by offer.** Selection, the cursor and installation still name the offer by its
  full coordinate, and only the drawn column drops the alias.
- **Wrapping.** The added columns make the grid wider. A terminal too narrow for every value on one
  line wraps as §178 says, and INV-274 still forbids truncation.

**INV-280 — An offer's row names where it is offered and where it came from.** Every Marketplace
artifact row shows, with details (§196), its Registry alias and its upstream as their own columns,
never a credential, and More info shows the redacted whole upstream URL.


# 182. Configuration, not Unset

Status: **ACCEPTED 2026-10-21 (D-460)**, on the owner's request (CP-34). This replaces the unset
inputs column of §173.8 and §181.

The last column was `Unset`, with values such as `3 not set`. The owner could not tell what it
meant.

- **Heading.** The column is `Configuration`, on Marketplace and on Installed.
- **Values.** `configured` when every input of what is installed has a value.
  `not configured (N missing)` while N inputs still hold `AART_NOT_SET`; on Marketplace, N is
  summed over the offer's installations, because each keeps its own (§169.4). An offer nothing
  installs leaves the column empty.
- **Not health.** Installed's health column keeps its own words (`ready`, …). Configuration says
  only whether the inputs have values, the same condition that makes §170.2's installation
  configuration stage `NOT CONFIGURED`.
- **Widths.** No column is narrower than its heading, so the header line names every column in
  full (INV-274). The grid still fits an 80-column terminal.

**INV-281 — Configuration is said in words.** Every Marketplace and Installed row that has an
installation says `configured` or `not configured (N missing)` under the heading `Configuration`,
and N is the count of inputs still holding `AART_NOT_SET`.


# 183. Collections are found, kept and placed plainly

Status: **ACCEPTED 2026-10-21 (D-461, D-462, D-463)**, on the owner's request (CP-34). This
extends §173.3's screens 51 and 52.

The owner, with two Registries and many approved artifacts, found Collections hard to use. The
editor listed every artifact with no way to find one. A refused Continue brought the editor back
empty, saying "Open a Collection from screen 51 first". The refusal talked about promotion. Nothing
said which Registry the Collections belonged to.

- **Search in the editor.** On an artifact row of the Collection Editor, `/` opens the filter
  Marketplace has. It matches the artifact's `kind/name`, case-insensitively, and keeps the Name,
  Summary and Continue rows. On the Name and Summary rows `/` is a character. A filter hides rows
  and never unticks one. The selected count includes ticks the filter hides, and Continue saves
  them. When the filter hides the row under the cursor, the cursor moves to the first match. Esc
  first clears an applied filter, and a second Esc leaves.
- **The editor keeps its Collection.** Continue's review stays about the Collection being
  edited. A refusal, or Back from the review, returns to the same Collection with its name,
  summary and ticks.
- **The refusal says where.** A Registry change is written into the checkout `aart-cli` was
  started in. When that directory is another Git repository, Collections, promotion and bulk
  promotion refuse before planning. The refusal names that directory, the Registry it is not, and
  the configured Registry location to start `aart-cli` in.
- **No screen numbers.** No message, status or refusal names a screen by its number. Screen
  numbers are this specification's index, not the reader's. A message names the screen as its
  heading does.
- **Collections name their Registry.** The Collections screen says "Collections of Registry
  ALIAS", and the editor says "New Collection in ALIAS" (or the Collection and version). Both say
  that saving writes into the Registry checkout `aart-cli` was started in. On the Registry screen,
  `o` is offered only while the cursor is on a Registry row, and opens that Registry's
  Collections.

**INV-282 — The editor finds an artifact by name.** On the Collection Editor's artifact rows `/`
filters the artifacts by `kind/name`, the form rows stay, and every tick, shown or hidden, is
counted and saved.

**INV-283 — A refused or abandoned Collection review returns to its Collection.** After a refusal
or Back, the Collection Editor shows the same Collection, draft and ticks. No user-visible message
names a screen by number.

**INV-284 — Collections name their Registry.** The Collections screen and the Collection Editor
name the Registry they belong to and where saving writes, and `o` opens only the Collections of
the Registry under the cursor.


# 184. Column headings are named and ruled off

Status: **ACCEPTED 2026-10-22 (D-464)**, on the owner's request (CP-34). This extends §173.8,
§181 and §182.

On Marketplace the heading line sat directly on the first offer, so scrolling the list the owner
could not tell headings from rows. Installed drew its cells (`ready  configured`) with no heading
at all.

- **Rule.** Under the heading line of Marketplace's grid and of Installed, a rule of `─` runs under
  each heading, starting where the heading starts and as wide as its column, with the column gap
  between rules. The rows start on the next line.
- **Installed headings.** Installed's columns are headed `Artifact`, `Health`, `Scope`, `Project`
  and `Configuration`, on the same grid as its rows. A Collection's row fills only Artifact and
  Health.
- **Narrow Marketplace.** The stacked form labels each field, so it has no heading line and no
  rule.

**INV-285 — Headings are named and ruled off.** Wherever Marketplace or Installed draws a heading
line, the next line is a rule under each heading, as wide as its column, and every heading starts
where its cells start.


# 185. The default branch others install from holds only remote upstreams

Status: **ACCEPTED 2026-10-22 (D-467)**, on the owner's request (CP-35). This extends §173.9 and
§180.

A maintainer tried artifacts out by promoting them from checkouts on their own machine into the
Registry, and pushed. Each such version records `origin.kind: "local"` and the checkout's absolute
path (self-contained), or a `local:` revision (pinned reference). Nobody else can check it against
its upstream, and §180 then holds the name against the real remote upstream. Nothing stopped it
reaching the default branch.

- **The audit names them.** `aart-cli maintain registry audit` reports every approved version
  promoted from a local checkout, with its coordinate and the location it records, and says to
  adopt it from its upstream's Git URL instead.
- **A trial Registry still works.** Without `--for-default-branch`, the finding is a warning.
  `publish` runs this audit, so a maintainer's trial Registry still commits and is told.
- **CI refuses them.** `--for-default-branch` makes the finding an error. The workflow
  `registry init` generates runs the audit with it, so a pull request whose result holds such a
  version is red. The Registry has no setting that turns it off: the workflow is managed, and a
  hand-edited copy is refused.
- **Branch protection is the Registry owner's part.** The check stops a merge only when it is
  required on the default branch. The generated README says so; aart-cli does not change
  repository settings.
- **Adopt and promote are not refused.** A trial Registry is where local checkouts belong, so the
  refusal sits where content becomes what others install.

**INV-286 — The default branch holds only remote upstreams.** The generated Registry CI fails for
every snapshot holding an approved version, self-contained or pinned reference, promoted from a
local checkout. The plain audit reports each such version as a warning naming its coordinate and
recorded location.

# 186. `consume install` answers inputs on the command line

Status: **ACCEPTED 2026-10-22 (D-468)**, on the owner's request (CP-35). This applies §169.4's
non-interactive channel and §172.3-4 to `consume install` and `consume update`. **Amended
2026-10-26 by §201 (D-486):** `--secret-env` is removed, and a credential is asked for by the
credential store's own prompt.

An agent installing an MCP server without a terminal could not answer a required input. The command
prepared with no answers and refused, so such artifacts installed only through the TUI.

- **The flag names the artifact.** `--input ALIAS/KIND/NAME:INPUT=VALUE` answers an ordinary input,
  and repeats. A generic input id is never read from the environment.
- **One answer per artifact, as on 07.** The answer is copied into each installation of that
  artifact this operation creates (§172.4). Each installation still gets its own configuration
  file and its own credential item.
- **A declared default is an answer.** An ordinary input no flag answers takes its declared
  default, as 07's pre-filled field does.
- **A credential is never an argument.** The credential store's own prompt takes it when the
  reviewed run is applied (§201). Its value reaches no plan, receipt, file or output.
- **`--set-later` installs with placeholders.** Every required input left unanswered gets
  `AART_NOT_SET`, as 07's and 07b's Set later does (§172.3). Credentials and variables sets it
  later.
- **Mistakes are refused before anything is written.** The command refuses, all at once:
  - a malformed flag;
  - an artifact the operation does not install;
  - an input the artifact does not declare;
  - a credential given to `--input`;
  - an input answered twice;
  - a credential to store when no credential store is available.

  No refusal shows a value.
- **The refusal says what to type.** When required ordinary inputs stay unanswered, the refusal
  lists the flag that answers each one and mentions `--set-later`. The JSON form gives each input's
  `flag`, which is `null` for a credential.

**INV-287 — A headless install answers each artifact's inputs by name.** `consume install` with
`--input` or `--set-later` installs an artifact that has required inputs, with no terminal. Each
installation holds its own copy of each answer. A credential's value reaches only the credential
store, and every refusal happens before anything is written.

# 187. An optional input is asked, and reaches the server only when answered

Status: **ACCEPTED 2026-10-22 (D-469)**, on the owner's request (CP-35). This narrows §172.3-4.

An Enterprise agent found two problems:
- 07 asked only required inputs, so an optional one could not be given at install.
- Set later puts `AART_NOT_SET` into every field it is handed. An optional input that reached the
  server as that text was read as a value. A URL became `AART_NOT_SET/...`.

- **07 shows an artifact's optional inputs** whenever it asks about that artifact. Each is marked
  optional, follows the required ones, and is pre-filled with its declared default, if any.
- **An empty optional field is no answer.** It needs no acceptance, the input stays unbound, and the
  server applies its own default.
- **Set later never fills an optional input.** It keeps a valid value, empties anything else, and
  puts `AART_NOT_SET` only into required inputs. The same holds for `consume install --set-later`
  (§186).
- **The command line binds an optional input** only when `--input` gives it or it declares a
  default.

**INV-288 — An optional input is never the placeholder.** No install path, form or command line,
binds `AART_NOT_SET` to an optional input. An optional input nobody answered is absent from the
installation's configuration and environment.

# 188. The default branch others install from takes only an upstream's default branch

Status: **ACCEPTED 2026-10-22 (D-470)**, on the owner's request (CP-35). This extends §185.

A maintainer may adopt from any branch or tag of an upstream, which is how a change is tried
before it lands. A version adopted from a feature branch holds what the upstream has not accepted.
Once the Registry's default branch has it, everyone installs it.

- **The upstream decides what its default branch is.** It is the branch the upstream's `HEAD`
  names on its Git host: `main`, `master`, `trunk` or anything else. aart-cli neither assumes a
  name nor lets a Registry override it.
- **Adoption records it.** `upstream adopt`, and the next version `upstream check` proposes,
  record `default_branch` beside the ref in the version's `aart.repository-adoption` provenance
  record. It is true when the adopted commit is reachable from the upstream's default branch, so a
  tag on that branch counts. The record is left out when the acquisition cannot tell.
- **The plain audit warns** about a version recorded as off the default branch, naming its ref and
  upstream. A trial Registry still publishes.
- **The CI refuses.** `registry audit --for-default-branch`, which the generated workflow runs, is
  an error for every remote version not recorded as on the upstream's default branch. That covers:
  - a version adopted from another branch;
  - a version adopted with no record;
  - a version promoted from a Git Source rather than adopted;
  - every pinned reference, which adoption never writes.

  The audit reads committed bytes only, so Registry CI needs no access to private upstreams.

**INV-289 — The default branch takes only an upstream's default branch.** The generated Registry CI
fails for every snapshot holding a remote version whose adoption record does not say its commit
is reachable from the upstream's default branch. `upstream adopt` writes that record from the
upstream's own `HEAD`.

# 189. A uv-locked project installs exactly its lock

Status: **ACCEPTED 2026-10-22 (D-471)**, from an Enterprise agent's report (CP-35). This makes the
`type: uv` contract of §108 installable.

An artifact that declared `type: uv` validated and was then refused at install, so the only way to
ship it was to drop the lock and let each installation resolve its own versions.

- **The lock sits beside the project.** The lock of a `type: uv` contract is the `uv.lock` in the
  directory of its `pyproject.toml`, the only one `uv sync` reads. A lock declared anywhere else is
  refused when the manifest is read.
- **Only uv installs it.** A lock is meaningful to the resolver that wrote it (§109), so a host
  without uv refuses the install. It never installs the loose project instead.
- **Exactly the lock, into the installation's own environment.** aart-cli runs `uv sync --frozen
  --no-dev --no-editable --no-python-downloads` against the payload's project, with the
  installation's environment (§85, INV-044) as uv's project environment, and `--offline` when the
  install is offline. uv neither re-resolves nor rewrites the lock, makes no `.venv` in the payload,
  installs no development dependencies, links nothing back to the payload, and downloads no
  interpreter.

**INV-290 — A uv-locked project installs exactly its lock.** Installing a `type: uv` artifact puts
the versions its `uv.lock` pins into that installation's own environment, leaves the payload and
its lock unchanged, and is refused rather than resolved loosely when uv is not the installer.

# 190. The Registry view names what each promotion published

Status: **ACCEPTED 2026-10-22 (D-472)**, on the owner's report (CP-36). This refines §164.8.

Recent promotions on the Maintainer Registry view listed only digests: the snapshot each promotion
produced and the candidate ids it promoted. Nobody could tell from them which artifacts had been
promoted.

- **Names, not digests.** Each promotion is numbered, newest first, with how many versions it
  published. Under it, each version is listed as `kind/name@version`, read from the approved
  version that candidate became. The Registry's alias is the row's own and is not repeated.
- **Nothing is dropped.** A candidate that no approved version carries any more is still listed,
  as no longer in this Registry, with its shortened candidate id.
- **Digests stay in Verbose.** The description of the row under the cursor gives each promotion's
  content mode and the full snapshot digest it produced, and each version's name with its full
  candidate id.
- **The validity diagnostic names versions too.** An approved version with no promotion record is
  named as `kind/name@version`.

**INV-291 — The Registry view names what each promotion published.** No line of Recent promotions
outside Verbose is a digest. Every version a promotion published appears there by
`kind/name@version`, or as no longer in this Registry.

# 191. A published Collection passes the Registry's own checks

Status: **ACCEPTED 2026-10-22 (D-473)**, on the owner's report (CP-36). This refines §173.3.

A Collection published with `registry collection --yes` made the Registry fail its own `validate`,
`audit`, `build` and `format` with "required file is missing: artifact.json", so `publish` refused
to commit it and the generated Registry CI would have failed. Those checks compiled every
self-contained approved version as a native package, and a Collection's version is one
`collection.json` naming its pinned members, not a package.

- **A Collection's version is not compiled as a package.** Its bytes are still held to its approval
  like every approved version's. Its members are approved versions this Registry already checks.
- **Its members decide where it installs.** Nothing on the Collection names a harness. It is offered
  only where every member can be hosted (§173.5).

**INV-292 — A published Collection passes the Registry's own checks.** A Registry that passes
`validate`, `audit`, `build --check` and `format --check` still passes them after `registry
collection --yes` publishes a Collection of its approved artifacts.

# 192. Publishing a release to an internal index can be retried

Status: **ACCEPTED 2026-10-22 (D-474)**, on the owner's Enterprise rollout (CP-37). This refines
§126.3.

A fork that sets `AART_CLI_INDEX_PUBLISH_URL` publishes each release's wheel to its own index,
which is the recommended way for its Registries to fetch aart-cli. The upload used to be the last
step of the release job. An index that refused turned the release red although the Release and its
wheel already existed. A tag released before the variables were set, or whose upload failed, could
only be published by deleting and recreating its Release.

- **Its own workflow.** `publish-index.yml` uploads after the release has attached the wheel. A
  refusal fails only that workflow.
- **The Release's own bytes.** It downloads the wheel attached to the Release rather than building
  the tag again, so the index holds exactly what the Release carries. It needs no workflow
  artifact, which GitHub Enterprise Server refuses.
- **By tag, at any time.** Anyone with access runs it again for any released tag.
- **Safe to run again.** It first asks the install index (`AART_CLI_PIP_INDEX_URL`) for the wheel.
  The same file already listed is success, and nothing is uploaded. A different file under the same
  name is refused, and nothing is replaced. Only a file the index does not list is uploaded.
- **Unset publishes nowhere.** Without `AART_CLI_INDEX_PUBLISH_URL` the workflow does nothing,
  which is the public run. The variable decides where a checked wheel goes, never whether anything
  is checked (INV-072).

**INV-293 — Publishing to an internal index is idempotent and retryable.** For any released tag,
running the index publication any number of times leaves the index holding exactly the Release's
wheel, or fails without replacing a different file already there. A failed publication never turns
the release itself red.

# 193. A fork labels its wheel's version, so it never shares a filename with PyPI

Status: **ACCEPTED 2026-10-23 (D-476)**, on the owner's request to publish the public release to
PyPI (CP-39). This refines §192 and D-373.

The public `aart-cli` is published to PyPI. An Enterprise fork bakes its own default Registry into
its wheel, so its `aart_cli-X.Y.Z` holds other bytes than the public one. An index group that
proxies PyPI then lists two files under one filename. `publish-index` refuses the fork's upload
(INV-293), and an install from the group may receive the public wheel.

- **A label of the fork's choosing.** `AART_CLI_LOCAL_VERSION_LABEL`, such as `corp`, makes the
  fork's wheel `X.Y.Z+corp`, a PEP 440 local version. Unset labels nothing, which is the public
  build.
- **The pin still matches, and prefers the fork.** `aart-cli==X.Y.Z` matches `X.Y.Z+corp`, and pip
  prefers it over the public `X.Y.Z`.
- **Only the distribution's version.** The filename and the wheel metadata carry the label.
  `aart-cli --version` reports `X.Y.Z`, which is what a Registry's `.aart-cli-version` is compared
  with, so no Registry changes.
- **Refused, never normalised.** A label is lower-case letters and digits in dot-joined segments,
  with no leading zero on a segment of digits only. Anything else fails the release, so the label
  in the variable is the label in the filename.
- **Checked and recorded.** The release checks the built wheel's filename and metadata against the
  tag plus the label, and the release receipt records the label.
- **Published under its own name.** GitHub stores `+` in a Release asset name as `.`, so the Release
  shows `X.Y.Z.corp`. `publish-index` names the wheel from its own metadata, so the index lists
  `X.Y.Z+corp`, the only name pip installs (D-477).

**INV-294 — A labelled fork wheel is distinct from the public one and still satisfies the pin.**
With a label set, the released wheel's filename and metadata version are the tag's version plus
that label, `aart-cli --version` reports the tag's version, and `==` on the tag's version selects
it over the unlabelled one. The index receives it under that name, whatever the Release calls the
asset. With no label set, the build is unchanged byte for byte.


# 194. The TUI says what is new, and where to go for it

Status: **ACCEPTED 2026-10-23 (D-478)**, on the owner's report that a Collection approved in the
Registry stayed invisible until `s` was pressed, that nothing said a sync was due, and that Updates
never listed anything (CP-41). This refines §82, §83, §161.10 and §165.11.

- **The TUI looks at its Registries when it opens.** Before it takes the screen, the application
  observes each connected Registry under `sync.mode`, as every CLI read already does. `auto`, the
  default, publishes a newer approved snapshot and keeps the last known good one when the origin
  cannot be reached. `manual` only compares. Each Registry is named on the terminal before it is
  fetched.
- **Updates lists what has a newer approved version.** An installation is an update when a
  connected Registry now offers its artifact at a strictly newer SemVer version. The offers and the
  machine are joined where the screens are composed, so a sync shows its updates at once. A measured
  problem outranks an update. Installed and Updates show the version it moves to, as `Update → 1.0.1`.
  An Updates row is the installation, which is what the update action addresses (§169.3).
- **A Registry row says when its snapshot is not current.** It stays `connected` and keeps offering
  what it approved. Under it the row says, as applicable, that the origin has newer approved content
  and `s` syncs it; that the snapshot is stale, and how old; or that the origin could not be reached
  and the snapshot from that age is used (§165.11).
- **The Dashboard points at it.** The Updates entry carries `● N` and the Registries entry `● N to
  sync`; the Dashboard's counts are followed by a line naming each and where to go. Screen 28's
  *Show available updates* governs the Updates announcement only; Updates itself still lists them.
- **Sync is still not update** (§161.7). Nothing installed moves without a reviewed update.

**INV-295 — What the TUI calls an update is what a connected Registry offers newer.** An installed,
ready artifact is drawn as an update on Installed, Updates and the Dashboard exactly when a connected
Registry's current snapshot offers the same artifact at a strictly higher SemVer version, and an
opened TUI has observed each enabled Registry under `sync.mode` before drawing.

# 195. One installation is one row, measured and changed where it was made

Status: **ACCEPTED 2026-10-23 (D-479)**, on two owner reports: the TUI failed entering Installed and
Doctor when one MCP was installed in one harness for the user and in two projects, and User
Variables And Credentials drew those installations as one entry nobody could tell apart (CP-42).
This refines §169.3, §172 and §173.

- **The key is the whole identity.** A row, a focus and a lookup address an installation by its
  coordinate, harness and profile, scope, and concrete root (§169.3). Two installations that differ
  only in scope or root are two rows.
- **Every entry says which installation it is.** Wherever an installation is named to a person
  (User Variables And Credentials and its detail, a credential's dependants, Doctor's Collection
  members, the MCP test), it reads `artifact · harness · user` or
  `artifact · harness · project <directory>`. User Variables And Credentials has one entry per
  installation, holding only that installation's configuration file and credentials.
- **Measured where it was made.** An installation's harness entries are resolved against its own
  root, not against the directory aart-cli was opened in. Another project's installation therefore
  reads as it does in its own project.
- **Changed only where it was made.** Repair, update, uninstall and configuration changes resolve
  harness paths against this session's root for the installation's own scope, whatever scope
  Settings prefer. A user installation is therefore changed from any project, at user scope. On an
  installation another project owns they refuse, name it, and say which directory to open aart-cli
  in. Nothing is written. User and project rows ticked together are changed one scope at a time.
- **An update replaces, and adds nothing.** The newer version goes into exactly the installations
  chosen, each in its own harness, scope and root, and into no harness that did not have it.

**INV-296 — One installation is one key, and it is measured and changed only under its own root.**
Two installation keys are equal exactly when coordinate, harness label, scope and root are. Every
listed installation is drawn as its own row and named with its harness and scope (and project). Its
harness state is observed under its recorded root. No lifecycle or configuration action prepared in
one project writes for an installation recorded under another. An update creates no installation
that the installations it replaces did not already make up.

# 196. Marketplace leads with what an offer is; the rest is one key away

Status: **ACCEPTED 2026-10-23 (D-480)**, on a colleague's report, passed on by the owner: with seven
columns Marketplace was overwhelming to read and to move through (CP-43). This refines §173.8,
§178, §181 and §182.

- **Two columns by default.** A Marketplace row shows `Artifact` and `Type`. Artifact is the offer's
  `name@version`. Type says what it is: `Skill`, `MCP`, `Guideline`, `Hook`, `Memory`, `Plugin` or
  `Collection`. Both columns are always drawn.
- **`d` shows the details.** On Marketplace, `d` (Details) adds the other columns after these two,
  in order: Registry, Upstream, Status, Scope, Harnesses, Configuration, with the values §173.8,
  §181 and §182 give them. `d` again (Hide details) returns to the two columns. The footer names
  what `d` does next.
- **For this session.** The choice holds while aart-cli runs, across screens. It is not a Settings
  value, and each start begins with two columns.
- **Separate from More info.** `v` still shows or hides the More info block for the offer under the
  cursor (§175). The two keys are independent.
- **Nothing else moves.** Search, selection, the cursor, paging and installation still name the
  offer by its full coordinate. Showing or hiding columns never changes what is selected, what a
  search matches, or which offer is under the cursor.
- **One line per offer, always.** On the owner's request a Marketplace offer never takes a second
  line, and there is no stacked form. Each column is as wide as its widest value when the window
  has room. In a narrower window:
  - the detail columns give up width first, widest first, but never below their heading;
  - a value longer than its column is cut and ends in `…`;
  - a column with no room even at its heading's width is left off whole, from the right, and a
    line under the list says "Widen the window to see:" and names each one;
  - Type is left off before Artifact is narrowed, so an offer's name is cut only when it is the one
    column left.
  Every heading drawn is whole, and a window wide enough for every value shows each one whole.
  This replaces §175's wrapping and stacking and §178's wrapping for Marketplace. §184's headings
  and rules stay.

**INV-297 — Marketplace leads with what an offer is.** Without details every Marketplace row shows
exactly its `name@version` and its Type. With details it shows, after them, Registry, Upstream,
Status, Scope, Harnesses and Configuration. Toggling details never changes the selection, the search
or the offer under the cursor. Every offer is one line at every window width: a value is cut and
marked `…` rather than wrapped, a column with no room is left off and named under the list, and
Artifact is whole while any other column is drawn.

---

# 197. An artifact points to its own documentation

Status: **ACCEPTED 2026-10-26 (D-481)**, on the owner's request (CP-44). A summary is one line, and
an input's `help` is a few. Neither has room for a longer manual, the steps to obtain a credential,
or a configuration walkthrough. An author can now point to a page that has room. This refines §154,
§161 and §175.

- **One optional manifest field.** `artifact.documentation` in `aart-cli.json` is the URL of the
  artifact's documentation. It is a plain `http` or `https` URL, at most 2048 characters, with no
  user information. It has no credential-shaped text, no space and no terminal control or format
  character. These are the rules `help.obtain_from.url` already follows (D-263). It also has
  nothing aart-cli's redaction would hide, such as a token in the query, because the link is
  printed whole. An artifact without it shows no link, and aart-cli never invents one.
- **Approved with the package.** The compiler writes it into the canonical `artifact.json` as
  `documentation`. That makes it part of the approved package, reviewed when the artifact is
  promoted (§154.3, INV-160, INV-165). It is metadata (INV-159): aart-cli never fetches it, and it
  changes nothing about what is installed or how a value reaches the artifact.
- **Shown wherever the artifact or its inputs are explained:**
  - in Marketplace's More info, as `Documentation` after the Description, so someone browsing can
    copy it;
  - with every credential and configuration value the artifact asks for, wherever it is asked or
    explained: screen 07, the briefing on the terminal lent to a credential prompt, and the CLI's
    refusal for unanswered inputs;
  - in Credentials and variables, for each installed artifact whose approved offer carries one;
  - in the CLI: the Marketplace listing (text and JSON), the install review's "What you will
    need", and the result of an install, which names the documentation of each artifact it
    installed.
- **Where to get a credential.** When a credential's `help` does not say where to get it, the
  artifact's documentation is where to look. The fallback names the documentation instead of
  sending the reader to the maintainer.
- **Whole, as plain text.** The link is printed as written, on its own line or after its label, with
  no escape sequence. A terminal that recognizes URLs can open it, and any terminal can copy it.
  aart-cli never cuts it or puts it in a column. Only a window narrower than the link wraps it.

**INV-298 — An artifact's documentation link is approved metadata, shown whole.** An artifact's
documentation link comes only from its approved manifest's `documentation`. It is refused at
authoring and at reading unless it is a plain `http(s)` URL with no control character and nothing
redaction would hide. Every surface that shows it shows it exactly as approved, and none shows a
link for an artifact that declares none. Each credential and configuration input an artifact declares carries
that artifact's link wherever the input is explained.

---

# 198. Credentials and variables from the command line

Status: **ACCEPTED 2026-10-26 (D-483)**, on the owner's request (CP-45). An agent or a script could
set an installed artifact's configuration only through the TUI's Credentials and variables. This
refines §161.8, §169.4 and §186, and leaves §186's install-time flags as they are.

- **Three commands, one service.** `aart-cli consume inputs` has three actions:
  - `list` reads;
  - `set` changes one ordinary value;
  - `set-credential` stores or replaces one credential.

  Each action prepares and executes through the same consumer actions as the TUI screens. What an
  installation's inputs are, and which of them are still `AART_NOT_SET`, is decided by one module
  that the TUI and the CLI share. The checks, the review digest and the writes are therefore the
  TUI's own.
- **An installation is named, never guessed.** A command names an artifact as
  `ALIAS/KIND/NAME`, with or without `@VERSION`. `--harness` and `--scope` narrow it, and
  `--project` names the project root. The artifact name must match whole, so `alias/mcp/git` never
  names `alias/mcp/github`.

  `set` and `set-credential` change exactly one installation (§169.3). When the name matches more
  than one, nothing changes, and the refusal lists each match with the flags that select it. Every
  other installation, including the same artifact in another harness, keeps its own values (§169.4).
- **`list` only reads.** For each installation it shows:
  - its harness, scope and root;
  - each ordinary value, or `not set`, and where it is kept;
  - the state of each credential, never a value;
  - the artifact's documentation link (§197);
  - the exact command that sets each value that is missing or `AART_NOT_SET`.

  `--json` gives the same as data. Reading the result again is how a change is verified.
- **`set INPUT=VALUE` is for configuration only.** A configuration value is not a credential, so
  it may be an argument and may be pasted to an agent.

  Naming a credential input is refused. The refusal does not repeat the value and gives the
  `set-credential` command instead.
- **`set-credential` never reads the value.** It takes no value, and refuses one given as
  `INPUT=VALUE` without repeating it. A configuration input is refused, and the refusal gives the
  `set` command.

  The terminal is lent to the credential store's own prompt, the same handover the TUI uses (§161.8,
  D-371). The briefing goes to standard error, the person types into the store, and the value never
  passes through aart-cli. An agent may run the command or hand it to a person. It can never supply
  the value.
- **No terminal, no change.** Without a terminal on standard input, `set-credential` refuses before
  touching the store and prints the command to run in a terminal. The refusal comes first because
  replacing an item removes the old one before it asks.
- **Review, then `--yes`.** Without `--yes` a change is only reviewed: it prints what would change
  and the review digest. `--yes` executes, and `--expect DIGEST` refuses a change that differs from
  the one reviewed. Every refusal says what was refused and how to proceed, with `--json` giving
  `{"ok": false, "diagnostics": [...]}`.
- **What stays elsewhere.** Deleting a retained credential stays in the TUI, which names its sole
  owner (INV-057, B-235). `consume install` asks for a credential in the same way (§201).

**INV-299 — An installation's inputs are set from the command line through the TUI's own service,
and a credential's value never passes through aart-cli.** `consume inputs set` changes exactly one
ordinary value of exactly one named installation, after the review its `--expect` digest names.
`consume inputs set-credential` takes no value: it lends the terminal to the credential store or
refuses with nothing changed. No argument, output, plan, receipt or refusal of either command
carries a credential's value.

---

# 199. Installed reads like Marketplace

Status: **ACCEPTED 2026-10-26 (D-484)**, on the owner's request (CP-45). Installed and Updates
listed the whole coordinate and the harness in one cell, wrapped long cells, and had no More info
for the row under the cursor. This refines §173.6, §173.8 and §184, and applies §196 to them.

**Amended 2026-10-28 by D-498 (CP-46, §210):** Installed and Updates list by default what an
agent here reaches, the user's installations and this project's; `a` lists every project's.

- **Four columns by default:**
  - `Artifact` is `name@version`;
  - `Type` is the same word Marketplace uses, and `Collection` for a Collection;
  - `Harness` is the installation's harness;
  - `Health` is the measured health, with `→ VERSION` when an update is offered.
- **`d` shows the details:** Registry, Scope, Project (the root's last name) and Configuration
  (§182). `d` again hides them. The choice holds while aart-cli runs. It is kept apart from
  Marketplace's choice, so each list keeps its own.
- **One line per row, on Marketplace's grid.** The same rules as §196 apply:
  - columns narrow in the same order;
  - a cut value is marked `…`;
  - a column with no room is named under the list;
  - the headings are ruled off (§184).

  A Collection's members stay indented under it (§173.6).
- **More info describes the row under the cursor.** `v` shows the installation whole:
  - artifact, version, Type and Registry;
  - harness, scope and the whole project root;
  - health and any offered update;
  - each ordinary value, or `not set`, and each credential's state, never its value;
  - the documentation link, whole and last (§197).

  For a Collection, More info shows its version, Registry, health, how many artifacts it includes,
  and which of them need attention.
- **Nothing else moves.** Rows, keys, selection, search and every action still address the
  installation by its full key (§169.3).

**INV-300 — Installed and Updates draw one line per installation on Marketplace's grid.** Without
details a row shows exactly Artifact `name@version`, Type, Harness and Health. With details it adds
Registry, Scope, Project and Configuration. No line exceeds the window. Toggling details never
changes the rows, the selection or the cursor. More info for an installation names its harness,
scope, root and the state of each input, and never a credential's value.

---

# 200. The TUI names its version

Status: **ACCEPTED 2026-10-26 (D-485)**, on the owner's request (CP-45). A screenshot or a report
of a screen did not say which aart-cli drew it.

- The footer caption that names the launch directory (QA-086) ends with ` · aart-cli X.Y.Z`. The
  version is the one the executable reports (`aart-cli --version`).
- A session with no launch directory still draws no caption, as before.

**INV-301 — Every screen with a launch directory names the running aart-cli's version beside it.**

---

# 201. `consume install` asks the credential store, never the environment

Status: **ACCEPTED 2026-10-26 (D-486)**, on the owner's request (CP-45, B-236). This amends §186.
`--secret-env` read a credential from an environment variable inside aart-cli. That broke the rule
§198 set: aart-cli never reads a credential, and the store's own prompt takes it.

- **`--secret-env` is removed.** A credential is never a flag, an argument or an environment
  variable that aart-cli reads. `--input` naming a credential is refused, without repeating the
  value. The refusal says to apply in a terminal, or to use `--set-later` and then
  `consume inputs set-credential`.
- **The review says what the store will ask for.** Without `--yes`, `consume install` and `consume
  update` list each credential the store will ask for, once per artifact, as
  `ALIAS/KIND/NAME:INPUT`. Each is explained as on 07b and in the store's briefing: what it is, who
  needs it and how to get it (D-263). The JSON review gives them as `asked_by_credential_store`,
  each with its `input` and `guidance`.
- **Applying in a terminal hands the terminal to the store.** With `--yes` and a terminal on
  standard input, the reviewed run is applied. Each installation's credential is stored in its own
  item by the store's own prompt, during the transaction, after a briefing on standard error. The
  value never passes through aart-cli. This is the same handover as `set-credential` (§198) and the
  TUI's Credentials and variables (§161.8, D-371).
- **No terminal, no change.** With `--yes` and no terminal, the command refuses before anything is
  written or locked. The refusal names each credential, and says to run the same command in a
  terminal, or to pass `--set-later` and set each one later with `consume inputs set-credential`.
- **`--set-later` is unchanged.** It stores the `AART_NOT_SET` placeholder in each credential's item
  and asks nothing (§172.3).
- **The TUI does the same.** 07b lets the store ask for a credential when its row is chosen, and
  never reads one (§172.6, §207, D-495).

**INV-302 — Installing never reads a credential.** No flag, argument, environment variable or
screen gives `consume install`, `consume update` or the TUI's install flow a credential's value. Each credential the run
needs is either stored by the credential store's own prompt in a terminal, or left as the
placeholder under `--set-later`. Without a terminal, a run that needs the prompt changes nothing.

# 202. Only the Registry here opens, and its commands are there

Status: **ACCEPTED 2026-10-27 (D-488, D-489)**, on the owner's report and their review of it
(CP-46). This refines §164.7, §164.8 and §190.

With a large terminal font, the Recent promotions of one Registry on screen 46 pushed the next
Registry off the screen, so the list of Registries could not be read as a list. And the commands on
the list looked as if they acted on the Registry under the cursor, when Initialize, Rebuild, Scan
Repository, Check upstream, Push and Collections act on the Registry in the directory aart-cli runs
in, whichever row is chosen.

- **The list is short.** Screen 46 shows each Registry in a few lines: its validity, its
  diagnostics, its approved versions by kind and how many promotions it has recorded, and for a
  subscribed Registry its working tree. Its revision, snapshot and Recent promotions are not on the
  list.
- **The Registry here is marked.** The Registry in the directory aart-cli runs in is the first row,
  marked `● you are here`. What it holds is read from its checkout, promotions not pushed yet
  included.
- **The list acts on nothing.** Screen 46 offers no command, with one exception: where the
  directory holds no Registry, `n` Initialize creates one, since there is nothing to open.
- **Only the Registry here opens.** Enter on its row opens screen 46k, titled `This Registry`: its
  row, its validity, revision, snapshot, approved versions and Recent promotions (§190), and in
  Verbose where its checkout stands (§164.7) and every digest.
- **Its commands are there.** Screen 46k offers `c` Candidates, `b` Rebuild, `s` Scan Repository,
  `u` Check upstream, `p` Push when ready (§164.7) and `o` its Collections. Enter opens Bulk
  Promotion when Ready Candidates wait. Initialize is not offered: the Registry exists.
- **Any other Registry says where to work on it.** A subscribed Registry does not open. With the
  cursor on it, the screen says to run aart-cli in its Registry checkout to work on it. When the
  subscription has the name of the Registry here, the screen says so and points to the marked row.
- **Back keeps the Registry.** Esc from 46k returns to screen 46 on the marked row. Esc from a
  screen opened on 46k returns to 46k.

**INV-303 — The Registry list holds no promotion history.** No line of screen 46 is a promotion.
Recent promotions appear on screen 46k, the Registry in this directory opened from its row.

**INV-304 — Only the Registry here is acted on.** Screen 46 offers no command acting on a Registry
and opens no Registry but the one in the directory aart-cli runs in. Every command acting on a
Registry is offered on screen 46k, which is that Registry.

# 203. A running action shows it is working, and `mcp test` reads generated schemas

Status: **ACCEPTED 2026-10-27 (D-490)**, on the owner's request and an enterprise run of
`consume mcp test` (CP-46). This refines `QA-082` and §170.3.

An install that took a while held its last frame until it finished, so a slow install could not be
told from a hung one. Separately, `consume mcp test` refused a working fastmcp server before calling
it, because its schemas used keywords the validator did not implement.

- **A running action beats.** While an action is prepared or run, its frame's heading carries a
  turning mark and the whole seconds taken, for example `⠹ working 12s`. The heartbeat redraws the
  step the action last reported, so the frame keeps showing how far it got. It stops when the action
  returns.
- **A heartbeat never draws over a prompt.** While the terminal is lent to the credential store's
  prompt (§201), no beat is drawn. A beat that falls during the loan is skipped, not drawn after it.
- **`mcp test` applies a generated schema's bounds.** It applies:
  - the bounds a schema puts on a value: `minimum`, `maximum`, `exclusiveMinimum`,
    `exclusiveMaximum`, `multipleOf`, `minLength`, `maxLength`, `minItems`, `maxItems`,
    `uniqueItems`, `minProperties` and `maxProperties`;
  - the branches `anyOf`, `oneOf` and `allOf`;
  - `type` as a list of types.
- **Annotations and extensions are read past.** These constrain no value, so they are passed over:
  - `format`, `contentEncoding` and `contentMediaType`, which JSON Schema 2020-12 treats as
    annotations unless a vocabulary asserts them;
  - every keyword starting with `x-`, which a schema producer uses for its own purposes (fastmcp
    writes `x-fastmcp-wrap-result`).
- **What it does not implement is still refused.** A keyword it does not apply, such as `not` or
  `if`, is still reported as unsupported validation (§170.3), including inside a branch. §205 adds
  `pattern`, `$ref` and the other keywords FastMCP generates.

**INV-305 — A running action is never silent.** While an action is prepared or run in the TUI, its
frame's heading shows a mark that turns and the seconds taken. No beat is drawn while the terminal
is lent to a prompt.

**INV-306 — A schema keyword is applied, read past, or refused.** `consume mcp test` applies every
keyword it implements. It passes over an annotation or an `x-` extension, and refuses any other
keyword as unsupported validation. No keyword is silently skipped.

**Addendum (D-491).** The owner then tested an MCP installed for the user from the TUI, started in a
project, and was told `…#opencode#user#/Users/… has no recorded MCP installation to test`. A test
that could not run had also said only that it could not run.

- **A test reads each installation where it was made.** The installation key names its scope and
  root (§169.3). Test MCP reads the records in those, not in the scope and root of the session, so
  an MCP installed for the user is tested from any project.
- **A test that cannot be prepared or run says why.** The notice names what failed, for example
  `the MCP test could not be run: OSError: …`, on one bounded line.

**INV-307 — A failed MCP test says what failed.** Test MCP finds a chosen installation in the scope
and root its key names. A test that cannot be prepared or run names the error on the screen it was
asked on.

# 204. A credential may declare its length, and a cut value is entered another way

Status: **ACCEPTED 2026-10-27 (D-492)**, on an enterprise report (CP-46). This refines §91, §172
and §201.

An Atlassian API token of about 190 characters was stored as 128. macOS's
`security add-generic-password -w` reads the value through libc `getpass`, which keeps at most 128
characters and drops the rest without a word. Nothing reported the stored value as wrong.

- **A secret may declare its length.** A secret input may carry an optional `validation` with
  `min_length`, `max_length`, or both, and an optional one-line `message`. Each bound is a whole
  number of at least 1, and `min_length` is not above `max_length`. A secret declares no `pattern`:
  judging a pattern needs the value, and aart-cli never reads it.
- **The length is measured, never the value.** The provider measures the stored value in child
  processes (`MacOsKeychainProvider.stored_length`). Only the number reaches aart-cli. A length is
  counted in bytes, which for the ASCII tokens services issue is characters.
- **The receipt keeps the declaration.** An installation's receipt records each credential's
  declared length as `credential_checks`, written only when one is declared.
- **A value of the wrong length is not configured.** A stored value outside its declared length is
  reported as invalid, with why, wherever credentials are read:
  - Credentials and variables and `consume inputs list` say `Not configured: …`;
  - `doctor` says `… is not configured: …` and is not ok;
  - the installation needs attention.
  The skip placeholder (§172.3) and a value whose length cannot be measured are not judged.
- **A cut value is entered another way.** After the store's prompt, the value is checked against
  its declared length. Without a declaration, a value exactly 128 characters long, as many as the
  prompt keeps, is treated as cut. Such a value is entered another way while the terminal is still
  lent. Then the provider is asked again.
- **The other ways are adapters, tried in order.** Each is behind one port, so CI exercises the chain
  with fakes and a way can be replaced later:
  1. a macOS dialog with a hidden field (`osascript`). Its script UTF-8 hex encodes what was typed and
     writes it to `security -i` through a pipe. The value is on no argv, in no file and never in
     aart-cli;
  2. where no dialog can be shown, instructions to add the item in Keychain Access, which is opened.
     aart-cli waits for Enter, or `s` to leave it for now.
- **An install is not failed by a cut value; a set is.** An install goes on and reports the
  credential as invalid, with why. `Set credential` (TUI) and `consume inputs set-credential` fail by
  name while the value is still the wrong length.

**INV-308 — A declared credential length is judged without the value.** A secret's declared length
is recorded on its receipt. The stored value's length is measured outside aart-cli. A value outside
it is reported as not configured, with why, in Credentials and variables, `consume inputs list` and
`doctor`.

**INV-309 — A credential the prompt cut is entered another way.** When a stored value fails its
declared length, or sits on the prompt's 128-character ceiling with none declared, the configured
fallback ways are tried in order. Then the provider is asked again. No way hands the value to
aart-cli.

# 205. `mcp test` reads every schema FastMCP generates

Status: **ACCEPTED 2026-10-28 (D-493)**, on the owner's request after the enterprise run of
`consume mcp test` against sooperset's mcp-atlassian (CP-46). This refines §170.3 and §203.

After §203, `jira_get_issue` was still refused before the call:
`unsupported JSON Schema keyword 'pattern' at $.issue_key`. mcp-atlassian 0.23.1 (FastMCP 3.4) and
0.21.1 (FastMCP 2.14) use only one keyword §203 did not apply, `pattern`, in 36 places. FastMCP
writes more for other Pydantic types. The owner asked for aart-cli to work with FastMCP, and with
this server exactly.

- **The keywords FastMCP writes are applied.** These, with JSON Schema 2020-12 meaning:
  - `pattern`, searched for in a string, not anchored. A pattern is ECMA-262: `\d`, `\w` and `\b`
    are ASCII, and `$` is the end of the string, never before a final newline. A pattern Python
    cannot read the same way, such as `\p{L}` or `(?<name>…)`, is refused as unsupported;
  - `patternProperties`, `propertyNames`, and `additionalProperties` as a schema. A member that no
    property or pattern names is an additional one;
  - `prefixItems` for the leading positions of an array, with `items` for every one after them;
  - `$ref` into the tool's own schema, as a JSON Pointer from `#`, with `$defs` and `definitions`
    holding what it reaches. A reference anywhere else is never fetched and is refused as
    unsupported. A reference that leads back to itself without the value moving is refused too.
- **`discriminator` is read past.** It is OpenAPI's hint for a tagged union, and the `oneOf` beside
  it decides which branch a value is.
- **A server's numbers are read exactly.** aart-cli's own documents carry no number with a fraction
  (protocol JSON forbids it). A server's schemas and answers do: FastMCP writes a `float`
  parameter's bounds as `0.0` and `1.0`. `mcp test` reads such a number as the exact decimal the
  server wrote, a whole one as an integer, and refuses one that is not finite. The response preview
  shows it as written. The number never reaches protocol code.
- **A refusal is said alone.** A call refused before invocation says only why. What the server wrote
  to stderr while starting, such as FastMCP's banner, is added only when the process itself failed.

**INV-310 — FastMCP's schemas are read.** For every tool that mcp-atlassian 0.23.1 and 0.21.1
advertise, and for each Pydantic shape FastMCP 3.4 and 2.14 generate, a call meeting the schema is
allowed and an answer meeting the output schema passes. A value outside a keyword FastMCP writes
fails, naming that keyword's verdict.

# 206. Every screen taller than the terminal scrolls

Status: **ACCEPTED 2026-10-28 (D-494)**, on the owner's request during CP-46: "żeby można było
scrollować" screen 07 with many settings, screen 07b with many credentials, the Ready summary, and
every screen with many items, in both the consumer and the maintainer TUI. This extends §175's
Marketplace paging to every screen.

Only Marketplace paged. Any other screen taller than the terminal was cut at the bottom row, so
what stood below it could be neither read nor reached.

- **The body pages; the trail and the keys stay.** On a screen taller than the terminal, the trail
  stays at the top and the footer with its keys at the bottom. Between them, a page of everything
  else is drawn: rows, what the cursor is on, status, notices and help. Marketplace keeps its column
  headings above its page as before.
- **What a page leaves out is said.** A line above the page says how many lines are above it and
  that PgUp shows them. A line below says the same of what is below and PgDn.
- **PgUp and PgDn turn half a terminal.** Each moves the page by half the terminal's rows, at least
  one line. The last page is clamped, so PgDn at the end changes nothing and one PgUp moves at once.
- **The cursor is followed until a page is turned.** Moving the cursor, or any other key that
  changes the screen, brings the focused row back into view with a line of what follows it.
  A turned page stays where it was until then. Another screen opens at its top.
- **The legend offers it only when it applies.** `[PgUp/PgDn] Scroll` is in the legend when the
  screen does not fit without it, and never while searching.
- Both TUIs run one loop, so this holds on every consumer and maintainer screen. A terminal whose
  height is unknown pages nothing.

**INV-311 — A screen taller than the terminal can be read whole.** Paging from the top with PgDn
shows every line of the screen's body, in order, and never draws more lines than the terminal has.
The trail and the keys are drawn on every page.

# 207. A credential is entered on 07b

Status: **ACCEPTED 2026-10-28 (D-495)**, on the owner's request during CP-46: the store's prompt
opens on 07b when the row is chosen, not later during the install. This amends §172.6 and D-487.
§201's terminal handover and §204's length check and dialog are unchanged; only when they run moves.

Marking a row and being asked minutes later, inside the install, put the prompt where nobody
expected it. A cut or cancelled value was found only after the transaction had begun.

- **Enter on a row asks now.** Enter on a 07b credential lends the terminal to the credential
  store's own prompt at once. The briefing comes first, and the prompt asks once for each
  installation's own item (D-334). A value the prompt cut, or one that fails its declared length,
  is asked again in the macOS dialog (§204). aart-cli never sees a value.
- **A row is stored whole or not at all.** If a prompt is cancelled or a value still does not fit,
  every item that row stored is deleted. The row stays `not set`, and a notice says why.
- **An item somebody stored before this review is left alone.** It is not asked for and not
  deleted. Enter on a row already entered in this review asks again, and replaces those items.
- **The install is prepared again.** Storing changes the machine the review measured, so after
  each stored row the same install is prepared again. Ready confirms that review. Without this,
  Ready's preflight would refuse the install as changed after Review.
- **The install asks nothing.** Every secret not entered on 07b is stored as `AART_NOT_SET` without
  prompting (INV-261). Ready says which credentials were stored on 07b.
- **What was entered belongs to the review until it is installed.** Leaving the review's screens,
  quitting, or a failed install deletes what 07b stored. Set later and a successful install keep it.
- `consume install` keeps §201's flow: the store asks during the transaction.

**INV-312 — 07b's values live only as long as their install.** Every item 07b's store prompt
created exists after the session only if the reviewed install that it was entered for completed.
Every item that existed before the review is unchanged by 07b.

# 208. Uninstall deletes the credentials of the installations it removes

Status: **ACCEPTED 2026-10-28 (D-496)**, on the owner's request during CP-46: credentials that
outlive their installation are clutter in the Keychain nobody owns. This amends INV-185 and every
statement that an uninstall retains credentials.

Every installation has its own credential items (D-334). No other installation can use them, so
keeping them after an uninstall protected nobody.

- **An uninstall deletes the removed installations' own items.** These are the values entered and
  the `AART_NOT_SET` placeholders alike. They are deleted in the same reviewed transaction as the
  files and the harness registration.
- **Only what is removed.** An installation that a Collection removal narrows, because something
  else still owns it, stays installed and keeps its credentials. Another harness's or scope's
  installation of the same artifact is not touched.
- **The review says so first.** The TUI's Uninstall Review lists each `credential:INPUT` among the
  components changing, with the credential-mutation risk. `consume uninstall` reviews
  `"credentials": {"deleted": ["ARTIFACT: INPUT", ...]}`, and as text `Credentials deleted with
  their installations:` followed by each, or `none.`
- A credential whose installation is already gone is still deleted from Credentials and variables,
  as before.

**INV-313 — An uninstall deletes exactly the credentials of what it removes.** After an uninstall
completes, no credential item of an installation it removed remains. Every item of an installation
it did not remove is unchanged.

# 209. Scope is chosen before configuration and credentials

Status: **ACCEPTED 2026-10-28 (D-497)**, on the owner's request during CP-46: "w trakcie instalacji
niech scope będzie przed konfiguracją i credentialami". This amends the order of §172.1.

A pair becomes one installation once its scope is known (§172.1). Its credential item is addressed
by that scope and root (§169.4), so a credential entered on 07b (§207) should be entered for an
installation whose place is already decided.

- **The order is 05, 07a, 07, 07b, Ready.** 07a still appears only when some pair may go to more
  than one scope, and 07 and 07b only when something is asked. The Default path still takes its
  scope from Settings and never shows 07a (§173.7).
- **07a needs no plan.** Its rows are the pairs' offered scopes, known once 05 is answered. Each
  pair starts on the Settings scope, as before. Choosing a scope prepares the install again; while
  07 is still unanswered, that preparation returns the form, and what was already typed into it
  is kept.
- **07a opens on its first column.** Its columns are scopes, not 05's harnesses.
- **After 07, 07a is not asked again.** 07 goes on to 05 only while a choice of Python installer is
  still open (D-380), then to 07b or Ready. Going back to 05 asks the scope, then the form, again.

**INV-314 — A credential is entered for an installation whose place is chosen.** On every TUI
install path, 07a, when shown, comes before 07 and 07b, and each item 07b asks for is addressed by
the scope chosen there.

# 210. Installed shows what an agent here reaches

Status: **ACCEPTED 2026-10-28 (D-498)**, on the owner's request during CP-46: Installed should show
by default the artifacts an agent has access to in the current context, with a toggle to see every
project's. This amends §199's Installed and Updates lists and Home's counts.

A project-scope installation is made into one project's root (§169.3). An agent working in another
project cannot use it, so listing it beside this project's own read as if it could.

- **By default, what is reached here.** Installed and Updates list the user's installations and
  those of the project aart-cli runs in. An installation whose record names no scope is listed,
  since nobody can say it is elsewhere. A session that knows no project leaves nothing out.
- **What is left out is said.** The view's status says how many installations in other projects
  are not shown, and that `a` shows them. Updates counts only the updates it leaves out.
- **`a` shows every project.** The legend offers `[a] All projects`. Pressed, Installed and
  Updates list every installation on the machine, the status says `Showing installations in every
  project`, and the legend offers `[a] This project`. The choice lasts for the session, like `d`.
- **A Collection goes with its members.** A Collection is listed by default when one of its
  installed members is reached here, or when none of its members is installed at all.
- **Home counts what Installed lists by default.** Its installed, ready, update and attention
  counts are of the installations reached here, so its `open Updates` matches Updates.
- Marketplace lists offers, not installations, so it is unchanged. Doctor and Credentials and
  variables still read the whole machine (B-243).

**INV-315 — Installed lists by default exactly what an agent here reaches.** Without `a`, every
user installation and every installation of this project is listed, and no other project's
installation is. With `a`, every installation on the machine is listed.

# 211. A newer aart-cli that a Registry runs is announced, with how to install it

Status: **ACCEPTED 2026-10-28 (D-499)**, on the owner's request during CP-47: tell the person when
the Registry runs a newer aart-cli than the one they are using, and how to upgrade it, in the way
their organisation actually supplies aart-cli rather than one way that does not work everywhere.

A Registry pins the aart-cli its CI runs in `.aart-cli-version` (one line, a SemVer). An
organisation upgrades by bumping that pin in a pull request, so a person whose aart-cli is older
than the pin of a Registry they consume is behind what that Registry was checked with.

- **Which pin counts.** The pin of the Registry this build was released with as its default
  (§169, D-309), when it is connected and its current snapshot carries a readable pin. Otherwise
  the highest readable pin among the connected Registries' current snapshots, and among equal pins
  the Registry whose alias sorts first. A newer version is announced only when that pin is above
  the running version; build metadata (`+corp`) is ignored, as SemVer orders it. Nothing is fetched
  to find out: the pins are read from the snapshots already synced.
- **Where aart-cli comes from: `.aart-cli-source`.** A Registry may commit a file
  `.aart-cli-source` beside its pin. Each line is `NAME=value`; blank lines and lines starting with
  `#` are ignored. The names are the Registry CI's own variables: `AART_CLI_PIP_INDEX_URL`,
  `AART_CLI_PACKAGE`, `AART_CLI_WHEEL_URL`, `AART_CLI_TOOL_PATH`, `AART_CLI_TOOL_URL` and
  `AART_CLI_REPOSITORY`. `{version}` in a value stands for the pin. An empty value is unset. The
  first route set wins, in the order the CI's own step tries them: the package on the index
  (`AART_CLI_PACKAGE`, from `AART_CLI_PIP_INDEX_URL`, else `https://pypi.org/simple`), the wheel at
  `AART_CLI_WHEEL_URL`, the directory `AART_CLI_TOOL_PATH`, then Git at `AART_CLI_TOOL_URL` or at
  `AART_CLI_REPOSITORY` (`owner/name` on the Registry's own host), at the tag `v<pin>`.
- **The file never holds a credential.** A line that is not `NAME=value`, an unknown or repeated
  name, a quoted value, a value with a control character, an address carrying a password, or an
  `http(s)` address carrying a user name refuses the whole file, and the reason, which never repeats
  the value, is said instead of any command. An SSH user name (`git@host:...`) is not a
  credential. A sign-in is the
  person's own, through their package manager or Git, never a Registry's file.
- **The commands follow how this aart-cli was installed.** pipx (`pipx install --force`), uv
  (`uv tool install --force`) or pip with the running Python (`python -m pip install --upgrade
  --no-deps`) receive the Registry's route. An editable install from a Git checkout is moved to the
  tag with `git -C <checkout> fetch --tags` and `git -C <checkout> checkout v<pin>`, whatever the
  file says. A wheel address may need a sign-in in a browser: the wheel can then be downloaded and
  installed with `aart-cli upgrade --wheel FILE`. `AART_CLI_TOOL_PATH` names a directory on the
  CI's runner, so it gives no command, only that the Registry's maintainers know where it comes
  from. With no file, the newer version is still announced, with the advice that the Registry's
  maintainers can add `.aart-cli-source`. Copyable commands carry no comments.
- **Where it is said.** The TUI's Home says `● aart-cli <pin> available (Registry <alias>) — open
  AART CLI Update`, its entry `AART CLI Update` carries `● <pin>`, the footer's `aart-cli <version>`
  adds `(<pin> available)`, and the screen `30-aart-cli-update` shows the running version, the pin
  and its Registry, how this aart-cli was installed, and the commands. Every `consume` command says
  it in one line on stderr, so a `--json` document on stdout is unchanged. `aart-cli upgrade --how`
  prints the same instructions and installs nothing; `--wheel` and `--source-checkout` are as
  before. `aart-cli --version` is unchanged, since a Registry's CI compares it with the pin.
- **A defect in finding out never stops anything.** A pin or file that cannot be read is
  announced as nothing; the command or screen runs as it would have.

**INV-316 — The announced aart-cli is the governing pin, and only when it is newer.** For any set
of connected Registries' pins and any running version, a newer aart-cli is announced exactly when
the governing pin (the default Registry's, else the highest, ties by alias) is above the running
version, and the version announced is that pin.

**INV-317 — `.aart-cli-source` gives commands only from a file it accepts in full, and none that
carries a credential.** Every accepted file yields commands whose words come from its values with
`{version}` replaced by the pin; every file with an unknown, repeated, quoted or malformed line, an address with a password, or an
`http(s)` address with a user name, yields no command and a reason.

# 212. Activity is kept in SQLite, and records which artifacts are used

Status: **ACCEPTED 2026-10-28 (D-500)**, on the owner's request during CP-47: Activity also shows
which skills and MCPs are actually used, per harness, with a ranking, kept in SQLite rather than in
JSON files, in preparation for a telemetry server that does not exist yet.

- **One database.** `state/activity.sqlite3` in the application home (§169.2) holds the finished
  actions (install, update, uninstall, each with its receipt) and the recorded artifact uses, each
  event its own row. It is created owner-only (0600). A database whose schema version is not the one
  this aart-cli reads is reported and never rewritten. Activity reads only the newest 500 actions.
  Action records written as JSON files by earlier versions are not carried over (§169: no
  migrators).
- **Many writers at once.** Agents and their subagents call tools in parallel, and every call starts
  its own hook. Each write is one statement that waits for the others; creating the database waits
  under one lock; the journal becomes WAL as soon as no other connection holds the file. No use is
  lost because another hook or aart-cli was writing in the same moment.
- **What a use is.** The harness, `skill` or `mcp`, the name, the project directory the harness
  reported, and the moment. Never what a tool was called with, a prompt or an answer. Claude Code:
  a `Skill` tool call is the skill's name; `mcp__<server>__<tool>` is the server. opencode: the
  `skill` tool is the skill's name; a tool whose name holds `_` is kept whole as an MCP tool and
  ranked under the longest installed MCP server name it starts with.
- **The hook.** A user-level hook in each harness, not a Marketplace artifact: an entry in Claude
  Code's `~/.claude/settings.json` (`PreToolUse`, matcher `Skill|mcp__.*`, `async`), and a plugin
  `~/.config/opencode/plugins/aart-cli-usage.js` (`tool.execute.before`, a detached process). Both run
  this aart-cli's own Python with `-I` and its own `aart_cli/io/usage_hook.py` by absolute path, so
  nothing in the project can replace what runs. The hook never writes to stdout and always exits 0;
  what it cannot read or write records nothing. Settings that are not JSON, or whose hooks are not
  the documented shape, are refused and left byte for byte; removing the hook removes aart-cli's
  entry only and keeps everyone else's; a plugin file aart-cli did not write is never deleted.
- **Consent per harness.** Settings has one row per detected harness that can record:
  `Artifact usage <harness>: on|off`. When the cursor is on the row, the screen says what is
  recorded, what never is, the file the hook changes and where the uses are kept. Tabnine has no
  hook mechanism and cannot record. A hook that cannot be written leaves the row off.
- **Recording without asking is the deployment's decision.** The release variable
  `AART_CLI_DEFAULT_USAGE_HARNESSES` names the harnesses a build records in until a person chooses:
  names separated by commas, each a harness that can record (`claude`, `opencode`), or `none`.
  Unset or `none` bakes none, so the public build records nowhere until a harness is turned on. A
  name that cannot record, an empty or a repeated one fails the release. The value is baked into
  the wheel and written in the release receipt. In a harness the build names, the TUI puts the
  hook in place at start when that harness is on this machine and says so once; the person's own
  choice in Settings, once made, always wins.
  Turning a harness off removes its hook; `consume usage disable --harness H --forget` and `consume
  usage forget --harness H` delete what was recorded for it. `consume usage show [--json]` says
  which harnesses record and lists the ranking.
- **Where it is shown.** Activity lists `most used:` — uses, artifact (its installation name when
  aart-cli installed it, else the name with `(not installed by aart-cli)`), kind, harness and the
  last use in UTC — and which harnesses record. One artifact in two harnesses is two lines.
- **Local unless telemetry is on.** Nothing is sent anywhere until a person turns telemetry on
  (§213), which is its own consent, separate from recording here.

**INV-318 — A recorded use carries names only.** For any hook payload, the use recorded holds the
harness, kind, name, project and moment, and no part of what the tool was called with.

**INV-319 — Usage is recorded only in a harness whose row is on, and without asking only where the
build says.** Until a person chooses, the rows that are on are exactly the harnesses baked from
`AART_CLI_DEFAULT_USAGE_HARNESSES`, none when it is unset or `none`. A harness with its row off has
no aart-cli hook; turning a row off removes that hook and leaves every other hook and plugin in its
configuration as it was.

**INV-320 — Concurrent writers lose nothing.** Any number of hooks and aart-cli commands writing to
the Activity database at once, including while it is created, all record their rows.

**INV-321 — The Activity database is its owner's alone and read only at the schema version it
was written with.** It is created 0600, and a database with another schema version is reported and left
unchanged.

# 213. Telemetry: installs, updates, removals and uses sent to a telemetry server

Status: **ACCEPTED 2026-10-29 (D-503, D-504, D-505)**, on the owner's request after 0.21.0, from
their telemetry implementation brief: the organisation sees which artifacts are used, how often, by
how many installations, and how that changes, on a dashboard. Supersedes §212's "Local only" for an
installation where telemetry is on. D-505 (the owner, the same day): a build that names a server
starts with telemetry on, and turning it on sends Activity's history too.

- **Two repositories, one contract.** The server is a separate repository,
  `aart-cli-telemetry-server` (a functional core behind FastAPI; SQLite in WAL by default and
  PostgreSQL by URL, through one SQLAlchemy repository; a Chart.js dashboard). The only thing the two
  share is `docs/telemetry-api-v1.md` with `contract/telemetry-api-v1.examples.json`, kept
  identical in both and read by each one's contract tests. aart-cli imports nothing of the server
  and gains no runtime dependency: the client is `sqlite3`, `json`, `urllib.request`, `fcntl`,
  `subprocess` and `uuid`.
- **On from the start where the build names a server; otherwise off until a person turns it
  on.** A build whose release variable `AART_CLI_TELEMETRY_ENDPOINT` names a server turns telemetry
  on for an application home that has never had it on or off, at its first `aart-cli` terminal
  session or `consume` command (not `consume telemetry …`, not `--offline`), and says so once: on
  stderr for a command, before the terminal takes the screen for the TUI. A build that names none,
  as the public one does, sends nothing until `consume telemetry enable --endpoint URL`.
  `consume telemetry enable` without `--endpoint` uses the baked address. `consume telemetry
  disable` stops recording and sending, and that choice is kept: no later start turns it on again.
  `--forget` also deletes what is waiting and the installation id, and keeps the choice.
- **Turning it on sends Activity's history too.** Each time telemetry is turned on, by the build or
  by a person, every install, update and removal and every recorded use Activity holds is queued
  with its own moment, beside what happens from then on. Each Activity record has one event id,
  drawn from a random key kept in the outbox and the record's row, so a record queued twice -- as it
  happens and again from the history, or on turning telemetry on again -- is kept once in the
  outbox and counted once by the server. While it is off nothing new is queued; the history queued
  when it is next turned on includes what happened meanwhile.
- **The address.** `https://` for any host, `http://` only for `127.0.0.1`, `::1` or `localhost`;
  never with a user, password, query or fragment. aart-cli appends `/api/v1/events/batch`.
  Version 1 sends no credential; a server reachable beyond loopback sits behind the organisation's
  authenticating proxy, and no shared secret is baked into aart-cli.
- **What is sent.** `artifact.installed`, `artifact.updated` (an update or a downgrade) and
  `artifact.removed` for each artifact an action changed and completed, from `aart_cli`; and
  `artifact.used` from `claude_hook` or `opencode_plugin` for a use §212 recorded, only when it is
  an artifact aart-cli installed: named by its installation (kind, name, version), never by the
  tool the harness called. A use no installed artifact answers to is never sent. Each event has
  its Activity record's `event_id` (above) and its UTC moment; the request has a random installation id, drawn when
  telemetry is turned on, and aart-cli's version. Never a project, path, argument, prompt,
  Registry address, user or host name, or credential.
- **The outbox.** `state/telemetry.sqlite3` in the application home, created 0600, holds whether
  telemetry is on or off once that was decided, the address, the installation id, the history key,
  every event with whether it is waiting, sent, rejected or skipped,
  and the synchronisation state: last success, last attempt, the next moment an attempt may start,
  failures in a row, and a pause after a refused authorisation. A database with another schema
  version is reported and never rewritten.
- **When it is sent: on activity, at most every ten minutes.** Recording an event commits it to
  the outbox, then checks, without waiting, whether a synchronisation is due: something is
  waiting, nothing was ever sent successfully or at least 600 s passed since the last success,
  and the backoff or pause has passed. When it is due, a short-lived process is started and the
  hook or command returns at once. There is no daemon, LaunchAgent, timer or event-count
  threshold; after a quiet period nothing is sent until the next event, or `consume telemetry
  sync`.
- **One sender at a time.** The process takes a non-blocking lock on `state/telemetry.lock`, and
  only its holder checks again and sends; another exits. It sends up to 100 events a request, at
  most 20 requests and 60 seconds a run, with a 10-second timeout, and never holds a transaction
  open while a request is in flight.
- **What an answer does.** Only the ids a `200` acknowledges are marked sent. Events the server
  names in a `422` are marked rejected and the rest are sent again; a request refused as a whole
  (`400`, `413`, `422` naming none) is split, and a single event refused is marked rejected. `401`
  or `403` pauses automatic attempts for an hour. Anything else, a timeout or no connection keeps
  every event and backs off 1, 2, 5, 10, then 30 minutes, plus up to a fifth more at random. A
  success clears the backoff. A process killed mid-request leaves its events waiting.
- **It never fails what it rides on.** A hook still exits 0 with nothing on stdout, and an
  install, update or uninstall still reports its own outcome, whatever telemetry does.
- **`consume telemetry status [--json]`** shows whether it is on, the address, the installation
  id, how many events wait, were sent, rejected or skipped, the last success and attempt, and when
  the next attempt may start. **`consume telemetry sync [--force]`** sends now: it does not wait
  for the ten minutes, keeps the lock, and honours the backoff and pause unless `--force`.

**INV-322 — Nothing is sent unless telemetry is on, and what is sent is Activity's, each record
once.** For any sequence of actions, uses and turning telemetry on and off, the outbox holds exactly
one event per Activity record (one per artifact an action changed) that was recorded while
telemetry was on or existed when it was turned on, and nothing else. A build that names no server
holds none until a person turns telemetry on; one that does turns it on only for a home where
nobody decided yet.

**INV-323 — An event carries the contract's fields only, and a use only as an installed
artifact.** Every event sent satisfies `docs/telemetry-api-v1.md`; a use that no installed
artifact answers to produces no event; no event holds a project, path or argument.

**INV-324 — A synchronisation is due only on time, never on count.** For any state, moment and
number waiting, a synchronisation is due exactly when something waits, the backoff or pause has
passed, and nothing was sent successfully before or `SYNC_INTERVAL` has passed since.

**INV-325 — An event is marked sent only when the server acknowledged its id.** Whatever a server
answers, or if it never answers, every event not acknowledged by id stays waiting or, when the
server named it invalid, rejected.

**INV-326 — At most one sender at a time.** Any number of concurrent triggers start at most one
upload at a time for one application home.

**INV-327 — A telemetry address never carries a credential, and is plain HTTP only to loopback.**
Every accepted address is `https://`, or `http://` to a loopback host, with no user, password,
query or fragment.

**INV-328 — Telemetry never fails what triggered it.** A hook exits 0 with nothing on stdout and an
action's outcome is unchanged whatever the outbox, the lock, the network or the server does.
