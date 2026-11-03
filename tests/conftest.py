"""What every test shares.

A command or the terminal application that fails journals the failure in its application home
(§215), which for a test that runs `cli.main` or `tui.run` without a home of its own would be this
machine's `~/.aart-cli`. So such a failure is journaled only in a module that asks for it with
`RECORDS_FAILURES = True`, and gives what it runs a home of its own.

A `consume` command also puts the usage hook in place where recording is on (§212, D-516), which
without a home of its own would be this machine's `~/.config/opencode` or `~/.claude`. So that is
done only in a module that asks for it with `RECORDS_USAGE = True`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_failure_journal_in_the_real_home(request: pytest.FixtureRequest) -> None:
    if getattr(request.module, "RECORDS_FAILURES", False):
        return
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        "aart_cli.commands.report.record_in_application_home", lambda *args, **kwargs: None
    )
    request.addfinalizer(patcher.undo)


@pytest.fixture(autouse=True)
def _no_usage_hook_in_the_real_home(request: pytest.FixtureRequest) -> None:
    if getattr(request.module, "RECORDS_USAGE", False):
        return
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        "aart_cli.commands.usage.record_usage_for_this_build", lambda *args, **kwargs: None
    )
    request.addfinalizer(patcher.undo)
