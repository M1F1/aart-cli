# Maintaining a registry

A registry is an ordinary Git checkout. Maintainer mutations prepare reviewed files and stop. The
explicit `registry publish --yes` flow runs every publisher gate and creates the listed commit, and
stops there. `registry push --branch NAME` then pushes that commit to a review branch — never the
registry's default branch, which is refused by name, because a subscriber reads the default branch
and only a merge should change what it can install. Merging is the reviewer's work, on the forge.
An empty Git repository is not a registry until its `aart-cli-registry.json` marker exists.

AART reaches every remote by running system Git, with an allowlisted environment rather than the
operator's. If a repository clones at a shell prompt but not through AART, the environment is where
to look: [the environment AART gives Git](../configuration/git-environment-v1.md) lists what is
passed, what is dropped, and what to configure instead — `https_proxy` is dropped, and behind a
proxy that is the whole failure.

`registry init` turns an empty checkout into a registry: the two JSON markers, a `.gitignore`,
the quality workflow, a `README.md` describing the registry it just made, and a `.aart-cli-version` pinning the AART
that created it. Those last two are written only when absent — they are the files
you own afterwards, and AART never compares or overwrites them. The workflows and the JSON are
managed: hand-edit one and `init` refuses the registry.

The generated workflows need no configuration to run on github.com. To run them inside a company,
set repository variables — no file in the registry changes. See
[Rolling out AART on GitHub Enterprise Server](../ci/github-enterprise-rollout.md).

```sh
# Create a registry
aart-cli registry init --source . --source-id company --display-name "Company Registry"
aart-cli registry init --source . --source-id company --display-name "Company Registry" --yes

# Author in a separate Source checkout, then scan and promote its reviewed Candidate
aart-cli registry scan --help
aart-cli registry promote --help

# Or copy foreign content the upstream has not packaged for AART
aart-cli registry vendor skill code-review --source . \
  --url https://github.com/acme/prompts.git --ref main --path prompts/code-review \
  --artifact-version 1.0.0 --summary "Review code." \
  --profile claude --platform darwin

# Review, then finalize lock + build + validate + audit + one commit
aart-cli registry publish --source .
aart-cli registry publish --source . --yes

# Push the commit to a review branch, then open a pull request
aart-cli registry push --source . --branch add-code-review
```

`vendor` is the foreign-repository path: it copies a file or subtree into this registry, records the
origin and pinned commit in `provenance.json`, and makes this registry the copy's owner. `revendor`
compares that copy with upstream and plans an explicit versioned refresh; validation and audit reject
a copied payload that drifts from its provenance.

For the complete path, use the [walked company-registry tutorial for Tabnine](../tutorials/company-registry-tabnine-v1.md).
The [vendoring tutorial](../tutorials/vendoring-v1.md) covers provenance and re-vendoring, and
[porting an MCP server](../tutorials/mcp-servers-into-the-registry.md) covers setup recipes.

An author team whose repository becomes a Source commits one `aart-cli.yaml` beside each artifact. A
complete MCP example — Python stdio server, `requirements.txt` dependencies, one Keychain secret and
one per-harness setting — is [docs/examples/author-source/example-mcp/aart-cli.yaml](../examples/author-source/example-mcp/aart-cli.yaml),
held to what AART accepts by `tests/author_manifest_example_test.py`.
