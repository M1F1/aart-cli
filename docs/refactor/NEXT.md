# AART Refactor — Next Work

## Current objective

Open **CP-10 Production MCP stdio vertical slice** on the verified CP-07 planning pipeline, CP-08
input and credential algebras, and CP-09 artifact-owned Python environments.

This is the first slice where the canonical path has to carry a real installation end to end:
Python source tree, stdio transport, isolated runtime, declarative inputs, a generated runtime
projection and one real harness adapter. It is also the slice where the legacy `setup_*` authority
first becomes removable, so treat "the new path is the one actually used" as the deliverable, not
"the new path exists".

## Immediate next actions

1. Read Product Specification sections 113–115 again alongside the harness/transport sections, then
   characterize the current launcher and harness-configuration behaviour before changing anything.
2. Write CP-10 RED tests for the generated runtime projection: it invokes the artifact-owned
   interpreter, it reads secrets through the provider at launch rather than baking them in, and it
   installs nothing at run time.
3. Implement the launcher generation and one harness adapter behind ports, keeping generation pure
   and writing behind an interpreter.
4. Prove AART is absent from the runtime path after installation — a negative test, not a claim.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker or OCI distribution (B-003);
- no changes to old AART repositories;
- no Source Sync promotion;
- no reconciliation engine or receipts beyond what this slice must write (CP-11/12);
- no additional secret providers (B-004) or installer backends beyond pip and uv;
- no backlog work unless it becomes a proven critical-path blocker.

## Carried forward

- CP-08: `TransientSecret` lives only in `io/`; nothing in `domain` or `application` may gain a
  field that can hold a secret value. `plan_credential_mutation` takes `policy` as a required
  keyword. Keychain replacement is delete-then-add (D-017). `domain/inputs.py` parses URLs itself.
- CP-09: `ArtifactEnvironment` paths are derived, never supplied — the generated launcher must take
  its interpreter from there. The runtime interpreters refuse effects outside the artifact they were
  constructed for, and the tests assert no process ran; keep both. A declared lock is refused, not
  ignored (D-021).
