# AART

AART installs reviewed **skills, guidelines, MCP servers, hooks, and memory** from canonical,
validated registry snapshots into a selected harness.

## Install an artifact

One route, end to end: no AART on the machine, to an installed artifact you can verify. You need
Python 3.10 or later, the address of a Registry somebody maintains, and the harness you are
installing into — `claude`, `opencode`, `tabnine` or `vibe`. Everything in angle brackets is yours
to fill in.

**1. Install AART.** The exact command for the repository you are reading this in is on its
[Releases page](../../releases), already filled in with the right address and version; from a
checkout, `python scripts/install_commands.py` prints the same lines. The shape, where
`<repository>` is that address and `X.Y.Z` is the release you want:

```sh
uv tool install "git+<repository>.git@vX.Y.Z"
```

`pip` and `pipx`, private Enterprise instances and the case where a release cannot be installed
from its URL at all are in [Installing AART](docs/install/installing-aart-v1.md).

**2. Connect a Registry.** `source add` acquires, compiles and validates the snapshot *before* it
saves anything, so a Registry that does not answer or does not validate never becomes
configuration:

```sh
cd /path/to/your-project
aart-cli source add --alias <alias> --kind registry-git --location <registry-url> --ref main --default
```

**3. Find the artifact.** `list` prints the whole catalog; `search` is how you find one thing in
it. Every word must match, so a second word narrows rather than widens, and the coordinate it
prints is the one `install` takes:

```sh
aart-cli marketplace search <word>
```

**4. Install it.** Every mutation is two commands on purpose. The first renders the plan and
changes nothing; the second finalizes exactly that plan:

```sh
aart-cli marketplace install <alias>/<kind>/<name> --profile <harness>
aart-cli marketplace install <alias>/<kind>/<name> --profile <harness> --yes
```

**5. Verify.** `status` reports what is installed and whether it still matches the Registry —
`current`, `update_available`, `removed_upstream`, `source_unavailable` or `local_drift`:

```sh
aart-cli marketplace status --profile <harness>
```

### Or do all five in the TUI

Running `aart-cli` with no subcommand on a terminal opens the human-oriented interface, which is
the primary route for a person rather than a script:

```sh
aart-cli
```

It adds the Source, lists and searches the catalog (press `/` and keep typing), shows the same
reviewed plan before anything is applied, and reports the same status. It submits the identical
canonical requests as the flags above — it is not a second command engine, so nothing is available
in one and missing from the other.

### One name, spelled two ways

The command, the package you install and the product are all **`aart-cli`**; the import package is
**`aart_cli`**, because Python names cannot carry a hyphen. There is no second command and no
alias. `agent-artifacts` on a package index is a **different project, belonging to someone else** —
installing it gives you their code, not this one.

## What AART is

A package manager for agent artifacts -- the things an agent is configured with, rather than the
code it edits. It installs **skills**, **guidelines**, **MCP** servers, **hooks** and **memory**
into a harness, from a catalog somebody in your organization has reviewed.

An artifact reaches you through four places that are deliberately not one place. A **Source** is a
repository an author writes in. Scanning one produces **Candidates**: compiled and validated, not
yet approved. A maintainer promotes a Candidate into the **Registry**, the approved and immutable
catalog. **Marketplace** is your view of that Registry -- what you search, what you install, and
what `status` later compares your machine against. No Source installs anything directly, and
nothing enters the Registry without a maintainer putting it there.

On your side of that line AART is a Registry client, which acquires and validates a whole snapshot
before believing any of it; a review surface, which renders the plan an install would apply and
applies nothing until you accept it; and an installer, which writes the harness's own configuration
and can reverse what it wrote. The same compiler runs at both ends, so a catalog cannot publish a
document its consumers would have to work around.

One product, one interface: `source`, `marketplace` and `registry`. Input outside the contract is
rejected with a diagnostic; there are no compatibility flags and no silent fallbacks.

## Documentation

**The specification** — [the Product Specification](docs/product-specification/PRODUCT_SPECIFICATION.md),
the product's single source of truth, which every document below is written against

**Using AART** — [installing it](docs/install/installing-aart-v1.md) ·
[the consumer lifecycle](docs/using/consumer-lifecycle-v1.md) ·
[with a company registry](docs/tutorials/company-registry-v1.md) ·
[with direct sources only](docs/tutorials/direct-source-v1.md) ·
[the environment AART gives Git](docs/configuration/git-environment-v1.md) ·
[advisory runtime requirements](docs/marketplace/runtime-requirements-v1.md)

**The TUI and the CLI** — [TUI walkthrough](docs/testing/TUI_MANUAL_WALKTHROUGH.md) ·
[CLI walkthrough](docs/testing/END_TO_END_ACCEPTANCE.md)

**Authoring and vendoring** — [writing an artifact](docs/authoring/authoring-an-artifact-v1.md) ·
[porting an MCP server into the registry](docs/tutorials/mcp-servers-into-the-registry.md) ·
[vendoring one](docs/tutorials/vendoring-v1.md) ·
[vendoring the next one](docs/tutorials/vendor-next-mcp-server.md) ·
[setup recipe v2](docs/protocol/setup-recipe-v2.md)

**Maintaining a registry** — [the maintainer's route](docs/registry/maintaining-a-registry-v1.md) ·
[standing up your first one](docs/tutorials/company-registry-tabnine-v1.md) ·
[maintainer commands](docs/registry/maintainer-commands-v1.md) ·
[maintenance planning](docs/registry/maintenance-planning-v1.md)

**Inside a company** — [what changes there](docs/ci/running-inside-a-company-v1.md) ·
[rolling out on GitHub Enterprise Server](docs/ci/github-enterprise-rollout.md)

**Security and policy** — [installation-risk baseline](docs/security/baseline-v1.md) ·
[attestations and policy](docs/security/attestations-v1.md) ·
[optional analyzers](docs/security/analyzers-v1.md)

**Protocol contracts** — [native source v1](docs/protocol/native-source-v1.md) ·
[registry v1](docs/protocol/registry-v1.md)

**Development and testing** — [the package and its interface](docs/development/packaging-and-interface-v1.md) ·
[the quality gates](docs/development/quality-gates-v1.md) ·
[manual acceptance](docs/testing/manual-acceptance.md) ·
[system matrix](docs/testing/system-matrix-v1.md) ·
[the repository's workflows](docs/ci/workflows-v1.md)

**Releases** — [cutting one](docs/release/releasing-v1.md) ·
[the release model](docs/release/release-model-v1.md) ·
[wheel reproducibility](docs/release/wheel-reproducibility-v1.md)

## License

AART is released under the [MIT License](LICENSE). Free for any use, including commercial, with no
obligation beyond keeping the copyright notice and the warranty disclaimer. The software is provided
as is, with no warranty and no liability on the author.

Copyright (c) 2026 Michał Filek. From Poland with <3
