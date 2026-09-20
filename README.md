# AART

AART installs reviewed **skills, guidelines, MCP servers, hooks, and memory** from canonical,
validated registry snapshots into a selected harness.

## Install an artifact

This page goes from a machine with no aart-cli on it to an artifact installed in your agent, and
one command that proves it worked.

**What you need:**

- **Python 3.10 or later** — and nothing else. aart-cli has no dependencies of its own.
- **aart-cli itself.** Steps 1 and 2 below install it.
- **The address of a Registry.** A Registry is a Git repository of approved artifacts that somebody
  in your organization maintains. Ask whoever runs it for the URL — this is not a value you can
  invent.
- **An artifact in that Registry** that you want. Finding one is step 4.
- **A harness to install it into** — one of `claude`, `opencode`, `tabnine` or `vibe`. This is the
  agent tool whose own configuration aart-cli writes.

**The angle brackets.** Commands on this page contain blanks written like `<registry-url>` and
`<alias>`. Replace each one with your own value, brackets and all: `--alias <alias>` typed for real
becomes `--alias company`. They are left blank because none of these values is the same at two
organizations.

### 1. Download the wheel

AART is meant to be run from your organization's own instance, where the release is private — so
the route in front is the authenticated one. `<repository>` is the address of the repository you
are reading this in; nothing on this page names an instance, because nothing on this page can know
which one you are on.

**With the GitHub CLI**, already signed in to that instance:

```sh
gh release download vX.Y.Z --repo "<repository>" --pattern 'aart_cli-*-py3-none-any.whl' --dir .
```

**Or by hand**, which needs nothing installed at all: open the repository's
[Releases page](../../releases), choose the release, and download
`aart_cli-X.Y.Z-py3-none-any.whl` from its **Assets**.

### 2. Install it from the file

The wheel has no dependencies, so none of these fetches anything else. Use whichever you already
have:

```sh
python -m pip install --no-deps --force-reinstall ./aart_cli-X.Y.Z-py3-none-any.whl
```

```sh
pipx install --python "$(command -v python3)" --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

```sh
uv tool install --force ./aart_cli-X.Y.Z-py3-none-any.whl
```

`pip` installs into **whatever environment is active right now**; `pipx` and `uv tool` build an
isolated one for the tool. To look at it before installing anything, `uvx` runs the wheel and keeps
nothing behind:

```sh
uvx --from ./aart_cli-X.Y.Z-py3-none-any.whl aart-cli --version
```

Installing straight from a public repository — `git+<repository>`, or the wheel's own address — is
in [Installing AART](docs/install/installing-aart-v1.md), together with what stops working when the
release is private, and why.

### 3. Connect a Registry, in the TUI

A Registry is the approved catalog somebody in your organization maintains; `<registry-url>` is the
repository your platform team points you at. Running `aart-cli` with no subcommand on a terminal
opens the human-oriented interface, which is the primary route for a person rather than a script:

```sh
aart-cli
```

Open **Registries**, then **Add Registry**. The form validates a fresh snapshot *before* it saves
anything, so a Registry that does not answer or does not validate never becomes configuration:

```text
AART / Registries / Add Registry

✓ Registries → ▸ Add Registry → · Review Registry

────────────────────────────────────────────────────────────────

> Alias: <type a short name>
  Transport: Remote Git
  Registry URL: <type an HTTPS or SSH Git URL>
  Branch or tag: <repository default>
  Make default registry: yes
  Continue: Validate and review

────────────────────────────────────────────────────────────────

- Connect an approved registry. AART validates a fresh snapshot before saving it.
  A local checkout reads one branch's committed content; your worktree is never read.

- This adds another registry. Nothing already connected is changed.

────────────────────────────────────────────────────────────────

[Type] Edit   [Backspace] Delete   [Enter] Next
[↑/↓] Move   [Esc] Back
```

The interface does the whole route, not just this step: it lists and searches the catalog (press
`/` and keep typing), shows the same reviewed plan before anything is applied, and reports the same
status. It submits the identical canonical requests as the commands below — it is not a second
command engine, so nothing is available in one and missing from the other.

### The same route, as commands

For a script, or when you already know what you want. Connect the Registry:

```sh
cd /path/to/your-project
aart-cli source add --alias <alias> --kind registry-git --location <registry-url> --ref main --default
```

Find the artifact. `list` prints the whole catalog; `search` is how you find one thing in it. Every
word must match, so a second word narrows rather than widens, and the coordinate it prints is the
one `install` takes:

```sh
aart-cli marketplace search <word>
```

Install it. Every mutation is two commands on purpose: the first renders the plan and changes
nothing, the second finalizes exactly that plan:

```sh
aart-cli marketplace install <alias>/<kind>/<name> --profile <harness>
aart-cli marketplace install <alias>/<kind>/<name> --profile <harness> --yes
```

Verify. `status` reports what is installed and whether it still matches the Registry — `current`,
`update_available`, `removed_upstream`, `source_unavailable` or `local_drift`:

```sh
aart-cli marketplace status --profile <harness>
```

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
catalog. **Marketplace** is your view across every registry you have connected -- one, or several
at once -- and it is what you search, what you install from, and what `status` later compares your
machine against. An artifact keeps the alias of the registry it came from, so the same name in two
registries stays two different things. No Source installs anything directly, and
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
[where AART keeps what it owns](docs/configuration/application-home-v1.md) ·
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
