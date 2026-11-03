# CP-56 — An end by SIGTERM or SIGHUP is journaled

Status: **done** on its branch; merged with its PR.
Authority: Product Specification §215 (amended), INV-335, INV-339, D-513. Resolves B-265.

## Why

A closed terminal sends SIGHUP and a supervisor SIGTERM. At their default either ends the process
at once, with no exception `cli.main` or the terminal application could catch, so an end by either
left nothing in the journal, unlike Ctrl+C.

## What changed

- `io/termination.py`: `TerminationGuard(record, place)`. While its `with` block runs it takes
  SIGTERM and SIGHUP, each only if it holds its default handling and only in the main thread. On the
  signal it calls `record(place, 128 + number)`, drops whatever that raises, gives the signal back
  its default handling and sends it again, so the process ends by that signal. Leaving the block
  gives back the default where the handler is still its own. `place` can be changed while it runs.
- `commands/report.py`: `journaling_terminations(request, place)`, the guard recording an
  `interrupted` failure in the command's application home.
- `cli.main`: the dispatch runs inside it, at the command's place (`consume.list`).
- `consumer_actions.LocalConsumerActions.journaling_terminations()`: the guard at `tui`, giving a
  callable that moves it to `tui.<action>` while an action runs and back to `tui` with None. With no
  data root it keeps nothing.
- `tui_consumer.run_consumer_shell(on_action_running=)`: told each action before the handler runs
  it and None after, whatever the handler does.
- `tui.run_consumer_text` and `run_consumer` (curses): the shell runs inside the guard.

An end nothing can catch (SIGKILL, a lost machine) is still not journaled: the marker B-265 first
suggested would find it at the next start, but not where it happened in a command, and nobody asked
for it (D-513).

## Evidence

`tests/termination_test.py`; each test that names a signal sends the real one to a real process:

- the guard: SIGTERM and SIGHUP are journaled at the place held when they arrive, 143 and 129, and
  the process ends by the signal (return code −15, −1) without running on; a record that raises
  still ends it, with nothing on stderr; a signal set to ignore or to its own handler before is left
  so (nothing journaled, the process runs on); leaving gives back SIG_DFL; another thread takes
  nothing;
- `cli.main(["consume", "list"])` ended by either signal: one `interrupted` failure at
  `consume.list`, exit code 143 or 129, no exception type, and the process ends by the signal;
- the terminal: `tui.install` while that action runs, `tui` after it and with none;
- the shell tells the action before the handler runs and None after; the text and the curses
  terminal both run the shell inside the guard and pass its callable.

Targeted mutations, each killed by the test that names it:

- M1 the exit code without 128;
- M2 a signal taken whatever its handler;
- M3 the signal not sent again (the process runs on);
- M4 a record that raises not dropped;
- M5 the default not given back;
- M6 another thread's refusal not caught;
- M7 the shell not saying an action is over;
- M8 the place not going back to `tui`;
- M9 the terminal's place wrong;
- M10 `cli.main` not guarded;
- M11 and M12 the text and the curses terminal not passing the callable.

Existing tests whose stand-in actions were `mock.Mock` now use `mock.MagicMock`, since the terminal
enters the actions' guard with `with`.

`make mutants ONLY=aart_cli/io/termination.py TESTS="tests/termination_test.py"` gives no verdict
here: mutmut's runner times out on the in-process guard test and cannot see the mutants in the
real processes the other tests start. The targeted mutations above are the evidence.
