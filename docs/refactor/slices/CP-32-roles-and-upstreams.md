# CP-32 — Three roles, three command families: consume, maintain, author

Status: **specified**, not started. Authority: the product owner (2026-10-17), Product
Specification §175, D-439.

## Why

`aart-cli source` configures Registries and author repositories alike, and `source list` shows
them together. A consumer can add an author repository although the Marketplace offers nothing from
it (`aart_cli/io/configured_offers.py` skips every non-Registry). The word "source" names both, so
neither role can tell from a command what it is about.

## Target

See §175.2 for the full command tree. In short: `consume` (Registries and installation), `maintain`
(`upstream`, `candidate`, `registry`), `author`; `doctor`, `upgrade`, `reset` and `security` stay
at the top level. Configuration keeps `registries` and `upstreams` apart; the TUI names its areas
the same way.

## Steps

See `docs/refactor/plan.json`, epic CP-32.

1. Specification (§175, INV-269, INV-270, D-439). Done.
2. Configuration split.
3. `consume`.
4. `maintain upstream`.
5. `maintain candidate`.
6. `maintain registry`.
7. Remove `source`, `marketplace`, top-level `registry` and the four kinds.
8. TUI names and hints.
9. Documentation.
10. Full verification and the PR.

## Notes for the implementer

- No aliases, fallback readers or migrators (§169); a changed `config.json` shape is a clean break.
- Steps 3–6 can each land with focused tests (D-334): the argparse tree, one CLI e2e per family,
  and INV-269 as a test that no consumer path accepts an upstream.
- Policy fields `allow_direct_sources`, `recommended_sources` and `required_sources` follow the
  split: the direct switch goes; the other two name Registries.
