# The package and its interface

## Canonical package

A self-contained Registry version lives at `artifacts/<kind>/<name>/<version>/` and contains
`artifact.json` and `payload/`.
Its manifest defines SemVer, compatibility, installation, optional `setup`, `requires_aart`, and
`requires`. When it declares setup, `setup/installer.json` must be v2 and `SETUP.md` must be at
the package root; the modules a recipe may use are listed in the
[setup recipe reference](../protocol/setup-recipe-v2.md). An invalid hook, setup, dependency, symlink, or unknown file fails compilation
before publication or installation.

```json
{
  "requires": [
    {"type": "skill", "name": "using-residues"}
  ]
}
```

Approved records under `registry/versions/` bind versions to commits and content digests.
`registry/index.json` and `registry/snapshot.json` are deterministic derived catalogs, validated
against those records before publication. Reference-mode versions use `references/`; no separate
authoring-workspace lock/index is generated.

## Interface

```text
aart-cli author init|check
aart-cli consume registry add|list|sync|remove|resubscribe|health
aart-cli consume list|search|health|install|update|uninstall|status|setup|receipt|mcp test
aart-cli doctor
aart-cli reset [--restore DIR] [--yes]
aart-cli maintain upstream add|list|sync|remove|resubscribe|health|scan|adopt|check
aart-cli maintain candidate list|promote
aart-cli maintain registry init|collection|format|validate|lock|build|audit|publish|push|test|diff
aart-cli security scan|show|verify|analyzers|suites
aart-cli upgrade --wheel FILE | --source-checkout DIR
```

Running `aart-cli` without a subcommand on a TTY opens the human-oriented TUI (curses or text
fallback). The TUI submits the same canonical requests as flag mode; it is not a second command
engine.

`aart-cli reset` is the CLI-only clean start. It lists the exact AART-owned per-user configuration,
managed state and cache paths, then, after one typed confirmation or `--yes`, moves them into
`<application home>-backups/<UTC timestamp>/`; `--restore DIR` brings a backup back. It deletes
nothing and never touches projects, harness files, organization policy or credentials owned by
another application.

## Verification

```sh
python -m unittest
git diff --check
```

The manual walks are [the TUI walkthrough](../testing/TUI_MANUAL_WALKTHROUGH.md) and
[the command-line walkthrough](../testing/END_TO_END_ACCEPTANCE.md); what they find is tracked in
[manual acceptance](../testing/manual-acceptance.md).
