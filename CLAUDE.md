# CLAUDE.md — AART Refactor Execution Contract

> Mirrors `AGENTS.md`. If the two ever diverge, `AGENTS.md` is the contract of record and this file
> must be corrected to match it. Neither file may override
> `docs/product-specification/PRODUCT_SPECIFICATION.md`.

## Repository target

Work only in this repository: **`M1F1/aart-cli`**.

`M1F1/aart`, `agent-artifacts`, `Agent Artifacts`, registry experiments and any other older AART
repository are legacy/reference sources only. Do not refactor them, merge their histories, or treat
them as the target.

## Sole source of product truth

Before architectural or product work, read:

`docs/product-specification/PRODUCT_SPECIFICATION.md`

It is the canonical and sole AART Product Specification.

If anything else conflicts with it, the Product Specification wins. Historical `PLAN.md`,
`PROGRESS.md`, `TODO.md`, `docs/design/*`, old specs and legacy code are evidence/reference only.

## Autonomous execution rule

The intended operating mode is long unattended agent runs. Do not wait for user input when the
answer can be derived safely. Use this order:

1. Product Specification and its invariants.
2. Current `aart-cli` behavior and characterization tests.
3. Current public standards/contracts that the Product Specification intentionally interoperates with.
4. The smallest conservative implementation choice that preserves the invariants.

Record material implementation choices in `docs/refactor/DECISIONS.md` and continue. Ask only when a
true critical-path product contradiction remains and no safe compliant choice exists.

## Critical path vs backlog

`docs/refactor/EXECUTION_PLAN.md` defines the mandatory critical path.
`docs/refactor/NEXT.md` identifies the next executable work.

Anything discovered during implementation that is useful but not required to complete the current
critical path or satisfy a Product Specification invariant goes to `docs/refactor/BACKLOG.md`; do
not expand the active slice for it.

A backlog item becomes critical only if evidence proves that without it a mandatory invariant,
acceptance test, security boundary, compatibility requirement, or critical-path slice cannot be
completed. Record that reclassification explicitly.

## Migration discipline

Use a strangler/vertical-slice migration, not a big-bang rewrite. Characterize behavior before
replacing it. New domain/application code must use explicit effect boundaries and remain independent
of filesystem, subprocess, network, secrets, terminal UI and GitHub APIs. Preserve valid existing
behavior until the replacement slice is verified. Remove legacy authority only after acceptance
evidence exists.

## Quality discipline

Use TDD for product changes: characterize/red → green → refactor →
negative/property/integration/E2E tests.

Do not weaken quality gates to make a change pass. Keep secret values out of plans, receipts, logs,
output, fixtures and committed files. Run the strongest relevant repository gates after each slice
and the full quality suite before declaring a slice verified.

## Durable handoff

At the end of every meaningful work segment update:

- `docs/refactor/MIGRATION_STATUS.md`
- `docs/refactor/NEXT.md`
- the relevant `docs/refactor/slices/*.md` file
- `docs/refactor/BACKLOG.md` for noncritical discoveries
- `docs/refactor/DECISIONS.md` for material choices

The repository, not chat history, must be sufficient for the next agent to resume safely.

## Repository commands

Gates are driven by `scripts/quality.py` through the `Makefile`. Zero runtime dependencies is an
invariant: developer/CI tooling comes from Poetry's dev group and never reaches the installed
runtime.

```bash
make quality
```

| Task | Command |
|---|---|
| Broad unit/regression gate | `make unit` |
| End-to-end integration gate | `make integration` |
| Both of the above | `make test` |
| Lint / format check / types | `make lint`, `make format-check`, `make typecheck` |
| Coverage | `make coverage` |
| Packaging, docs, secret shape | `make packaging-check`, `make docs-check`, `make secret-shape-check` |
| Full quality suite | `make quality` |
| Schema/content validation | `make validate` |
| Wheel build | `make wheel` |

Run focused tests while developing; run the strongest relevant gates before calling a slice
verified, and the full suite before declaring completion.
