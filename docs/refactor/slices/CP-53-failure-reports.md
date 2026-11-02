# CP-53 — Failures aart-cli meets are journaled, reportable, and sent to the telemetry server

Status: **in progress**; steps 1–4 done, the PRs open.
Authority: Product Specification §213, §215, INV-333–INV-336, D-509.

## Steps

See `docs/refactor/plan.json`, epic CP-53.

1. The failure, its fingerprint and `aart_cli.failed` in contract version 1 (domain, contract,
   examples). Done.
2. The journal `state/failures.sqlite3` and every place that records into it: commands, the
   terminal application and its actions, the usage hook, the telemetry sender. Done.
3. `consume report`, the build's and the person's choice, sending. Done.
4. The server stores, checks and shows failures (aart-cli-telemetry-server, `feat/error-reports`).
   Done.
5. The PRs.

## Why

The owner asked, after 0.23.0, that error states, errors and terminations be known before anyone
opens a GitHub issue, precisely enough to write the patch and release it, and approved the plan
with its defaults: on by default through a release variable and a Settings choice, never an
exception's message, a local journal with `consume report`, and a dashboard on the server.

## What changed

- `domain/failures.py`: `Failure` holds only fields of the contract's shapes; `failure_of` keeps
  aart-cli's own frames (innermost 30), distinct codes (first 10), and names an unnamable crash
  `Exception`; `fingerprint`; `from_document` checks it; `JournaledFailure`, `FailureGroup`,
  `grouped`.
- `domain/telemetry.py`: `FAILED = "aart_cli.failed"`; `TelemetryEvent.failure`, present exactly for
  that type, with kind and place as `artifact_type`/`artifact_id` and no version; `failure_event`;
  `parse_failures_sent`, sharing `_switch` with `parse_unmanaged_uses`.
- `io/telemetry_store.py`: `open_versioned`, the outbox's opener, extracted for the journal too.
- `io/failure_journal.py`: `FailureJournal` (record keeping the newest 500, waiting, entries, settle,
  skip_waiting, counts, forget); `record_failure`, which never raises or prints; `noting` and
  `note_diagnostics` (a `ContextVar`).
- `io/telemetry_sync.py`: `_Run` shares one budget across the outbox and the journal;
  `_send_journal` sends waiting failures in batches of one version with it as `client_version`, or
  skips them when failures are not sent; journal rows count toward a due synchronisation; the
  sender's own crash is journaled without starting one.
- `io/usage_hook.py`: a crash is journaled as `usage-hook`; the hook still exits 0 silently.
- `cli.py`: `_dispatch` runs inside `noting()`; a crash and Ctrl+C are journaled and re-raised, a
  nonzero exit journaled with the codes noted. `commands/report.py`: `consume report`,
  `command_place`, `record_command_failure`, `record_in_application_home`.
- `commands/{marketplace,registry,source,candidate,doctor}.py`: `_emit_error` notes its codes.
- `tui.py`: `_render_internal_failure` journals `tui` after drawing; both terminals pass
  `on_action_failed`. `tui_consumer.run_consumer_shell` calls it for each `ACTION_FAILED`;
  `LocalConsumerActions.record_action_failed` journals `tui.<action>`.
- Choice: `_default_telemetry.ERRORS`, `scripts/inject_default_telemetry.py`,
  `configuration/seed.baked_failures_sent`, `scripts/release.py` (`default_telemetry_errors`),
  `.github/workflows/release.yml` (both jobs), `ConsumerSettings.telemetry_errors` /
  `sends_failures` (stored as `telemetry_failures`), the Settings row `telemetry-errors`,
  `consume telemetry errors on|off`, `status` (`errors`, `journal`), the announcement and `enable`.
  `disable --forget` deletes the journal.
- `tests/conftest.py`: a command's or the terminal's failure is journaled only in a module that
  sets `RECORDS_FAILURES = True`, so no test writes the real `~/.aart-cli`.
- Docs: §215, `docs/telemetry-api-v1.md` (Failures), the contract's examples, the user guide
  (Failures aart-cli met) and the enterprise rollout's variable table.

## Evidence

- `tests/failure_domain_test.py` (14): what is kept, frames and codes bounded and filtered, a type
  that cannot be named, places and platforms the contract cannot carry; the fingerprint keeps
  across moved lines and changes with a function; Hypothesis: the fingerprint is the contract's own
  digest and ignores line numbers (INV-334), and whatever text is given only the contract's shapes
  are kept (INV-333); the contract's valid failure examples are what this client builds and none
  of its seven invalid ones can be built.
- `tests/failure_journal_test.py` (36): the journal is 0600, keeps the newest, settles, forgets,
  refuses another schema without rewriting it, skips an unreadable row; a real exception raised in
  aart-cli keeps its frame and type, and neither its message nor the test's frame reaches the file;
  Hypothesis over messages (INV-333); a failing `consume list --json` journals `error` at
  `consume.list` with exit code 1 and exactly the codes it printed; a crash and Ctrl+C are journaled
  and re-raised; success journals nothing; the place is never an argument; a command's exit code,
  stdout and stderr are identical with the journal absent, failing to write or failing to build the
  record (INV-335); the hook stays silent and exits 0; the sender's crash waits; the terminal draws
  the same report; an action that stopped is journaled from the real composition and the real shell
  calls back; `consume report` text and JSON, grouping, `--limit`, an empty journal; sending:
  journaled before telemetry was on and sent once it is, batches per version, turned off skipped
  and never sent, a rejection settles, a down server keeps it, a waiting failure makes a sync due
  (INV-336); the build's value, the injector, the workflow and receipt, Settings, the command,
  `status --json`, `disable --forget`, and the announcement.
- 956 tests of telemetry, the CLI, the TUI, settings, usage, release, doctor, candidates, sources
  and registries pass, the contract digests among them: both repositories hold the same bytes.
- The server (`aart-cli-telemetry-server`, `feat/error-reports`), `tests/test_failures.py` (47):
  the fingerprints aart-cli computed in the contract's examples are the ones the server computes;
  each invalid example names the rule it breaks; changing what names a defect without its
  fingerprint is refused, and accepted once refitted; a line or an exit code never changes it
  (Hypothesis); every pattern of the `failure` object, a field beyond it (Hypothesis), a kind, a
  place and a version; every failure the contract allows reads back as sent (Hypothesis); grouping
  by defect as its latest occurrence says, with installations, versions, platforms, first and last
  seen, and the order; a version-1 database gains its `failure` table and keeps its events; an id
  kept as another event is never counted as a failure; the endpoint's body and bounds. The
  repository contract holds SQLite (and PostgreSQL when configured) to the definitions over
  generated histories in which a defect recurs. `tests/test_e2e_aart_cli.py` runs this branch's
  aart-cli against the server: a failing `consume report --limit 0` and a crash in aart-cli's own
  code arrive as two defects with aart-cli frames only; after `consume telemetry errors off` the
  next one is skipped and never arrives. `make quality` on the server: 130 passed, 98% branch
  coverage.

## Targeted mutations

| # | Mutation | Killed by |
|---|---|---|
| M1 | The fingerprint includes line numbers | `failure_domain_test` (INV-334 property) |
| M2 | The outermost 30 frames kept, not the innermost | `failure_domain_test` |
| M3 | A document's fingerprint not checked | `failure_domain_test` |
| M4 | A crash with an unnamable type has none | `failure_domain_test` |
| M5 | A code of any shape kept | `failure_domain_test` |
| M6 | The oldest 500 kept, not the newest | `failure_journal_test` |
| M7 | No frame extracted | `failure_journal_test` |
| M8 | A type named without its module | `failure_journal_test` |
| M9 | Recording starts no synchronisation | `failure_journal_test` |
| M10 | No code noted | `failure_journal_test` |
| M11 | An unreadable row reported | `failure_journal_test` |
| M12 | Failures sent though turned off | `failure_journal_test` |
| M13 | One batch for several versions | `failure_journal_test` |
| M14 | A batch's version not the recording one | `failure_journal_test` |
| M15 | Waiting failures never make a sync due | `failure_journal_test` |
| M16 | The journal never sent | `failure_journal_test` |
| M17 | The sender's crash starts a sync | `failure_journal_test` |
| M18 | The hook's crash at another place | `failure_journal_test` |
| M19 | A nonzero exit not journaled | `failure_journal_test` |
| M20 | Ctrl+C not journaled | `failure_journal_test` |
| M21 | A crash not journaled | `failure_journal_test` |
| M22 | `marketplace._emit_error` notes no code | `failure_journal_test` |
| M23 | The place is only the command | `failure_journal_test` |
| M24 | `--limit` ignored | `failure_journal_test` |
| M25 | Groups not ordered seen-last first | `failure_journal_test` |
| M26 | The person's choice ignored | `failure_journal_test` |
| M27 | The build's value ignored | `failure_journal_test` |
| M28 | `--forget` leaves the journal | `failure_journal_test` |
| M29 | The terminal's crash not journaled | `failure_journal_test` |
| M30 | The shell does not tell an action that stopped | `failure_journal_test` |
| M31 | An action that stopped not journaled | `failure_journal_test` |
| M32 | Any build value accepted | `failure_journal_test`, `failure_domain_test` |
| M33 | The report says nothing here left the machine | `failure_journal_test` |

After 0.24.0: its report said "nothing here left this machine", which is false once telemetry has
sent a failure. §215 says only that the report sends nothing; it now says that, and points to
`consume telemetry status` (M33).

On the server:

| # | Mutation | Killed by |
|---|---|---|
| S1 | The server's fingerprint includes line numbers | `test_failures` |
| S2 | A fingerprint not checked | `test_failures` |
| S3 | A crash without its exception accepted | `test_failures` |
| S4 | Any place accepted | `test_failures` |
| S5 | A module name of any length accepted | `test_failures` |
| S6 | Repeated diagnostics accepted | `test_failures` |
| S7 | A failure on another event type accepted | `test_failures` |
| S8 | A bad failure field reported as another reason | `test_failures` |
| S9 | Equally frequent defects not latest first | `test_failures` |
| S10 | A defect said as its earliest occurrence | `test_failures` |
| S11 | Failures not counted in the summary | `test_failures` |
| S12 | Occurrences counted as installations | `test_failures` |
| S13 | SQL counts unmanaged uses as failures | `test_failures`, `test_repository_contract` |
| S14 | SQL says a defect as an arbitrary occurrence | `test_repository_contract` |
| S15 | SQL ranks without the latest | `test_repository_contract` |
| S16 | SQL counts a failure row beside another event | `test_failures` |
| S17 | A version-1 database not given its failure table | `test_failures` |
| S18 | SQL keeps no failure row | `test_failures`, `test_repository_contract` |
| S19 | The endpoint drops versions | `test_failures` |
| S20 | An event's failure not tied to its type | `test_failures` |

S14 survived at first: generated histories almost never held one defect twice. The strategy now
draws recurring defects at varying lines for histories, and S14 is killed. `make mutants` was not
run over the new modules; the targeted mutations above are the slice's record.
