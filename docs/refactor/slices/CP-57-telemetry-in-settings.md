# CP-57 — Settings turns telemetry on and off

Status: **done**; merged in aart-cli #124 with CP-56.
Authority: Product Specification §213 (amended), D-514. Resolves B-253.

## Why

Telemetry was turned on and off only with `consume telemetry`. Settings showed the two choices
about what it sends, but not whether it sends at all.

## What changed

- `application/telemetry_settings.py`:
  - `TelemetryView`: on or off, the address (kept, else the build's), the installation id, events
    and failures waiting, the last success, and whether this machine runs as automation;
  - `what_is_sent`: the two sentences of consent `consume telemetry enable` prints, which now come
    from here;
  - `sent_as`: how requests are counted, which `consume telemetry status` now prints from here;
  - `telemetry_status`: the row's status.
- `application/consumer_views.py`: `TELEMETRY_ROW`, first under the Telemetry heading, with its
  purpose. It is no consumer setting, so `ConsumerSettings.toggled` refuses it.
- `application/consumer_ui.py`: `ConsumerActionKind.TELEMETRY`, `ConsumerUiCommandKind.RUN_TELEMETRY`.
  Enter on the row asks to run it and keeps no preference; its answer leaves Settings where it was.
- `tui_consumer.py`: `ConsumerScreens.telemetry`; the row reads on or off from it; on the row the
  status is `telemetry_status`, in Fast too; the shell hands `RUN_TELEMETRY` to the handler.
- `consumer_actions.py`: `_telemetry()` reads the outbox, the failure journal and the environment;
  `_run_telemetry` turns it off (`disable(forget=False)`) or on (`turn_on` with the kept address,
  else the build's), and refuses with `--endpoint` named when there is neither.

## Evidence

`tests/telemetry_settings_row_test.py`:

- the row comes right before *Uses of tools aart-cli did not install* and reads on or off from the
  outbox's view, off without one; it is not a setting;
- the status, on: where with the batch path, the consent lines, what waits, the last success,
  `sent_as`, and that Enter turns it off; off: where it would send, with a random installation id,
  or that no server is named and `--endpoint`;
- Hypothesis: for any installation id and choices, `what_is_sent` names uses of tools aart-cli did
  not install and failures exactly when they are sent, and the id exactly when there is one;
- `consume telemetry enable` prints `what_is_sent`'s lines, and `status` under `CI` prints
  `sent_as(True)`;
- the reducer: Enter runs `RUN_TELEMETRY` and keeps settings; its answer stays on Settings; elsewhere
  nothing happens;
- on a real home: on with the build's address, then off, kept in the outbox and drawn; on again with
  the address kept before and the same id; with no address, refused and nothing kept; `CI` read as
  automation; what waits (3 events, 1 failure) and the last success after a real synchronisation;
- the shell: Enter on the row turns it on.

Existing tests changed for the new row: the Settings block's rows, the unmanaged row's place under
the heading, and the binary-settings test, which leaves the telemetry row out as it does the two
choices.

Targeted mutations, each killed by the test that names it:

- N1 never turning it off;
- N2 the kept address ignored;
- N3 automation never read;
- N4 a decision read as on whatever it was;
- N5 the build's address not offered;
- N6, N16, N17 what waits, failures waiting and the last success not read;
- N7 the consent left out of the status;
- N8 uses of other tools always named;
- N9 no word on turning it off;
- N10 the row on whenever a view exists;
- N11 the row toggling nothing;
- N12 its answer not clearing the action;
- N13 the shell not running it;
- N14 `status` not saying automation;
- N15 an empty installation id named.

N6 first survived, because the test read an empty outbox; it now sends, waits and journals for
real.
