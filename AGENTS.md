# AGENTS.md — AART Refactor Execution Contract

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

### The two tools that check the tests themselves

Passing tests prove the code does what the tests say. They do not prove the tests say anything worth
holding, and coverage does not either: a line that ran is not a line whose behaviour anything
asserts. Two dev-group packages exist to close that gap and both are to be used.

**Hypothesis** for property tests. Where a claim is universal — a parser rejects every malformed
input, a projection round-trips, an ordering is total — state it as a property over generated input
rather than over three examples chosen by the person who wrote the code. Prefer it wherever the
invariant is genuinely universal; keep example-based tests for the specific scenarios a Product
Specification section names.

**mutmut** for mutation adequacy, through `make mutants ONLY=<path.py> TESTS="<test files>"`
(`scripts/mutants.py`). A mutant that survives is a change to the code that no test noticed, which
means some claim is unheld. Run it over the module a slice just changed, with the tests that claim
to cover it. It is advisory rather than a gate, and always scoped: mutating this repository whole is
days of compute (D-134). Read survivors as findings — one inside the slice's claims is a test that
does not hold what its name says; one outside them is a backlog note. Never weaken a test to change
the number.

Neither replaces the targeted mutation each slice records. Before a test counts as evidence, make
one deliberate, semantically real change to the code it names and watch that test — and ideally only
that test — turn red. `make mutants` finds claims nobody thought to make; the targeted mutation
proves the claim you did make is load-bearing, and it is what the slice document records.

## Durable handoff

At the end of every meaningful work segment update:

- `docs/refactor/MIGRATION_STATUS.md`
- `docs/refactor/NEXT.md`
- the relevant `docs/refactor/slices/*.md` file
- `docs/refactor/BACKLOG.md` for noncritical discoveries
- `docs/refactor/DECISIONS.md` for material choices

The repository, not chat history, must be sufficient for the next agent to resume safely.
