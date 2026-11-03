# CP-61 — Each event says where and how it happened

Status: **done** on its branch; merged with its PR.
Authority: Product Specification §213 (amended), D-518, INV-340. The rest of revision 7 is B-269.

## Why

The owner asked on 2026-11-03 for events to be as broad as possible and queryable on the server,
with no field about the project. The server's contract revision 7 (aart-cli-telemetry-server #19)
defines the optional fields and the request's `environment`.

## What changed

- `docs/telemetry-api-v1.md` and `contract/telemetry-api-v1.examples.json` were copied from the server
  at revision 7, and the digests in `tests/telemetry_domain_test.py` updated.
- `domain/telemetry.py`:
  - `EventContext` holds revision 7's fields, validated by the contract's shapes;
  - `fitting` drops a value the contract cannot carry;
  - `problem` holds which field each event may say;
  - `Environment` and `environment_of`;
  - `TelemetryEvent.context` and `document(revision=)`, which adds the context only from revision 7;
  - `batch_document(revision=, environment=)`;
  - `read_contract`;
  - `lifecycle_event(harness=, scope=)`;
  - every event names its Registry alias, and an opencode MCP use names its tool.
- `application/consumer_views.py`: a receipt's artifact view keeps its installation owner's harness
  and scope, and stores them as optional keys.
- `application/telemetry_events.py` passes them to each lifecycle event.
- `io/telemetry_store.py`:
  - the outbox gains a `context` column, added in place where it is missing;
  - an event keeps its context;
  - unreadable text reads as no context.
- `io/telemetry_sync.py`:
  - `http_get`, and `synchronise(get=, platform=)`;
  - `_Run.ask` asks `GET /api/v1/contract` once per run before the first send;
  - a refused or unanswered question ends the run as a send's answer would.
- Telemetry's announcement and the Settings row now name what is sent and what is never sent.
- Spec §213, INV-340, D-518, B-269.

## Evidence

`tests/telemetry_context_test.py`:

- the contract's examples are read at revision 7;
- a written-out table of which field each event may say, and each refusal rule;
- a Hypothesis round trip of a context through its document;
- `read_contract`'s answers;
- below revision 7 and with no revision, nothing of the context is sent;
- the environment's shapes;
- lifecycle and use events name their Registry alias, harness, scope and tool;
- a real proposed and executed installation's receipt names the owner's harness and scope, and
  reads them back.

`tests/telemetry_sync_test.py::WhatEachServerIsSentTest`, against a local HTTP server:

- revision 7 is sent the context and the environment;
- revision 6 and no revision are sent neither;
- a contract answer of `503`, `429` or `401` stops the run;
- a server that is down;
- the question is asked once a run;
- an old outbox gains the column and its events are sent.

Targeted mutations, each killed:

- the lifecycle scope dropped;
- the owner's harness and scope never read;
- the scope key never stored;
- the harness never read back;
- the scope never passed to the event;
- the context never stored, the column never added, or never read;
- the contract asked every send;
- a refused contract answer ignored;
- the revision forgotten;
- the environment never sent;
- never asking.

Two survivors were equivalent: a `bool` revision check, and the harness check on an opencode tool.
Both conditions were removed.
