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

This build generates `guideline`, `hook`, `mcp`, `memory`, `skill`, and OpenCode `plugin` skeletons. Each carries the
payload its package format requires: one Markdown document for a guideline or memory, an executable
script and `hook.json` for a hook, an entrypoint for an MCP server, or `SKILL.md` for a skill. Each
skeleton also names the blocks it deliberately leaves to you.

Inside a Git repository, AART reads what Git would commit: the tracked files and the untracked ones
your ignore rules do not exclude. Keep `.venv/`, caches and editor state in the repository and
ignore them as usual; they are never part of the upstream input. Outside Git, the whole directory is read.

`aart-cli author check` reads the directory the way an Upstream Sync reads one and puts every `aart-cli.yaml`
and `aart-cli.json` it finds through the parser *and* the compiler a Registry uses. A manifest that
passes here parses and compiles to the package `aart-cli maintain upstream scan` would accept, and the check
prints the artifact identity it compiled:

```
ok    github-mcp/aart-cli.yaml  ->  mcp/github-mcp
```

It is the command to run in a loop while editing; `--json` makes the verdict machine-readable.

## Author Mode in the TUI

Open `aart-cli`, enable **Author Mode** in Settings, then open **Author**. This preference is
off by default and independent of Registry Maintainer Mode. **Workspace** remembers one normalized
absolute directory outside AART's application home. Choose your upstream checkout there.

**Check** uses the CLI's Git-visible reader and compiler, lists every manifest and opens each
manifest's full diagnostics. Press `r` to rerun after editing. **New artifact** asks for kind,
name and an optional workspace subdirectory, writes the CLI's template without replacing existing
files, then checks and focuses that manifest. A destination cannot escape the workspace through
`..` or symlinks, or land in the application home. These author actions neither connect an upstream
nor modify a Registry.

Manifests carry no version. The Registry assigns a version when a maintainer approves an artifact.
Collections are defined in the Registry from approved artifacts, using
`aart-cli maintain registry collection` or its Collections TUI; authors do not define them in an
upstream manifest.

## Local MCP smoke verification

Before publishing a new MCP to a remote
Registry, the recommended workflow is: commit its canonical package to a branch in your local
Registry repository, add that local repo and branch as a Registry under its own alias, install the
artifact through the normal Marketplace/CLI flow, then run `aart-cli consume mcp test`
command for the intended harness installations, review all stage results, then publish the tested
content. After changing and committing the content, synchronize that Registry, update the local
installation and test again. No separate Candidate Test Install process or remote push is required.

The command operates only on already installed MCPs, individually or in batches, and also lets a
consumer check existing installations without an authoring workflow. It reports two stages
separately: installation configuration, then MCP startup and protocol. Only a predeclared, reviewed
read-only tool and arguments may be called; absent declarations cannot trigger guessed operations.
The test starts the installed launcher directly for the chosen harness; it does not ask a harness
agent to evaluate a response. The interactive application offers the same test, optionally, right after an install that
made an MCP installation; it never changes that install.

This recommendation does not introduce an automatic publication gate. See
[Product Specification §170](../product-specification/PRODUCT_SPECIFICATION.md#170-local-mcp-smoke-verification)
for the verification contract.

The minimal declaration is a top-level manifest block:

```yaml
smoke_test:
  tool: get_current_user
  read_only: true
```

Choose an existing reviewed read-only tool; no special health tool or `{"ok": true}` response
is required. Optional `arguments` supplies fixed JSON values or an explicit installation-local
non-secret configuration reference such as `tenant: {configuration: tenant}`. Otherwise an empty
argument object is used and checked against the tool's schema. Tool calls default to a 15-second
timeout; `timeout_seconds` may be from 1 through 60. Those four fields are the whole block: any
other key is refused as unknown.

Missing credentials and any ordinary or secret `AART_NOT_SET` input yield `NOT CONFIGURED`
and protocol `NOT RUN`; no server starts. Provider inspection does not read secret values.

The generic evaluator checks protocol completion and errors and the declared schemas, accepting
supported text, structured, image and empty results. It does not guess business meaning from
keywords or ask a model to decide success. A passing protocol stage is not proof that the server
reached its external service: a server that turns an upstream failure into an ordinary result
passes it. The read-only flag is a reviewed declaration, not a sandbox guarantee.

For a server you control, break its configuration once on purpose (a wrong token, say) and run
the test. If the protocol stage goes red, the server reports upstream failures as MCP errors, and a
pass from it means something for that server. If it stays green, the test cannot tell a working
service from a broken one for this server.

Default-off `--show-response` permits bounded inspection of the server response in current output,
without application persistence. These behaviors are specified in Product Specification §170.
