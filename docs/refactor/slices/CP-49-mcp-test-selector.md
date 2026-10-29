# CP-49 — `consume mcp test` accepts a coordinate without its version

Status: **done**, in the CP-47/CP-48 PR, on `feat/cp-47-aart-cli-update`, from a bug report by the
owner (2026-10-28). Authority: Product Specification §170.1, D-501.

## Why

`consume inputs list|set|set-credential` take `ALIAS/KIND/NAME[@VERSION]`, and the commands they
suggest use the form without a version. `consume mcp test` refused it
(`selector 'company/mcp/azure-data' names no installed MCP target`), so a coordinate copied from
one command failed in the other.

## What changed

- `aart_cli/application/mcp_smoke.py`: `_names` also accepts the coordinate without its version;
  `_no_target` adds `did you mean <installed coordinate>?` when the same artifact is installed in
  the requested scope and harnesses at another version.
- `aart_cli/cli_parser.py`: the help says `ALIAS/KIND/NAME[@VERSION]` or an installation key.
- `docs/using/consumer-lifecycle-v1.md`: both forms, and what a wrong version does.

## Evidence

`tests/mcp_smoke_selection_test.py`, `SelectorWithoutVersionTest`: the bare form selects the
installation; it selects the artifact in every requested harness; `company/mcp/ident`,
`company/mcp/identity-extra` and `mcp/identity` select nothing; `@0.9.0` against an installed
`1.0.0` selects nothing and names `company/mcp/identity@1.0.0`; Hypothesis over harnesses, version
(including pre-release and build metadata) and form: the bare, versioned and key forms select
exactly what the installation keys select. Four of the six were red before the fix.

| # | Mutation | Red |
|---|---|---|
| MA | the form without a version is not accepted | bare form, every harness, the property |
| MB | a prefix of the coordinate selects it | the artifact is named whole |
| MC | the version is ignored | another version is refused |
| MD | no hint | another version is refused |
