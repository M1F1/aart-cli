# AART Refactor — Next Work

## Current objective

Open **CP-09 Isolated Python runtime/dependency effects** on the verified CP-08 input and
credential algebras.

## Immediate next actions

1. Read Product Specification sections on Python environments and dependency descriptors, then
   characterize the existing environment/dependency seams (`setup_runtime.py`,
   `setup_verify_probes.py`, `runtime_contract.py`, `sources/runtime.py`) before changing anything.
2. Write CP-09 RED tests for per-artifact isolated environments, `RequirementsFile` and `PyProject`
   descriptors, and the separation between an installer *capability* (pip or uv is present) and an
   installer *remediation* (this plan will use it) — the CP-07 distinction, applied to dependencies.
3. Implement the environment and dependency effects as pure plan values first, with the interpreter
   behind a port in `io/`, so planning still never touches the host.
4. Prove that a generated launcher installs nothing at runtime and that the system Python is never
   mutated; both are negative tests, not comments.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no Source Sync promotion;
- no launcher generation or harness projection (CP-10);
- no effect interpreter, mutation, receipt or reconciliation engine (CP-11/12);
- no additional secret providers beyond the macOS Keychain (B-004);
- no backlog work unless it becomes a proven critical-path blocker.

## Carried forward from CP-08

- `TransientSecret` lives only in `io/`. Nothing in `domain` or `application` may gain a field that
  can hold a secret value.
- `plan_credential_mutation` takes `policy` as a required keyword. Do not give it a default.
- Keychain replacement is delete-then-add and a test asserts `-U` is absent; D-017 records the
  measurement behind that. Do not "simplify" it back.
- `domain/inputs.py` parses URLs itself. Do not reintroduce `urllib` into `domain` to shorten it.
