# Writing an artifact

`aart-cli author init` starts one in the directory you name. It writes an `aart.yaml` carrying every
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

`aart-cli author check` reads the directory the way a Source Sync reads one and puts every `aart.yaml`
and `aart.json` it finds through the parser *and* the compiler a Registry uses. A manifest that
passes here parses and compiles to the package `aart-cli registry scan` would accept, and the check
prints the coordinate it compiled to:

```
ok    github-mcp/aart.yaml  ->  mcp/github-mcp@0.1.0
```

It is the command to run in a loop while editing; `--json` makes the verdict machine-readable.
