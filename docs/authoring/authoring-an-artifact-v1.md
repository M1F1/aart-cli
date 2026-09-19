# Writing an artifact

`aart-cli author init` starts one in the directory you name. It writes an `aart-cli.yaml` carrying every
field this build accepts — the optional blocks commented out, one line of explanation above each —
so narrowing the manifest down to what your artifact needs is an edit rather than a search through
a schema. A payload skeleton is written beside it, and nothing already in the directory is
replaced.

```sh
aart-cli author init --kind guideline --name commit-style --into ./commit-style
aart-cli author init --kind hook --name guard-bash --into ./guard-bash
aart-cli author init --kind mcp --name github-mcp --into ./github-mcp
aart-cli author init --kind memory --name team-context --into ./team-context
aart-cli author init --kind skill --name code-review --into ./code-review
aart-cli author check --source ./github-mcp
aart-cli author check --source . --json
```

This build generates `guideline`, `hook`, `mcp`, `memory`, and `skill` skeletons. Each carries the
payload its package format requires: one Markdown document for a guideline or memory, an executable
script and `hook.json` for a hook, an entrypoint for an MCP server, or `SKILL.md` for a skill. Each
skeleton also names the blocks it deliberately leaves to you.

`aart-cli author check` reads the directory the way a Source Sync reads one and puts every `aart-cli.yaml`
and `aart-cli.json` it finds through the parser *and* the compiler a Registry uses. A manifest that
passes here parses and compiles to the package `aart-cli registry scan` would accept, and the check
prints the coordinate it compiled to:

```
ok    github-mcp/aart-cli.yaml  ->  mcp/github-mcp@0.1.0
```

It is the command to run in a loop while editing; `--json` makes the verdict machine-readable.

## Planned local MCP smoke verification

**Accepted for CP-26.20a; not implemented yet.** Before publishing a new MCP to a public remote
Registry, the recommended workflow will be: commit its canonical package to a branch in your local
Registry repository, add that local repo and branch as a Registry under its own alias, install the
artifact through the normal Marketplace/CLI flow, then run the planned `aart-cli mcp test`
command for the intended harness installations, review all stage results, then publish the tested
content. After changing and committing the content, synchronize that Registry, update the local
installation and test again. No separate Candidate Test Install process or remote push is required.

The command will operate only on already installed MCPs, individually or in batches, and will
also let a consumer check existing installations without an authoring workflow. It will report
installation configuration, MCP startup/protocol, service access, harness/model-provider access
and actual harness/MCP/service execution separately. Only a predeclared, reviewed read-only tool
and arguments may be called; absent declarations cannot trigger guessed operations. OpenCode CLI
and Tabnine CLI are priority acceptance targets, with Claude Code as an additional adapter.

This recommendation does not introduce an automatic publication gate. See the accepted
[Product Specification §170](../product-specification/PRODUCT_SPECIFICATION.md#170-local-mcp-smoke-verification-through-the-cli)
and the [CP-26 execution slice](../refactor/slices/cp-26-authoring-and-legacy-removal.md) for the
pending contract; do not treat the planned command as available in the current build.

The accepted minimal declaration for that future command is a top-level manifest block:

```yaml
smoke_test:
  tool: get_current_user
  read_only: true
```

Choose an existing reviewed read-only tool; no special health tool or `{"ok": true}` response
is required. Optional `arguments` supplies required parameters; otherwise an empty argument object
is used and checked against the tool's schema. Tool calls default to a 15-second timeout. Optional
`expect` will add deterministic checks against existing output, with its exact syntax documented
when implemented. The generic evaluator checks protocol completion/errors and declared schemas,
accepting supported text, structured, image and empty results. It does not guess business meaning
from keywords or ask a model to decide success. Successful invocation is reported separately from
external-service evidence; cached output or an error disguised as normal text cannot alone prove
service access. The read-only flag is a reviewed declaration, not a sandbox guarantee.
