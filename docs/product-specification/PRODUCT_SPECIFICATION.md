# AART Product Specification

> **STATUS: CANONICAL — SOLE PRODUCT SOURCE OF TRUTH**
>
> **Target repository:** `M1F1/aart-cli`
>
> This document is the canonical product specification for the AART refactor. It defines the
> accepted product behavior, architecture, UX, TUI contracts, domain model, registry/source/
> candidate/marketplace boundaries, lifecycle, reconciliation model, policies, security rules,
> credential handling, testing expectations, maintainer workflows, consumer workflows, edge cases,
> migration invariants, and release direction.
>
> If any historical `PLAN.md`, `PROGRESS.md`, `TODO.md`, `docs/design/*`, `docs/product/*`, README
> prose, issue, comment, legacy implementation, or older AART repository conflicts with this
> document, **this Product Specification wins**.
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

# AART Enterprise Architecture v3 — Cumulative Design
## Algebraic model for artifacts, requirements, remediations, effects, policies, MCP runtimes, and TUI-driven configuration

> **Status:** cumulative architecture draft v3  
> **Primary goal:** design AART as an open-source, enterprise-ready package manager and marketplace for agent artifacts.  
> **Primary human interface:** TUI.  
> **Automation interface:** deterministic CLI / JSON suitable for CI/CD.  
> **Out of scope for now:** an autonomous agent itself as an AART artifact type.

---

# 1. Product direction

AART should not be only a marketplace for Agent Skills.

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

# 2. Public AART vs private enterprise configuration

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
          │ enterprise-aart-registry│
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

Nexus or Artifactory should be treated as a **distribution/storage layer**, not as the semantic definition of the AART registry.

---

# 3. Avoid mandatory enterprise forks where possible

A company may fork AART, but the architecture should minimize that need.

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
                       AART DOMAIN
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

Describes **what mutation AART can perform**.

## Remediation

Describes **how an unsatisfied requirement may be resolved**.

## Policy

Describes **which artifacts, requirements, remediations, and effects are permitted in a target environment**.

---

# 5. Artifact algebra

Conceptually:

```python
type Artifact = (
    SkillArtifact
    | McpArtifact
    | GuidelineArtifact
    | HookArtifact
    | MemoryArtifact
)
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
aart://company/mcp/github@1.4.0
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
type McpTransport = (
    StdioTransport
    | StreamableHttpTransport
)

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

the AART model can start conservatively.

Example:

```yaml
kind: mcp
format: aart-mcp-v2

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
AART installs and registers it
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

AART generates a launcher deterministically.

## V3 — native AART runtime adapter

```text
AART runtime adapter:
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

It does not mean AART has already read or stored the credential.

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

AART should explicitly support:

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
    StoreCredential
    | ReplaceCredential
    | DeleteCredential
    | VerifyCredentialAvailability
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
CredentialMutation(
    mode=Create | Replace | Delete
)
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

Replacing it may affect other artifacts
using the same credential reference.

Used by:
  company/mcp/github
  company/mcp/repository-search

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

AART's abstract effect should express intent; the provider-specific interpreter handles the safest implementation.

---

# 18. Never expose the old credential

AART should never offer:

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
aart plan does not require reading secret values
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

AART does not need to persist the actual secret.

---

# 21. Credential transformations

Some launchers transform retrieved secrets.

Avoid making arbitrary shell transformation the only model.

Possible future ADT:

```python
type CredentialTransform = (
    Identity
    | Prefix
    | JsonField
    | Base64Decode
    | Template
)
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

Initially, AART may continue supporting script-based launchers.

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

Runtime requirement does not automatically imply that AART must install the missing dependency.

It may instead provide a remediation.

---

# 26. Minimal dependencies should be a policy preference

Enterprise environments generally prefer fewer dependencies.

AART should not assume:

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

but should not become a required dependency of AART.

If current enterprise MCPs already work with:

```text
server.py
launcher.sh
Keychain
stdio
```

AART should support that path with zero Docker dependency.

---

# 28. Policy algebra

Public AART defines policy primitives.

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

Public AART owns:

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

The user should ideally be able to complete the full lifecycle without leaving AART:

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
aart credentials list
aart credentials inspect github-token
aart credentials verify github-token
aart credentials configure github-token
aart credentials replace github-token
aart credentials delete github-token
```

Equivalent actions should exist in the TUI.

This makes credential lifecycle a first-class application feature.

---

# 38. Shared credential references

A credential may be used by multiple artifacts.

Therefore before replacement or deletion, AART should inspect references.

Example:

```text
github-token is used by:

- company/mcp/github
- company/mcp/repository-search
- company/mcp/code-review
```

Replacement is normally safe if the semantic identity remains the same.

Deletion should warn that dependent artifacts may stop working.

The relationship should exist in registry/runtime metadata, not by searching secret values.

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
    id="github-token",
    provider="macos-keychain",
    service="aart.company.github",
)
```

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
) -> Result[InstallPlan, PlanningError]:
    ...
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
enterprise-agent-artifacts/
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
aart registry validate
 ↓
aart registry policy-check
 ↓
aart registry audit
 ↓
aart registry build
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
canonical AART artifact
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
    def probe(self, source: SourceSnapshot) -> ProbeResult:
        ...

    def discover(
        self,
        source: SourceSnapshot,
    ) -> tuple[ForeignArtifact, ...]:
        ...

    def compile(
        self,
        artifact: ForeignArtifact,
    ) -> CanonicalArtifact:
        ...
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

AART generalizes:

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

private enterprise configuration is not embedded into public AART source

harness-specific configuration never leaks into canonical artifact semantics

MCP does not imply Docker

distribution is independent from transport

runtime requirements are independent from install effects

consumer installation does not crawl arbitrary foreign repository layouts

receipts record only effects actually performed

credential deletion/replacement warns about dependent artifacts

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

credential replacement dependency warnings

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
- [ ] Shared-reference warning.
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

AART then adds:

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
aart
```

Searches for:

```text
company/mcp/github
```

AART shows:

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

AART says:

```text
One requirement is missing.

Configure github-token now?
```

The user pastes the token.

AART:

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
aart
→ Credentials
→ github-token
→ Replace
```

AART:

```text
This credential is used by 3 artifacts.

Enter replacement token.
```

Then:

```text
✓ new credential validated
✓ credential replaced
✓ dependent artifacts remain configured
```

The developer never needs to manually:

```text
open Keychain
edit JSON
export environment variables
leave the TUI
```

unless enterprise policy explicitly requires an external step.

That is the intended AART experience.
---

# 55. Author repository vs AART installation contract

AART must not require an MCP author to redesign the internal implementation of an existing server merely to participate in the marketplace.

An author repository may remain completely usable on its own:

```text
agent-mcp-servers/
└── github/
    ├── server.py
    ├── launcher.sh
    ├── src/
    ├── tests/
    └── aart.yaml
```

The author may continue using:

```text
launcher.sh
custom development scripts
manual debugging flows
repository-specific conventions
```

AART introduces a separate contract:

> **You own the MCP implementation. AART owns the installation contract.**

The `aart.yaml` / `aart.json` manifest is that contract.

---

# 56. `aart.yaml` is a package manifest, not a launcher

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
schema: aart.dev/mcp/v1

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

AART should not crawl arbitrary repository layouts and guess what constitutes an artifact.

Instead:

```text
repository
   ↓
discover known AART manifests
   ↓
each manifest defines one artifact boundary
```

For example:

```text
agent-mcp-servers/
│
├── github/
│   ├── server.py
│   ├── launcher.sh
│   └── aart.yaml
│
├── jira/
│   ├── server.py
│   └── aart.yaml
│
└── confluence/
    ├── server.py
    └── aart.yaml
```

produces three candidate artifacts.

The discovery contract should be explicit, for example:

```text
**/aart.yaml
**/aart.json
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
aart.yaml
```

is the **authoring format**.

```text
artifact.json + payload/
```

is the **canonical registry package**.

Conceptually:

```text
aart.yaml
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

An MCP can exist perfectly well outside AART.

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
author adds aart.yaml
      ↓
AART validation
      ↓
enterprise review/policy
      ↓
canonical artifact build
      ↓
registry
      ↓
marketplace
```

This makes adoption incremental instead of requiring every internal project to use AART from day one.

---

# 61. AART takes responsibility after publication

Once an artifact is published through the AART-native path:

```text
AART owns:
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

which compiles into known AART domain objects and effects.

---

# 63. Escape hatch for existing launchers

Existing `launcher.sh` scripts remain useful as a compatibility mechanism.

Example:

```yaml
launch:
  type: external-script
  path: launcher.sh
```

AART should model this explicitly as arbitrary executable behavior rather than pretending it understands the script.

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
AART Native
AART Compatible
Legacy
```

Possible semantics:

## AART Native

```text
declarative manifest
known requirements
known credential bindings
known launch model
known effects
no arbitrary installation scripts
```

## AART Compatible

```text
valid AART manifest
but uses an escape hatch such as external launcher
```

## Legacy

```text
no AART installation contract
manual/internal use only
not eligible for normal marketplace installation
```

Enterprise policy can require:

```yaml
marketplace:
  minimum_compliance: aart-native
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
 └── aart.yaml
        │
        │ aart build
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
        AART Registry
            │
            ▼
         Marketplace
            │
            ▼
        aart install
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
**/aart.yaml
**/aart.json
```

It should not infer artifact semantics from arbitrary repository contents.

## Manifest parser

Validates syntax and produces an authoring-domain representation.

## Compiler

Converts the authoring representation into the canonical AART artifact model.

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
AART manifest ───────► compiler ──┐
                                  │
Foreign format ──────► importer ──┼──► CanonicalArtifact
                                  │
Native registry pkg ──────────────┘
```

---

# 67. AART effect engine is predefined and finite

The manifest should select from capabilities understood by AART.

It should not define new effect implementations.

Conceptually:

```text
aart.yaml
    ↓
declarations
    ↓
AART compiler
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

New effect types are introduced by new AART versions, reviewed as public tool behavior, rather than injected by artifact manifests.

This is essential for enterprise auditability.

---

# 68. Manifest declares intent; AART chooses implementation

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

AART lowers the declaration using platform-specific interpreters.

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
                         aart.yaml
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
                       AART Registry
                              │
                              ▼
                        Marketplace
                              │
                              ▼
                         aart install
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
└── aart.yaml
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
shared-reference warnings
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

and migrate popular marketplace MCPs toward `AART Native`.

---

# 71. Final publication contract

The marketplace contract should be simple enough to explain to an internal MCP author:

> Your MCP may be implemented and developed however you want.  
> If you want it distributed through the AART marketplace, add an AART manifest next to the artifact entry point.  
> The manifest declares which files form the artifact, what runtime and credentials it needs, how it is launched, and what compatibility it has.  
> AART validates that declaration, builds a canonical immutable artifact, evaluates enterprise policy, and takes responsibility for installation and configuration.

This preserves developer freedom while standardizing enterprise distribution.

The concise principle is:

```text
Author owns implementation.
Manifest owns declaration.
Registry owns approved identity.
Policy owns permission.
AART owns installation.
```

---

# 72. Registry synchronization model

AART should distinguish two completely different synchronization workflows:

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
  - id: agent-mcp-servers
    repo: git.company/agent-mcp-servers
    discovery:
      manifests:
        - "**/aart.yaml"
        - "**/aart.json"

  - id: platform-ai
    repo: git.company/platform-ai
    discovery:
      manifests:
        - "**/aart.yaml"
        - "**/aart.json"
```

A scheduled or manually triggered CI workflow scans those repositories:

```text
configured source repositories
            ↓
checkout source at a concrete commit
            ↓
discover known AART manifests only
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

The author explicitly opts into AART distribution by adding a supported manifest.

The invariant remains:

```text
No manifest
=
No AART artifact candidate
```

---

# 73. Automated registry update PRs

Discovery of an upstream change must not automatically modify the approved registry.

Instead, registry CI produces an update proposal, preferably as a pull request.

Example:

```text
Registry sync: agent-mcp-servers

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

For approved enterprise registries, AART should default to materializing the complete installable artifact into the registry rather than leaving the registry entry as only a link to an upstream repository.

Example upstream:

```text
agent-mcp-servers/
└── github/
    ├── aart.yaml
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
If an approved artifact version exists in an AART Registry,
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

A source repository commit changing does not necessarily mean an AART artifact changed.

Especially in monorepositories, unrelated files may change constantly.

Therefore registry scanning should compute an `ArtifactInputDigest` from only the inputs that semantically define the artifact.

Conceptually:

```text
aart manifest
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

This becomes particularly important when AART scans hundreds of repositories or large monorepositories.

---

# 79. Registry CI at scale

The final developer running `aart` should never be responsible for scanning hundreds of enterprise source repositories.

Source discovery belongs to registry maintenance infrastructure.

A private enterprise registry repository may look like:

```text
enterprise-aart-registry/
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
aart registry scan
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
- artifact authors own `aart.yaml`,
- registry automation owns discovery and compilation,
- reviewers own promotion decisions,
- consumers see only approved registry state.

---

# 80. Optional referenced mode

AART may still support a lighter referenced artifact mode:

```python
type ArtifactSourceMode = Vendored | Referenced
```

`Referenced` means the registry stores a pinned source reference rather than a durable canonical payload.

This can be useful for:

```text
development registries
experimental artifacts
personal registries
temporary integrations
very large or externally managed artifacts
```

However, `Vendored` should be the default for approved enterprise marketplaces.

The marketplace can surface the distinction:

```text
company/mcp/github
✓ Vendored
✓ Reproducible
✓ Upstream-independent
```

versus:

```text
experimental/mcp/foo
⚠ Referenced upstream
⚠ Availability depends on source
```

Policy can restrict the mode:

```yaml
production:
  allowed_source_modes:
    - vendored
```

The finite policy algebra therefore may include primitives such as:

```text
AllowArtifactSourceMode(Vendored)
ForbidArtifactSourceMode(Referenced)
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
AART CLI
```

A consumer may not even need permission to access the original author repository.

---

# 83. Consumer marketplace and available updates

After consumer registry synchronization, AART compares installed artifact receipts/locks against the approved versions now available in subscribed registries.

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

# 84. Project and global installation scopes

AART should retain explicit installation scopes.

At minimum:

```python
type InstallScope = (
    ProjectScope
    | UserScope
    | HarnessGlobalScope
)
```

## 84.1 Project scope

Project-local artifacts are associated with a project and can be pinned reproducibly.

Example:

```text
my-project/
└── .aart/
    ├── lock.json
    └── receipts/
```

Typical use cases:

```text
skills
guidelines
hooks
project-specific MCP servers
project memory/configuration
```

Example command:

```text
aart install company/mcp/github
```

may default to project scope when executed inside an AART-enabled project.

The lock captures the exact approved artifact version/digest.

---

## 84.2 Global / harness scope

Artifacts may also be installed for a user or globally into a selected harness environment.

Examples:

```text
Claude
Codex
Cursor
other supported harnesses
```

Conceptually:

```text
aart install company/mcp/github --global
```

The receipt records the target:

```yaml
scope: harness-global
harness: claude
artifact: company/mcp/github
version: 1.5.0
digest: sha256:...
```

Global and project installations are independently updateable.

Examples:

```text
aart update --project
aart update --global
```

---

# 85. Install target as a first-class domain value

Rather than scattering `--global` logic through installers, scope and harness should form a first-class value in the planning model.

Example:

```python
@dataclass(frozen=True)
class InstallTarget:
    scope: InstallScope
    harness: Harness | None
```

Examples:

```python
InstallTarget(
    scope=ProjectScope(path="/workspace/project"),
    harness=Claude(),
)
```

or:

```python
InstallTarget(
    scope=HarnessGlobalScope(),
    harness=Codex(),
)
```

The planner can then lower semantic installation intent into target-specific primitive effects.

This keeps scope logic out of the TUI and out of artifact manifests.

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
                              aart registry/source sync
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
aart registry scan
aart registry discover
aart registry refresh-upstreams
```

Preferred semantic meaning:

```text
registry scan
=
inspect configured source repositories and produce candidate registry changes
```

Possible consumer-side vocabulary:

```text
aart source sync
```

or:

```text
aart registry sync
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
AART Manifest
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
Consumer AART
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

For the enterprise AART use case, the recommended default is now:

```text
Author repository
    ↓
aart.yaml
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

AART must explicitly distinguish confidential runtime inputs from ordinary runtime configuration.

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

AART connects those two sides during installation.

The core rule is:

```text
Artifact declares contract.
Environment declares binding.
AART builds the installation projection.
```

---

# 92. Runtime input algebra

AART should model runtime inputs as at least two separate classes:

```python
type RuntimeInput = (
    SecretInput
    | ConfigInput
)
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

They may be collected interactively during setup and persisted as part of the local AART installation state or generated runtime projection.

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

the artifact manifest should describe those process bindings without coupling them to Keychain, Vault, environment variables, or AART itself.

Example authoring manifest:

```yaml
schema: aart.dev/mcp/v1

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
AART credential storage implementation
```

Those belong to deployment/user configuration.

---

# 94. Value source and process binding are separate concepts

AART should not conflate:

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
    SecretProviderReference
    | PersistedConfigValue
    | PromptedValue
    | PolicyProvidedValue
)

type ProcessBinding = (
    CliArgumentBinding
    | EnvironmentBinding
    | FileBinding
    | StdinBinding
)
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

Non-secret configuration may be persisted in local AART-owned state.

For example:

```text
project/
└── .aart/
    ├── lock.json
    ├── config/
    │   └── company-mcp-github.json
    └── receipts/
```

Example persisted configuration:

```json
{
  "github-host": "https://github.company",
  "username": "michal.filek"
}
```

This state contains no secret values.

A receipt may reference the configuration identifiers and hashes without treating them as confidential.

---

# 97. Generated launcher may embed non-secret values

When producing a runtime projection, AART may materialize non-secret configuration values directly into the generated launcher.

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

This keeps runtime independent from AART while preventing secrets from being written into generated files.

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
        └── aart/
            └── mcp/
                └── github/
                    ├── launch.sh
                    ├── server.py
                    └── src/
```

Tabnine settings should point directly to the generated runtime projection:

```json
{
  "mcpServers": {
    "github": {
      "command": ".tabnine/agent/aart/mcp/github/launch.sh"
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

AART is not required at runtime.

---

# 100. Runtime independence invariant

A successful AART installation must not require the AART executable during artifact runtime unless the artifact explicitly declares AART itself as a runtime dependency.

Strong invariant:

```text
Successful installation
MUST NOT require `aart` at runtime.
```

Therefore:

```text
AART = installer / compiler / planner / configurator

AART != implicit artifact runtime
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

AART may support secret delivery through CLI arguments when that is the executable's existing public contract.

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


AART
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

AART connects the two at install time
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
.tabnine/agent/aart/mcp/github/
├── payload/
│   ├── server.py
│   ├── requirements.txt
│   └── src/
├── runtime/
│   └── .venv/
└── launch.sh
```

This isolates dependency versions between MCP servers and makes update, rollback, uninstall, verification, and ownership significantly simpler.

Deduplicating environments may be considered later as an optimization, but it must not weaken isolation or reproducibility semantics.

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

AART should not invent a replacement Python dependency language.

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

AART must explicitly separate:

```text
dependency specification
!=
dependency installer
```

For example, `requirements.txt` describes dependency input. It does not require AART to use `pip`; a compatible backend such as `uv` may install the same requirements.

Conceptually:

```python
type PythonDependencySpec = (
    RequirementsFile
    | PyProjectSpec
    | PoetryProjectSpec
    | UvProjectSpec
)

type PythonDependencyInstaller = (
    PipInstaller
    | UvInstaller
    | PoetryInstaller
)
```

The artifact declares the dependency specification. The AART environment/platform/profile/policy selects a compatible installer.

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

AART should not require every artifact to provide multiple equivalent formats such as:

```text
requirements.txt
poetry.lock
uv.lock
```

An artifact chooses one supported dependency contract. AART adapts to that contract.

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

AART itself can retain zero Python runtime dependencies by invoking available system tooling through its effect interpreters rather than importing package-manager libraries.

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

AART is not present in the runtime path after successful installation.

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

The default ownership rule is:

```text
Each installed Python MCP owns:
- its canonical/materialized payload
- its isolated Python environment
- its resolved dependency installation
- its generated runtime projection
- its AART-owned harness configuration fragment
```

Therefore AART can reason precisely about:

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
AART installs artifact dependencies into an artifact-owned isolated runtime by default.
It MUST NOT mutate the user's global language environment unless explicitly requested and permitted by policy.
```

---

# 116. TUI evolution strategy: reuse behavior, refactor boundaries

The existing AART TUI should be evolved rather than rewritten from zero.

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

The most important design criterion for AART, including the TUI, is:

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
Preferred AART design
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
def transition(state: AppState, event: UiEvent) -> AppState:
    ...
```

or, where commands/effects must be emitted:

```python
def transition(state: AppState, event: UiEvent) -> tuple[AppState, tuple[UiCommand, ...]]:
    ...
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
agent_artifacts/
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

AART should retain the value of a zero-runtime-dependency CLI/TUI unless a strong product reason appears to change it.

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

This section is the **single canonical quick-reference list of AART architectural invariants**.

Earlier sections may explain or motivate individual invariants, but this catalog is the authoritative place to review the complete set. When a new invariant is introduced, it should be added here in the same change.

## A. Core architectural invariants

**INV-001 — Public/private boundary**

```text
PUBLIC TOOLING != PRIVATE ENTERPRISE CONTENT
```

Public AART contains reusable mechanisms, schemas, algebras, planners, adapters, interpreters, CLI/TUI, and policy machinery. Enterprise-specific artifact definitions, policy values, profiles, internal endpoints, credential references, and trust decisions live outside the public tool.

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

Undo may reverse only state owned or explicitly captured by the corresponding AART operation; it must not blindly restore unrelated external state.

## B. Artifact and package invariants

**INV-010 — Semantic kind is separate from format/protocol**

Artifact kind, concrete package format, and runtime protocol are separate dimensions.

**INV-011 — Repository is not artifact payload**

```text
Git repository != artifact payload
```

The declared artifact boundary determines canonical payload membership.

**INV-012 — No manifest, no native candidate**

For AART-native repository discovery:

```text
No supported AART manifest = No AART artifact candidate
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
If an approved vendored artifact version exists in an AART Registry,
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

When multiple registries expose conflicting coordinates/versions in an enterprise context, AART should surface ambiguity or require explicit selection rather than silently choosing an unreviewed source.

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

A requirement states what must be true; an effect states what AART may do to make/change something.

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

**INV-039 — AART is not an implicit runtime**

```text
Successful installation MUST NOT require `aart` at artifact runtime
unless the artifact explicitly declares AART as a runtime dependency.
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

**INV-044 — Python MCPs own isolated environments by default**

```text
1 installed Python MCP = 1 artifact-owned isolated Python environment
```

unless a future explicitly selected and policy-approved sharing model is used.

**INV-045 — No implicit global language mutation**

AART must not mutate the user's global Python/language environment unless explicitly requested and allowed by policy.

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

`server.py` should know its CLI/runtime input contract, not macOS Keychain, AART, Tabnine, or enterprise secret-manager implementation details.

**INV-051 — Secret values never enter persistent AART state**

Secret material must never be persisted in normal AART artifact/configuration state.

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

**INV-055 — Config values may persist only under policy**

Non-secret configuration may be stored/materialized when policy permits; this permission does not extend to secrets.

**INV-056 — Credential replacement does not expose the old secret**

Replacing/rotating a credential must not require reading or displaying the previous value.

**INV-057 — Shared credential mutations surface dependents**

Deleting/replacing/rebinding a credential reference warns about artifacts that depend on the same reference before destructive mutation.

## H. Scope and ownership invariants

**INV-058 — Installation scope is explicit**

Project, user/global, and harness-specific targets are explicit installation boundaries rather than inferred side effects.

**INV-059 — Project and global installation states are independent**

Mutating one scope must not silently mutate another.

**INV-060 — Installed artifact ownership is explicit**

An installed Python MCP normally owns its payload, isolated runtime, resolved dependency installation, generated runtime projection, and AART-owned harness configuration fragment.

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

The baseline AART CLI/TUI should not gain mandatory presentation dependencies without a demonstrated product/security/maintenance benefit. Richer frontends may be optional skins.

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
INV-057  shared credential dependency warnings
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

AART should continue the strong idea already present in the current repository: the public repository contains one canonical workflow implementation, while an enterprise fork adapts execution through GitHub repository/organization settings rather than rewriting workflow YAML.

The governing principle is:

```text
PUBLIC CI SEMANTICS
        +
ENTERPRISE EXECUTION PROFILE
        =
SAME QUALITY CONTRACT IN A DIFFERENT ENVIRONMENT
```

Enterprise forks should therefore parameterize infrastructure, not redefine correctness.

## 126.1 What the current AART CI already gets right

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

## 126.2 What should be improved as AART grows

As the architecture gains registries, policy, artifact compilation, dependency resolution, TUI tests, credential abstractions, and property tests, a flat list of unrelated `AART_*` variables will become harder to reason about. The solution is not to make GitHub Actions itself more clever. The solution is to define an explicit **CI Profile Contract**.

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

This mirrors the wider AART architecture:

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
AART_RUNNER
AART_CI_IMAGE
AART_PYTHON
AART_PYTHON_VERSIONS
AART_PIP_INDEX_URL
AART_RELEASE_PYTHON_VERSION
AART_POETRY
AART_REFERENCE_REGISTRY_URL
AART_INDEX_PUBLISH_URL
```

Use variables to point to secret names where dynamic lookup is required:

```text
AART_IMAGE_USERNAME_SECRET
AART_IMAGE_PASSWORD_SECRET
AART_PIP_INDEX_CREDENTIALS_SECRET
AART_INDEX_PUBLISH_CREDENTIALS_SECRET
```

The actual credential values remain only in GitHub Secrets.

This is the CI equivalent of AART's runtime rule:

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
AART_SKIP_TESTS=true
AART_DISABLE_PROPERTY_TESTS=true
AART_IGNORE_POLICY_FAILURES=true
AART_MIN_COVERAGE=0
AART_SKIP_PACKAGING_CHECK=true
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
AART_CI_IMAGE set
  -> Python setup download must not be required

private image credentials selected
  -> both referenced secrets must resolve

AART_PYTHON_VERSIONS with a fixed one-Python image
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
  AART_RUNNER=["self-hosted","linux"]

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
├── AART_RUNNER
├── AART_CI_IMAGE
├── AART_PIP_INDEX_URL
├── secret references
└── internal publishing endpoints

repository
└── overrides only when genuinely repository-specific
```

This makes a newly created AART registry or enterprise fork work with minimal setup and reduces configuration drift across many registries.

## 126.10 Reusable workflows versus local composite actions

The existing local composite actions are a good choice for sharing implementation between public/private-image job shells. Keep them for step composition.

Reusable workflows can be useful later for organization-wide policy, but AART should not require a central enterprise workflow repository to function. A fork must remain self-contained.

Preferred layering:

```text
workflow YAML              orchestration / permissions / matrix
local composite actions    reusable GitHub-specific step adapter
Python scripts             deterministic build/validation logic
AART domain/application    reusable semantic logic where applicable
```

## 126.11 Fork portability invariant

The desired enterprise experience remains:

```text
1. fork/mirror AART
2. configure organization/repository variables + secrets
3. run the same workflows
4. no source edits required for infrastructure differences
```

Only intentional semantic customization should require committed source/policy changes.

## 126.12 Development tooling boundary

Hypothesis, pytest, mutmut, ruff, mypy, coverage, and similar tools are CI/development dependencies only. Their presence in CI is encouraged; their presence in the installed AART runtime is forbidden by INV-071.

---

# 116. Automated Semantic Versioning and Release Automation

AART release versioning MUST be automatic, driven from reviewed change semantics, and MUST NOT depend on hand-maintained version consistency tests between source files, tags, release metadata, or package metadata.

The release model is based on Semantic Versioning plus Conventional Commits:

```text
fix:        -> PATCH
feat:       -> MINOR
<type>!:    -> MAJOR
BREAKING CHANGE: -> MAJOR
```

The version is a derived release artifact, not a value developers manually keep synchronized across files.

## 116.1 Release automation tool

For AART, the preferred default is **Release Please** rather than Python Semantic Release.

Reasons:

1. AART already uses GitHub Actions as the public CI orchestration layer.
2. Release Please creates and continuously updates a release PR from Conventional Commits.
3. The release PR makes the generated CHANGELOG and proposed SemVer bump reviewable before release.
4. Merging the release PR creates the tag and GitHub Release.
5. Package publication remains a separate explicit release effect, which fits AART's existing CI architecture and enterprise-fork model.
6. Release Please supports Python packages but does not become a runtime dependency of AART.
7. Release automation runs in CI only and therefore does not violate the zero-runtime-dependency invariant.

Python Semantic Release is a good Python-native alternative, but it couples version calculation, source version stamping, changelog generation, tagging, and publication more tightly. AART prefers release orchestration where version decision/release metadata and package publication remain separable effects.

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

AART SHOULD use squash merge for normal feature PRs.

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

They MUST NOT become AART runtime dependencies.

This extends the development-tool isolation invariant already covering Hypothesis, pytest, mutmut, ruff, mypy, and coverage.

## 116.9 Release tests that should disappear

AART SHOULD remove tests whose only purpose is keeping manually duplicated version values synchronized, for example tests asserting that:

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

AART's default release semantics are `fix -> PATCH`, `feat -> MINOR`, and breaking changes -> `MAJOR`.

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

Semantic-release/changelog/commit-validation tooling MUST NOT enter AART's runtime dependency graph.

### INV-089 — Release artifact verification targets outputs, not bookkeeping

Release checks SHOULD verify properties of the produced artifact and publication result, not manually duplicated version bookkeeping.

### INV-090 — Reviewed merge boundary drives release semantics

Under the preferred squash-merge workflow, the reviewed PR title/squash commit is the canonical Conventional Commit used by release automation.


## 116.10 Hands-off release mode

AART distinguishes automatic version calculation from release approval.

The default recommended mode is reviewable automation: Release Please maintains the release PR automatically; merging that PR materializes the release.

If the project requires literal hands-off releases, the release PR MAY be auto-merged once the stable required CI gate succeeds and repository policy permits it. In that mode no developer manually edits a version or changelog and no separate release command/button is required.

The trade-off MUST remain explicit: automatic merging increases release frequency and removes the final human batching/release boundary. Therefore hands-off auto-merge is a repository release-policy choice, while SemVer calculation itself remains identical in both modes.

### INV-091 — Version calculation is never manual

Whether release materialization is reviewable or hands-off, the next SemVer and changelog MUST be calculated automatically from reviewed change semantics.


# Release lifecycle architecture

## Canonical release flow

AART uses Conventional Commits semantics, Semantic Versioning, and Release Please to automate version calculation and changelog generation while retaining an explicit release boundary.

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

The generated release PR passes the normal project quality contract. AART does not introduce a second large release-specific source test suite merely to repeat tests already proven on ordinary pull requests.

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
- `aart --version` works;
- `aart --help` works;
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
- **INV-096 — Release PR uses project quality contract:** A generated release PR MUST satisfy the normal required quality contract before it can become a release.
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

# 141. Migration strategy: evolve the existing AART repository

The preferred implementation strategy is to refactor the existing AART repository rather than
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
agent_artifacts/
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
aart.yaml
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

AART has a verification layer above unit, property, integration and deterministic E2E tests:
a **Git-backed live acceptance ecosystem**.

It models the topology in which AART actually operates:

```text
aart-cli
  │
  ├── artifact source repo A
  │     ├── mcp/github/
  │     │     ├── server.py
  │     │     ├── dependency descriptor
  │     │     └── aart.yaml
  │     └── other artifacts + manifests
  │
  ├── artifact source repo B
  │     └── artifacts + manifests
  │
  ├── synthetic AART registry repo
  │     ├── artifacts/
  │     ├── policies/
  │     ├── profiles/
  │     └── sources.yaml
  │
  └── consumer project repo
        ├── harness configuration
        ├── .aart state
        └── normal project files
```

The source repositories are ordinary artifact-development repositories. Artifacts can exist and run
without AART; AART integration begins with their manifests.

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
aart
aart-live-source-mcp
aart-live-source-skills
aart-live-registry
aart-live-consumer-tabnine
aart-live-consumer-generic
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
mocks of internal AART functions.

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
acceptance/lint/type/coverage/CI tooling must not leak into AART's production runtime dependency
graph.

**INV-122 — Acceptance topology is implementation-independent.** Repositories may be split or
consolidated over time; correctness depends on modeled contracts and realistic topology, not fixed
repository names or count.

**INV-123 — Fast feedback and realistic proof coexist.** Mandatory PR verification should retain a
fast feedback path with selected live smoke scenarios; broader expensive acceptance matrices may
run in deep-quality, scheduled or release-candidate workflows.

---

# 145. Multi-artifact installation, Collections and TUI Selection

AART installation is modeled as:

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

Resolution produces exact approved versions and deduplicates artifacts while retaining why each is
present. The same artifact may be required by a direct selection and multiple Collections.

An exact Collection installation is distinct from using a Collection as a selection template. If a
member is removed before installation, the resulting state is a custom selection derived from the
Collection, not a false claim that the exact Collection is installed.

Ownership provenance must survive installation so removing one Collection never removes an artifact
still required by another Collection or direct installation intent.

## 145.2 One transaction wizard

Bulk installation must not create N independent wizards. Requirements are aggregated across the
resolved set, with equivalent requirements deduplicated while preserving dependants.

Configuration and secrets remain separate stages. One final InstallPlan describes all artifact
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
│ AART / Marketplace                                      scope: PROJECT       │
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

Installed views preserve Collection ownership and show all ownership reasons when an artifact is
shared.

# 148. Bulk Install Plan reference

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
│ + .tabnine/agent/aart/mcp/github/**                                          │
│ + .tabnine/agent/aart/mcp/jira/**                                            │
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

**INV-129 — Shared ownership prevents unsafe removal.** Removing one ownership reason cannot remove
an artifact still required by another.

**INV-130 — Bulk installation produces one coherent plan.** A multi-artifact operation has one
InstallPlan and one review boundary.

**INV-131 — Requirements aggregate semantically.** Equivalent requirements should be deduplicated
while preserving which artifacts depend on them.

**INV-132 — Config and secrets remain distinct during bulk setup.** Aggregation cannot collapse
ConfigInput and SecretInput into an untyped prompt flow.

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

The AART migration will span multiple sessions and may be implemented by different coding agents.
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

AART serves users with different levels of infrastructure knowledge. The installation workflow must
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

> Ask only for decisions or values that AART cannot safely derive.

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
│ AART will securely store the token in macOS Keychain.                       │
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

AART must surface information when user action or informed approval is required, including:

```text
missing required input
credential creation/replacement/deletion
shared credential impact
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
aart marketplace install ...
aart marketplace install ... --verbose
```

Exact CLI flags remain an implementation decision.

CI/JSON interfaces are not governed by human-oriented minimal presentation. Machine-readable output
should remain complete, stable and structured while still respecting secret-redaction invariants.

---

# 153. Canonical Project Invariant Catalog — progressive-disclosure additions

**INV-149 — Fast and Verbose share installation semantics.** Presentation detail must not select a
different planner, policy path, resolver or effect semantics.

**INV-150 — Minimal mode asks only necessary questions.** Fast installation should request only
values/decisions AART cannot safely derive plus approvals required by risk or policy.

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
installation without understanding AART internals.

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

The purpose is to remove the need for the user to leave AART and guess what is required.

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
shared credential value
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

If multiple artifacts share the same semantic input, AART should avoid presenting the same guidance
multiple times where safe to do so.

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

**INV-164 — Collection guidance aggregates without duplication.** Multi-artifact installation
should consolidate equivalent input guidance while preserving which artifacts depend on the input.

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

AART is not only an installer. For installed artifacts it acts as a declarative desired-state
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

AART may propose:

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
longer owned/required elsewhere. Shared artifacts are retained with a user-facing explanation.

Credentials are retained by default when the final dependent artifact is removed unless the user
explicitly chooses credential deletion or policy requires another outcome.

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

**INV-175 — Unsupported repair semantics are surfaced.** When AART cannot safely inspect or repair a
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

**INV-185 — Credential cleanup is explicit.** Uninstall must not silently delete credentials merely
because their final known artifact dependency disappeared; deletion is a separate explicit/policy
governed mutation.

**INV-186 — Collection health derives from member state.** Collection status must reflect relevant
member health without hiding which member requires attention.


---

# 161. Accepted Consumer TUI Screen Catalog

Status: **ACCEPTED**. This catalog is the canonical consumer-side product/interaction contract. Exact terminal spacing may evolve, but information hierarchy, safety behavior and navigation semantics must remain intact unless explicitly superseded.

## 161.1 01 Dashboard — ACCEPTED

Persistent application with left navigation and Fast UX by default. Overview emphasizes installed count, updates, attention and recent activity. Global keys include arrows, Enter, Esc, `/`, `?`, `q`. Contextual shortcuts appear only where relevant.

Maintainer Mode is hidden by default and enabled in Settings. With it disabled, maintainer navigation does not appear.

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

Canonical flow:

```text
Marketplace
   ↓
Review Selection
   ↓
automatic resolution / inspection
   ↓
Required Inputs       [only if needed]
   ↓
Remediation           [only if a decision is needed]
   ↓
Ready to Install
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

Known valid config is pre-filled. Existing secrets are shown only as `Configured securely`.

### 08 Remediation

Only meaningful choices are surfaced. Example:

```text
Python environment required

AART will create an isolated Python environment for 2 MCP servers.
This will not modify your system Python.

[ Continue ]
```

### 09 Ready to Install

Concise final review summarizes outcomes such as configured MCP servers, isolated environments, installed skills/rules and securely stored credentials. `Show details` exposes the same InstallPlan in Verbose mode.

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

Lists Collections and artifacts with health, version and ownership/use context.

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

Uninstall respects ownership. Collection removal deletes only artifacts no longer required/owned elsewhere and explains what is retained and why. Credentials are retained by default unless explicitly deleted or policy says otherwise.

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

**Registry sync is not artifact update.** Sync may discover `github-mcp 1.6`; installed `1.5` remains untouched until an explicit update plan is accepted.

## 161.8 22–24 Credentials — ACCEPTED

Credentials is a reference/lifecycle view, never a password manager exposing values.

```text
✓ GitHub token       Ready
  Used by 3 artifacts

⚠ Jira token         Attention
  Authentication failed
  Used by jira-mcp

○ Database token     Unused
```

Credential Details show provider, health, consumers and actions:

```text
GitHub token                                      ✓ Ready
Stored securely: macOS Keychain

Used by
• github-mcp
• code-review-mcp
• repository-search

[ Verify ] [ Replace ] [ Delete ]
```

A CredentialReference may be shared by multiple artifact consumers. Replacement is a single credential mutation followed by verification of affected consumers where supported. Deleting an in-use credential clearly shows affected artifacts and remains policy governed.

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
[ ] Maintainer Mode
```

Maintainer Mode OFF hides Sources, Candidates, Promotion, Registry Diff, Validation and Publish from consumer navigation.

## 161.11 29 Doctor / Check System — ACCEPTED

Doctor performs environment-wide inspection and reconciliation:

```text
AART / Check system

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
aart doctor
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
│           ├── Remediation           [conditional]
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
    └── Maintainer Mode toggle
```

Maintainer navigation is added as a separate advanced area only when Maintainer Mode is enabled.

---

# 163. Canonical Project Invariant Catalog — Consumer TUI additions

**INV-187 — Accepted TUI behavior is a product contract.** Refactoring terminal components must preserve accepted information hierarchy, safety behavior and navigation semantics unless explicitly superseded.

**INV-188 — Registry sync never implies artifact update.** Learning about a newer registry snapshot must not silently mutate installed artifacts.

**INV-189 — Credentials UI is reference-oriented, not value-oriented.** Consumer views may expose provider, health, usage and lifecycle actions but never secret values.

**INV-190 — Shared credentials preserve consumer relationships.** A credential reference may serve multiple artifacts and replacement/verification must account for affected consumers.

**INV-191 — Fast audit UX is Activity.** Receipt remains the complete technical/audit record while the default consumer projection describes meaningful user actions.

**INV-192 — Receipt does not promise universal undo.** Undo, rollback and compensation are offered only when supported by actual effect semantics and retained safe state.

**INV-193 — Maintainer navigation is opt-in.** Maintainer-only concepts remain hidden until Maintainer Mode is enabled.

**INV-194 — Doctor uses reconciliation, not reinstall-all.** Environment-wide health checking identifies drift and constructs minimal repairs rather than replaying all installation workflows.

**INV-195 — Consumer screens progressively disclose implementation detail.** Fast describes outcomes and required decisions; Verbose exposes technical resolution, provenance, requirements, effects and receipts without changing semantics.

**INV-196 — Known valid inputs are reused.** Installation, update, configuration and repair do not reprompt for valid values AART can safely reuse.

**INV-197 — Conditional steps stay conditional.** Required Inputs and Remediation screens exist only when the current plan actually requires user input or a meaningful choice.

**INV-198 — Collection UI preserves semantic identity.** Exact Collection installation and custom member selection remain visibly distinct.

---

# 164. Accepted Maintainer TUI Screen Catalog

This section records the canonical Maintainer Mode screens accepted during the screen-by-screen
review. Status: **ACCEPTED**.

Maintainer Mode is explicitly enabled from Settings and is intentionally more technical than the
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

## 164.1 Screen 30 — Maintainer Dashboard — ACCEPTED

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ AART / Maintainer                                              Verbose       │
├───────────────────┬──────────────────────────────────────────────────────────┤
│ Dashboard         │ Maintainer overview                                      │
│ Marketplace       │                                                          │
│ Installed         │ Sources                         4                          │
│ Updates           │ Candidates                      7                          │
│ Registries        │ Validation failures             1                          │
│ Credentials       │ Ready for promotion             3                          │
│ Activity          │                                                          │
│ Settings          │ Recent maintainer activity                                  │
│                   │ ✓ Synced agent-mcp-servers                                │
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
**/aart.yaml
**/aart.json
```

AART must not discover artifacts by guessing from arbitrary README files, `server.py`, `pyproject`
or repository layout.

Source list:

```text
✓ agent-mcp-servers                                          Synced
  git@github.company:ai/agent-mcp-servers.git
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

Ready         github-mcp            1.6.0        agent-mcp-servers
Ready         jira-mcp              2.3.0        agent-mcp-servers
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

## 164.7 Screens 41–45 — Promotion and Registry Commit — ACCEPTED

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

Commit is explicit. AART may create the local registry commit but does not push it.

## 164.8 Screen 46 — Registry Maintainer View — ACCEPTED

Maintainer Registry view exposes registry validity, artifact counts by kind, current snapshot,
working-tree state and recent promotions.

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

AART never silently chooses a conflicting version.

V1 defaults to one active version per artifact coordinate per scope. Namespaced multi-version
support may be added later but is not assumed by the initial architecture.

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

AART may provide `Prepare Revert`, but the resulting state remains auditable through ordinary Git
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

If a secret is discovered in canonical payload, AART must clearly state that removing the current
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

AART does not claim transaction atomicity beyond actual effect guarantees.

If all applied effects are safely compensatable, the previous state may be restored.

Otherwise:

```text
⚠ Installation partially completed

5 artifacts ready
2 restored
1 needs attention

AART could not fully restore:
database-mcp

[ Repair ]
[ View details ]
```

Partial outcomes are explicit and auditable.

## 165.14 Interrupted execution

An interrupted operation is never resumed by blindly continuing from the next imperative command.

```text
AART found an interrupted operation.

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

AART detects drift in owned/generated state.

```text
⚠ github-mcp configuration changed outside AART

[ Restore AART version ]
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

If AART cannot safely map an old config field to a new one, it asks only for the newly required
value.

Authentication-model changes are explicit:

```text
github-mcp 2.0 requires a new authentication method.

Existing GitHub token cannot be reused.

You will need:
• Client ID
• Client secret
```

Old credentials remain if still referenced by other installed artifacts.

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

AART does not silently convert the exact Collection into a 7/8 custom selection.

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

When the same coordinate/version exists in multiple registries with different content, AART
surfaces ambiguity rather than applying silent registry priority.

```text
⚠ Multiple approved sources

github-mcp 1.6.0

● company-core
○ platform-ai
```

Identical digests may be deduplicated visually, but installation provenance still records the
selected registry/snapshot.

Cross-registry dependency resolution is supported only when allowed by effective policy and remains
visible in Verbose resolution output.

Registry trust classifications such as Enterprise Approved, Community or Local/Unreviewed are
policy inputs and user guidance, not cryptographic proof of safety.

## 165.23 Development installs

Maintainers may test a candidate before registry promotion using an explicit development intent,
for example:

```text
aart dev install ./mcp/github
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
audit references rather than requiring AART to implement its own enterprise RBAC system.

## 165.27 Git PR publication workflow

Recommended enterprise publication:

```text
AART promote
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

AART owns artifact/registry validation and preparation. Existing Git hosting owns branch protection,
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

**INV-201 — Manifest discovery is explicit.** Native source discovery uses declared AART manifests
rather than heuristic repository crawling.

**INV-202 — Maintainer review is semantic-first.** Semantic artifact changes are the primary review
surface; raw file diffs remain available as deeper evidence.

**INV-203 — Published coordinate/version content is immutable.** Different content under an existing
published coordinate/version is a hard conflict requiring a new version.

**INV-204 — Enterprise promotion vendors by default.** Referenced promotion may exist as an explicit
weaker mode, but vendored canonical payload is the enterprise default.

**INV-205 — Promotion never implies push.** AART may validate, materialize and commit registry
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

**INV-212 — V1 assumes one active version per coordinate per scope.** Multi-version activation
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

**INV-222 — AART does not claim Git secret erasure.** Emergency payload purge cannot be represented
as proof that sensitive material disappeared from repository history.

**INV-223 — Offline capability is decomposed.** Cached metadata, payload and runtime dependencies are
separate capabilities and must not be conflated.

**INV-224 — Verification failure changes final health.** Applied effects followed by failed
verification are not reported as clean success.

**INV-225 — Transaction guarantees match effect guarantees.** AART never claims atomicity,
reversibility or compensation that its effects/interpreters cannot provide.

**INV-226 — Interrupted operations re-inspect before resume.** Resume is reconciliation from observed
state, not continuation from an assumed imperative program counter.

**INV-227 — Concurrent mutations are serialized by scope.** Conflicting mutating operations cannot
race over the same managed state.

**INV-228 — External drift is detected.** Owned/generated state changed outside AART is surfaced
before repair; arbitrary drift is not silently adopted.

**INV-229 — Superseded candidates remain auditable.** New candidate revisions do not erase prior
review state.

**INV-230 — Downgrade is reconciliation, not receipt undo.** Version downgrade is planned against
current requirements, policy and compatibility.

**INV-231 — Input contract migrations are explicit.** AART asks for or transforms changed inputs only
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

**INV-241 — AART does not replace Git review authorization.** Enterprise PR/CI/branch protection can
remain the authority for human approval and publication.

**INV-242 — Local promotion is not publication.** Published means present on the canonical
consumer-visible registry branch/snapshot, not merely prepared or committed locally.

