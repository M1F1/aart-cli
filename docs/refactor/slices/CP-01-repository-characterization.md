# CP-01 — Repository characterization and invariant map
Status: VERIFIED

## Goal

Characterize the current `aart-cli` repository before changing architectural authority. Inventory
the package, public commands, TUI, protocols, tests and quality gates; identify existing seams and
legacy authority; map every Product Specification invariant to a target owner and evidence gap.

## Product Specification sections/invariants

All `INV-001` through `INV-242`. Detailed ownership and evidence status live in
`docs/refactor/INVARIANT_TRACEABILITY.md`.

## Repository baseline

- Branch baseline: `codex/aart-refactor` from `origin/main` at `90faa96`.
- Bootstrap commit: `5515e11`.
- Production package: 169 Python files under `agent_artifacts/`.
- Test suite: 204 `*_test.py` files; 1,903 discovered tests at characterization time.
- Runtime dependencies: none (`pyproject.toml [project].dependencies = []`).
- Primary interfaces: `aart` and `agent-artifacts`, both routed to `agent_artifacts.cli:main`.
- TUI implementation: stdlib/curses with plain-text fallback; the main `tui.py` is 6,308 lines.

## Current public command surface

```text
upgrade
source: add, list, sync, remove, resubscribe, health
marketplace: list, search, health, install, update, uninstall, status, setup, receipt
registry: init, scaffold, collection, discover, format, promote-native, vendor,
          vendor-batch, revendor, refresh-native, validate, lock, build, audit,
          publish, test, diff
security: scan, show, verify, analyzers, suites
reporting: validate-event, validate-issue, aggregate
```

There is no canonical `doctor` command yet. Credential lifecycle is not a first-class command
family. Existing `marketplace setup` is the current configuration/remediation path.

## Existing architectural seams

### Seed domain kernel

`agent_artifacts/domain/` provides frozen identifiers, diagnostics, `Result`, terminal outcomes,
collection helpers and callable query/command ports. `tests/domain_kernel_test.py` proves frozen
values and forbids filesystem, subprocess, network and legacy imports from that package.

### Pure/reviewed plans already present

- `installation/model.py`: immutable reviewed install plans and file/config operations.
- `lifecycle/model.py`: immutable update/uninstall plans and ownership-aware teardown.
- `registry_maintenance/model.py`: immutable registry mutation plans bound to review digests.
- `compiler/graph.py`: marketplace artifacts, Collections, selection and compatibility values.
- `marketplace/model.py`: source-qualified catalog and explicit ambiguity/trust inputs.

These are valuable characterization and migration seams. They are not yet the canonical Artifact,
Requirement, Remediation, Effect and Policy algebras required by CP-03.

### Explicit effect adapters already present

Application services accept injected protocols in several subsystems. Concrete filesystem, Git,
object-store, source and security behavior lives primarily in `agent_artifacts/io/` or subsystem
`io.py` modules. Registry and installation paths already separate prepare/review from finalize in
several flows.

### Existing source/registry/marketplace behavior

The repository already distinguishes configured sources, immutable snapshots, marketplace
projection and registry maintenance in separate packages. Existing tests cover source health,
pinning, native manifests, registry vendoring, review digests, publication boundaries, trust and
ambiguous marketplace coordinates. This is behavior evidence, not permission to retain any
boundary that conflicts with the canonical Product Specification.

### Existing TUI behavior

The current stdlib TUI has headless/text rendering tests, immutable wizard state, marketplace and
source flows, install-scope handling, review screens, receipts and maintainer curation paths. It is
usable characterization for CP-13/CP-14. The 6,308-line orchestration module and direct legacy
workflow vocabulary are migration debt, not a public source-compatibility boundary.

## Missing canonical authority

- No complete five-algebra domain model.
- No canonical `SecretInput != ConfigInput` and value-source/process-binding model.
- No first-class `CredentialReference` lifecycle with Keychain interpreter and dependent warnings.
- No Python artifact-owned environment/dependency effect algebra for the required MCP slice.
- No component `DesiredState`, `CurrentState`, drift/diff and effect-capability model.
- Existing lifecycle reconciliation is installation-record/path oriented, not the full component
  desired-state engine.
- No complete accepted consumer Dashboard/Marketplace/Installed/Updates/Registries/Credentials/
  Activity/Settings/Doctor screen catalog.
- No complete accepted Maintainer Source/Candidate/semantic-diff/validation/promotion flow.
- No Hypothesis dependency or property-test suite yet.
- No complete Git-backed source → candidate → promotion → consumer → MCP runtime acceptance flow.
- Release workflow still contains manual version/changelog/cut-release authority that conflicts
  with `INV-081` through `INV-105`.

## Quality and verification inventory

Canonical local gates in `scripts/quality.py`:

```text
format-check, lint, typecheck, unit, integration, validate, coverage,
packaging-check, docs-check, secret-shape-check
```

CI has a stable aggregate `pr-check`, public/enterprise runner profiles, zero-public-egress support
and explicit variable/secret separation. The full suite uses stdlib `unittest`; `*e2e_test.py`
drives real CLI/filesystem flows. Existing live-acceptance documentation is historical evidence,
not yet CP-17 proof against the new architecture.

## Characterization evidence

- `python3 -m unittest discover -s tests -p '*boundary_test.py'`
  - 32 tests passed.
- Focused domain/compiler/marketplace/lifecycle/concurrency/MCP/TUI suite
  - 86 tests passed.
- Full discovery
  - 1,903 tests ran.
  - 1,884 passed.
  - 16 errors and 3 failures were confined to wheel/release cases requiring the unavailable
    `poetry` executable; the failure shape is environmental and must not be hidden by product-code
    changes.

## Legacy/current paths

- Large legacy coordination surfaces: `agent_artifacts/tui.py`, `agent_artifacts/setup.py`,
  `agent_artifacts/setup_runtime.py`, `agent_artifacts/cli.py`.
- Parallel historical domain values remain in `agent_artifacts/model.py`,
  `agent_artifacts/outcomes.py` and subsystem-local model modules.
- Manual release scripts/workflows remain active evidence but conflict with the accepted release
  model.
- Historical `PLAN.md`, `PROGRESS.md`, `TODO.md` and `docs/design/*` remain reference only.

## Target paths/owners

- Domain ADTs: `agent_artifacts/domain/`.
- Application orchestration and ports: `agent_artifacts/application/`.
- Concrete effects: adapter/interpreter packages outside the domain.
- Interfaces: CLI/JSON/TUI as projections over application services.
- Durable traceability: `docs/refactor/INVARIANT_TRACEABILITY.md` and per-slice records.

## Non-goals

- No broad package move in CP-01.
- No deletion of legacy paths before replacement and acceptance evidence.
- No TUI framework replacement.
- No optional backlog features.

## Done

- Bootstrap and sole product authority read and committed.
- Package, commands, TUI, protocols, tests, gates and CI inventoried.
- Existing clean seams and legacy authority identified.
- Baseline boundary and vertical-path tests run.

## Remaining

None for CP-01. Pinned formatter/type-checker and Poetry-backed packaging evidence remain required
by later touched-code/full-release gates; they are not silently treated as passed here.

## Known compromises

The local environment lacks the repository-required `poetry` executable. Packaging/release tests
therefore do not currently provide a green baseline. This is recorded evidence, not a product-code
failure and not grounds to weaken the gate.

## Backlog discoveries

None. All missing items above are already on the critical path.

## Blockers

None for CP-01 or CP-02. Poetry availability affects the complete packaging gate but not current
characterization or clean-domain migration work.

## Legacy removal criteria

No legacy removal is allowed in CP-01. Each path needs a replacement owner, characterization and
the slice-specific acceptance evidence before deletion.

## Handoff

- Current working state: CP-01 verified; all 242 invariants have target ownership and evidence gaps.
- Exact next action: enforce the CP-02 dependency seam with focused architecture tests.
- Do not undo: bootstrap commit `5515e11`; zero runtime dependencies; current behavioral tests.
- Tests last run/results: 32 boundary + 86 focused tests passed; full discovery 1,884/1,903 passed,
  with all 19 non-passing tests requiring missing Poetry packaging infrastructure.
- Failure evidence: full traceback retained in the active task; summarized above for durable use.
