# SEARCH-DOCUMENTATION — `consume search` prints each artifact's documentation link

**Status:** done (released with the PR that carries it). §197 amended; D-527.

## Why

`consume list` and the install review printed an artifact's approved `documentation`; `consume
search`, the command a person runs to find one artifact, did not. The owner asked for the link in
the search answer, so that the page with the install commands is one copy away.

## What was done

`aart_cli/commands/marketplace.py`:
- `_search_rows` carries the approved `documentation` (or `None`) on every artifact row.
- Text output prints `    Documentation: <url>` on its own line under the row, whole, only when
  the artifact declares one.
- JSON: every artifact match has `documentation`, the link or `null`, as `consume list --json`.

The `search` help, `README.md`, `docs/using/consumer-lifecycle-v1.md` and §197 say so.

## Evidence

`tests/artifact_documentation_test.py`, over a real compiled, promoted and published MCP:
- `test_search_names_the_link_under_the_artifact_it_finds`: the text line directly under the row
  and the JSON `documentation`.
- `test_an_undocumented_artifact_shows_no_link_anywhere`: no line, and `null` in JSON.

Targeted mutations, all killed:

| Mutation | Turned red |
|---|---|
| No text line | `test_search_names_the_link_under_the_artifact_it_finds` |
| No JSON field | both tests above |
| A line for every artifact, documented or not | the undocumented test and `test_the_limit_keeps_the_best_row` |

Focused: 340 search, documentation, parser, command-reference and Marketplace CLI tests pass; ruff,
ruff format and docs-check pass.
