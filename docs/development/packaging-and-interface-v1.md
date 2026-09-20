# The package and its interface

## Canonical package

A vendored Registry package lives at `artifacts/<kind>/<name>/<version>/` and contains
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
aart-cli source add|list|sync|remove|resubscribe|health
aart-cli marketplace list|search|health|install|update|uninstall|status|setup|receipt
aart-cli doctor
aart-cli reset
aart-cli registry init|collection|scan|promote|adopt|check-upstream|discover|format|vendor|vendor-batch|revendor|validate|lock|build|audit|publish|push|test|diff
aart-cli security scan|show|verify|analyzers|suites
aart-cli upgrade --wheel FILE | --source-checkout DIR
```

Running `aart-cli` without a subcommand on a TTY opens the human-oriented TUI (curses or text
fallback). The TUI submits the same canonical requests as flag mode; it is not a second command
engine.

`aart-cli reset` is the CLI-only factory reset. It lists the exact AART-owned per-user configuration,
managed state and cache paths, then requires two different typed confirmations. It never removes
projects, harness files, organization policy or credentials owned by another application.

## Verification

```sh
python -m unittest
git diff --check
```

The manual walks are [the TUI walkthrough](../testing/TUI_MANUAL_WALKTHROUGH.md) and
[the command-line walkthrough](../testing/END_TO_END_ACCEPTANCE.md); what they find is tracked in
[manual acceptance](../testing/manual-acceptance.md).
