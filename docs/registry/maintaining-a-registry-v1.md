# Maintaining a registry

A registry is an ordinary Git checkout. Maintainer mutations prepare reviewed files and stop. The
explicit `maintain registry publish --yes` flow runs every publisher gate and creates the listed commit, and
stops there. `maintain registry push --branch NAME` then pushes that commit to a review branch — never the
registry's default branch, which is refused by name, because a subscriber reads the default branch
and only a merge should change what it can install. Merging is the reviewer's work, on the forge.
An empty Git repository is not a registry until its `aart-cli-registry.json` marker exists.

AART reaches every remote by running system Git, with an allowlisted environment rather than the
operator's. If a repository clones at a shell prompt but not through AART, the environment is where
to look: [the environment AART gives Git](../configuration/git-environment-v1.md) lists what is
passed, what is dropped, and what to configure instead — `https_proxy` is dropped, and behind a
proxy that is the whole failure.

`maintain registry init` turns an empty checkout into a registry: the two JSON markers, a `.gitignore`,
the quality workflow, a `README.md` describing the registry it just made, and a `.aart-cli-version` pinning the AART
that created it. Those last two are written only when absent — they are the files
you own afterwards, and AART never compares or overwrites them. `init` runs once: it refuses a
checkout that is already a registry. The workflow is generated and the same for every registry, so
configure it with repository variables rather than edits, and a newer copy can replace it whole.

The generated workflows need no configuration to run on github.com. To run them inside a company,
set repository variables — no file in the registry changes. See
[Rolling out AART on GitHub Enterprise Server](../ci/github-enterprise-rollout.md).

```sh
# Create a registry
aart-cli maintain registry init --source . --source-id company --display-name "Company Registry"
aart-cli maintain registry init --source . --source-id company --display-name "Company Registry" --yes

# Author in a separate upstream checkout, then scan and promote its reviewed Candidate
aart-cli maintain upstream scan --help
aart-cli maintain candidate promote --help

# Or adopt artifacts from a repository's manifests without subscribing to it
aart-cli maintain upstream adopt --source . --url https://github.com/acme/prompts.git --ref main

# Review, then finalize lock + build + validate + audit + one commit
aart-cli maintain registry publish --source .
aart-cli maintain registry publish --source . --yes

# Push the commit to a review branch, then open a pull request
aart-cli maintain registry push --source . --branch add-code-review
```

For the complete path, use the [walked company-registry tutorial for Tabnine](../tutorials/company-registry-tabnine-v1.md).

An author team whose repository becomes an upstream commits one `aart-cli.yaml` beside each artifact. A
complete MCP example — Python stdio server, `requirements.txt` dependencies, one Keychain secret and
one per-harness setting — is [docs/examples/author-source/example-mcp/aart-cli.yaml](../examples/author-source/example-mcp/aart-cli.yaml),
held to what AART accepts by `tests/author_manifest_example_test.py`.

## How content enters a Registry

A Registry never defines an artifact. Content enters by adopting an author's manifest: each
artifact is an `aart-cli.yaml` (or `aart-cli.json`) beside its payload in an author checkout.
`maintain upstream scan` and `maintain candidate promote` take Candidates from a subscribed Upstream repository. `maintain upstream adopt`
reads one Git URL and ref without subscribing to it:

```sh
aart-cli maintain upstream adopt --source . --url https://github.com/acme/prompts.git --ref main
aart-cli maintain upstream adopt --source . --url https://github.com/acme/prompts.git --ref main --artifact skill/code-review@1.0.0 --yes
```

The first run only reports what the manifests compile to. The second writes the reviewed Registry
copy, which `maintain registry publish` then commits. The Marketplace offers what the Registry approved:
nothing an author checkout holds is offered until a maintainer adopts or promotes it.

## Versions belong to the Registry

No manifest carries a version. The Registry counts approved changes and assigns the next version
itself:

- the first approved version is `1.0.0`;
- every approved change raises the patch, up to `x.y.5`;
- the change after `x.y.5` raises the minor (`x.(y+1).0`), up to `x.3.5`;
- the change after `x.3.5` raises the major (`(x+1).0.0`).

An unchanged manifest and payload never produce a new version: Sync and adoption reconcile them as
already approved. A version says how much an artifact changed, not whether it broke anything.

## Collections

A Collection is Registry curation, not an artifact: a name, a one-line summary, and the approved
artifacts it installs together, each pinned at an exact approved version. Create or change one with
`maintain registry collection`, or from the Maintainer TUI's Collections view:

```sh
aart-cli maintain registry collection starter --source . --summary "Review and lint." --include skill/code-review --include skill/lint-review
aart-cli maintain registry collection starter --source . --summary "Review and lint." --include skill/code-review --include skill/lint-review --yes
```

Each `--include` names an artifact this Registry approved, and pins its highest approved version.
The first run reviews the change; `--yes` writes it as one Registry transaction.

Collections bump themselves. When a promotion or adoption approves a member's new version, the same
transaction publishes the next version of every Collection naming it, pinned to the new member
version. The Registry diff and the promote review list each bumped Collection.

A person installs a Collection whole from the Marketplace, or customizes which members to take.
Installed shows it as one row with its member installations under it, and uninstalling it removes
the member installations it owns. A member also installed directly stays.

## What a promotion writes

Promotion checks the selected Candidate, its source revision, validation evidence and policy against
the reviewed state, then writes:

- a versioned canonical package under `artifacts/<kind>/<name>/<version>/` for self-contained mode,
  or a pinned document under `references/<kind>/<name>/<version>.json` for pinned-reference mode;
- the approved record at `registry/versions/<kind>/<name>/<version>.json`;
- the Candidate audit record under `registry/promotions/`;
- the derived `registry/index.json` and `registry/snapshot.json` catalogs.

An approved version cannot be replaced with different package bytes. Upstream movement is
discovered and reviewed explicitly; it never changes approved versions or installed artifacts by
itself. Retired authoring-workspace layouts are refused; there is no importer or migration.

## What every maintainer command guarantees

`aart-cli docs maintain registry` lists each command with its options and defaults. These are the
guarantees its help cannot show.

**Review, then apply.** A mutation plan binds the expected snapshot, the ordered changes, each
file's previous digest and its resulting bytes to one review digest. `--yes` rechecks the checkout
and applies only that plan. Ordinary file maintenance never commits or pushes; `publish` and `push`
keep their own review boundaries.

**Where it may write.** Mutation requires a writable real directory containing `.git` (a directory
or a worktree gitfile). Managed symlinks and special files are refused. Writes are atomic, verified
after writing and rolled back on a partial failure. Read-only commands work on a plain snapshot
without `.git` and need no write permission.

**What `--check` returns.** `format --check`, `lock --check` and `build --check` exit `0` when the
generated content is current and `1` when it has drifted, and never apply their plan. `--json`
gives the operation, the number of changed paths, the review digest and the diagnostics.

**Lock and build.** Approved records under `registry/versions/` already carry each version's source
and content pins, so `lock` checks them with nothing to resolve and writes no lock file. `build`
rebuilds `registry/index.json` and `registry/snapshot.json` deterministically from those records.

**Audit.** Audit warnings are gaps in evidence, not risk conclusions: a missing license or
provenance, and absent assessment evidence, are named. When `security/index.json` exists, audit
verifies every attestation's byte digest, publisher and registry-input identity and its coverage of
the compiled objects, refuses evidence for unknown objects and refuses critical installation risk.
High or unknown risk stays a review warning. See the
[installation-risk baseline](../security/baseline-v1.md) and
[attestations and policy](../security/attestations-v1.md).

**Other catalog formats.** Only the native package contract is read; other layouts are not
translated. Give the other repository an `aart-cli.yaml` beside each artifact, then bring it in
with `adopt`, or with `scan` and `promote`.

A local Registry connection reads the committed branch the user selected, through the same
admission path as a remote one. It never changes the checkout, includes uncommitted files or
publishes the branch.
