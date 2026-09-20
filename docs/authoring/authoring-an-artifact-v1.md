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

## Local MCP smoke verification

CP-26.20a now provides the local command and its direct MCP, OpenCode CLI, and Claude Code routes;
final Tabnine CLI acceptance remains pending. Before publishing a new MCP to a public remote
Registry, the recommended workflow is: commit its canonical package to a branch in your local
Registry repository, add that local repo and branch as a Registry under its own alias, install the
artifact through the normal Marketplace/CLI flow, then run `aart-cli mcp test`
command for the intended harness installations, review all stage results, then publish the tested
content. After changing and committing the content, synchronize that Registry, update the local
installation and test again. No separate Candidate Test Install process or remote push is required.

The command operates only on already installed MCPs, individually or in batches, and
also let a consumer check existing installations without an authoring workflow. It will report
installation configuration, MCP startup/protocol, service access, harness/model-provider access
and actual harness/MCP/service execution separately. Only a predeclared, reviewed read-only tool
and arguments may be called; absent declarations cannot trigger guessed operations. OpenCode CLI
and Tabnine CLI are priority acceptance targets, with Claude Code as an additional adapter.

This recommendation does not introduce an automatic publication gate. See
[Product Specification §170](../product-specification/PRODUCT_SPECIFICATION.md#170-local-mcp-smoke-verification-through-the-cli)
and the [CP-26 execution slice](../refactor/slices/cp-26-authoring-and-legacy-removal.md) for the
implementation contract and remaining acceptance obligation.

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
timeout; `timeout_seconds` may be from 1 through 60. Optional `expect` is exactly one of:

```yaml
expect:
  text_contains: expected text
```

or:

```yaml
expect:
  structured_path: user.login
  equals: expected-login
```

Optional `reaches_service: true` is your reviewed statement that this tool performs a real read
against the configured external service using the installation's own credentials. It is what
makes the `mcp-to-external-service` stage a claim worth grading: without it the stage reports
`NOT CONFIGURED` and stays outside the required set, so an installation that works exits zero.
With it, the stage passes only when `expect` also holds -- the declaration is the reviewed
behaviour and the expectation is the observed result, and neither alone establishes the read.
A declared service read with no `expect` is reported `NOT VERIFIED`. Only `true` is accepted.

The generic evaluator checks protocol completion/errors and declared schemas,
accepting supported text, structured, image and empty results. It does not guess business meaning
from keywords or ask a model to decide success. Successful invocation is reported separately from
external-service evidence; cached output or an error disguised as normal text cannot alone prove
service access. The read-only flag is a reviewed declaration, not a sandbox guarantee.

## The harness leg is run by the operator (D-368)

AART does not launch a harness or submit a prompt to one. `aart-cli mcp test --prompt` composes a
prompt naming every selected installation, the declared tool and arguments for each, and the JSON
report shape it asks for; a person runs that in their own harness session, and
`aart-cli mcp test --report <path>` grades what comes back.

The report carries the observation, not the verdict: each tool result it holds is graded by the
same deterministic evaluator the direct route uses, and the English assessment (`status`,
`summary`, `possible_error`, each text field bounded to 2,000 characters) stays a separate stage
that cannot establish protocol success or service access. Such evidence is declared as coverage
`direct-and-attested` and never counts as direct evidence.

For an author this means one thing in practice: **a `reaches_service` claim is only as good as its
`expect`.** That expectation is what a fabricated or carelessly copied report cannot satisfy, on
either route. Choose a value only the real service can return.

Default-off `--show-response` permits bounded inspection of the server response in current output,
without application persistence. These behaviors are specified in Product Specification §170.
