# CP-09 — Isolated Python runtime and dependency effects
Status: VERIFIED

## Goal

Give a Python artifact its own environment and its own resolved dependencies, without ever
mutating the user's global Python and without a package manager's name reaching the artifact
contract. The artifact declares a dependency *specification*; the platform and policy select an
*installer*; the generated runtime uses the artifact-owned interpreter.

## Product Specification sections/invariants

Sections 25–27, 105–115; INV-041–INV-047, and the CP-07 planning invariants they build on
(INV-004, INV-035, INV-036).

- INV-041 — a Python runtime requirement is not a Python package requirement.
- INV-042 — a dependency specification is not an installer backend.
- INV-043 — an artifact provides one dependency contract, not every equivalent format.
- INV-044 — one installed Python MCP owns one isolated environment.
- INV-045 — no implicit global language mutation.
- INV-046 — generated launchers use the artifact-owned runtime.
- INV-047 — author dependency intent and approved resolution are separate.

## Legacy/current paths

- `setup_runtime.py` owns the current environment/dependency behaviour.
- `setup_verify_probes.py` owns the current interpreter and package probes.
- `runtime_contract.py` publishes the current runtime capability names.
- `sources/runtime.py` carries source-side runtime metadata.
- `domain/effects.py` already has `CreatePythonEnvironment` and `InstallPythonDependencies`, but
  neither records which interpreter or which installer the plan approved.
- `installation_planning.py::_possible_remediations` returns no options for a
  `PythonPackageRequirement`, so dependency installation cannot yet be planned or reviewed.

## Target paths/owners

`domain/python_runtime.py` for the dependency-specification algebra and the artifact-owned
environment layout; `domain/remediations.py` for the installer remediation; extensions to
`domain/effects.py`, `domain/inspection.py` and `domain/policies.py`; installer selection in
`application/python_environment.py`; the venv and installer interpreters in `io/python_runtime.py`.

## Dependencies

CP-07 planning pipeline and CP-08 input/credential algebras are verified.

## Non-goals

- No Poetry specification or backend (B-005).
- No launcher generation or harness projection (CP-10).
- No effect interpreter wiring into a public flow, receipt or reconciliation (CP-11/12).
- No environment deduplication or sharing model; §105 defers it and it must not weaken isolation.
- No dependency resolution or lock generation; registry-approved resolution is INV-047's other
  half and belongs to registry CI, not to the installer.

## Characterization / RED evidence

New RED covers: a specification that names no installer; an installer chosen from platform
capability ∩ policy ∩ preference with deterministic failure when the intersection is empty; an
environment path that must live under the artifact root; the refusal to plan against a base
interpreter inside the artifact-owned environment; and the negative case that no planned effect
mutates a global interpreter.

## Implementation steps

1. Add `domain/python_runtime.py`: `RequirementsFile` and `PyProjectSpec` specifications,
   `PythonInstaller`, the compatibility relation between them, and `ArtifactEnvironment` deriving
   the venv root and interpreter from the artifact root.
2. Extend the effects so a review binds what was approved: `CreatePythonEnvironment` records the
   base interpreter, `InstallPythonDependencies` records the selected installer.
3. Add `InstallPythonPackages` to the remediation algebra and `PYTHON_INSTALLER` to the
   remediation-capability kinds.
4. Extend `EffectivePolicy` with `allowed_python_installers`, composing by intersection.
5. Teach `installation_planning` to derive, risk-classify and filter dependency remediations.
6. Add `application/python_environment.py`: pure installer selection and effect lowering.
7. Add `io/python_runtime.py`: the venv and installer interpreters behind a port, plus capability
   observation for pip and uv.

## Property tests

A restrictive overlay cannot add an installer; installer selection is deterministic and
order-independent; a chosen installer is always compatible with the declared specification.

## Integration tests

Create a real isolated environment in a temporary directory with the running interpreter, install
from a real `requirements.txt` with no network (an empty or local-only requirement set), and prove
the system interpreter's `sys.prefix` and installed packages are unchanged.

## E2E/live acceptance

Reached in CP-10 when a real MCP installs through this path; full remote-backed proof is CP-17.

## Done

- CP-09 opened from verified commit `a030579`.
- `domain/python_runtime.py` holds `RequirementsFile` and `PyProjectSpec`, neither of which names a
  backend, and `PythonInstaller`, which no artifact chooses. `installers_for_lock` is the single
  compatibility rule, shared by the specification and by `PythonPackageRequirement`.
- `ArtifactEnvironment` derives `payload`, `environment` and `interpreter` from the artifact root as
  `init=False` fields, so an interpreter path outside the root is not something a caller can supply.
  `owns()` refuses any path containing a parent segment.
- Descriptor paths are validated as payload-relative: absolute paths, `..` segments and empty
  segments are refused, so a descriptor cannot read outside the artifact.
- `CreatePythonEnvironment` now records the base interpreter and `InstallPythonDependencies` records
  the descriptor kind and the selected installer, so approving an install with uv is not the same
  review as approving it with pip.
- `InstallPythonPackages` joined the remediation algebra and `PYTHON_INSTALLER` the capability kinds,
  so `installation_planning` now offers, risk-classifies and policy-filters dependency installation
  instead of returning no options for a `PythonPackageRequirement`.
- `EffectivePolicy` gained `allowed_python_installers`, composing by intersection; preference stayed
  out of the policy algebra deliberately (D-019).
- `application/python_environment.py` selects by intersection and lowers to effects, refusing an
  installer incompatible with the specification and a base interpreter inside the environment.
- `io/python_runtime.py` runs `venv`, pip and uv behind a port, refusing any effect outside the one
  artifact it was constructed for before a process starts (D-020), and refusing a locked project
  rather than installing loose versions (D-021).

## Remaining

- Nothing in this slice. A real MCP installs through this path in CP-10; remote-backed proof is
  CP-17.

## Known compromises

- The environment layout is POSIX only; B-017 tracks the Windows layout.
- A locked project is modelled, planned and refused at execution; B-018 tracks installing one.
- No dependency resolution or lock generation. INV-047's other half belongs to registry CI.

## Backlog discoveries

- B-017 — Windows environment layout for artifact-owned Python environments.
- B-018 — installing a locked Python project.

## Blockers

None.

## Legacy removal criteria

`setup_runtime.py` environment authority remains until CP-10 routes a real MCP installation
through the canonical environment port with equivalent isolation evidence.

## Handoff

- Current working state: CP-09 verified. Domain, application and io layers complete, with the
  interpreters proven against real `venv`, real pip and real uv.
- Exact next action: open CP-10 (production MCP stdio vertical slice).
- Do not undo: derived-only paths on `ArtifactEnvironment`; the interpreter's ownership refusals
  and the tests asserting no process ran; the explicit refusal of a locked project; the installer
  and descriptor kind travelling in the effect so they reach the review digest.
- Tests last run/results: full quality green — all ten gates, 2,066 unit tests, 46 E2E tests,
  83.20% coverage. `tests/python_environment_integration_test.py` is 14 tests; the uv test skips
  when uv is absent, everything else runs everywhere and touches no network — the package it
  installs is a wheel the test builds itself.
- Failure evidence: none outstanding.
