# CP-54 — Automation says so, and the telemetry server counts it apart from people

Status: **done**; the server's side merged first (aart-cli-telemetry-server #14), this PR is the
client's.
Authority: Product Specification §213, INV-337, D-511.

## Why

The owner asked to tell automata from real users. A CI job runs aart-cli in a fresh environment and
draws a new installation id each time, so every job read as a new person on the dashboard.

## What changed

- `docs/telemetry-api-v1.md`, `contract/telemetry-api-v1.examples.json`: the optional envelope field
  `automated`, a valid example from automation, and the versioning rule it was added under. Both
  are byte-identical with the server's, and the digests are updated on both sides.
- `domain/telemetry.py`: `AUTOMATED_VARIABLE`; `automated(environment)`, which reads
  `AART_CLI_AUTOMATED` (on/true, off/false), then `CI` (anything but nothing, false or 0), and no
  other variable; `batch_document(..., automated=)` adds `"automated": true` only when true.
- `io/telemetry_sync.py`: `synchronise(..., environ=None)` decides once a run, from the environment
  the detached sender inherited, and `_Run.send` passes it to every batch, the outbox's and the
  journal's.
- `commands/telemetry.py`: `consume telemetry status` says "sent as: automation …" or "sent as: a
  person's installation …", and `--json` adds `automated`.
- `docs/using/consumer-lifecycle-v1.md`: what a person or a pipeline sets.

## Evidence

- `telemetry_domain_test.AutomationTest`: the field only when true; the table of environments; a
  Hypothesis property that no other variable ever changes the answer.
- `telemetry_sync_test`: a request says `automated` exactly when the sender's environment says so,
  and never `false`.
- `telemetry_cli_test`: status, as text and JSON, for CI, none, and CI overruled.
- The contract's valid example from automation is one this client builds exactly.
- Targeted mutations, each killed by the test that names it:
  - A1 `on` without `true`;
  - A2 `off` without `false`;
  - A3 `CI` compared without lowering its case;
  - A4 `0` no longer counted as no;
  - A5 the setting no longer stripped;
  - A6 `"automated": false` sent for a person;
  - B1 the run's answer not passed to the batch;
  - B2 `environ` ignored for `os.environ`;
  - B3 status always saying a person's.
- Server side (aart-cli-telemetry-server #14):
  - the full quality gate in python:3.13;
  - the repository contract on PostgreSQL 16;
  - mutations of the contract, events, stats, SQL and API, all killed (one first survived and its
    test was strengthened).
