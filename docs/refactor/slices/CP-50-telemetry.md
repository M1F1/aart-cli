# CP-50 — Telemetry: installs, updates, removals and uses sent to a telemetry server

Status: **done in code and evidence**, on `feat/cp-50-telemetry`; the PR is open and the owner's
review is next (2026-10-29).
Authority: Product Specification §213, INV-322–INV-328, D-503, D-504.

## Steps

See `docs/refactor/plan.json`, epic CP-50.

1. The contract (`docs/telemetry-api-v1.md`, `contract/telemetry-api-v1.examples.json`) and the
   pure rules: the address, an event, when a sync is due, what an answer does. Done.
2. The outbox in SQLite, recording from actions and from the usage hook while telemetry is on. Done.
3. The sender: one at a time under a lock, a detached process, split and backoff. Done.
4. `consume telemetry status|enable|disable|sync`, and the release variable
   `AART_CLI_TELEMETRY_ENDPOINT`. Done.
5. The server, in its own repository (`aart-cli-telemetry-server`), and an end-to-end run of this
   aart-cli against it. Done.
6. The PR. Open.

## Why

After 0.21.0 the owner asked for a new CP for this repository and a new repository with a telemetry
server, "tak jak mówi specka", from their implementation brief: the organisation sees which
artifacts are used, how often, by how many installations and how that changes. The brief's
acceptance tests 1–10 and the cost of the hook were to be measured. For the server they then asked
for the same quality gates as aart-cli (tach, mypy, ruff, unit tests, Hypothesis), a functional
style with `returns`, pydantic and an ORM allowed, and the database abstracted as a functional core
with an imperative shell, because it may later move to PostgreSQL.

## What changed

- `aart_cli/domain/telemetry.py` (new, pure): `parse_telemetry_endpoint`, `TelemetryEvent`,
  `lifecycle_event`, `use_event`, `batch_document`, `classify_answer`, `SyncState`, `sync_due`,
  `after_success`, `after_failure`, the limits (`SYNC_INTERVAL`, `BATCH_SIZE`,
  `MAX_REQUESTS_PER_RUN`, `RUN_SECONDS`, `HTTP_TIMEOUT_SECONDS`, `AUTH_PAUSE`).
- `aart_cli/application/telemetry_events.py` (new): `lifecycle_events` from a finished action's
  receipt, completed members only.
- `aart_cli/io/telemetry_store.py` (new): `TelemetryOutbox` in `state/telemetry.sqlite3` (0600,
  schema version 1, another version reported and left alone): the setting, the installation id,
  events and their state, the sync state, forget.
- `aart_cli/io/telemetry_sync.py` (new): `http_post` (no proxy for loopback, bounded answer),
  `synchronise` under a non-blocking `fcntl` lock on `state/telemetry.lock`, `maybe_sync`,
  `spawn_sync` (a detached `python -I -c` bootstrap with this package's root on its path), `main`.
  A use is sent only as the installed artifact it resolves to; one nothing answers to is marked
  skipped.
- `aart_cli/domain/artifact_usage.py`: `resolve_installed` (the ranking's resolution, now shared),
  `InstalledName.version`.
- `aart_cli/io/receipt_store.py` and `aart_cli/io/usage_hook.py`: after a recorded action or use,
  one `stat` where telemetry was never turned on; otherwise the events are kept and a due sync is
  started. Nothing there can fail the action or the hook.
- `aart_cli/commands/telemetry.py` (new), `cli.py`, `cli_parser.py`, `model.py`:
  `consume telemetry status [--json] | enable [--endpoint URL] | disable [--forget] |
  sync [--force]`.
- `aart_cli/_default_telemetry.py` (new, empty in the source), `scripts/inject_default_telemetry.py`
  (new), the release action's step, both release jobs' `AART_CLI_TELEMETRY_ENDPOINT`, the receipt's
  `default_telemetry_endpoint`, `configuration.seed.baked_telemetry_endpoint`; `tach.toml`.
- `docs/telemetry-api-v1.md` and `contract/telemetry-api-v1.examples.json` (new), byte for byte the
  server's; each repository's contract tests pin both digests.
- The server, `aart-cli-telemetry-server` (D-504): `domain` (events, the strict pydantic contract,
  the dashboard's definitions), `application` (the `EventRepository` port and the use cases as
  `IOResult` flows), `adapters` (an in-memory oracle; SQLAlchemy Core for SQLite in WAL and for
  PostgreSQL), `effects.perform` as the only `returns.unsafe` import, `web` (FastAPI, a strict-CSP
  Chart.js dashboard), `cli` (loopback unless `--behind-authenticating-proxy`, `backup`).

## Evidence

- `tests/telemetry_domain_test.py` (17): the contract copies' digests; every valid example is an
  event this client could build and no invalid one can be; Hypothesis — no address with a user is
  accepted, a sync is due exactly on time and never on count, backoff grows to its cap and success
  clears it, only ids that were sent are marked; a use is sent as the installed artifact and one
  nothing answers to never is; lifecycle events name the artifact and version.
- `tests/telemetry_sync_test.py` (23): the outbox holds exactly what was recorded while on
  (Hypothesis); 0600; forget; another schema version left alone; the brief's scenarios 1–9 against
  a scripted server; partial acknowledgement; a held lock; concurrent threads send each event once;
  a sender killed mid-request leaves its events waiting; REJECTED and SPLIT; the 401 pause and
  `--force`; the manual interval; `http_post` against a real `ThreadingHTTPServer` with the proxy
  ignored for loopback; the real hook end to end, the detached sync delivering; nothing fails what
  triggered it.
- `tests/telemetry_cli_test.py` (8) and `tests/release_default_telemetry_injection_test.py` (10,
  Hypothesis: every accepted address survives baking; a refused one fails the release).
- The brief's test 10, live: the server's `tests/test_e2e_aart_cli.py` with `AART_CLI_PYTHON` on
  this branch's environment: 150 events delivered in 2 requests, sent again from a second home,
  stored once.
- The hook's cost, 15 runs each, median: 55 ms with telemetry off, 77 ms with it on and no sync
  due (the sync itself runs detached).
- The server: `make quality` — ruff, mypy strict (pydantic and returns plugins), tach (layers and
  external dependencies), 80 tests under branch coverage 98% (minimum 95%); the repository contract
  on PostgreSQL 16 with an ICU `en-US` database, 17 passed; mutmut over `domain` and
  `application`: 379 of 399 killed, the 20 left equivalent (README).

## Targeted mutations

| # | Mutation | Killed by |
|---|---|---|
| M1 | Every waiting id settled, not the acknowledged ones | `telemetry_sync_test` (only what the server acknowledged) |
| M2 | `LOCK_SH` instead of `LOCK_EX` | `telemetry_sync_test` (concurrent senders) |
| M3 | The backoff never saved | the brief's tests 4 and 5, the 401 pause |
| M4 | A refused batch never halved | `telemetry_sync_test` (SPLIT) |
| M5 | A use nothing answers to never skipped | `telemetry_sync_test` (skipped uses) |
| M6 | `spawn or True` | `telemetry_sync_test` (never fails what triggered it) |
| M7 | No `ProxyHandler({})` for loopback | `telemetry_sync_test` (`http_post` ignores the proxy) |
| M9 | The outbox treats every row as on | the outbox property and the CLI tests |
| M10 | A recorded event always starts a sync | `telemetry_sync_test` |
| D1 | A sync always due | `telemetry_domain_test` (due exactly on time) |
| D2 | `pending < 0` | `telemetry_domain_test` |
| D3 | The backoff ignored when manual | `telemetry_domain_test` (manual sync honours it) |
| D4 | The backoff always its first step | `telemetry_domain_test` (grows to its cap) |
| D5 | Jitter ×1 instead of a fifth | `telemetry_domain_test` (bounds) |
| D6 | `http://` to a non-loopback host accepted | `telemetry_domain_test` (https anywhere, http only to loopback) |
| D7 | A success keeps the failure count | `telemetry_domain_test` (success clears it) |
| S1 | Server: `COLLATE "C"` removed from the ranking | the repository contract on an ICU PostgreSQL database (2 failed); not on a `C`-collated one, so CI creates it with ICU `en-US` |

M8 (`usage_hook` starts a sync whenever `record_use` answered `Ok`, ignoring whether it kept
anything) is equivalent: `maybe_sync` checks for itself that telemetry is on and something waits.
D5 once also turned `the outbox holds exactly what was recorded while on` red under mutmut's CPU
load; on unchanged code that test passed six runs in a row.

## Not done here

B-253 (telemetry in the TUI's Settings), B-254 (a per-user credential beyond loopback),
B-255 (a corporate CA bundle), B-256 (whether an organisation's build starts with telemetry on),
B-257 (the server's next stage: AKS, Alembic, retention). The server is `M1F1/aart-cli-telemetry-server`
(private), created by the owner on 2026-10-29.
