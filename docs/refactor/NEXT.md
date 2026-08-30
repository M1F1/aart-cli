# AART Refactor — Next Work

## Current objective

Open **CP-08 Runtime inputs and credential lifecycle** on the verified CP-07 canonical plan.

## Immediate next actions

1. Read Product Specification sections 14–21, 37–39, 91–104 and 154–157, then characterize the
   existing setup/credential/config seams (`setup.py`, `setup_engine/*`, `configuration/*`,
   `io/config_store.py`, `io/config_cas.py`).
2. Write CP-08 RED tests for `SecretInput` vs `ConfigInput`, `InputValueSource` vs `ProcessBinding`,
   and `CredentialReference` vs credential value, including the negative case that no persistent
   secret-value type exists.
3. Implement inspect/store/verify/replace/delete with dependent-artifact awareness and a macOS
   Keychain interpreter behind an explicit port; never read or display an old secret value.
4. Carry registry-provided input guidance as metadata only, with secret help limited to format
   hints and obtain-from locations.

## Do not do yet

- no broad package moves;
- no TUI rewrite;
- no switch to Textual/Rich;
- no Docker-first MCP design;
- no changes to old AART repositories;
- no Source Sync promotion;
- no Python environment/dependency backend (CP-09);
- no MCP launcher/harness projection (CP-10);
- no effect interpreter, mutation, receipt or reconciliation engine (CP-11/12);
- no backlog work unless it becomes a proven critical-path blocker.
