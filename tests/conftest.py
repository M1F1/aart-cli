"""What every test shares.

A command or the terminal application that fails journals the failure in its application home
(§215), which for a test that runs `cli.main` or `tui.run` without a home of its own would be this
machine's `~/.aart-cli`. So such a failure is journaled only in a module that asks for it with
`RECORDS_FAILURES = True`, and gives what it runs a home of its own.
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
